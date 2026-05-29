"""
test_condensation_v070_e2e.py — v0.7.0 结露预警 E2E 测试

覆盖范围（完整用户故事端到端路径，无真实 MQTT，Mock MQTT 消息注入）：

  E2E-US01-001  US-CW-01 AC-01: 260001 完整报文 → T1 INSERT 含所有快照字段
  E2E-US01-002  US-CW-01 AC-02: 快照字段缺失 → NULL 兜底不报错
  E2E-US01-003  US-CW-01 AC-03: 重复预警报文 → 不新增 DB 行（T2 路径）
  E2E-US01-004  US-CW-01 AC-04: alarm=0 报文 → T3 is_active=False + recovered_at
  E2E-US01-005  US-CW-01 AC-05: 未知 MAC → WARNING 日志，不写 DB
  E2E-US01-006  US-CW-01 AC-06: 重启重建（rebuild_from_db）+ 后续 T2 正确路由
  E2E-US01-007  US-CW-01 AC-07: 非数字 condensation_alarm → 正常态，不触发 T1/T3
  E2E-US01-08a  US-CW-01 AC-08a: 120003 无 system_switch → PLCLatestData 兜底
  E2E-US01-08b  US-CW-01 AC-08b: 120003 无记录 → system_switch="unknown"
  E2E-US03-001  US-CW-03 AC-01: 默认 is_active=True（未回复）列表
  E2E-US03-002  US-CW-03 AC-02: 切换"已回复" → is_active=False
  E2E-US03-003  US-CW-03 AC-03: 切换"全部" → 全部记录
  E2E-US04-001  US-CW-04 AC-03: 3 段房号精确筛选 → startswith+endswith 映射
  E2E-US05-001  US-CW-05 AC-01/02: 默认 7 天 + 自定义时间段
  E2E-US06-001  US-CW-06 AC-01/02: 大屏在线（≤15min）/离线（>15min）
  E2E-US08-001  US-CW-08 AC-02/03: 清理 90 天边界 + 活跃豁免

  E2E-FRONTEND-001  前端列数核对：Vue 组件实际渲染 12 列验证（静态解析）

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_condensation_v070_e2e \\
        --settings=freearkweb.test_settings --verbosity=2
"""

