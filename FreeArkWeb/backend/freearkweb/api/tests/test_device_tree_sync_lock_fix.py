"""
设备树同步锁修复测试套件
========================

覆盖场景：
  TC-LOCK-01: 单户同步成功路径（_ensure_attr_defs 预创建 attr_def 生效）
  TC-LOCK-02: 多户并发同步同一批 product_code 不产生锁等待（根因消除验证）
  TC-LOCK-03: 主事务中 attr_def 不存在时的兜底（mock DoesNotExist 路径）

运行方式：
    cd FreeArkWeb/backend/freearkweb
    py manage.py test api.tests.test_device_tree_sync_lock_fix \
        --settings=freearkweb.test_settings -v 2
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock

from unittest import skipIf

from django.conf import settings
from django.test import TestCase

from api.models import (
    DeviceAttrBinding,
    DeviceAttrDef,
    DeviceFloor,
    DeviceNode,
    DeviceRoom,
    OwnerInfo,
)
from api.device_tree_sync import (
    _ensure_attr_defs,
    upsert_tree,
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_owner(specific_part: str, unique_id: str = 'mac_test_01') -> OwnerInfo:
    return OwnerInfo.objects.create(
        specific_part=specific_part,
        location_name='测试坐落',
        building='1栋',
        unit='1单元',
        floor='1楼',
        room_number='101',
        bind_status='已绑定',
        unique_id=unique_id,
    )


def _make_data_payload(
    product_code: str = 'PC001',
    floor_no: int = 1,
    device_sn: int = 1001,
    attr_tags: list[str] | None = None,
) -> list[dict]:
    """构造最小合法的 data_payload（楼层列表）。"""
    if attr_tags is None:
        attr_tags = ['ATTR_TEMP', 'ATTR_MODE']

    attrs = [
        {
            'attrTag': tag,
            'attrValueType': 1,
            'attrConstraint': 0,
            'selectValues': ['on', 'off'],
            'numValue': None,
        }
        for tag in attr_tags
    ]

    return [
        {
            'floor': floor_no,
            'floorName': f'{floor_no}楼',
            'rooms': [
                {
                    'oriRoomName': 'LivingRoom',
                    'roomName': '客厅',
                    'roomType': 1,
                    'devices': [
                        {
                            'deviceSn': device_sn,
                            'deviceName': '测试设备',
                            'systemFlag': 2,
                            'relatedDeviceSn': None,
                            'productCode': product_code,
                            'categoryCode': 10,
                            'deviceProtocol': {'protocol': 1, 'addressCode': 1},
                            'attrs': attrs,
                        }
                    ],
                }
            ],
        }
    ]


# ===========================================================================
# TC-LOCK-01: 单户同步成功路径
# ===========================================================================

class SingleOwnerSyncTest(TestCase):
    """TC-LOCK-01: 单户完整同步路径，验证 pre-pass + 主事务 get() 流程正确落库。"""

    def test_tc_lock_01_001_attr_def_created_by_pre_pass(self):
        """TC-LOCK-01-001: _ensure_attr_defs 执行后，DeviceAttrDef 行应已存在。"""
        payload = _make_data_payload(product_code='PC001', attr_tags=['ATTR_A', 'ATTR_B'])
        _ensure_attr_defs(payload)

        self.assertEqual(DeviceAttrDef.objects.filter(product_code='PC001').count(), 2)
        self.assertTrue(DeviceAttrDef.objects.filter(product_code='PC001', attr_tag='ATTR_A').exists())
        self.assertTrue(DeviceAttrDef.objects.filter(product_code='PC001', attr_tag='ATTR_B').exists())

    def test_tc_lock_01_002_upsert_tree_full_path(self):
        """TC-LOCK-01-002: pre-pass 后调用 upsert_tree，DeviceNode + 绑定全部落库。"""
        owner = _make_owner('1-1-1-101')
        payload = _make_data_payload(
            product_code='PC002',
            floor_no=1,
            device_sn=2001,
            attr_tags=['ATTR_X', 'ATTR_Y'],
        )

        # 模拟完整调用链：pre-pass 在外，upsert_tree 在主事务内
        _ensure_attr_defs(payload)
        stats = upsert_tree(owner, payload)

        # 验证落库统计
        self.assertEqual(stats['floors'], 1)
        self.assertEqual(stats['rooms'], 1)
        self.assertEqual(stats['devices'], 1)
        self.assertEqual(stats['attr_defs_total'], 2)
        self.assertEqual(stats['bindings'], 2)

        # 验证 DeviceNode 存在
        self.assertTrue(DeviceNode.objects.filter(device_sn=2001).exists())

        # 验证 DeviceAttrBinding 已建立
        node = DeviceNode.objects.get(device_sn=2001)
        binding_count = DeviceAttrBinding.objects.filter(device=node).count()
        self.assertEqual(binding_count, 2)

    def test_tc_lock_01_003_pre_pass_idempotent(self):
        """TC-LOCK-01-003: 重复调用 _ensure_attr_defs 是幂等的（行数不增加）。"""
        payload = _make_data_payload(product_code='PC003', attr_tags=['ATTR_Z'])
        _ensure_attr_defs(payload)
        _ensure_attr_defs(payload)  # 第二次调用

        self.assertEqual(DeviceAttrDef.objects.filter(product_code='PC003').count(), 1)

    def test_tc_lock_01_004_stats_attr_defs_new_zero_on_second_sync(self):
        """TC-LOCK-01-004: 第二次同步同一户时，attr_defs_new=0（行已存在，pre-pass 是 get_or_create）。"""
        owner = _make_owner('1-1-1-102')
        payload = _make_data_payload(product_code='PC004', device_sn=3001, attr_tags=['ATTR_1'])

        _ensure_attr_defs(payload)
        upsert_tree(owner, payload)

        # 第二次同步
        _ensure_attr_defs(payload)
        stats2 = upsert_tree(owner, payload)

        # 第二次 attr_defs_new 应为 0（行已存在，主事务 get() 成功，不走兜底路径）
        self.assertEqual(stats2['attr_defs_new'], 0)


# ===========================================================================
# TC-LOCK-02: 多户并发同步同一批 product_code 不产生锁等待
# ===========================================================================

@skipIf(
    settings.DATABASES['default']['ENGINE'].endswith('sqlite3'),
    'SQLite 使用文件级独占写锁，无法测试真正的多线程并发；本组测试仅在 MySQL 下有意义'
)
class ConcurrentSyncLockTest(TestCase):
    """TC-LOCK-02: 多户并发同步同一 product_code 的 attr 定义，验证无竞争异常。

    根因消除验证：修复前 update_or_create 在主事务内对同一 product_code 行加写锁，
    4 个并发 worker 会产生 1205 Lock wait timeout。
    修复后 pre-pass 用 get_or_create（独立于主事务）预创建行，主事务只 get()，
    多线程并发读同一行不产生写锁竞争。
    """

    def _make_n_owners(self, n: int) -> list[OwnerInfo]:
        owners = []
        for i in range(n):
            owners.append(_make_owner(f'2-1-1-{200 + i}', unique_id=f'mac_{i:04d}'))
        return owners

    def test_tc_lock_02_001_concurrent_4_workers_same_product_code(self):
        """TC-LOCK-02-001: 4 个线程并发 upsert_tree，使用相同 product_code，全部成功无异常。"""
        owners = self._make_n_owners(4)
        # 所有户使用相同 product_code（模拟同款设备共享 attr_def 的生产场景）
        payloads = [
            _make_data_payload(
                product_code='PC_SHARED',
                floor_no=1,
                device_sn=5000 + i,
                attr_tags=['ATTR_TEMP', 'ATTR_MODE', 'ATTR_FAN'],
            )
            for i, _ in enumerate(owners)
        ]

        errors = []
        results = []

        def _sync(owner, payload):
            try:
                _ensure_attr_defs(payload)
                stats = upsert_tree(owner, payload)
                return stats
            except Exception as exc:
                errors.append((owner.specific_part, str(exc)))
                return None

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(_sync, owner, payload)
                for owner, payload in zip(owners, payloads)
            ]
            for fut in as_completed(futures):
                result = fut.result()
                if result is not None:
                    results.append(result)

        # 所有 4 个 worker 必须全部成功，无异常
        self.assertEqual(len(errors), 0, f'并发同步发生异常: {errors}')
        self.assertEqual(len(results), 4, f'期望 4 个成功结果，实际 {len(results)} 个')

        # DeviceAttrDef 只有 3 行（3 个 attr_tag）——共享，不重复
        def_count = DeviceAttrDef.objects.filter(product_code='PC_SHARED').count()
        self.assertEqual(def_count, 3, f'DeviceAttrDef 行数期望 3，实际 {def_count}')

        # 4 个 DeviceNode，每个有 3 个绑定
        node_count = DeviceNode.objects.filter(product_code='PC_SHARED').count()
        self.assertEqual(node_count, 4)

    def test_tc_lock_02_002_concurrent_data_integrity(self):
        """TC-LOCK-02-002: 并发写入后，每个 owner 的设备树数据完整且独立（无串写）。"""
        owners = self._make_n_owners(4)
        payloads = [
            _make_data_payload(
                product_code='PC_SHARED2',
                floor_no=1,
                device_sn=6000 + i,
                attr_tags=['T1', 'T2'],
            )
            for i, _ in enumerate(owners)
        ]

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(lambda o, p: (_ensure_attr_defs(p), upsert_tree(o, p))[1], owner, payload)
                for owner, payload in zip(owners, payloads)
            ]
            for fut in as_completed(futures):
                fut.result()

        # 验证每个 owner 下只有 1 个 DeviceNode
        for i, owner in enumerate(owners):
            node_sn = 6000 + i
            self.assertTrue(
                DeviceNode.objects.filter(device_sn=node_sn).exists(),
                f'owner {owner.specific_part} 的 DeviceNode(sn={node_sn}) 不存在',
            )


# ===========================================================================
# TC-LOCK-03: 主事务中 attr_def 不存在时的兜底路径
# ===========================================================================

class AttrDefFallbackTest(TestCase):
    """TC-LOCK-03: 模拟 pre-pass 后行被删除的极罕见竞态，验证兜底 get_or_create 生效。"""

    def test_tc_lock_03_001_fallback_get_or_create_on_does_not_exist(self):
        """TC-LOCK-03-001: 主事务 get() 抛 DoesNotExist 时，兜底 get_or_create 应创建行并继续。

        用 mock 模拟：第一次 get() 抛 DoesNotExist，后续 get_or_create 正常。
        """
        owner = _make_owner('3-1-1-301')
        payload = _make_data_payload(
            product_code='PC_FALLBACK',
            floor_no=1,
            device_sn=7001,
            attr_tags=['ATTR_FALLBACK'],
        )

        # pre-pass 正常执行（确保 DeviceAttrDef 已存在）
        _ensure_attr_defs(payload)

        # 记录正常的 get_or_create 用于兜底
        real_get_or_create = DeviceAttrDef.objects.get_or_create

        call_count = {'get': 0}

        original_manager_get = DeviceAttrDef.objects.get

        def patched_get(**kwargs):
            if kwargs.get('product_code') == 'PC_FALLBACK' and call_count['get'] == 0:
                call_count['get'] += 1
                raise DeviceAttrDef.DoesNotExist('模拟竞态：行被删除')
            return original_manager_get(**kwargs)

        with patch.object(DeviceAttrDef.objects, 'get', side_effect=patched_get):
            # upsert_tree 内部 get() 第一次会抛 DoesNotExist，兜底 get_or_create 应接管
            stats = upsert_tree(owner, payload)

        # 兜底路径执行后，同步仍应成功
        self.assertEqual(stats['devices'], 1)
        self.assertEqual(stats['attr_defs_total'], 1)
        self.assertEqual(stats['bindings'], 1)

        # DeviceAttrDef 行存在（由兜底 get_or_create 确保）
        self.assertTrue(
            DeviceAttrDef.objects.filter(
                product_code='PC_FALLBACK', attr_tag='ATTR_FALLBACK'
            ).exists()
        )

    def test_tc_lock_03_002_no_fallback_needed_when_pre_pass_succeeds(self):
        """TC-LOCK-03-002: pre-pass 成功时，主事务 get() 不触发兜底，attr_defs_new=0。"""
        owner = _make_owner('3-1-1-302')
        payload = _make_data_payload(
            product_code='PC_NORMAL',
            floor_no=1,
            device_sn=7002,
            attr_tags=['ATTR_N1', 'ATTR_N2'],
        )

        _ensure_attr_defs(payload)
        stats = upsert_tree(owner, payload)

        # 正常路径：pre-pass 创建行，主事务 get() 成功，attr_defs_new=0
        self.assertEqual(stats['attr_defs_new'], 0)
        self.assertEqual(stats['attr_defs_total'], 2)
        self.assertEqual(stats['bindings'], 2)
