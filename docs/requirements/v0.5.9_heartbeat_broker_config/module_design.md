# 模块设计文档

**版本**：v0.5.9-heartbeat-broker-config  
**日期**：2026-05-23  
**状态**：DRAFT — 待用户 CONFIRM  
**作者**：SDLC System Architect (sub_agent_system_architect)

---

## 1. 模块总览

| 模块 ID | 名称 | 类型 | 文件 | 主要职责 |
|---------|------|------|------|---------|
| MOD-BE-HBC-01 | 心跳 Broker 配置 API | 后端视图 | `api/views_heartbeat_config.py`（新建） | 读取/写入配置文件 + 触发服务重启 |
| MOD-BE-HBC-02 | URL 路由注册 | 后端路由 | `api/urls.py`（修改） | 注册 2 条新 URL pattern |
| MOD-BE-HBC-03 | Consumer 配置加载 | 后端 Management Command | `api/management/commands/screen_heartbeat_consumer.py`（修改） | 启动时读取配置文件，按协议初始化 paho client |
| MOD-FE-HBC-01 | 心跳 Broker 配置页 | 前端 Vue 组件 | `frontend/src/views/HeartbeatBrokerConfigView.vue`（新建） | 展示/编辑 broker 配置，发起保存请求 |
| MOD-FE-HBC-02 | 路由注册 | 前端路由 | `frontend/src/router/index.js`（修改） | 新增 `/services/heartbeat-config` 路由 |
| MOD-FE-HBC-03 | 导航菜单 | 前端布局 | `frontend/src/components/Layout.vue`（修改） | 在「服务管理」子菜单下新增「心跳中间件配置」入口 |
| MOD-SVC-HBC-01 | systemd service 文件 | 部署配置 | `systemctl/freeark-screen-heartbeat.service`（修改） | 新增 StartLimitIntervalSec/Burst |
| MOD-DATA-HBC-01 | 配置文件 | 数据文件 | `FreeArkWeb/backend/heartbeat_broker_config.json`（新建） | 持久化 broker 连接参数 |

---

## 2. MOD-BE-HBC-01：心跳 Broker 配置 API

### 2.1 文件：`api/views_heartbeat_config.py`（新建）

#### 常量与工具函数

```python
import json, os, re, subprocess, logging
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

# 配置文件路径（与 mqtt_config.json 同级）
_HBC_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'heartbeat_broker_config.json',
)

# 默认配置（文件不存在时的 fallback，与现有硬编码值一致）
_HBC_DEFAULT_CONFIG = {
    "protocol": "mqtt",
    "host": "47.117.41.184",
    "port": 11883,
    "path": "/mqtt",
    "username": "admin",
    "password": "public",
    "topic": "/screen/upload/screen/to/cloud/#",
    "client_id": "freeark-screen-heartbeat",
    "keepalive": 60,
}

# host 字段安全校验正则（IPv4 或域名）
_HOST_PATTERN = re.compile(
    r'^(?:(?:\d{1,3}\.){3}\d{1,3}|(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,})$'
)
```

#### 工具函数

```python
def _read_hbc_config() -> dict:
    """读取 heartbeat broker 配置文件，文件不存在时返回默认配置。"""
    try:
        with open(_HBC_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning('heartbeat_broker_config.json 不存在，返回默认配置')
        return dict(_HBC_DEFAULT_CONFIG)
    except (json.JSONDecodeError, OSError) as e:
        logger.error('读取 heartbeat_broker_config.json 失败: %s', e)
        return dict(_HBC_DEFAULT_CONFIG)


def _write_hbc_config(config: dict) -> None:
    """原子写入配置文件：先写临时文件，再 rename，防止写入中途崩溃导致文件损坏。"""
    tmp_path = _HBC_CONFIG_PATH + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, _HBC_CONFIG_PATH)


def _restart_heartbeat_service() -> tuple[bool, str]:
    """触发 freeark-screen-heartbeat 服务重启，返回 (success, message)。"""
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'restart', 'freeark-screen-heartbeat'],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return True, 'freeark-screen-heartbeat 重启成功'
        else:
            msg = result.stderr.strip() or result.stdout.strip() or f'returncode={result.returncode}'
            logger.error('systemctl restart freeark-screen-heartbeat 失败: %s', msg)
            return False, f'systemctl restart 返回非零: {msg}'
    except subprocess.TimeoutExpired:
        logger.error('systemctl restart freeark-screen-heartbeat 超时（30s）')
        return False, 'systemctl restart 超时（30s）'
    except Exception as e:
        logger.error('systemctl restart freeark-screen-heartbeat 异常: %s', e)
        return False, str(e)
```

