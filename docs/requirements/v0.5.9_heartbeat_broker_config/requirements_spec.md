# 需求规格说明书

**版本**：v0.5.9-heartbeat-broker-config  
**日期**：2026-05-23  
**状态**：DRAFT — 待用户 CONFIRM  
**作者**：SDLC Requirement Analyst (sub_agent_requirement_analyst)  
**项目**：FreeArk 大屏心跳服务 — 消息中间件地址 Web 可配置

---

## 1. 背景与现状

### 1.1 现状摘要（基于代码分析）

| 维度 | 当前状态 |
|------|---------|
| 服务文件 | `FreeArkWeb/backend/freearkweb/api/management/commands/screen_heartbeat_consumer.py` |
| 硬编码常量 | `MQTT_HOST = '47.117.41.184'`、`MQTT_PORT = 11883`、`MQTT_USERNAME = 'admin'`、`MQTT_PASSWORD = 'public'` |
| 传输协议 | 仅 TCP (`mqtt.Client()`，无 TLS/WSS) |
| systemd 单元 | `systemctl/freeark-screen-heartbeat.service`，User=yangyang，Restart=on-failure，RestartSec=30s |
| 配置机制 | 无；所有连接参数硬编码在源文件模块级常量中 |
| 已有服务管理 API | `POST /api/services/<name>/action/`，支持 start/stop/restart，白名单含 `freeark-screen-heartbeat` |
| 已有 mqtt_config.json | 存在于 `FreeArkWeb/backend/mqtt_config.json`（用于 PLC consumer），但 heartbeat consumer 完全不读取该文件 |

### 1.2 新增需求来源

用户明确要求：
- 新增 broker 地址 `wss://www.ttqingjiao.site:8084`（WebSocket over TLS）。
- 通过 Web 界面配置「消息中间件地址」，字段含协议、host、port、path（wss 用）、client_id、username、password、topic。
- 保存配置后重启 `freeark-screen-heartbeat` 服务使其生效。
- 报文解析逻辑不变（只切换传输层）。
- 旧地址 47.x.x.x 仍可作为合法配置项继续工作，不做强制迁移。

---

## 2. 范围

### 2.1 包含（In Scope）

- REQ-FUNC-001：新建 `heartbeat_broker_config.json` 配置文件，存储 heartbeat consumer 的 broker 连接参数，支持 `mqtt`（TCP）和 `wss`（WebSocket over TLS）两种协议。
- REQ-FUNC-002：后端新增「心跳 Broker 配置」读取/写入 API（GET + PUT，需 admin 角色）。
- REQ-FUNC-003：前端「服务管理」页面或独立「系统设置」子页面新增「心跳消息中间件配置」表单，支持协议下拉切换、字段联动显示（wss 时显示 path 字段）。
- REQ-FUNC-004：保存配置后，后端 API 持久化 JSON 文件，并通过 `sudo systemctl restart freeark-screen-heartbeat` 触发服务重启。
- REQ-FUNC-005：`screen_heartbeat_consumer.py` 启动时从配置文件读取连接参数，不再使用硬编码常量；支持 `mqtt` 和 `wss` 两种传输模式，使用 paho-mqtt 的对应初始化方式。
- REQ-FUNC-006：配置错误时（broker 连不上），心跳 consumer 应记录错误日志，不进入 crash-loop（依托已有 `Restart=on-failure` + `RestartSec=30s` 的 systemd 配置，不在进程内无限重试连接）；Web 端显示当前服务状态以供观测。
- REQ-NFUNC-001：权限安全 — 配置写入和服务重启接口仅 admin 角色可调用；systemd restart 通过已有 `sudoers` 白名单执行，不暴露任意命令注入面。
- REQ-NFUNC-002：兼容性 — 旧地址 `47.117.41.184:11883`（mqtt 协议）必须可作为合法值填入并继续工作；配置迁移路径为手动填写，无自动迁移。
- REQ-NFUNC-003：可观测性 — heartbeat consumer 在连接成功/失败时均产生日志，配置文件路径、协议类型、host 在启动日志中可见。
- REQ-NFUNC-004：配置文件格式稳定 — JSON，字段名固定，避免版本升级后格式不兼容。

