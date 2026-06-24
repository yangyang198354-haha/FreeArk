# 需求规格说明书 — v1.5.0 微信小程序移动端

**文档编号**: REQ-SPEC-MP-v150-001
**项目名称**: FreeArk 微信小程序移动端（v1.5.0_wechat_miniprogram）
**版本**: 1.1.0
**状态**: APPROVED（2026-06-23 用户确认架构阶段拍板决策，OQ 已关闭）
**创建日期**: 2026-06-23
**作者**: requirement-analyst (via pm-orchestrator)
**来源锁定**: 用户简报（2026-06-23，已确认的关键约束不得推翻）

---

## 版本历史

| 版本  | 日期       | 变更摘要                             |
|-------|------------|--------------------------------------|
| 1.0.0 | 2026-06-23 | 初始草稿，基于用户锁定简报与现有路由表盘点 |
| 1.1.0 | 2026-06-23 | 架构阶段回写：关闭 OQ-01/02/03/04/05/06/07/08/09；US-14 提为首期 P1；附录 A/B 更新 |

---

## 0. 问题陈述

### 0.1 背景现状

FreeArk（自由方舟）是已上线的三恒系统（恒温/恒湿/恒氧）监控运维 Web 应用，单人维护。现有前端为 Vue 3 + Vue Router + Element Plus + ECharts/Chart.js + MQTT.js 的桌面 Web，部署在树莓派（aarch64），生产数据库 MySQL（192.168.31.51）。

运维人员有移动端访问需求：在现场或非桌面场景下，需要随时查看设备状态、故障告警、能耗数据，并能通过 AI 问答快速定位问题。现有桌面 Web 在手机端体验极差，不适合现场触屏操作。

### 0.2 本版本目标

1. 以**微信小程序**为首发目标，采用 **uni-app（Vue 系）** 一套代码多端框架，首期上线微信小程序，后续可同源编译 H5 / App。
2. **复用现有 Django 后端 API**，尽量不新增/少改后端接口。
3. 覆盖移动高频功能（首期 MVP）：登录、综合看板、设备与房间监控、故障与结露预警查看、能耗报表查看、AI 问答。
4. 管理员与普通用户在移动端页面可见性上有明确区分。
5. 建立技术选型、鉴权策略、实时数据方案、后端适配清单等基础决策，为架构设计阶段提供输入。

---

## 1. 范围与边界

### 1.1 首期（MVP）纳入范围

| 编号 | 功能域 | 页面/功能摘要 | 目标用户 |
|------|--------|---------------|----------|
| REQ-FUNC-MP-01 | 鉴权 | 账号密码登录、登出、持久化 Token | 全部 |
| REQ-FUNC-MP-02 | 首页综合看板 | 关键指标概览卡片（在线 PLC 数、当前告警数、今日能耗） | 全部 |
| REQ-FUNC-MP-03 | 监控 — PLC 在线率 | PLC 状态列表（在线/离线/异常），可下拉刷新 | 全部 |
| REQ-FUNC-MP-04 | 监控 — 设备卡片 | 按房间/部件分组的设备卡片列表，显示核心参数 | 全部 |
| REQ-FUNC-MP-05 | 监控 — 设备参数历史 | 指定设备的参数趋势折线图（近 1h/24h/7d） | 全部 |
| REQ-FUNC-MP-06 | 监控 — 房间历史 | 指定房间温湿氧历史趋势图 | 全部 |
| REQ-FUNC-MP-07 | 故障管理 — 查看 | 故障列表（含状态筛选、房间筛选），只读查看 | 全部 |
| REQ-FUNC-MP-08 | 结露预警 — 查看 | 结露预警列表，只读查看 | 全部 |
| REQ-FUNC-MP-09 | 能耗 — 用量查询 | 用量查询（时间范围、设备维度） | 全部 |
| REQ-FUNC-MP-10 | 能耗 — 日报/月报 | 能耗日报与月报（只读，图表 + 数据表格） | 全部 |
| REQ-FUNC-MP-11 | AI 问答 | 方舟龙虾/三恒专家多专家聊天，含会话历史列表 | 全部 |
| REQ-FUNC-MP-12 | 巡检工单 — 查看 | 巡检工单列表（运维只读；管理员可审批） | 全部 |
| REQ-FUNC-MP-13 | 巡检工单 — 管理员审批 | 管理员在移动端审批/拒绝巡检工单中的 PLC 写提案 | 管理员 |
| REQ-FUNC-MP-14 | 个人中心 — 改密 | 修改自己的密码 | 全部 |

