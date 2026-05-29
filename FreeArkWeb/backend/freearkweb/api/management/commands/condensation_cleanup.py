"""
condensation_cleanup — 结露预警事件清理 Management Command（MOD-BE-CW-04，v0.7.0-CW）

镜像 fault_cleanup.py（ADR-CW-06）。
由 freeark-condensation-cleanup.timer 每天 03:30 触发（ADR-CW-05，错开故障清理的 03:00）。
运行方式：python manage.py condensation_cleanup [--days=90] [--batch-size=1000] [--sleep-ms=100] [--dry-run]

清理策略：
  - 仅删除 first_seen_at < NOW() - {days}天 AND is_active=False 的记录
  - 活跃预警（is_active=True）永远不删
  - 分批删除，批次间 sleep {sleep_ms}ms，避免大事务
"""

import logging
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = '清理超过保留期限的已恢复结露预警事件（freeark-condensation-cleanup）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=90,
            help='保留天数（默认 90）。超过此天数且已恢复的记录将被删除。',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='每批删除的行数上限（默认 1000）。',
        )
        parser.add_argument(
            '--sleep-ms',
            type=int,
            default=100,
            help='每批删除后的 sleep 毫秒数（默认 100ms）。',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='演练模式：不执行删除，仅统计预计删除行数。',
        )

    def handle(self, *args, **options):
        days = options['days']
        batch_size = options['batch_size']
        sleep_ms = options['sleep_ms']
        dry_run = options['dry_run']

        if days <= 0:
            raise CommandError('--days 必须大于 0')
        if batch_size <= 0:
            raise CommandError('--batch-size 必须大于 0')

        cutoff = timezone.now() - timedelta(days=days)

        logger.info(
            'condensation_cleanup 启动: days=%d batch_size=%d sleep_ms=%d dry_run=%s cutoff=%s',
            days, batch_size, sleep_ms, dry_run, cutoff.isoformat(),
        )

        if dry_run:
            self._dry_run(cutoff)
            return

        self._run_cleanup(cutoff, batch_size, sleep_ms)

    def _dry_run(self, cutoff):
        """演练模式：统计预计删除行数，不执行删除。"""
        from api.models import CondensationWarningEvent
        close_old_connections()
        count = CondensationWarningEvent.objects.filter(
            first_seen_at__lt=cutoff,
            is_active=False,
        ).count()
        self.stdout.write(
            f'[DRY-RUN] 预计删除行数: {count}（cutoff={cutoff.isoformat()}）'
        )
        logger.info('condensation_cleanup dry-run: 预计删除 %d 行', count)

    def _run_cleanup(self, cutoff, batch_size: int, sleep_ms: int):
        """分批删除超期已恢复结露预警事件，循环直到 affected_rows == 0。"""
        from api.models import CondensationWarningEvent

        total_deleted = 0
        batch_num = 0

        while True:
            close_old_connections()
            try:
                # 获取当前批次要删除的 id 列表（避免全表锁）
                ids = list(
                    CondensationWarningEvent.objects.filter(
                        first_seen_at__lt=cutoff,
                        is_active=False,
                    ).values_list('id', flat=True)[:batch_size]
                )
                if not ids:
                    break

                deleted_count, _ = CondensationWarningEvent.objects.filter(id__in=ids).delete()
                total_deleted += deleted_count
                batch_num += 1

                logger.info(
                    'condensation_cleanup 第 %d 批：删除 %d 行，累计 %d 行',
                    batch_num, deleted_count, total_deleted,
                )

                if deleted_count == 0:
                    break

                # 批次间 sleep，避免大量 IO 冲击
                if sleep_ms > 0:
                    time.sleep(sleep_ms / 1000.0)

            except Exception as exc:
                logger.error(
                    'condensation_cleanup 批次 %d 异常，停止清理: %s', batch_num + 1, exc
                )
                break

        logger.info('condensation_cleanup 完成：共删除 %d 行，共 %d 批次', total_deleted, batch_num)
        self.stdout.write(f'condensation_cleanup 完成：共删除 {total_deleted} 行')