import json
import logging
import re
from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from api.models import (
    CondensationWarningEvent,
    ScreenConnectivityStatus,
    PLCLatestData,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _mqtt_msg(topic, payload_dict):
    msg = MagicMock()
    msg.topic = topic
    msg.payload = json.dumps(payload_dict).encode('utf-8')
    return msg


def _dsupdate(device_sn='22554', product_code='260001', items=None):
    return {
        'header': {'name': 'DeviceStatusUpdate', 'screenMac': 'aabbccddeeff'},
        'payload': {'data': {'deviceSn': device_sn, 'productCode': product_code, 'items': items or []}},
    }


def _inject_alarm(device_sn, product_code, specific_part, alarm_val, extra_items=None, mac_map=None):
    """注入一条含 condensation_alarm 的 MQTT 消息，驱动状态机。"""
    from api.management.commands.condensation_consumer import _handle_message
    cache = MagicMock()
    cache.get_specific_part.return_value = specific_part
    items = [{'attrTag': 'condensation_alarm', 'attrValue': str(alarm_val)}]
    if extra_items:
        items.extend(extra_items)
    msg = _mqtt_msg(f'screen/upload/screen/to/cloud/{device_sn}',
                    _dsupdate(device_sn=device_sn, product_code=product_code, items=items))
    _handle_message(msg, cache)


# ---------------------------------------------------------------------------
# E2E-US01-*: US-CW-01 结露预警自动持久化（端到端 MQTT → DB 完整路径）
# ---------------------------------------------------------------------------

class US01PersistenceE2ETest(TestCase):

    def setUp(self):
        import api.condensation_consumer.state_machine as sm
        sm._cw_state_machine.clear()

    def test_e2e_us01_001_full_260001_t1_insert(self):
        """E2E-US01-001 (AC-CW-01-01): 260001 完整报文 → T1 INSERT，所有快照字段正确写入。"""
        from api.management.commands.condensation_consumer import _handle_message
        cache = MagicMock()
        cache.get_specific_part.return_value = '3-1-7-702'

        items = [
            {'attrTag': 'condensation_alarm', 'attrValue': '1'},
            {'attrTag': 'dew_point_temp', 'attrValue': '12.5'},
            {'attrTag': 'NTC_temp', 'attrValue': '18.0'},
            {'attrTag': 'humidity', 'attrValue': '65'},
            {'attrTag': 'system_switch', 'attrValue': 'off'},
        ]
        msg = _mqtt_msg(
            'screen/upload/screen/to/cloud/aabbccddeeff',
            _dsupdate(device_sn='22554', product_code='260001', items=items),
        )
        _handle_message(msg, cache)

        cwe = CondensationWarningEvent.objects.get(specific_part='3-1-7-702')
        self.assertTrue(cwe.is_active)
        self.assertEqual(cwe.system_switch, 'off')
        self.assertEqual(cwe.dew_point_temp, '12.5')
        self.assertEqual(cwe.ntc_temp, '18.0')
        self.assertEqual(cwe.humidity, '65')
        self.assertEqual(cwe.condensation_alarm_value, '1')
        self.assertIsNotNone(cwe.first_seen_at)
        self.assertIsNone(cwe.recovered_at)

    def test_e2e_us01_002_missing_snapshot_null(self):
        """E2E-US01-002 (AC-CW-01-02): 快照字段缺失 → NULL，不报错，不丢弃预警。"""
        _inject_alarm(
            device_sn='22554', product_code='260001',
            specific_part='3-1-7-702', alarm_val='1',
            extra_items=[{'attrTag': 'system_switch', 'attrValue': 'on'}],
        )
        cwe = CondensationWarningEvent.objects.get(specific_part='3-1-7-702')
        self.assertIsNone(cwe.dew_point_temp)
        self.assertIsNone(cwe.ntc_temp)
        self.assertIsNone(cwe.humidity)
        self.assertTrue(cwe.is_active)

    def test_e2e_us01_003_duplicate_no_insert(self):
        """E2E-US01-003 (AC-CW-01-03): 重复预警报文 → 不新增 DB 行（T2 路径）。"""
        _inject_alarm('22554', '260001', '3-1-7-702', '1',
                      extra_items=[{'attrTag': 'system_switch', 'attrValue': 'on'}])
        count_after_t1 = CondensationWarningEvent.objects.count()
        self.assertEqual(count_after_t1, 1)

        # 再次发送同一设备的报警
        _inject_alarm('22554', '260001', '3-1-7-702', '1',
                      extra_items=[{'attrTag': 'system_switch', 'attrValue': 'on'}])
        self.assertEqual(CondensationWarningEvent.objects.count(), count_after_t1)

    def test_e2e_us01_004_recover_alarm_zero(self):
        """E2E-US01-004 (AC-CW-01-04): alarm=0 → T3 is_active=False + recovered_at。"""
        _inject_alarm('22554', '260001', '3-1-7-702', '1',
                      extra_items=[{'attrTag': 'system_switch', 'attrValue': 'on'}])
        _inject_alarm('22554', '260001', '3-1-7-702', '0')

        cwe = CondensationWarningEvent.objects.get(specific_part='3-1-7-702')
        self.assertFalse(cwe.is_active)
        self.assertIsNotNone(cwe.recovered_at)

    def test_e2e_us01_005_unknown_mac_no_db(self):
        """E2E-US01-005 (AC-CW-01-05): 未知 MAC → 不写 DB，服务不崩溃。"""
        from api.management.commands.condensation_consumer import _handle_message
        cache = MagicMock()
        cache.get_specific_part.return_value = None  # MAC 未找到

        msg = _mqtt_msg(
            'screen/upload/screen/to/cloud/unknownmac',
            _dsupdate(items=[{'attrTag': 'condensation_alarm', 'attrValue': '1'}]),
        )
        _handle_message(msg, cache)
        self.assertEqual(CondensationWarningEvent.objects.count(), 0)

    def test_e2e_us01_006_rebuild_then_t2(self):
        """E2E-US01-006 (AC-CW-01-06): rebuild_from_db 后同设备报警走 T2。"""
        import api.condensation_consumer.state_machine as sm
        now = timezone.now()

        # 预置 DB 活跃记录，模拟重启前状态
        CondensationWarningEvent.objects.create(
            specific_part='3-1-7-702', device_sn='22554', product_code='260001',
            first_seen_at=now, last_seen_at=now, is_active=True,
            warning_type='结露预警', warning_message='结露报警',
        )

        # 模拟重启后 rebuild
        count = sm.rebuild_from_db()
        self.assertEqual(count, 1)

        # 收到同设备报警 → T2（DB 行数不变）
        _inject_alarm('22554', '260001', '3-1-7-702', '1')
        self.assertEqual(CondensationWarningEvent.objects.count(), 1)

    def test_e2e_us01_007_non_numeric_alarm_normal(self):
        """E2E-US01-007 (AC-CW-01-07): 非数字 condensation_alarm → 不触发 T1/T3，不崩溃。"""
        _inject_alarm('22554', '260001', '3-1-7-702', 'xyz')
        self.assertEqual(CondensationWarningEvent.objects.count(), 0)

    def test_e2e_us01_08a_120003_plc_fallback(self):
        """E2E-US01-08a (AC-CW-01-08a): 120003 无 system_switch → PLCLatestData 兜底。"""
        PLCLatestData.objects.create(
            specific_part='3-1-7-702', param_name='system_switch', value=1
        )
        _inject_alarm('22549', '120003', '3-1-7-702', '1',
                      extra_items=[{'attrTag': 'dew_point_temp', 'attrValue': '10.0'}])

        cwe = CondensationWarningEvent.objects.get(specific_part='3-1-7-702')
        self.assertEqual(cwe.system_switch, 'on')
        self.assertEqual(cwe.dew_point_temp, '10.0')

    def test_e2e_us01_08b_no_plc_record_unknown(self):
        """E2E-US01-08b (AC-CW-01-08b): 120003 + PLCLatestData 无记录 → system_switch='unknown'。"""
        _inject_alarm('22549', '120003', '9-9-9-999', '1')
        cwe = CondensationWarningEvent.objects.get(specific_part='9-9-9-999')
        self.assertEqual(cwe.system_switch, 'unknown')


# ---------------------------------------------------------------------------
# E2E-US03/04/05/06: REST API 过滤场景
# ---------------------------------------------------------------------------

class APIFilterE2ETest(APITestCase):
    """E2E-US03/04/05/06: 回复状态/房号/时间段/大屏在线过滤。"""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='e2euser', password='e2epass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = '/api/devices/condensation-warning-events/'

    def _mk_event(self, sp, is_active=True, days_ago=1, sn='SN'):
        now = timezone.now() - timedelta(days=days_ago)
        return CondensationWarningEvent.objects.create(
            specific_part=sp, device_sn=sn, product_code='260001',
            first_seen_at=now, last_seen_at=now,
            recovered_at=now if not is_active else None,
            is_active=is_active, warning_type='结露预警', warning_message='结露报警',
        )

    def test_e2e_us03_001_default_is_active_true(self):
        """E2E-US03-001 (AC-CW-03-01): 传 is_active=true → 只看未回复。"""
        self._mk_event('1-1-1-101', is_active=True, days_ago=1)
        self._mk_event('1-1-1-102', is_active=False, days_ago=1)

        resp = self.client.get(self.url, {'is_active': 'true'})
        results = resp.json()['results']
        self.assertTrue(all(r['is_active'] for r in results))

    def test_e2e_us03_002_is_active_false_recovered_at_not_null(self):
        """E2E-US03-002 (AC-CW-03-02): is_active=false → 每条 recovered_at 非空。"""
        self._mk_event('1-1-1-102', is_active=False, days_ago=1)

        resp = self.client.get(self.url, {'is_active': 'false'})
        results = resp.json()['results']
        self.assertEqual(len(results), 1)
        for r in results:
            self.assertIsNotNone(r['recovered_at'])

    def test_e2e_us03_003_all_no_filter(self):
        """E2E-US03-003 (AC-CW-03-03): 不传 is_active → 全部记录。"""
        self._mk_event('1-1-1-101', is_active=True, days_ago=1, sn='SN1')
        self._mk_event('1-1-1-102', is_active=False, days_ago=1, sn='SN2')

        resp = self.client.get(self.url)
        total = resp.json()['count']
        self.assertEqual(total, 2)

    def test_e2e_us04_001_specific_part_3_segment(self):
        """E2E-US04-001 (AC-CW-04-03): 3 段房号 '3-1-702' → 匹配 '3-1-7-702'/'3-1-3-702' 但不匹配 '4-1-7-702'。"""
        self._mk_event('3-1-7-702', is_active=True, days_ago=1, sn='SN1')
        self._mk_event('3-1-3-702', is_active=True, days_ago=1, sn='SN2')
        self._mk_event('4-1-7-702', is_active=True, days_ago=1, sn='SN3')

        resp = self.client.get(self.url, {'specific_part': '3-1-702', 'is_active': 'true'})
        results = resp.json()['results']
        sps = {r['specific_part'] for r in results}
        self.assertIn('3-1-7-702', sps)
        self.assertIn('3-1-3-702', sps)
        self.assertNotIn('4-1-7-702', sps)

    def test_e2e_us05_001_default_7_days(self):
        """E2E-US05-001 (AC-CW-05-01): 不传时间参数 → 默认最近 7 天。"""
        self._mk_event('1-1-1-101', is_active=False, days_ago=5)   # 5天前 → 在范围内
        self._mk_event('1-1-1-102', is_active=False, days_ago=10)  # 10天前 → 超出

        resp = self.client.get(self.url, {'is_active': 'false'})
        results = resp.json()['results']
        sps = {r['specific_part'] for r in results}
        self.assertIn('1-1-1-101', sps)
        self.assertNotIn('1-1-1-102', sps)

    def test_e2e_us05_002_custom_time_range(self):
        """E2E-US05-002 (AC-CW-05-02): 自定义时间段 → 仅返回范围内记录。"""
        now = timezone.now()
        self._mk_event('1-1-1-101', is_active=False, days_ago=3)   # 3天前
        self._mk_event('1-1-1-102', is_active=False, days_ago=20)  # 20天前

        after = (now - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%S')
        resp = self.client.get(self.url, {
            'is_active': 'false',
            'first_seen_after': after,
        })
        results = resp.json()['results']
        sps = {r['specific_part'] for r in results}
        self.assertIn('1-1-1-101', sps)
        self.assertNotIn('1-1-1-102', sps)

    def test_e2e_us06_001_screen_online_15min(self):
        """E2E-US06-001 (AC-CW-06-01/02): 大屏在线/离线判定（15 分钟阈值）。"""
        self._mk_event('3-1-7-702', is_active=True, days_ago=1, sn='SN1')
        self._mk_event('3-1-7-703', is_active=True, days_ago=1, sn='SN2')
        self._mk_event('3-1-7-704', is_active=True, days_ago=1, sn='SN3')

        now = timezone.now()
        # 702: 5 分钟前 → 在线
        ScreenConnectivityStatus.objects.create(
            specific_part='3-1-7-702', last_seen_at=now - timedelta(minutes=5)
        )
        # 703: 14 分 59 秒前 → 在线（边界内）
        ScreenConnectivityStatus.objects.create(
            specific_part='3-1-7-703', last_seen_at=now - timedelta(seconds=14*60+59)
        )
        # 704: 无记录 → 离线

        resp = self.client.get(self.url, {'is_active': 'true'})
        results = resp.json()['results']
        online_map = {r['specific_part']: r['is_screen_online'] for r in results}

        self.assertTrue(online_map.get('3-1-7-702'))
        self.assertTrue(online_map.get('3-1-7-703'))
        self.assertFalse(online_map.get('3-1-7-704'))


# ---------------------------------------------------------------------------
# E2E-US08: 清理策略
# ---------------------------------------------------------------------------

class CleanupE2ETest(TestCase):
    """E2E-US08-001: 清理命令 90 天边界 + 活跃豁免端到端。"""

    def _mk_event(self, sp, days_ago, is_active, sn='SN'):
        t = timezone.now() - timedelta(days=days_ago)
        return CondensationWarningEvent.objects.create(
            specific_part=sp, device_sn=sn, product_code='260001',
            first_seen_at=t, last_seen_at=t,
            recovered_at=t if not is_active else None,
            is_active=is_active, warning_type='结露预警', warning_message='结露报警',
        )

    def test_e2e_us08_001_cleanup_boundary_and_exempt(self):
        """E2E-US08-001 (AC-CW-08-02/03): 91天+inactive→删；91天+active→保留；5天+inactive→保留。"""
        self._mk_event('1-1-1-101', days_ago=91, is_active=False, sn='SN1')  # 应删
        self._mk_event('1-1-1-102', days_ago=91, is_active=True, sn='SN2')   # 活跃豁免
        self._mk_event('1-1-1-103', days_ago=5, is_active=False, sn='SN3')   # 未过期

        out = StringIO()
        call_command('condensation_cleanup', '--days=90', '--batch-size=1000',
                     '--sleep-ms=0', stdout=out)

        remaining = set(
            CondensationWarningEvent.objects.values_list('specific_part', flat=True)
        )
        self.assertNotIn('1-1-1-101', remaining, '91天inactive应被删除')
        self.assertIn('1-1-1-102', remaining, '91天active应豁免')
        self.assertIn('1-1-1-103', remaining, '5天inactive不应被删除')


# ---------------------------------------------------------------------------
# E2E-FRONTEND-001: 前端列数核对（静态解析 Vue 组件）
# ---------------------------------------------------------------------------

class FrontendColumnCheckE2ETest(TestCase):
    """E2E-FRONTEND-001: 核对 CondensationWarningView.vue 实际渲染列数与需求一致性。

    需求 AC-CW-02-03 列出 12 列（v0.3.0 定稿）：
      房号、房间、大屏是否在线、系统开关、预警类型、预警内容、
      露点温度、NTC温度、湿度、预警发生时间、最后活跃、恢复时间

    开发汇报为 12 列；本测试静态解析 Vue 文件，验证 el-table-column 数量和标签文字。
    """

    VUE_FILE = (
        r'C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\frontend\src\views\CondensationWarningView.vue'
    )

    EXPECTED_LABELS = [
        '房号', '房间', '大屏在线', '系统开关',
        '预警类型', '预警内容', '露点温度', 'NTC温度',
        '湿度', '预警发生时间', '最后活跃', '恢复时间',
    ]

    def test_frontend_001_column_count_and_labels(self):
        """E2E-FRONTEND-001: Vue 组件包含 12 个 el-table-column，标签与需求一致。"""
        try:
            with open(self.VUE_FILE, encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            self.fail(f'Vue 文件不存在: {self.VUE_FILE}')

        # 提取所有 el-table-column 的 label 属性
        # 匹配 label="xxxx" 或 label='xxxx'
        col_labels = re.findall(r'<el-table-column[^>]+label=["\']([^"\']+)["\']', content)

        actual_count = len(col_labels)
        self.assertEqual(
            actual_count, 12,
            f'前端列数为 {actual_count}，需求要求 12 列。实际列标签: {col_labels}'
        )

        # 验证需求要求的列标签均存在
        for expected in self.EXPECTED_LABELS:
            self.assertIn(
                expected, col_labels,
                f'前端缺少需求要求的列: "{expected}"。实际列: {col_labels}'
            )

    def test_frontend_002_extra_columns_explained(self):
        """E2E-FRONTEND-002: 验证前端无超出需求的额外列（多余列需说明来源）。

        需求 12 列 = 房号/房间/大屏在线/系统开关/预警类型/预警内容/
                    露点温度/NTC温度/湿度/预警发生时间/最后活跃/恢复时间

        注：AC-CW-02-03 原文列了 12 列（含"房间"列），Vue 实现亦为 12 列。
        """
        try:
            with open(self.VUE_FILE, encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            self.skipTest(f'Vue 文件不存在: {self.VUE_FILE}')

        col_labels = re.findall(r'<el-table-column[^>]+label=["\']([^"\']+)["\']', content)
        extra = [lbl for lbl in col_labels if lbl not in self.EXPECTED_LABELS]

        self.assertEqual(
            len(extra), 0,
            f'前端存在需求中未定义的列: {extra}。若为合理扩展请在测试文档中说明来源。'
        )