### 1.2 后期（二期/不纳入首期）

| 功能 | 不纳入首期的原因 |
|------|----------------|
| 用户管理（创建/编辑/删除用户） | 管理重度，桌面端操作；移动场景价值低；增删用户等危险操作不适合触屏误触 |
| 业主管理 | 同上，管理重度 |
| 三恒知识库管理（文档上传） | 上传大文件（≤50MB PDF/DOCX）在小程序端有技术限制（uploadFile 域名白名单、文件选择 API 限制）；且仅管理员使用，移动场景极少触发 |
| PLC 参数写入（设备参数设置） | 安全合规敏感：PLC 写操作含工单审批门控，移动端误触风险高；建议保留在桌面端作为受控操作环境 |
| 设置审计记录（PlcWriteRecord） | 桌面管理场景，移动端意义有限；数据量大，分页复杂 |
| 服务状态管理（ServicesView） | DevOps 管理场景，不适合移动端 |
| 部件详情（SpecificPartDetailView） | 参数项过多，移动端表格适配成本高；可在二期结合设备卡片点击进入 |
| 微信登录（OAuth 打通） | 需后端实现 code→openid→FreeArk 账号绑定流程，架构复杂；首期用账号密码登录 + Token 复用 |

> **取舍说明**：巡检工单审批（REQ-FUNC-MP-13）纳入首期，原因是管理员在现场巡检结束后需要移动端快速审批/拒绝写提案，等回到桌面端审批时效性差。其余写操作均因安全合规和误触风险暂缓。

---

## 2. 功能需求详述

### 2.1 FR-MP-01 账号密码登录与会话管理

**来源**：用户简报约束4；现有后端 `/api/auth/login/` 端点。

- 小程序启动时读取本地 Storage 中的 `userToken` 和 `userInfo`。
- 若 Token 有效（本地存在），直接进入首页；否则跳转登录页。
- 登录请求调用 `POST /api/auth/login/`，成功后将 `token`、`user_info`（含 `role` 字段）持久化到本地 Storage。
- 登出清空本地 Storage，跳转登录页。
- 鉴权逻辑：管理员 = `userInfo.role === 'admin'`（与现有 Web 端路由守卫逻辑一致）。
- 所有 API 请求携带 `Authorization: Token {token}` 请求头。
- `/api/auth/me/` 不返回 `is_staff`，不得使用 `is_staff` 做任何移动端权限判断。

**验收标准**：见 user_stories.md US-01。

---

### 2.2 FR-MP-02 首页综合看板

**来源**：现有 HomeView（v1.0.0 已重做）。

- 展示核心摘要指标卡片：
  - 在线 PLC 数 / 总 PLC 数
  - 当前活跃故障数
  - 当前结露预警数
  - 今日总能耗（kWh）
- 快捷入口卡片：故障列表、结露预警、AI 问答、设备卡片。
- 支持下拉刷新（uni-app `onPullDownRefresh`）。
- 小程序看板不需复制桌面端的全量 ECharts 大图，以数字卡片 + 文字状态为主，减少渲染负担。

**验收标准**：见 user_stories.md US-02。

---

### 2.3 FR-MP-03 PLC 状态列表

**来源**：现有 PlcStatusView；调用 `/api/plc-status/`（或等效端点）。

- 列表展示所有 PLC 的编号、名称、在线状态（在线/离线/异常），颜色标签区分。
- 支持下拉刷新。
- 离线 PLC 数量 > 0 时，列表顶部显示醒目提示横幅。

**验收标准**：见 user_stories.md US-03。

---

### 2.4 FR-MP-04 设备卡片列表

**来源**：现有 DeviceCardsView；调用 `/api/device-cards/`（或等效端点，接受 `specific_part` 查询参数）。