### 2.2 不包含（Out of Scope）

- 不修改消息解析逻辑（topic 格式、MAC 解析、`_upsert_last_seen` 均不变）。
- 不修改 `freeark-mqtt-consumer`（PLC consumer）的配置，二者配置文件独立。
- 不支持多 broker 同时订阅（单配置单连接）。
- 不做配置项的历史版本管理（无回滚至上一次配置的功能）。
- 不做 TLS 客户端证书认证（服务端证书验证默认 enabled，但不要求客户端证书）。
- 不做自动检测 broker 连通性的健康检查端点（观测手段为 ServicesView 现有服务状态展示 + systemd journal 日志）。

### 2.3 约束

| 约束 | 说明 |
|------|------|
| 技术栈锁定 | Python 3.11 + Django 5.2 + paho-mqtt >= 1.6.1，前端 Vue 3 + Element Plus |
| 生产环境 | 树莓派，systemd 部署，User=yangyang，已有 sudoers 白名单用于 service 操作 |
| 不停机迁移 | 配置文件变更后需重启服务；重启期间（≤30s RestartSec）心跳短暂中断可接受 |
| 无 HTTPS | 当前后端以 HTTP 运行，API 调用不加密；配置文件含 broker 密码，文件权限须收紧（chmod 600） |

---

## 3. 功能需求详细说明

### REQ-FUNC-001 配置文件

- **文件路径**：`FreeArkWeb/backend/heartbeat_broker_config.json`（与 `mqtt_config.json` 同级，便于 DevOps 统一管理）。
- **字段定义**：

```json
{
  "protocol": "mqtt",           // 枚举: "mqtt" | "wss"
  "host": "47.117.41.184",
  "port": 11883,
  "path": "/mqtt",              // 仅 wss 时有效；mqtt 时忽略
  "username": "admin",
  "password": "public",
  "topic": "/screen/upload/screen/to/cloud/#",
  "client_id": "freeark-screen-heartbeat",
  "keepalive": 60
}
```

- **初始值**：首次创建时默认填充当前硬编码值（即 mqtt + 47.117.41.184:11883），确保服务不中断。
- **文件权限**：`chmod 600`，Owner = yangyang（服务运行用户）。

### REQ-FUNC-002 后端 API

- `GET /api/heartbeat-broker-config/` — 读取当前配置，返回 JSON（password 字段 mask 为 `"***"` 或留空，前端展示不回显密码明文）。
  - 权限：IsAuthenticated（任意登录用户可读，便于运维人员查看）。
- `PUT /api/heartbeat-broker-config/` — 写入配置 + 触发 `sudo systemctl restart freeark-screen-heartbeat`。
  - 权限：IsAdminUser（role='admin'）。
  - 请求体：完整配置 JSON（password 若为空字符串则保留文件中的原值，避免前端每次都要传密码）。
  - 响应：`{ "success": true, "message": "配置已保存，服务重启中" }` 或错误信息。
  - 写入成功但 restart 失败时：返回 `{ "success": false, "error": "配置已保存，但服务重启失败: <reason>" }`（配置文件已落盘，用户可手动重启）。

### REQ-FUNC-003 前端配置页

- 挂载在「服务管理」子菜单下，新路由 `/services/heartbeat-config`，或复用现有服务管理页（以 Tab 或展开面板形式）。
- 表单字段：
  - 协议（el-select，选项：mqtt / wss）
  - Host（el-input，必填）
  - Port（el-input number，必填，范围 1-65535）
  - Path（el-input，仅 protocol=wss 时显示，默认 `/mqtt`）
  - Username（el-input）
  - Password（el-input，type=password，placeholder=「留空则不修改」）
  - Topic（el-input，必填）
  - Client ID（el-input）
  - Keepalive（el-input number，单位秒）
