"""
MQTTClient 断线重连后自动恢复订阅 —— 回归测试。

背景（2026-06-27 生产事故）：
  paho 默认 clean_session=True，broker 中断后客户端虽自动重连 TCP（socket 仍 ESTAB），
  但订阅不会自动恢复；旧 _on_connect 只打日志不重订阅 → PLCWriteSubscriber 静默失聪，
  写命令全部漏收、写操作永久卡 pending、设备无动作。
  本测试锁定：任何 (重)连成功都会把已登记的订阅重新下发。
"""

from unittest.mock import MagicMock

import paho.mqtt.client as mqtt

from datacollection.mqtt_client import MQTTClient


def _make_client():
    c = MQTTClient(host='127.0.0.1', port=1883, client_id='test-resub')
    # 用 Mock 替换底层 paho client，拦截 subscribe 调用，避免真实网络
    c.client = MagicMock()
    c.client.subscribe.return_value = (mqtt.MQTT_ERR_SUCCESS, 1)
    return c


def test_subscribe_registers_topic_for_recovery():
    """subscribe() 应登记 (topic, qos) 以便重连后恢复。"""
    c = _make_client()
    c.connected = True
    c.subscribe('/a/b/#', qos=1, callback=lambda t, p: None)
    assert ('/a/b/#', 1) in c._subscriptions


def test_subscribe_registers_even_when_disconnected():
    """未连接时也应登记订阅，连接建立后由 _on_connect 补订阅。"""
    c = _make_client()
    c.connected = False
    assert c.subscribe('/x/#', qos=1) is False  # 当前未连接返回 False
    assert ('/x/#', 1) in c._subscriptions       # 但已登记


def test_on_connect_resubscribes_registered_topics():
    """重连成功（rc=0）应重新下发所有已登记订阅（核心修复点）。"""
    c = _make_client()
    c.connected = True
    c.subscribe('/cmd/#', qos=1, callback=lambda t, p: None)
    c.client.subscribe.reset_mock()  # 清掉首次订阅的调用记录

    # 模拟断线后自动重连触发 on_connect
    c._on_connect(c.client, None, {}, 0)

    c.client.subscribe.assert_any_call('/cmd/#', qos=1)
    assert c.connected is True


def test_on_connect_failure_does_not_resubscribe():
    """连接失败（rc!=0）不应订阅，且 connected=False。"""
    c = _make_client()
    c.subscribe('/cmd/#', qos=1)
    c.client.subscribe.reset_mock()

    c._on_connect(c.client, None, {}, 5)  # rc=5 连接被拒

    c.client.subscribe.assert_not_called()
    assert c.connected is False


def test_no_duplicate_registration():
    """重复 subscribe 同一 topic 不应重复登记。"""
    c = _make_client()
    c.connected = True
    c.subscribe('/dup/#', qos=1)
    c.subscribe('/dup/#', qos=1)
    assert c._subscriptions.count(('/dup/#', 1)) == 1