- 支持按房间/设备类型筛选。
- 每个卡片显示：设备名称、核心参数（温度/湿度/氧气浓度等）、最后更新时间。
- 点击卡片可导航至该设备的参数历史页（REQ-FUNC-MP-05）。

**验收标准**：见 user_stories.md US-04。

---

### 2.5 FR-MP-05 设备参数历史趋势图

**来源**：现有 DeviceParamHistoryView；调用历史数据接口（含 `specific_part`、`sub_type` 参数）。

- 使用 uni-app 兼容的图表库（推荐 uCharts 或 ECharts for uni-app），展示参数趋势折线图。
- 时间范围：近 1 小时 / 近 24 小时 / 近 7 天，切换 Tab。
- 手机屏宽适配：单图全宽展示，支持横向滚动图表（若数据点密集）。

**验收标准**：见 user_stories.md US-05。

---

### 2.6 FR-MP-06 房间历史趋势图

**来源**：现有 RoomHistoryView。

- 展示指定房间的温度/湿度/氧气浓度历史折线图，时间范围同上。
- 与 FR-MP-05 共用趋势图组件。

**验收标准**：见 user_stories.md US-06。

---

### 2.7 FR-MP-07 故障管理 — 只读查看

**来源**：现有 FaultManagementView（v0.6.x 系列已迭代完善）。

- 故障列表展示：故障描述、发生时间、所在房间、状态（未解决/已解决）。
- 支持按状态（未解决/已解决/全部）、按房间筛选，支持分页（下拉加载更多）。
- 无故障处理（确认/关闭）操作——首期只读；写操作保留在桌面端。
- 结合 REQ-FUNC-MP-02 首页跳转：首页故障数字卡片点击进入故障列表。

**验收标准**：见 user_stories.md US-07。

---

### 2.8 FR-MP-08 结露预警 — 只读查看

**来源**：现有 CondensationWarningView（v0.7.0）。

- 展示结露预警列表：位置、预警时间、当前状态。
- 支持下拉刷新，支持分页。
- 首页结露预警数字卡片点击进入。

**验收标准**：见 user_stories.md US-08。

---

### 2.9 FR-MP-09 能耗用量查询

**来源**：现有 UsageQueryView；调用 `/api/usage-data/`。

- 支持选择时间范围（日/周/月），展示能耗数据表格（分设备类型）。
- 简单柱状图展示汇总趋势（可选，复杂度评估后决定）。

**验收标准**：见 user_stories.md US-09。

---

### 2.10 FR-MP-10 能耗日报/月报

**来源**：现有 DailyUsageReportView、MonthlyUsageReportView。

- 日报：选择日期，展示当日各设备能耗明细。
- 月报：选择年月，展示各设备月度汇总，图表（柱状图）+ 数据表。
- 只读，无导出功能（首期不纳入）。

**验收标准**：见 user_stories.md US-10。

---

### 2.11 FR-MP-11 AI 问答（方舟龙虾 + 三恒专家）

**来源**：现有 ChatView；调用 `/api/langgraph_chat/`（WebSocket 流式）和 `/api/memory/me/`、`/api/memory/session/{key}/history/`。

- 展示会话历史列表（最近 N 条）。
- 选择会话或新建会话，进入聊天界面。
- 消息流式接收（SSE 或 WebSocket，小程序 WebSocket API 可用，见 NFR-MP-05）。
- 多专家选择（方舟龙虾/三恒专家）。
- 消息气泡展示，支持 Markdown 渲染（基础格式：标题/列表/粗体/代码块）。
- 发送文字消息。

**验收标准**：见 user_stories.md US-11。

---

### 2.12 FR-MP-12/13 巡检工单查看与审批

**来源**：现有 WorkOrderListView（v1.3.x）。

- 所有用户可见工单列表（状态/时间过滤）。
- 管理员额外可见审批按钮（批准/拒绝），调用现有审批 API。
- 非管理员用户审批操作隐藏（依据 `userInfo.role`）。

**验收标准**：见 user_stories.md US-12。

---

### 2.13 FR-MP-14 个人中心 — 修改密码

**来源**：现有 ChangePasswordView；调用改密 API。

- 页面：旧密码、新密码、确认新密码，提交后提示成功/失败。

**验收标准**：见 user_stories.md US-13。

---

## 3. 非功能需求