#### GET 视图

```python
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def heartbeat_broker_config_get(request):
    """
    GET /api/heartbeat-broker-config/
    读取当前心跳 Broker 配置，password 字段 mask 为空字符串。
    权限：任意已登录用户。
    """
    config = _read_hbc_config()
    # 不回显 password 明文
    config['password'] = ''
    return Response({'success': True, 'data': config})
```

#### PUT 视图

```python
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def heartbeat_broker_config_put(request):
    """
    PUT /api/heartbeat-broker-config/
    写入心跳 Broker 配置并触发服务重启。
    权限：admin role。

    请求体字段（均可选，缺省保留原值）：
      protocol, host, port, path, username, password, topic, client_id, keepalive
    """
    # 权限：仅 admin
    user = request.user
    if not (getattr(user, 'role', None) == 'admin' or user.is_staff or user.is_superuser):
        return Response(
            {'success': False, 'error': '权限不足，仅 admin 可修改心跳 Broker 配置'},
            status=status.HTTP_403_FORBIDDEN,
        )

    data = request.data
    current = _read_hbc_config()

    # --- 字段校验 ---
    protocol = data.get('protocol', current.get('protocol', 'mqtt'))
    if protocol not in ('mqtt', 'wss'):
        return Response(
            {'success': False, 'error': 'protocol 字段必须为 "mqtt" 或 "wss"'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    host = data.get('host', current.get('host', ''))
    if not host or not _HOST_PATTERN.match(str(host)):
        return Response(
            {'success': False, 'error': 'host 字段无效，必须是合法 IPv4 地址或域名'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        port = int(data.get('port', current.get('port', 1883)))
        assert 1 <= port <= 65535
    except (ValueError, AssertionError):
        return Response(
            {'success': False, 'error': 'port 字段必须是 1-65535 的整数'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # password：若请求中为空字符串，保留文件中原值（避免每次必须传密码）
    password = data.get('password', '')
    if not password:
        password = current.get('password', '')

    # 组装新配置
    new_config = {
        'protocol': protocol,
        'host': str(host),
        'port': port,
        'path': str(data.get('path', current.get('path', '/mqtt'))),
        'username': str(data.get('username', current.get('username', ''))),
        'password': password,
        'topic': str(data.get('topic', current.get('topic', '/screen/upload/screen/to/cloud/#'))),
        'client_id': str(data.get('client_id', current.get('client_id', 'freeark-screen-heartbeat'))),
        'keepalive': int(data.get('keepalive', current.get('keepalive', 60))),
    }

    # --- 写入配置文件 ---
    try:
        _write_hbc_config(new_config)
        logger.info('heartbeat_broker_config.json 已更新: protocol=%s host=%s port=%d', protocol, host, port)
    except OSError as e:
        logger.error('写入 heartbeat_broker_config.json 失败: %s', e)
        return Response(
            {'success': False, 'error': f'配置文件写入失败: {e}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # --- 触发服务重启 ---
    ok, msg = _restart_heartbeat_service()
    if ok:
        return Response({'success': True, 'message': '配置已保存，服务重启中'})
    else:
        return Response(
            {'success': False, 'error': f'配置已保存，但服务重启失败: {msg}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
```

---

## 3. MOD-BE-HBC-02：URL 路由注册

在 `api/urls.py` 中新增（`from . import views_heartbeat_config` 已加入 import 区）：

```python
# 心跳 Broker 配置接口
path('heartbeat-broker-config/', views_heartbeat_config.heartbeat_broker_config_get, name='heartbeat-broker-config-get'),
path('heartbeat-broker-config/update/', views_heartbeat_config.heartbeat_broker_config_put, name='heartbeat-broker-config-put'),
```

> 说明：GET 和 PUT 挂在同一 URL 亦可（通过 `@api_view(['GET', 'PUT'])` 合并），但分开注册与现有代码风格一致，且便于权限分离描述。

**备选（合并路由）**：

```python
path('heartbeat-broker-config/', views_heartbeat_config.heartbeat_broker_config, name='heartbeat-broker-config'),
```

此时视图函数通过 `request.method` 分支 GET/PUT，减少一条 URL。开发时选择其一，保持一致即可。

---

## 4. MOD-BE-HBC-03：Consumer 配置加载（修改）

### 4.1 文件：`api/management/commands/screen_heartbeat_consumer.py`

**改动点 1**：新增 `_load_heartbeat_config()` 函数（替换硬编码常量）

