# 用户故事

**版本**：v0.5.9-heartbeat-broker-config  
**日期**：2026-05-23  
**状态**：DRAFT — 待用户 CONFIRM  
**作者**：SDLC Requirement Analyst (sub_agent_requirement_analyst)

---

## 角色定义

- **运维管理员（Admin）**：拥有系统 admin 角色的登录用户，负责配置消息中间件地址并触发服务重启。
- **普通用户（User）**：只读权限，可查看服务状态但不能修改配置。
- **心跳消费者（Service）**：`freeark-screen-heartbeat` systemd 服务进程，被动读取配置文件。

---

## US-HBC-001：查看当前心跳 Broker 配置

**作为**运维管理员，  
**我想要**在 Web 界面查看当前 `freeark-screen-heartbeat` 服务使用的消息中间件地址（协议、host、port、topic 等），  
**以便**了解服务当前的连接目标，在排查心跳异常时快速定位 broker 信息。

### 验收标准

**Given** 运维管理员已登录系统，  
**When** 进入「心跳 Broker 配置」页面（服务管理 > 心跳中间件配置），  
**Then** 页面加载后展示当前配置的协议、host、port、path（若协议为 wss）、topic、client_id、keepalive，password 字段显示为空（不回显明文）。

**Given** 配置文件不存在（首次部署前），  
**When** 进入配置页面，  
**Then** 页面展示默认值（protocol=mqtt, host=47.117.41.184, port=11883），并提示「当前为默认配置，请确认后保存」。

---

## US-HBC-002：编辑并保存心跳 Broker 配置

**作为**运维管理员，  
**我想要**编辑心跳服务的消息中间件地址并一键保存，  
**以便**将 broker 从旧地址切换到新地址而无需登录服务器手工改文件。

### 验收标准

**Given** 运维管理员在配置页面，  
**When** 修改 host/port 字段后点击「保存并重启服务」，  
**Then** 后端将配置持久化至 `heartbeat_broker_config.json`，API 返回成功，前端显示「配置已保存，服务重启中」。

**Given** Host 字段为空，  
**When** 点击保存，  
**Then** 前端校验失败，显示「Host 不能为空」，请求不发送。

**Given** Port 字段超出 1-65535 范围，  
**When** 点击保存，  
**Then** 前端校验失败，显示「端口号范围：1-65535」，请求不发送。

---

## US-HBC-003：协议切换（mqtt vs wss）

**作为**运维管理员，  
**我想要**通过下拉菜单切换协议为 `mqtt`（TCP）或 `wss`（WebSocket over TLS），  
**以便**连接不同类型的 broker，例如将当前 mqtt 连接切换至 `wss://www.ttqingjiao.site:8084`。

### 验收标准

**Given** 协议下拉选择 `wss`，  
**When** 切换完成，  
**Then** 表单显示「Path」字段（默认值 `/mqtt`），Port 默认填充 8084（或保留用户上次填写值）。

**Given** 协议下拉选择 `mqtt`，  
**When** 切换完成，  
**Then** 「Path」字段隐藏，Port 默认填充 1883（或保留用户上次填写值）。

**Given** 选择 wss + host=www.ttqingjiao.site + port=8084 + path=/mqtt，  
**When** 保存并重启，  
**Then** consumer 重启后使用 paho WebSocket 传输连接至该 broker，订阅相同 topic，心跳写入功能正常。

---

## US-HBC-004：重启服务生效

**作为**运维管理员，  
**我想要**保存配置后系统自动重启 `freeark-screen-heartbeat` 服务，  
**以便**新配置立即生效，无需我手动 SSH 到服务器执行 `systemctl restart`。

### 验收标准

**Given** 运维管理员提交有效配置，  
**When** 后端写入配置文件成功，  
**Then** 后端调用 `sudo systemctl restart freeark-screen-heartbeat`，该命令在 sudoers 白名单内，不需要密码。

**Given** `systemctl restart` 执行成功（returncode=0），  
**When** API 响应返回，  
**Then** 响应为 `{ "success": true, "message": "配置已保存，服务重启中" }`，HTTP 200。

**Given** `systemctl restart` 执行失败（超时或非零 returncode），  
**When** API 响应返回，  
**Then** 响应为 `{ "success": false, "error": "配置已保存，但服务重启失败: <原因>" }`，HTTP 500；前端提示用户手动重启。

**Given** 运维管理员在确认弹窗点击「取消」，  
**When** 弹窗关闭，  
**Then** 不提交请求，不发生任何变更。

---

## US-HBC-005：配置错误时的回退与可观测性

**作为**运维管理员，  
**我想要**在 broker 地址填写错误（连不上）时，服务不会无限 crash-loop 耗尽系统资源，并且我能通过 Web 界面观察到服务状态，  
**以便**及时发现并纠正错配置。

### 验收标准

**Given** 配置了无法连通的 broker 地址，  
**When** `freeark-screen-heartbeat` 重启后尝试连接，  
**Then** paho 记录连接失败日志（WARNING 级），由 systemd `Restart=on-failure` 在 30s 后重试；但 `StartLimitBurst=5/300s` 限制后服务进入 failed 状态，不无限重启。

**Given** 服务进入 failed 状态，  
**When** 运维管理员访问「服务管理」页面，  
**Then** `freeark-screen-heartbeat` 的 `active_state` 显示 `failed`（红色标签），管理员可通过修正配置后手动重启服务。

**Given** 配置文件不存在（意外删除），  
**When** `screen_heartbeat_consumer` 启动，  
**Then** 降级使用内嵌 fallback 常量（mqtt/47.117.41.184/11883），记录 WARNING 日志「配置文件未找到，使用默认配置」，服务正常启动。

---

## US-HBC-006：权限校验

**作为**系统安全架构，  
**我想要**配置写入和服务重启仅允许 admin 角色调用，  
**以便**普通用户无法随意变更 broker 配置或触发服务重启。

### 验收标准

**Given** 普通用户（role=user）已登录，  
**When** 调用 `PUT /api/heartbeat-broker-config/`，  
**Then** 返回 HTTP 403，响应体含 `{ "detail": "权限不足" }`；配置文件不变，服务不重启。

**Given** 未登录用户，  
**When** 调用 `GET /api/heartbeat-broker-config/` 或 `PUT /api/heartbeat-broker-config/`，  
**Then** 返回 HTTP 401。

**Given** admin 用户在前端配置页填写 broker 地址，  
**When** 提交包含注入字符（如 `; rm -rf /`）的 host 字段，  
**Then** 后端校验 host 字段（正则白名单：域名/IPv4），拒绝请求返回 HTTP 400；`systemctl` 不被调用。

---

## US-HBC-007：旧地址兼容

**作为**运维管理员，  
**我想要**能够将配置恢复为旧的 47.117.41.184:11883（mqtt 协议），  
**以便**在新 broker 出现问题时快速回退到旧地址，无需重新部署代码。

### 验收标准

**Given** 当前配置为 wss/www.ttqingjiao.site/8084，  
**When** 管理员将表单改回 mqtt/47.117.41.184/11883 并保存，  
**Then** 配置文件更新，服务重启后以 mqtt TCP 连接旧 broker，心跳消费功能正常。

**Given** 配置为 mqtt + 47.117.41.184:11883，  
**When** consumer 启动，  
**Then** paho 使用 `transport="tcp"` 初始化，行为与改造前完全一致。

---

*文档状态：DRAFT。请用户确认后进入架构设计阶段。*