### 3.1 NFR-MP-01 技术选型约束

- **框架**：uni-app（Vue 3 + Composition API），首发微信小程序，后续可编译 H5/App。
- **图表库**：uCharts 或 ECharts for uni-app（两者均原生支持小程序画布，避免 DOM 依赖）。
- **UI 组件库**：uni-ui 或 wot-design-uni（轻量，兼容小程序）；不得引用 Element Plus（依赖 DOM，在小程序环境不可用）。
- **状态管理**：Pinia（Vue 3 官方推荐，uni-app 支持）。
- **后端**：复用现有 Django REST Framework，不新建独立移动端服务。

### 3.2 NFR-MP-02 平台合规约束（微信小程序强制要求）

- **HTTPS 合法域名**：小程序的 `wx.request`、`wx.connectSocket`（WebSocket）所有请求域名必须在微信公众平台「服务器域名」白名单中配置，且必须为 HTTPS（request）/ WSS（socket）合法域名。
- 现有生产地址（花生壳动态域名 + 非标端口）**无法直接用于小程序**；用户须另行准备已 ICP 备案 + HTTPS:443 的固定合法域名（详见第 6 节外部依赖）。
- 小程序代码包大小：主包 ≤ 2MB，总包（分包）≤ 20MB。图表库、资源须控制体积，必要时按功能分包。
- 微信小程序禁止动态执行代码（无 `eval`、`new Function`）；Markdown 渲染须使用静态解析方案。

### 3.3 NFR-MP-03 性能要求

- 首页综合看板冷启动数据加载 ≤ 3 秒（从进入页面到数据展示完毕，4G 网络）。
- 列表页（故障/工单）每页 ≤ 20 条，分页加载，单次请求响应 ≤ 2 秒。
- 图表页（设备历史/房间历史）图表渲染 ≤ 2 秒（数据到位后）。
- 小程序总包大小 ≤ 8MB（含分包）。

### 3.4 NFR-MP-04 安全要求

- Token 存储于微信小程序 `wx.setStorageSync`（本地加密存储，不存 Cookie）。
- 所有 API 请求必须携带 `Authorization: Token {token}` 请求头。
- 管理员敏感操作（工单审批）须在请求前于客户端二次确认（`wx.showModal` 确认弹窗）。
- 不在前端存储明文密码；密码字段传输全程 HTTPS。
- `userInfo.role` 仅用于控制 UI 可见性，后端鉴权仍以服务端 Token + 角色校验为准。

### 3.5 NFR-MP-05 实时数据与 WebSocket 约束

小程序 WebSocket（`wx.connectSocket`）限制：
- 同时最多 **2 个并发 WebSocket 连接**（微信平台限制）。
- 小程序进入**后台 5 秒后**，未完成的 WebSocket 连接可能被挂起或断开。
- **首期处理策略**：
  - AI 问答流式输出使用 WebSocket（与现有后端 ASGI WebSocket 协议对接），占用 1 个连接。
  - 设备实时数据（MQTT/WebSocket）**降级为轮询**（每 30 秒刷新一次），不与 AI 问答争抢 WebSocket 连接数。
  - 用户离开页面（`onHide` / `onUnload`）时主动断开 WebSocket 连接，避免后台挂起。
- 若后续需要真正的实时数据推送，可在二期评估 MQTT over WebSocket 方案，并争取微信「长连接」使用资格。

### 3.6 NFR-MP-06 可访问性与国际化

- 本期仅支持中文界面，不做国际化。
- 支持 iOS 和 Android 微信客户端，目标微信版本 ≥ 8.0。
- 最小触控目标尺寸 ≥ 44×44px（符合触屏无障碍基准）。

### 3.7 NFR-MP-07 部署约束

- 后端：禁止 Docker，物理机部署，树莓派 Pi（aarch64）。
- 小程序客户端代码由微信开发者工具打包，通过微信小程序管理后台发布审核；无需修改树莓派部署流程。
- 后端适配改动一律通过 `git pull + 重启服务` 部署（禁止 pscp 逐文件上传）。

---

## 4. 约束、外部依赖与假设

### 4.1 外部前置依赖（小程序上线前必须就绪，不在本期开发交付范围内）