```python
import json, os

_HBC_CONFIG_PATH = os.path.join(
    os.path.dirname(  # commands/
    os.path.dirname(  # management/
    os.path.dirname(  # api/
    os.path.dirname(  # freearkweb/
    os.path.dirname(  # backend/
    os.path.abspath(__file__)))))),
    'heartbeat_broker_config.json',
)

_FALLBACK_CONFIG = {
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

def _load_heartbeat_config() -> dict:
    """
    从 heartbeat_broker_config.json 加载 broker 连接配置。
    文件不存在或解析失败时降级使用 _FALLBACK_CONFIG，并记录 WARNING。
    """
    try:
        with open(_HBC_CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        logger.info(
            '_load_heartbeat_config: 已加载配置文件 protocol=%s host=%s port=%s',
            cfg.get('protocol'), cfg.get('host'), cfg.get('port'),
        )
        return cfg
    except FileNotFoundError:
        logger.warning(
            '_load_heartbeat_config: 配置文件不存在 (%s)，使用默认配置 mqtt/47.117.41.184/11883',
            _HBC_CONFIG_PATH,
        )
        return dict(_FALLBACK_CONFIG)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning('_load_heartbeat_config: 配置文件读取失败 (%s)，使用默认配置: %s', _HBC_CONFIG_PATH, e)
        return dict(_FALLBACK_CONFIG)
```

**改动点 2**：`Command.handle()` 方法改造

```python
def handle(self, *args, **options):
    import paho.mqtt.client as mqtt

    # 加载配置（替换硬编码常量）
    cfg = _load_heartbeat_config()
    protocol   = cfg.get('protocol', 'mqtt')
    host       = cfg.get('host', '47.117.41.184')
    port       = int(cfg.get('port', 11883))
    path       = cfg.get('path', '/mqtt')
    username   = cfg.get('username', 'admin')
    password   = cfg.get('password', 'public')
    topic      = cfg.get('topic', '/screen/upload/screen/to/cloud/#')
    client_id  = cfg.get('client_id', 'freeark-screen-heartbeat')
    keepalive  = int(cfg.get('keepalive', 60))

    mac_cache = MacCache()

    # ... on_connect / on_message / on_disconnect 回调定义不变（内部引用 topic / host / port 改为局部变量）...

    # 根据协议初始化 paho client
    if protocol == 'wss':
        client = mqtt.Client(client_id=client_id, transport='websockets')
        client.tls_set()                    # 使用系统 CA bundle，验证服务端 TLS 证书
        client.ws_set_options(path=path)    # wss path，如 "/mqtt"
        logger.info('使用 wss 传输: %s:%d%s', host, port, path)
    else:
        client = mqtt.Client(client_id=client_id, transport='tcp')
        logger.info('使用 mqtt TCP 传输: %s:%d', host, port)

    if username:
        client.username_pw_set(username, password)

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    client.connect(host, port, keepalive=keepalive)
    logger.info('screen_heartbeat_consumer 启动，topic=%s', topic)
    client.loop_forever(retry_first_connection=True)
```

**注**：`on_connect` 回调中的 subscribe 调用改为引用局部变量 `topic`（非硬编码 `MQTT_TOPIC`）。

**废弃**：原模块级常量 `MQTT_HOST`、`MQTT_PORT`、`MQTT_USERNAME`、`MQTT_PASSWORD`、`MQTT_TOPIC`、`MQTT_CLIENT_ID` 可保留作注释（文档用途），或直接删除（推荐删除，避免误导）。

---

## 5. MOD-FE-HBC-01：心跳 Broker 配置页

### 5.1 文件：`frontend/src/views/HeartbeatBrokerConfigView.vue`（新建）

**交互流程**：

```
组件挂载 (onMounted)
    → GET /api/heartbeat-broker-config/
        → 填充表单初始值
        → 若 protocol=wss，显示 path 字段

用户编辑表单
    → 切换协议下拉框
        → wss：显示 path 字段，port 默认 8084（若当前为 1883）
        → mqtt：隐藏 path 字段，port 默认 1883（若当前为 8084）

用户点击「保存并重启服务」
    → el-dialog 确认弹窗（与 ServicesView 样式一致）
        → 确认 → PUT /api/heartbeat-broker-config/
            → 成功：ElMessage.success('配置已保存，服务重启中')
            → 失败：ElMessage.error(resp.error)
        → 取消 → 关闭弹窗
```

**表单字段定义**：

| 字段 | 组件 | 校验 | 条件显示 |
|------|------|------|---------|
| protocol | el-select | 必选，枚举 | 始终显示 |
| host | el-input | 必填，非空 | 始终显示 |
| port | el-input-number | 必填，1-65535 | 始终显示 |
| path | el-input | 可选 | protocol=wss 时显示 |
| username | el-input | 可选 | 始终显示 |
| password | el-input (password) | 可选（空=不修改） | 始终显示 |
| topic | el-input | 必填 | 始终显示 |
| client_id | el-input | 可选 | 始终显示 |
| keepalive | el-input-number | 可选，正整数 | 始终显示 |

