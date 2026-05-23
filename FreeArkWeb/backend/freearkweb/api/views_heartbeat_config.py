"""
views_heartbeat_config.py — 心跳 Broker 配置 API

GET  /api/heartbeat-broker-config/         任意已登录用户可读（password 字段返回空字符串）
PUT  /api/heartbeat-broker-config/update/  仅 admin 可写，写入后触发服务重启

设计约束（REQ-FUNC-002, REQ-NFUNC-001, ADR-001, ADR-002, ADR-004）:
- host 字段写入前正则校验（IPv4 / 域名），禁止注入
- password 空字符串时保留文件中原值（OQ-004）
- subprocess 调用模式与 service_management_action 保持一致（ADR-002）
- 原子写：先写 .tmp，再 os.replace（ADR-001）
"""

import json
import logging
import os
import re
import subprocess

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

# 与 mqtt_config.json 同级：FreeArkWeb/backend/heartbeat_broker_config.json
# 本文件位于 FreeArkWeb/backend/freearkweb/api/views_heartbeat_config.py
# __file__  → api/           (dirname×1)
#           → freearkweb/    (dirname×2)
#           → backend/       (dirname×3)  ← 配置文件在此层
_HBC_CONFIG_PATH = os.path.join(
    os.path.dirname(   # api/
    os.path.dirname(   # freearkweb/
    os.path.dirname(   # backend/
    os.path.abspath(__file__)))),
    'heartbeat_broker_config.json',
)

# ---------------------------------------------------------------------------
# 默认配置（与现有硬编码值一致，升级后零行为变化）
# ---------------------------------------------------------------------------

_HBC_DEFAULT_CONFIG: dict = {
    'protocol': 'mqtt',
    'host': '47.117.41.184',
    'port': 11883,
    'path': '/mqtt',
    'username': 'admin',
    'password': 'public',
    'topic': '/screen/upload/screen/to/cloud/#',
    'client_id': 'freeark-screen-heartbeat',
    'keepalive': 60,
}

# ---------------------------------------------------------------------------
# host 正则校验（IPv4 或域名，禁止注入字符）
# ---------------------------------------------------------------------------

_HOST_PATTERN = re.compile(
    r'^(?:'
    r'(?:\d{1,3}\.){3}\d{1,3}'          # IPv4
    r'|'
    r'(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}'  # 域名
    r')$'
)

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _read_hbc_config() -> dict:
    """读取 heartbeat_broker_config.json。文件不存在或解析失败时返回默认配置副本。"""
    try:
        with open(_HBC_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(
            '_read_hbc_config: 配置文件不存在 (%s)，返回默认配置', _HBC_CONFIG_PATH
        )
        return dict(_HBC_DEFAULT_CONFIG)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error('_read_hbc_config: 读取配置文件失败: %s', exc)
        return dict(_HBC_DEFAULT_CONFIG)


def _write_hbc_config(config: dict) -> None:
    """原子写入：先写 .tmp，再 os.replace，防止写入中断导致文件损坏。"""
    tmp_path = _HBC_CONFIG_PATH + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.replace(tmp_path, _HBC_CONFIG_PATH)


def _restart_heartbeat_service() -> tuple:
    """
    触发 freeark-screen-heartbeat 服务重启。
    复用 service_management_action 的调用模式：
      subprocess.run(['sudo', 'systemctl', action, service_name],
                     capture_output=True, text=True, timeout=30)
    返回 (success: bool, message: str)。
    """
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'restart', 'freeark-screen-heartbeat'],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info('_restart_heartbeat_service: 服务重启成功')
            return True, 'freeark-screen-heartbeat 重启成功'
        else:
            msg = (result.stderr or result.stdout or f'returncode={result.returncode}').strip()
            logger.error('_restart_heartbeat_service: systemctl restart 失败: %s', msg)
            return False, f'systemctl restart 返回非零: {msg}'
    except subprocess.TimeoutExpired:
        logger.error('_restart_heartbeat_service: systemctl restart 超时（30s）')
        return False, 'systemctl restart 超时（30s）'
    except Exception as exc:
        logger.error('_restart_heartbeat_service: 异常: %s', exc)
        return False, str(exc)