| 编号 | 依赖项 | 说明 | 负责方 |
|------|--------|------|--------|
| DEP-01 | 合法域名（ICP 备案） | 需一个已完成 ICP 备案的固定域名（如 `freeark.example.com`），用于小程序合法域名白名单配置 | 用户自行准备 |
| DEP-02 | HTTPS:443 SSL 证书 | 在合法域名上配置有效 SSL 证书（推荐 Let's Encrypt），并将 Waitress 或前置 Nginx 绑定到 443 端口 | 用户自行准备 |
| DEP-03 | 微信小程序 AppID | 在微信公众平台注册小程序，获取 AppID + AppSecret | 用户自行准备 |
| DEP-04 | 微信公众平台服务器域名白名单 | 将合法域名加入 request 合法域名（HTTPS）和 socket 合法域名（WSS） | 用户自行准备 |
| DEP-05 | 微信小程序审核通过 | 小程序上线需通过微信平台审核（一般 3~7 个工作日） | 用户自行准备 |

> **注意**：当前生产地址（花生壳动态域名 `et116374mm892.vicp.fun` + 非标端口 `57279`）**不满足**微信小程序合法域名要求（必须 443 端口 + ICP 备案）。在 DEP-01 至 DEP-04 就绪前，小程序只能在微信开发者工具「不校验合法域名」模式下本地联调，**不可上线**。

### 4.2 已确认的系统约束

| 编号 | 约束描述 | 来源 |
|------|----------|------|
| CON-01 | 首期**不做微信登录（OAuth）**，使用账号密码 + Token 方案 | 用户简报，首期不引入微信账号绑定流程 |
| CON-02 | 首期**不做故障主动推送**（服务号模板消息/企业微信等旁路方案不在本期范围） | 用户简报约束1 |
| CON-03 | PLC 写操作（设备参数设置）**不在首期小程序中实现** | 安全合规与误触风险 |
| CON-04 | 鉴权模型：`userInfo.role === 'admin'` 为管理员，不使用 `is_staff` | 用户简报约束4 |
| CON-05 | 移动端实时数据首期**降级为轮询**（≤2 个 WebSocket 并发限制） | 用户简报约束5 + 微信平台限制 |
| CON-06 | 后端禁止 Docker，物理机 git pull 部署 | 基础设施约束 |

---

## 5. 后端适配需求清单

以下为小程序访问现有后端时需要评估或改动的后端内容，供架构阶段详细设计。

### 5.1 必须适配（阻塞性）

| 编号 | 后端适配项 | 说明 | 优先级 |
|------|-----------|------|--------|
| BA-01 | **CORS 配置**：允许小程序来源 | 微信小程序 HTTP 请求时 Origin 为 `https://servicewechat.com`（或空），需确认现有 `django-cors-headers` 配置能允许此来源，或配置 `CORS_ALLOW_ALL_ORIGINS=True`（仅限内网场景评估） | P0 |
| BA-02 | **CSRF 豁免**：Token 认证请求不需要 CSRF Cookie | 小程序无 Cookie，现有 Token 认证（`Authorization: Token xxx`）已默认豁免 CSRF，需验证所有小程序将调用的端点均已正确配置 `@csrf_exempt` 或使用 DRF SessionAuthentication 以外的认证方式 | P0 |
| BA-03 | **HTTPS + 合法域名**：后端绑定到 443 端口，域名一致 | 依赖 DEP-01/DEP-02；需在 Waitress 前加 Nginx 反向代理处理 SSL 终止（Waitress 不直接处理 HTTPS 更稳定），并更新 `ALLOWED_HOSTS`、`CSRF_TRUSTED_ORIGINS` | P0，但属外部依赖 |
| BA-04 | **WebSocket 合法域名**：AI 问答 WebSocket 端点走 WSS** | 小程序 `wx.connectSocket` 只允许 WSS 协议；ASGI WebSocket 需通过 Nginx 反代 + SSL 终止转为 WSS | P0，但属外部依赖 |

### 5.2 建议适配（提升体验）