**状态管理**（Composition API）：

```javascript
const form = reactive({
  protocol: 'mqtt',
  host: '',
  port: 11883,
  path: '/mqtt',
  username: '',
  password: '',
  topic: '',
  client_id: '',
  keepalive: 60,
})
const loading = ref(false)
const saving = ref(false)
const confirmVisible = ref(false)

// 协议切换联动：port 默认值联动
watch(() => form.protocol, (newProto) => {
  if (newProto === 'wss' && form.port === 1883) form.port = 8084
  if (newProto === 'mqtt' && form.port === 8084) form.port = 1883
})
```

---

## 6. MOD-FE-HBC-02/03：路由与导航菜单修改

### router/index.js 新增

```javascript
{
  path: '/services/heartbeat-config',
  name: 'HeartbeatBrokerConfig',
  component: () => import('../views/HeartbeatBrokerConfigView.vue'),
  meta: { requiresAuth: true }
}
```

### Layout.vue 修改（服务管理子菜单下新增）

```html
<el-sub-menu index="services">
  <template #title>
    <el-icon><Setting /></el-icon>
    <span>服务管理</span>
  </template>
  <el-menu-item index="/services">服务列表</el-menu-item>
  <el-menu-item index="/services/heartbeat-config">心跳中间件配置</el-menu-item>  <!-- 新增 -->
</el-sub-menu>
```

---

## 7. MOD-SVC-HBC-01：systemd Service 文件修改

**文件**：`systemctl/freeark-screen-heartbeat.service`

**新增内容**（在 `[Service]` 节末尾）：

```ini
StartLimitIntervalSec=300
StartLimitBurst=5
```

**完整文件（修改后）**：

```ini
[Unit]
Description=FreeArk Screen Heartbeat Consumer Service
After=network.target

[Service]
Type=simple
User=yangyang
WorkingDirectory=/home/yangyang/Freeark/FreeArk/
ExecStart=/home/yangyang/Freeark/FreeArk/venv/bin/python /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/manage.py screen_heartbeat_consumer
Restart=on-failure
RestartSec=30s
StartLimitIntervalSec=300
StartLimitBurst=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=freeark-screen-heartbeat

[Install]
WantedBy=multi-user.target
```

---

## 8. MOD-DATA-HBC-01：配置文件初始内容

**文件**：`FreeArkWeb/backend/heartbeat_broker_config.json`（新建，首次部署时创建）

```json
{
  "protocol": "mqtt",
  "host": "47.117.41.184",
  "port": 11883,
  "path": "/mqtt",
  "username": "admin",
  "password": "public",
  "topic": "/screen/upload/screen/to/cloud/#",
  "client_id": "freeark-screen-heartbeat",
  "keepalive": 60
}
```

**说明**：初始值与现有硬编码值一致，保证服务升级后行为不变。

---

## 9. 接口契约（API Contract）

### GET /api/heartbeat-broker-config/

**Response 200**:
```json
{
  "success": true,
  "data": {
    "protocol": "mqtt",
    "host": "47.117.41.184",
    "port": 11883,
    "path": "/mqtt",
    "username": "admin",
    "password": "",
    "topic": "/screen/upload/screen/to/cloud/#",
    "client_id": "freeark-screen-heartbeat",
    "keepalive": 60
  }
}
```

### PUT /api/heartbeat-broker-config/ (或 /api/heartbeat-broker-config/update/)

**Request body**:
```json
{
  "protocol": "wss",
  "host": "www.ttqingjiao.site",
  "port": 8084,
  "path": "/mqtt",
  "username": "admin",
  "password": "",
  "topic": "/screen/upload/screen/to/cloud/#",
  "client_id": "freeark-screen-heartbeat",
  "keepalive": 60
}
```

**Response 200 (成功)**:
```json
{ "success": true, "message": "配置已保存，服务重启中" }
```

**Response 500 (配置写入成功但重启失败)**:
```json
{ "success": false, "error": "配置已保存，但服务重启失败: systemctl restart 返回非零: ..." }
```

**Response 400 (字段校验失败)**:
```json
{ "success": false, "error": "host 字段无效，必须是合法 IPv4 地址或域名" }
```

**Response 403 (权限不足)**:
```json
{ "success": false, "error": "权限不足，仅 admin 可修改心跳 Broker 配置" }
```

---

*文档状态：DRAFT。请用户确认后进入 tech_stack 确认阶段。*