- 「保存并重启服务」按钮，弹出确认对话框后提交。
- 保存成功后显示成功提示，3 秒后可再次编辑。

### REQ-FUNC-004 服务重启触发

- 后端 PUT 接口在写入配置文件成功后，调用 `subprocess.run(['sudo', 'systemctl', 'restart', 'freeark-screen-heartbeat'], ...)` 触发重启，超时 30s。
- 此路径复用已有 `service_management_action` 视图中的 `sudo systemctl` 调用模式，无需修改 sudoers（`freeark-screen-heartbeat` 已在白名单中）。

### REQ-FUNC-005 Consumer 启动配置读取

- `screen_heartbeat_consumer.py` 在 `handle()` 入口处调用 `_load_heartbeat_config()` 函数，从 `heartbeat_broker_config.json` 读取配置。
- 若文件不存在或解析失败，降级使用内嵌 fallback 常量（现有硬编码值），并记录 WARNING 日志。
- 根据 `protocol` 字段选择 paho 初始化方式：
  - `"mqtt"` → `mqtt.Client(transport="tcp")`，调用 `client.connect(host, port, keepalive)`。
  - `"wss"` → `mqtt.Client(transport="websockets")`，设置 `client.tls_set()`，调用 `client.connect(host, port, keepalive)`（path 通过 `client.ws_set_options(path=path)` 设置）。

### REQ-FUNC-006 错误回退与可观测性

- `on_connect` 回调中 rc != 0 时记录 WARNING，不主动 sys.exit。
- paho 的 `loop_forever(retry_first_connection=True)` 已内置重连逻辑，加上 systemd `Restart=on-failure`，不会永久停止。
- 需增加 `StartLimitIntervalSec=300`、`StartLimitBurst=5` 在 service 文件中（防止配置持续错误导致无限重启耗尽系统资源）。

---

## 4. 非功能需求

| 编号 | 类型 | 描述 |
|------|------|------|
| REQ-NFUNC-001 | 安全 | 配置写接口仅 admin 可调；sudo 白名单已含该服务，不扩大权限面 |
| REQ-NFUNC-002 | 兼容 | 旧 mqtt+47.x.x.x 配置合法，无强制迁移 |
| REQ-NFUNC-003 | 可观测 | 启动/连接失败日志写入 journal（StandardOutput=journal 已配置） |
| REQ-NFUNC-004 | 稳定性 | StartLimitBurst=5 / 300s 防 crash-loop 滥用 |
| REQ-NFUNC-005 | 配置文件安全 | chmod 600，避免其他进程读取 broker 密码 |

---

## 5. 开放问题（待确认事项）

- **OQ-001**：paho-mqtt `ws_set_options(path=...)` 在 paho >= 1.6.1 可用，但 paho 2.x API 有变化（`CallbackAPIVersion`）；需确认生产树莓派上 paho 实际版本（`pip show paho-mqtt`），以确定是否需要升级或做版本兼容分支。
- **OQ-002**：wss broker `www.ttqingjiao.site:8084` 的服务端 TLS 证书是否由受信任 CA 签发（Let's Encrypt 等）？若是自签，paho TLS 需 `tls_set(ca_certs=...)` 并提供 CA 证书路径。若是受信任 CA，则 `tls_set()` 无参数即可。
- **OQ-003**：前端新配置页挂载位置——优先选项 A：服务管理页内新 Tab；选项 B：独立子路由 `/services/heartbeat-config`。请用户确认偏好。
- **OQ-004**：password 字段前端回显策略——读取时后端 mask 为空字符串，前端以 placeholder 提示「留空则不修改」，PUT 时若 password 为空则沿用文件中原值。此行为是否符合预期？

---

*文档状态：DRAFT。请用户确认后进入架构设计阶段。*