# ---------------------------------------------------------------------------
# 视图：GET
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def heartbeat_broker_config_get(request):
    """
    GET /api/heartbeat-broker-config/
    读取当前心跳 Broker 配置，password 字段返回空字符串（不回显明文）。
    权限：任意已登录用户。
    """
    config = _read_hbc_config()
    # OQ-004：GET 时 password 字段返回空字符串
    config['password'] = ''
    return Response({'success': True, 'data': config})


# ---------------------------------------------------------------------------
# 视图：PUT
# ---------------------------------------------------------------------------

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def heartbeat_broker_config_put(request):
    """
    PUT /api/heartbeat-broker-config/update/
    写入心跳 Broker 配置并触发服务重启。
    权限：admin role（双层防御：API 层 + sudoers 层）。

    字段说明：
      - protocol: "mqtt" | "wss"（必填）
      - host: IPv4 或域名（必填，正则校验）
      - port: 1-65535（必填）
      - path: wss 时使用的 WebSocket path（可选，默认 "/mqtt"）
      - username, password, topic, client_id, keepalive: 可选，缺省保留原值
      - password 为空字符串时保留文件中原值（OQ-004）
    """
    # --- 1. 权限：仅 admin ---
    user = request.user
    if not (
        getattr(user, 'role', None) == 'admin'
        or getattr(user, 'is_staff', False)
        or getattr(user, 'is_superuser', False)
    ):
        return Response(
            {'success': False, 'error': '权限不足，仅 admin 可修改心跳 Broker 配置'},
            status=status.HTTP_403_FORBIDDEN,
        )

    data = request.data
    current = _read_hbc_config()

    # --- 2. 字段校验 ---

    # protocol
    protocol = data.get('protocol', current.get('protocol', 'mqtt'))
    if protocol not in ('mqtt', 'wss'):
        return Response(
            {'success': False, 'error': 'protocol 字段必须为 "mqtt" 或 "wss"'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # host（正则校验，防止注入）
    host = str(data.get('host', current.get('host', ''))).strip()
    if not host or not _HOST_PATTERN.match(host):
        return Response(
            {'success': False, 'error': 'host 字段无效，必须是合法 IPv4 地址或域名'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # port
    try:
        port = int(data.get('port', current.get('port', 1883)))
        if not (1 <= port <= 65535):
            raise ValueError('port out of range')
    except (ValueError, TypeError):
        return Response(
            {'success': False, 'error': 'port 字段必须是 1-65535 的整数'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # OQ-004：password 为空字符串时保留文件中原值
    password_input = data.get('password', '')
    password = password_input if password_input else current.get('password', '')

    # --- 3. 组装新配置 ---
    new_config = {
        'protocol': protocol,
        'host': host,
        'port': port,
        'path': str(data.get('path', current.get('path', '/mqtt'))),
        'username': str(data.get('username', current.get('username', ''))),
        'password': password,
        'topic': str(data.get('topic', current.get('topic', '/screen/upload/screen/to/cloud/#'))),
        'client_id': str(data.get('client_id', current.get('client_id', 'freeark-screen-heartbeat'))),
        'keepalive': int(data.get('keepalive', current.get('keepalive', 60))),
    }

    # --- 4. 原子写入配置文件 ---
    try:
        _write_hbc_config(new_config)
        logger.info(
            'heartbeat_broker_config.json 已更新: protocol=%s host=%s port=%d by user=%s',
            protocol, host, port, user.username,
        )
    except OSError as exc:
        logger.error('写入 heartbeat_broker_config.json 失败: %s', exc)
        return Response(
            {'success': False, 'error': f'配置文件写入失败: {exc}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # --- 5. 触发服务重启 ---
    ok, msg = _restart_heartbeat_service()
    if ok:
        return Response({'success': True, 'message': '配置已保存，服务重启中'})
    else:
        return Response(
            {'success': False, 'error': f'配置已保存，但服务重启失败: {msg}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