| 编号 | 后端适配项 | 说明 | 优先级 |
|------|-----------|------|--------|
| BA-05 | **登录接口响应增强**：返回 `role` 字段 | 现有 `/api/auth/login/` 返回的 `user_info` 中已包含 `role` 字段（见现有适配指南），需确认生产接口实际返回，否则小程序无法在登录时确定管理员身份 | P1 |
| BA-06 | **Token 有效期**：评估 DRF Token 无过期策略的安全影响 | DRF 默认 Token 永不过期；移动端长期持有 Token，若设备丢失存在风险；建议评估是否引入 Token 过期或刷新机制（首期可维持现状，二期加强） | P1 |
| BA-07 | **分页参数统一**：确认列表端点支持 `page` + `page_size` 参数 | 小程序列表页使用下拉加载更多，需后端支持分页；检查故障列表、工单列表、能耗数据等端点是否已有分页参数 | P1 |
| BA-08 | **数据压缩**：开启 Gzip 响应压缩 | 移动端 4G 环境下，历史数据点响应体可能较大；Nginx 反代时开启 `gzip on` 可显著减少传输量 | P2 |

### 5.3 无需改动（复用现状）

- 现有 API 端点路径、参数格式、认证方式（Token）均可直接复用。
- 数据库（MySQL）、ASGI 服务（Daphne）、MQTT Broker 均无需改动。
- 权限模型（`IsAdminUser` 基于 `user.role`）无需改动。

---

## 6. 开放决策（OQ）—— 已关闭（2026-06-23 架构阶段用户拍板）

| 编号 | 问题 | 状态 | 决策结果 |
|------|------|------|---------|
| OQ-01 | **微信登录打通策略** | **CLOSED — 二期** | 首期账号密码 + Token；微信 OAuth/openid 绑定列入二期路线图，不纳入首期开发范围 |
| OQ-02 | **图表库选型** | **CLOSED — uCharts** | 选用 **uCharts**（轻量，压缩约 200KB，专为小程序 Canvas 适配；放主包，分包 A/C 均可使用） |
| OQ-03 | **实时数据刷新频率** | **CLOSED — 30 秒** | 设备/故障/PLC 状态等均采用 **30 秒轮询**；AI 问答独占 WebSocket（不轮询） |
| OQ-04 | **AI 问答协议** | **CLOSED — 已确认（代码读取）** | 经阅读 `api/consumers.py` 和 `api/langgraph_chat/adapter.py`，协议为 **纯 JSON WebSocket**（`/ws/chat/?token=xxx`），无 HTTP SSE 端点；uni-app 通过 `uni.connectSocket` 完全可复刻（见 ARCH-MP-v150-001 ADR-002） |
| OQ-05 | **工单审批纳入首期** | **CLOSED — 纳入首期 P1** | 巡检工单审批（REQ-FUNC-MP-13）纳入首期，管理员移动端可批准/拒绝工单 |
| OQ-06 | **巡检工作日志纳入首期** | **CLOSED — 纳入首期 P1** | 巡检工作日志（US-14）提为首期 P1，只读浏览，调用 `/api/inspection/logs/` |
| OQ-07 | **Markdown 渲染方案** | **CLOSED — towxml** | 选用 **towxml 3.x**（专为小程序，内置静态 Markdown 解析，无 eval，支持代码高亮）；放分包 B（仅 AI 问答页使用） |
| OQ-08 | **小程序分包策略** | **CLOSED — 采用分包** | 主包（登录+首页+个人中心）+ 分包A（监控图表）+ 分包B（AI问答+towxml）+ 分包C（能耗）+ 分包D（运维/工单/故障）；uCharts 放主包（避免重复打包）；总包目标 ≤ 8MB |
| OQ-09 | **服务器状态页** | **CLOSED — 不纳入** | 服务状态管理（ServicesView）不纳入小程序任何期次（DevOps 管理场景，SSH 是正确工具） |

---

## 7. 风险登记

