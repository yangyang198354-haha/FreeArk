# 架构设计文档

**版本**：v0.5.9-heartbeat-broker-config  
**日期**：2026-05-23  
**状态**：DRAFT — 待用户 CONFIRM  
**作者**：SDLC System Architect (sub_agent_system_architect)

---

## 1. 架构概览

本次变更属于增量功能迭代，核心架构路径为：

```
[前端配置表单]
    → PUT /api/heartbeat-broker-config/  (Django REST API, admin only)
        → 写入 heartbeat_broker_config.json
        → subprocess: sudo systemctl restart freeark-screen-heartbeat
            → freeark-screen-heartbeat.service 重启
                → screen_heartbeat_consumer.py 读取 heartbeat_broker_config.json
                    → 根据 protocol 字段选择 mqtt TCP / wss WebSocket 连接
                        → 订阅 topic，处理心跳（逻辑不变）
```

---

## 2. 架构决策记录（ADR）

### ADR-001：配置持久化方式 — JSON 文件 vs 数据库

**问题**：heartbeat consumer 的 broker 连接参数应存储在哪里？

**方案对比**：

| 方案 | 优点 | 缺点 |
|------|------|------|
| A. JSON 文件（`heartbeat_broker_config.json`） | 与 mqtt_config.json 风格一致；consumer 启动读取无需 Django ORM；DevOps 可直接 vim 编辑；无 DB 依赖 | 文件权限需手动管理；无版本历史 |
| B. Django Model（DB 表） | 有版本历史；Admin 界面自带 | consumer 进程启动时需 Django 环境（已有，无额外成本）；但 consumer 使用的是 management command，访问 DB 有 ORM overhead |
| C. 环境变量（.env） | 简单 | 变更需 reload service；不支持 Web 可视化编辑 |

**决策**：选择方案 A（JSON 文件）。

**理由**：
1. 项目已有 `mqtt_config.json` 同等模式，DevOps 运维习惯一致。
2. Consumer 是独立 management command，JSON 读取代价最小，不引入额外 DB 查询。
3. Web API 读写 JSON 文件的路径在现有 `views.py` 中已有先例（见 `device_ondemand_refresh` 读取 `mqtt_config.json`）。
4. 文件路径固定（`FreeArkWeb/backend/heartbeat_broker_config.json`），部署路径明确。

---

### ADR-002：服务重启触发方式 — 直接 subprocess vs 复用 service_management_action

**问题**：PUT 配置 API 触发 restart 的实现方式。

**方案对比**：

| 方案 | 说明 |
|------|------|
| A. 在 PUT API 内 inline subprocess.run(['sudo', 'systemctl', 'restart', ...]) | 逻辑自包含，简单直接 |
| B. 调用已有 service_management_action 视图内部函数 | 复用逻辑，减少重复 |
| C. 前端两步操作：先保存配置，再单独调用服务重启接口 | 更灵活，但用户体验差（两步操作） |

**决策**：选择方案 A（inline subprocess）。

**理由**：
1. 方案 B 的 service_management_action 是视图函数，内部耦合 Request/Response 对象，提取为可复用函数需重构，代价不小。
2. 方案 A 与 service_management_action 的 subprocess 调用模式完全一致（相同的 sudoers 白名单、相同的 timeout、相同的错误处理），复制粘贴风险低，逻辑透明。
3. 白名单已含 `freeark-screen-heartbeat`，无需修改 sudoers。

**注**：若后续多个配置变更需要触发 restart，可将 subprocess 逻辑抽象为 `_trigger_service_restart(service_name)` 工具函数（位于 `views.py` 或新建 `utils_service.py`）。

---

### ADR-003：paho-mqtt 协议抽象 — transport 参数 vs 独立客户端

**问题**：如何在同一 consumer 内支持 `mqtt`（TCP）和 `wss`（WebSocket over TLS）？

**方案对比**：

| 方案 | 说明 |
|------|------|
| A. paho-mqtt `transport` 参数（"tcp" / "websockets"）+ `tls_set()` | 单一 paho client，内置支持；paho >= 1.4 已支持 websockets transport |
| B. 引入 gmqtt 库（async，支持 wss） | 需引入 asyncio；与现有同步 management command 不兼容，改动量大 |
| C. 引入 aiomqtt | 同上，async 依赖 |

**决策**：选择方案 A（paho transport 参数）。

**理由**：
1. paho-mqtt 已在 `requirements.txt` 中（`paho-mqtt>=1.6.1`），无需新增依赖。
2. paho >= 1.4 通过 `mqtt.Client(transport="websockets")` + `tls_set()` + `ws_set_options(path=path)` 原生支持 wss，API 稳定。
3. paho >= 2.0 引入了 `CallbackAPIVersion`，但 1.x 兼容 API 仍然可用（通过 `mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION1)` 或直接省略参数保持 1.x 行为）。
4. consumer 是同步长进程，`loop_forever` 模式无需改动。

**paho wss 初始化伪代码**（方案参考，非最终代码）：
```python
if protocol == "wss":
    client = mqtt.Client(client_id=client_id, transport="websockets")
    client.tls_set()          # 使用系统 CA bundle 验证服务端证书
    client.ws_set_options(path=path)   # 如 "/mqtt"
    client.connect(host, port, keepalive)
else:  # mqtt (TCP)
    client = mqtt.Client(client_id=client_id, transport="tcp")
    client.connect(host, port, keepalive)
```

---

### ADR-004：权限边界 — API 层 vs sudoers 层

**问题**：谁有权触发 `systemctl restart freeark-screen-heartbeat`？

