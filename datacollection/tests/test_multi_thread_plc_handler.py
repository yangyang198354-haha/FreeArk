"""
PLCReadWriter 连接腐烂/弃连重连 回归测试

锁定 fix/plc-snap7-stale-connection-recovery 的三项修复：
  1) connect() 不再盲信 self.connected 缓存标志，会用 get_connected() 实探，
     标志陈旧（底层已断）时触发真正重连；
  2) connect() 在底层真连接时仍短路返回，不做多余重连；
  3) read_db_data() 读失败重试耗尽后调用 _mark_broken()，弃连并置 connected=False，
     使下一轮 connect() 不再短路复用腐烂连接（修复"失败不弃连/缓存腐烂"）。

注：__init__ 里的 snap7 超时 set_param 调用已在生产真实 snap7 2.0.2 上验证，
这里用 __new__ 注入 MagicMock client，专注核心逻辑、不依赖 snap7 安装。

运行（从项目根目录）:
    python -m pytest datacollection/tests/test_multi_thread_plc_handler.py -v
"""
import os
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

FREEARK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if FREEARK_ROOT not in sys.path:
    sys.path.insert(0, FREEARK_ROOT)

from datacollection.multi_thread_plc_handler import PLCReadWriter


def _make_reader(connected=False):
    """绕过 __init__（避开 snap7 依赖），注入 MagicMock client。"""
    r = PLCReadWriter.__new__(PLCReadWriter)
    r.plc_ip = '192.168.3.27'
    r.rack = 0
    r.slot = 1
    r.client = MagicMock()
    r.connected = connected
    r.connect_time = 0.0
    r.lock = threading.RLock()
    return r


def test_connect_short_circuits_when_link_truly_alive():
    """connected=True 且底层真连接 → 短路返回 True，不重连。"""
    r = _make_reader(connected=True)
    r.client.get_connected.return_value = True

    assert r.connect() is True
    r.client.get_connected.assert_called_once()
    r.client.connect.assert_not_called()  # 没有多余重连


def test_connect_reprobes_and_reconnects_on_stale_flag():
    """connected=True 但底层已断（get_connected=False）→ 触发真正重连。"""
    r = _make_reader(connected=True)
    # 第一次 get_connected: 实探发现已断；重连后第二次: 已连接
    r.client.get_connected.side_effect = [False, True]

    assert r.connect() is True
    r.client.connect.assert_called_once_with('192.168.3.27', 0, 1)
    assert r.connected is True


def test_read_failure_marks_broken_and_drops_connection():
    """db_read 持续抛异常、重试耗尽 → _mark_broken 弃连，connected 归 False。"""
    r = _make_reader(connected=True)
    r.client.db_read.side_effect = RuntimeError('TCP : connection reset')

    with patch('datacollection.multi_thread_plc_handler.time.sleep'):
        success, message, value = r.read_db_data(db_num=14, offset=100, length=2, data_type='int16')

    assert success is False
    assert '已重试' in message
    # 弃连：连接被断开且标志清除，下一轮 connect() 不会再短路
    assert r.connected is False
    r.client.disconnect.assert_called()


def test_mark_broken_is_idempotent_and_safe():
    """_mark_broken 即使 disconnect 抛异常也安全，并最终置 connected=False。"""
    r = _make_reader(connected=True)
    r.client.disconnect.side_effect = RuntimeError('already closed')

    r._mark_broken()  # 不应抛出

    assert r.connected is False
    assert r.connect_time == 0