| 编号 | 风险描述 | 影响等级 | 概率 | 缓解措施 |
|------|----------|---------|------|---------|
| RISK-01 | 合法域名/ICP 备案准备周期可能超过 3 个月，阻塞小程序上线 | 高 | 中 | 开发阶段使用「不校验合法域名」模式内网联调；备案并行推进 |
| RISK-02 | 微信平台政策变更导致 WebSocket 并发数或包体积限制收紧 | 中 | 低 | 架构设计时预留降级为轮询的能力；控制分包总大小 |
| RISK-03 | 树莓派 Pi 在小程序上线后请求量增加，MySQL 查询负荷增大 | 中 | 中 | 首期采用轮询（30s），限制并发连接数；生产监控 DB 查询 QPS |
| RISK-04 | uCharts 在某些 iOS 微信版本上渲染异常 | 低 | 低 | 开发阶段 iOS/Android 双端真机验证；备选 ECharts for uni-app |
| RISK-05 | 微信小程序审核周期（3~7 工作日）影响上线节奏 | 中 | 高（首次审核必经）| 提前准备隐私协议、用户协议、首页截图等审核材料 |
| RISK-06 | 单人维护，同时维护桌面 Web 与小程序代码 | 中 | 高 | uni-app 最大化复用 API 层代码；小程序不实现写操作，降低维护面 |

---

## 附录 A：功能分期汇总表

| 功能 | 首期（MVP） | 后期 | 不纳入小程序 |
|------|:-----------:|:----:|:------------:|
| 账号密码登录/登出 | ✓ | | |
| 首页综合看板 | ✓ | | |
| PLC 状态列表 | ✓ | | |
| 设备卡片列表 | ✓ | | |
| 设备参数历史趋势图 | ✓ | | |
| 房间历史趋势图 | ✓ | | |
| 故障管理（只读查看） | ✓ | | |
| 结露预警（只读查看） | ✓ | | |
| 能耗用量查询 | ✓ | | |
| 能耗日报/月报 | ✓ | | |
| AI 问答（方舟龙虾/三恒专家） | ✓ | | |
| 巡检工单查看 | ✓ | | |
| 巡检工单审批（管理员） | ✓ | | |
| 个人中心 — 改密 | ✓ | | |
| 巡检工作日志（只读浏览） | ✓（OQ-06 已确认，首期 P1） | | |
| 部件详情（SpecificPartDetail） | | ✓ | |
| 微信登录（OAuth/openid 绑定） | | ✓ | |
| 故障处理操作（确认/关闭） | | ✓ | |
| 用户管理（增删改查） | | | ✓ |
| 业主管理 | | | ✓ |
| PLC 参数写入（设备参数设置） | | | ✓ |
| 设置审计记录（PlcWriteRecord） | | | ✓ |
| 三恒知识库管理（文档上传） | | | ✓ |
| 服务状态管理（ServicesView） | | | ✓ |

---

## 附录 B：现有 Web 路由与小程序页面映射

| 现有 Web 路由 | 小程序页面 | 首期 |
|--------------|-----------|:----:|
| `/home` | `pages/home/index` | ✓ |
| `/login` | `pages/login/index` | ✓ |
| `/plc-status` | `pages/monitor/plc-status` | ✓ |
| `/device-cards` | `pages/monitor/device-cards` | ✓ |
| `/device-history` | `pages/monitor/device-history` | ✓ |
| `/room-history` | `pages/monitor/room-history` | ✓ |
| `/device-management/faults` | `pages/faults/index` | ✓ |
| `/device-management/condensation-warnings` | `pages/faults/condensation` | ✓ |
| `/usage-query` | `pages/energy/query` | ✓ |
| `/daily-usage-report` | `pages/energy/daily` | ✓ |
| `/monthly-usage-report` | `pages/energy/monthly` | ✓ |
| `/chat` | `pages/chat/index` | ✓ |
| `/agent/work-orders` | `pages/agent/work-orders` | ✓ |
| `/change-password` | `pages/profile/change-password` | ✓ |
| `/agent/inspection-worklog` | `subpackages/ops/pages/worklog` | ✓（首期 P1，OQ-06 已确认） |
| `/specific-part-detail/:specificPart` | `pages/monitor/part-detail` | 后期 |
| `/device-management/device-list` | — | 不纳入 |
| `/device-management/device-settings` | — | 不纳入 |
| `/plc-write-records` | — | 不纳入 |
| `/user-list`, `/create-user`, `/edit-user/:id` | — | 不纳入 |
| `/owner-management` | — | 不纳入 |
| `/services` | — | 不纳入 |
| `/admin/knowledge-base` | — | 不纳入 |