**现状**：
- Django API 层：`IsAuthenticated` 已有，admin role 检查已有先例（`service_management_action` 中的 `request.user.is_staff or request.user.role == 'admin'` 模式）。
- OS 层：`yangyang` 用户已通过 sudoers 获得对 `freeark-*` 服务的 `systemctl start/stop/restart` 权限。

**决策**：双层防御——API 层限 admin role；OS 层依托已有 sudoers 白名单。

**安全约束**：
1. PUT 接口中 host 字段必须通过正则校验（仅允许域名字符和 IPv4 格式），防止命令注入（host 字段不进入 systemctl 命令，仅写入 JSON 文件，但仍需校验）。
2. `systemctl` 调用使用固定字符串 `freeark-screen-heartbeat`，不拼接用户输入。
3. 配置文件通过 `json.dumps` 序列化写入，不做字符串拼接，无注入面。

---

### ADR-005：crash-loop 防护 — StartLimitBurst

**问题**：broker 地址配置错误时，systemd 会无限重启服务，浪费资源。

**决策**：在 `freeark-screen-heartbeat.service` 中新增：

```ini
StartLimitIntervalSec=300
StartLimitBurst=5
```

含义：300 秒内最多启动 5 次，超过后服务进入 `failed` 状态，需管理员手动 `systemctl reset-failed` + `systemctl start`。

**理由**：这是 systemd 标准的防 crash-loop 机制，无需应用层改动，运维成本低。

---

## 3. 数据流图

```
管理员浏览器
    │
    │ GET /api/heartbeat-broker-config/
    ▼
Django API (views.py 或 views_heartbeat_config.py)
    │
    ├── 读取 heartbeat_broker_config.json
    │       │
    │       └─ 文件不存在 → 返回默认值（不自动创建文件）
    │
    └── 返回配置 JSON（password mask 为空字符串）
    
管理员浏览器
    │
    │ PUT /api/heartbeat-broker-config/  (admin only)
    ▼
Django API
    ├── 1. 校验权限（IsAdminUser）
    ├── 2. 校验请求体字段（protocol ∈ {mqtt, wss}，host 非空，port 1-65535）
    ├── 3. 若 password 字段为空 → 读取文件中原 password 值合并
    ├── 4. json.dumps 写入 heartbeat_broker_config.json（原子写：先写临时文件，再 rename）
    ├── 5. subprocess.run(['sudo', 'systemctl', 'restart', 'freeark-screen-heartbeat'], timeout=30)
    │       ├── returncode=0 → { "success": true }
    │       └── returncode!=0 / timeout → { "success": false, "error": "..." }
    └── 返回响应

systemd
    │
    └── 重启 freeark-screen-heartbeat.service
            │
            └── python manage.py screen_heartbeat_consumer
                    │
                    ├── 读取 heartbeat_broker_config.json
                    │       ├── 成功 → 使用文件中配置
                    │       └── 失败 → 使用 fallback 常量 + WARNING 日志
                    │
                    ├── protocol == "wss"？
                    │       ├── Yes → Client(transport="websockets") + tls_set() + ws_set_options(path)
                    │       └── No  → Client(transport="tcp")
                    │
                    └── connect(host, port, keepalive) → loop_forever()
                            │
                            └── on_message: topic 解析 + _upsert_last_seen（逻辑不变）
```

---

## 4. 模块依赖关系

```
前端
  └── HeartbeatBrokerConfigView.vue（新）
        └── api.js → /api/heartbeat-broker-config/

后端
  ├── urls.py（新增 2 条路由）
  ├── views_heartbeat_config.py（新文件，或追加至 views.py）
  │     ├── heartbeat_broker_config_get（GET）
  │     └── heartbeat_broker_config_put（PUT）
  │           ├── 依赖：_MONITORED_SERVICES_SET（已有，用于 subprocess 安全）
  │           └── 依赖：heartbeat_broker_config.json（文件 I/O）
  │
  └── management/commands/screen_heartbeat_consumer.py（修改）
        └── 新增：_load_heartbeat_config()
              └── 依赖：heartbeat_broker_config.json
```

---

## 5. 部署变更点

| 变更项 | 类型 | 说明 |
|--------|------|------|
| `heartbeat_broker_config.json` | 新建文件 | 初始内容为当前硬编码值，chmod 600 |
| `screen_heartbeat_consumer.py` | 修改 | 读取配置文件，支持 wss transport |
| `views_heartbeat_config.py`（或 views.py） | 新增/修改 | 2 个新视图函数 |
| `urls.py` | 修改 | 新增 2 条 URL pattern |
| `HeartbeatBrokerConfigView.vue` | 新建 | 前端配置表单 |
| `router/index.js` | 修改 | 新增路由 |
| `freeark-screen-heartbeat.service` | 修改 | 新增 StartLimitIntervalSec/Burst |
| `sudoers`（生产服务器） | 不变 | 已含 freeark-screen-heartbeat |

---

## 6. 风险与缓解

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| paho 版本不兼容 wss API | 中 | 开发前确认生产 paho 版本（pip show paho-mqtt），必要时 `pip install 'paho-mqtt>=1.6.1,<2.0'` 固定 |
| wss TLS 证书验证失败 | 中 | 确认 broker CA 是否受信任；若自签，需提供 CA 证书路径并在配置文件中增加 `ca_certs` 字段 |
| 配置文件写入权限问题 | 低 | Django 进程以 yangyang 用户运行，文件 owner=yangyang 即可写入 |
| 原子写失败（磁盘满） | 低 | 临时文件 + rename 策略；磁盘满时保留原配置文件不变 |

---

*文档状态：DRAFT。请用户确认后进入模块设计阶段。*
