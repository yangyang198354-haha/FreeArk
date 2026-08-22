"""
plc_write_timeout_service — 将长期卡在 pending 状态的 PLCWriteRecord 标记为 timeout。

断链场景（已知历史 RCA，见 datacollection/mqtt_client.py 的 broker 闪断后静默失聪注释）：
  - 2026-06 左右 broker 短暂闪断后，PLCWriteSubscriber 或 Django MQTTConsumer
    的 paho MQTT session 被 broker 清掉、订阅关系丢失，但 paho client 还是 ESTABLISHED、
    on_connect rc=0，导致「看起来在线其实收不到消息」的静默失聪状态。
  - 之后下发的写请求会在 PLCWriteRecord 中永远停留在 pending，
    用户侧 UI 也永远显示 pending，难以区分「还在路上」vs「丢了」。

本命令按「specific_part + 创单时间」小步批量标记 pending 行为 timeout，
更新 error_message 字段写入「可能原因分类 + 超时时长 + 创单时间」，
便于 UI 对 timeout 行做区分展示，也为运维侧 RCA 留下线索。

用法示例：
  # 安全预演：只显示会标为 timeout 的数量（不真 UPDATE）
  python manage.py plc_write_timeout_service --once --ttl-seconds 90 --dry-run

  # 立即执行一次，90 秒未回执算超时，批次 500 行
  python manage.py plc_write_timeout_service --once --ttl-seconds 90 --batch-size 500

  # 常驻进程：用 schedule 每 60 秒跑一轮（推荐生产模式）
  python manage.py plc_write_timeout_service --interval-seconds 60 --ttl-seconds 90
"""

import os
import sys
import time
from datetime import timedelta
from typing import Optional

import schedule
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from .common import (
    get_service_logger,
    log_error,
    log_service_start,
    log_service_stop,
    log_task_completion,
    log_task_start,
    log_warning,
)

logger = get_service_logger('plc_write_timeout_service')


def _one_round(*, ttl_seconds: int, batch_size: int, dry_run: bool = False) -> dict:
    """执行一轮：把 pending 且 created_at < NOW()-ttl_seconds 的行标 timeout。

    返回统计 dict（rows_marked, skipped, reason_stats）。dry_run 模式下 rows_marked=0
    但会返回会被标记的数量作为 rows_touched。
    """
    ttl_delta = timedelta(seconds=ttl_seconds)
    cutoff = timezone.now() - ttl_delta
    stats = {
        'rows_candidates': 0,  # 截止时间前的 pending 总数
        'rows_marked': 0,      # 本批实际 UPDATE 的行数
        'rows_skipped': 0,     # 过程中状态已变（非 pending）的乐观跳过数
        'batches': 0,
    }

    with connection.cursor() as c:
        # 先 COUNT 一下：走 status+created_at 联合索引（plcwr_status_cat_idx）
        c.execute(
            """
            SELECT COUNT(*) FROM plc_write_record
             WHERE status = %s AND created_at < %s
            """,
            ['pending', cutoff],
        )
        (stats['rows_candidates'],) = c.fetchone()

    if dry_run:
        logger.info(
            '[mark_write_timeout DRY-RUN] ttl=%ss cutoff=%s candidates=%s',
            ttl_seconds, cutoff.isoformat(timespec='seconds'), stats['rows_candidates'],
        )
        return stats

    # 分批 UPDATE：LIMIT 避免长事务；WHERE 保留 status=pending 防止并发 ack 时覆盖。
    # 一次单轮最多处理 20 批（20*batch_size 行），防止突然大量历史行卡死 DB。
    max_batches = 20
    updated_any = True
    while updated_any and stats['batches'] < max_batches:
        with connection.cursor() as c:
            c.execute(
                """
                UPDATE plc_write_record
                   SET status = %s,
                       error_message = CONCAT_WS(' | ',
                            COALESCE(NULLIF(error_message, ''), ''),
                            %s)
                 WHERE id IN (
                     SELECT id FROM (
                         SELECT id FROM plc_write_record
                          WHERE status = %s AND created_at < %s
                          ORDER BY created_at ASC
                          LIMIT %s
                     ) AS _t
                 ) AND status = %s
                """,
                [
                    'timeout',
                    (
                        f'marked_timeout: age>{ttl_seconds}s '
                        f'probable_reason: broker_session_lost_or_subscriber_silently_deaf '
                        f'(broker 闪断后订阅丢失导致 ack 未入库；'
                        f'详见 mqtt_client.py 2026-06 RCA 注释)'
                    ),
                    'pending',
                    cutoff,
                    batch_size,
                    'pending',
                ],
            )
            n = c.rowcount if hasattr(c, 'rowcount') else 0
        stats['batches'] += 1
        stats['rows_marked'] += max(0, int(n or 0))
        updated_any = (n and int(n) > 0)
        if updated_any:
            # 小批量之间给 DB 喘息 20ms
            time.sleep(0.02)

    if stats['rows_candidates'] > stats['rows_marked']:
        # 剩余的要么 max_batches 限制了，要么并发 ack 变 status 了（极少见）
        stats['rows_skipped'] = max(0, stats['rows_candidates'] - stats['rows_marked'])

    logger.info(
        '[mark_write_timeout] ttl=%ss candidates=%s marked=%s batches=%s skipped=%s dry_run=%s',
        ttl_seconds, stats['rows_candidates'], stats['rows_marked'],
        stats['batches'], stats['rows_skipped'], dry_run,
    )
    return stats


