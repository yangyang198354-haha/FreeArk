"""
management/commands/backfill_fault_message_zh.py — 故障描述中文化历史回填（BUG-FM-008）

将 fault_event 表中按旧逻辑生成的英文 fault_message 替换为
ERROR_CODE_LABELS 字典中的中文描述，使历史数据与新数据展示一致。

使用方法：
    # 预览影响行数（不修改 DB）
    python manage.py backfill_fault_message_zh --dry-run

    # 实际执行（分批写入，每批 500 行，默认）
    python manage.py backfill_fault_message_zh

    # 调整批次大小
    python manage.py backfill_fault_message_zh --batch-size=200

回填逻辑（与 get_fault_message 保持一致）：
    1. ERROR_CODE_LABELS 查表命中 → 替换为中文描述
    2. error_N 通用码（未在字典中）→ "设备故障 (错误码 N)"
    3. 其他（fresh_air_fault_bit_N 等）→ 跳过（原逻辑生成的英文格式保持不变）

注意：
    - 仅修改 fault_message 字段，不改动其他字段
    - fault_code 不变（fault_code 是原始故障码标识符，不受本次修复影响）
    - 可安全重复执行（幂等）
"""

import re
import time

from django.core.management.base import BaseCommand

from api.fault_consumer.constants import ERROR_CODE_LABELS
from api.fault_consumer.fault_classifier import get_fault_message

# error_N 模式，用于识别需要回填兜底描述的通用故障码
_ERROR_N_PATTERN = re.compile(r'^error_(\d+)$')


def _compute_new_message(fault_code: str):
    """根据 fault_code 计算新的中文 fault_message。

    Returns:
        str  → 新描述（需要更新）
        None → 跳过（不需要更新，或无法改善）
    """
    # 1. 字典命中 → 有中文描述，计算新值
    if fault_code in ERROR_CODE_LABELS:
        return get_fault_message(fault_code)
    # 2. error_N 通用码 → 兜底中文描述
    if _ERROR_N_PATTERN.match(fault_code):
        return get_fault_message(fault_code)
    # 3. 其他命名码（fresh_air_fault_bit_N、命名型旧数据等）→ 跳过
    return None


class Command(BaseCommand):
    help = '将 fault_event 表的 fault_message 字段回填为中文描述（BUG-FM-008）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='仅统计影响行数，不修改数据库',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='每批处理行数（默认 500）',
        )

    def handle(self, *args, **options):
        from api.models import FaultEvent  # 延迟导入，避免模块初始化顺序问题

        dry_run: bool = options['dry_run']
        batch_size: int = options['batch_size']

        if dry_run:
            self.stdout.write('=== DRY-RUN 模式，不修改数据库 ===')

        # 统计需要回填的总行数
        # 扫描所有 fault_code：在字典中或是 error_N 格式的记录都需要回填
        total_affected = 0
        total_updated = 0
        offset = 0

        while True:
            batch = list(
                FaultEvent.objects.order_by('id')
                .values('id', 'fault_code', 'fault_message')[offset:offset + batch_size]
            )
            if not batch:
                break

            to_update = []
            for row in batch:
                new_msg = _compute_new_message(row['fault_code'])
                if new_msg is None:
                    continue
                if new_msg == row['fault_message']:
                    # 已经是正确值（幂等保护）
                    continue
                total_affected += 1
                to_update.append({'id': row['id'], 'fault_message': new_msg})

            if not dry_run and to_update:
                # 批量更新（每行单独 UPDATE，避免复杂 CASE WHEN 构造）
                for item in to_update:
                    FaultEvent.objects.filter(pk=item['id']).update(
                        fault_message=item['fault_message']
                    )
                total_updated += len(to_update)
                self.stdout.write(
                    f'  已更新 {total_updated} 行（本批 {len(to_update)} 行）'
                )

            offset += batch_size

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'[DRY-RUN] 预计回填行数：{total_affected} 行（fault_message 将更新为中文描述）'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'回填完成，共更新 {total_updated} 行 fault_message 为中文描述。'
                )
            )