class Command(BaseCommand):
    help = '将长期 pending 的 PLCWriteRecord 标为 timeout，防止永远卡 pending'

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            default=False,
            help='只执行一轮就退出（不进入 schedule 常驻循环）',
        )
        parser.add_argument(
            '--interval-seconds',
            type=int,
            default=60,
            help='常驻模式下每多少秒跑一轮（默认 60s）；--once 时该参数无效',
        )
        parser.add_argument(
            '--ttl-seconds',
            type=int,
            default=90,
            help='pending 超过多少秒才标 timeout（默认 90s；'
                 '写操作默认 SLA ack≤30s，留 3x 余量避免误判网络抖动）',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='每批 UPDATE 的最大行数（默认 500）',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='只 COUNT 不 UPDATE（安全预演），仅在 --once 下有意义',
        )

    def handle(self, *args, **options):
        once: bool = options['once']
        interval: int = max(1, int(options['interval_seconds']))
        ttl: int = max(10, int(options['ttl_seconds']))
        batch_size: int = max(1, int(options['batch_size']))
        dry_run: bool = bool(options['dry_run'])

        log_service_start(
            logger,
            'PLC 写超时标记服务',
            {
                'mode': 'once' if once else f'interval {interval}s',
                'ttl_seconds': ttl,
                'batch_size': batch_size,
                'dry_run': dry_run,
            },
        )

        try:
            if once:
                log_task_start(logger, 'mark_write_timeout once')
                stats = _one_round(
                    ttl_seconds=ttl, batch_size=batch_size, dry_run=dry_run,
                )
                log_task_completion(logger, 'mark_write_timeout once')
                msg = (
                    f'✅ 执行完成：候选 {stats["rows_candidates"]} 行，'
                    f'实际标记 {stats["rows_marked"]} 行'
                    + (f'（dry-run，未真写 DB）' if dry_run else '')
                )
                self.stdout.write(self.style.SUCCESS(msg))
                return 0

            # 常驻 schedule 模式
            def _job():
                try:
                    log_task_start(logger, 'mark_write_timeout round')
                    _one_round(ttl_seconds=ttl, batch_size=batch_size, dry_run=False)
                    log_task_completion(logger, 'mark_write_timeout round')
                except Exception as exc:
                    log_error(logger, 'mark_write_timeout round 异常', exc)
                    import traceback
                    logger.error(traceback.format_exc())

            schedule.every(interval).seconds.do(_job)
            logger.info('🔁 常驻模式：每 %ss 跑一轮，Ctrl+C 退出', interval)
            self.stdout.write(
                self.style.WARNING(f'🔁 常驻模式启动，每 {interval}s 一轮；Ctrl+C 退出')
            )
            # 启动时立刻先跑一轮（清理历史积压）
            _job()
            while True:
                try:
                    schedule.run_pending()
                    time.sleep(1)
                except KeyboardInterrupt:
                    logger.info('🛑 收到 Ctrl+C，退出 schedule 循环')
                    break
            return 0
        except Exception as exc:
            log_error(logger, 'plc_write_timeout_service 异常', exc)
            import traceback
            logger.error(traceback.format_exc())
            self.stdout.write(self.style.ERROR(f'❌ 运行异常：{exc!r}'))
            return 1
        finally:
            log_service_stop(logger, 'PLC 写超时标记服务')
