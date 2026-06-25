# 需求规格说明书

**版本**：v1.8.0_miniprogram_owner_account  
**日期**：2026-06-25  
**状态**：APPROVED — 12 个 OPEN QUESTIONS 已于 2026-06-25 经用户逐条确认（见第 8 节决策记录）  
**作者**：requirement-analyst (SDLC Agent)  
**上游任务**：微信小程序业主端（role=user）账号体系 + 数据隔离

---

## 1. 背景与范围

### 1.1 背景

FreeArk v1.6.0 已建立三角色 RBAC（admin / operator / user），并通过 `UserRoleApiGuardMiddleware` 将 role=user 的账号彻底阻断于所有 web 业务 API 之外。v1.5.0 微信小程序以 uni-app 实现，复用 Django 后端，首期仅支持账号密码登录，且业主端能力尚未实装。

本版本（v1.8.0）目标：为微信小程序业主端（role=user）建立完整的注册/登录路径、专有部分绑定机制、数据隔离约束，并开放方舟智能体聊天能力。

### 1.2 范围

**本版本包含：**
- 业主注册：账号密码注册（复用现有逻辑）+ 微信一键注册/登录（新路径）
- 专有部分绑定：扫码绑定 / 输入 MAC 地址绑定
- 业主管理页"已绑定/未绑定"显示增强（web 端，admin/operator 可见）
- 方舟智能体聊天（仅小程序端 user 使用）：三恒专家提问 + 受限数据访问
- 数据隔离：user 通过智能体读写 FreeArk 数据时强制限制在自己绑定的专有部分
- 巡检范围隔离：user 触发/查看 inspection 结果仅限自己专有部分

**本版本明确不包含：**
- 微信推送通知（非刚需，暂不实施）
- 业主端能耗报表自定义导出
- 小程序端业主管理（仅 web admin/operator 可操作）
- 解绑操作（见 OQ-07，待确认）

### 1.3 关键约束（所有需求的通贯约束）

**C-01 不改变现有 web 行为**：本版本所有改动不得影响已上线的 web 端（admin/operator 用户）的任何现有功能。凡可能影响 web 行为的点，必须在第 8 节列为 OPEN QUESTION，不得擅自决定。

**C-02 role=user 不能访问 web 接口**：现有 `UserRoleApiGuardMiddleware` 必须继续有效。为小程序新增的 API 端点须放入独立命名空间（`/api/miniapp/`），并通过独立的权限检查机制，不得将 role=user 加入现有 web 白名单。

**C-03 数据隔离强约束**：role=user 通过方舟智能体访问 FreeArk 系统数据时，必须在工具调用层强制过滤到自己绑定的 `specific_part`，不得依赖 LLM 自主遵守。

**C-04 微信登录不影响现有 Token 体系**：微信一键登录最终落到同一 Django Token（`rest_framework.authtoken`），与账号密码登录的 Token 格式一致，现有小程序 WS 鉴权/API 调用无需改变。

---

## 2. 现有系统关键事实（需求分析依据）

以下为 Read/Grep 核实后的真实当前状态，作为本需求的事实基础。

### 2.1 UserRoleApiGuardMiddleware（已部署，commit 1da02d5）

- 位置：`FreeArkWeb/backend/freearkweb/api/middleware.py`
- 逻辑：凡 path 以 `/api/` 开头、不在白名单内、且 Token 解析出 role=user 的请求 → 返回 403
- 当前白名单（6条）：`/api/get-csrf-token/`、`/api/auth/login/`、`/api/auth/logout/`、`/api/auth/me/`、`/api/change-password/`、`/api/health/`
- **结论**：小程序专属 API 若放在 `/api/miniapp/` 下，当前中间件会拦截所有 role=user 的访问；需要在中间件白名单或逻辑中为 `/api/miniapp/` 路径专门放行。

### 2.2 OwnerInfo 模型

- 位置：`FreeArkWeb/backend/freearkweb/api/models.py`，db_table=`owner_info`
- screenMAC 对应字段：`unique_id`（CharField max_length=50，当前已有数据）
- 专有部分标识：`specific_part`（"楼-单-层-户"格式，unique，如"3-1-7-702"）
- 现有 `bind_status` 字段（"已绑定"/"未绑定"）：当前是**设备绑定状态**（screenMAC/PLC 是否已关联），与"业主用户账号是否已绑定"是两个不同概念。本需求引入第二个概念，需区分命名。
- `OwnerInfo` 与 `User`（`CustomUser`）表目前**没有外键关联**。

### 2.3 注册端点

- 位置：`/api/auth/register/`（AllowAny），`UserRegistrationSerializer.create()` 强制 `role='user'`
- 现有字段：username、email、password、first_name、last_name、department、position

### 2.4 LangGraph 工具层（生产路径，v1.7.0）

- 当前所有工具（`fa_tools.py`）无任何 user/owner 范围过滤参数
- `get_dashboard_summary()`：全局汇总，无参数
- `get_usage_daily(specific_part, ...)`：按 specific_part 查询，由 LLM 自行填参数
- `get_realtime_params(specific_part)`：同上
- `get_plc_status()`：查全部 PLC，无过滤
- `get_fault_summary(building, unit)`：按楼栋/单元过滤，无 user 维度
- `set_device_params(specific_part, items)` / `trigger_refresh(specific_part)`：写操作，经 interrupt 门
- `search_sanheng_knowledge(query)`：纯 RAG，无数据隔离需求

专家分组：`ENERGY_TOOLS`（能耗专家）、`INSPECTION_TOOLS`（巡检专家）、`SANHENG_TOOLS`（三恒知识专家）

### 2.5 业主管理 Web 页面

- `OwnerManagementView.vue` 已展示 `bind_status`（设备绑定状态）和 `unique_id` 列
- 本需求引入"账号绑定"概念，需区分于现有 `bind_status` 字段展示

---

## 3. 功能需求

### 3.1 账号注册与登录

#### REQ-AUTH-001：账号密码注册（小程序端）

小程序业主端应提供账号密码注册入口，允许用户输入用户名、密码、邮箱（可选）完成注册。注册后账号 role 强制为 user。

**约束**：必须调用新端点（`/api/miniapp/auth/register/`）而非直接复用现有 `/api/auth/register/`，以便在同一逻辑上为小程序增加微信 openid 关联等扩展字段，同时避免中间件放行规则的混淆。业务逻辑可与现有序列化器共享，但入口独立。

**合规引用**：C-01（不改现有 web 注册流程）、C-02（不将 user 加入 web 白名单）

#### REQ-AUTH-002：微信一键注册/登录

小程序业主端应支持通过微信授权一键注册或登录。

注册/登录流程：
1. 小程序前端调用 `wx.login()` 获取临时 code
2. 将 code 发送至后端新端点 `/api/miniapp/auth/wechat/`
3. 后端用 code 换取微信 openid（和 unionid，若已配置）
4. 若 openid 已关联到某 User → 登录该账号，返回 Token
5. 若 openid 未关联 → 自动创建新 User（role=user，username 由系统生成，如 wx_{openid[:8]}），建立 openid 关联，返回 Token

**数据模型需求**：需要存储 User ↔ WeChat openid 的关联（新增字段或新表，见 OQ-01）。

**合规引用**：C-02、C-04

#### REQ-AUTH-003：小程序登录（账号密码）

小程序已有功能（v1.5.0）。登录端点 `/api/auth/login/` 已在中间件白名单，无需更改。

#### REQ-AUTH-004：用户信息查询

`/api/auth/me/` 已在白名单，小程序可查询当前 user 的 role、用户名、绑定状态。**需确认**：是否需要在 `/api/auth/me/` 响应中追加"已绑定的 specific_part"字段，或通过独立小程序端点查询（见 OQ-02）。

---

### 3.2 专有部分绑定

#### REQ-BIND-001：扫码绑定

小程序业主端应提供"扫描二维码"方式绑定专有部分。

流程：
1. 用户通过小程序扫描二维码
2. 小程序解析二维码中的 `unique_id`（screenMAC）
3. 调用后端接口 `/api/miniapp/bind/`，传入 unique_id
4. 后端校验 unique_id 是否存在于 OwnerInfo 表
5. 若有效且通过绑定规则校验（见 OQ-03、OQ-04）→ 建立 User ↔ unique_id 绑定关系，返回成功
6. 若无效 → 返回具体错误码

**二维码内容**：二维码应编码 unique_id（screenMAC），由系统/管理员预先生成，非用户生成（见 OQ-05）。

#### REQ-BIND-002：输入 MAC 地址绑定

小程序业主端应提供手动输入 unique_id（MAC 地址）的绑定方式，作为扫码绑定的备选。流程与 REQ-BIND-001 步骤 3-6 相同，前端从输入框取 unique_id。

#### REQ-BIND-003：绑定关系存储

系统需要建立并持久化 User ↔ OwnerInfo(unique_id) 的绑定关系。

**数据模型需求**：`OwnerInfo` 与 `User` 当前无外键关联。需新增关联方式（见 OQ-03 和 OQ-04 的设计选项讨论，最终方案由架构阶段决定，本需求仅定义功能意图）。

**约束**：
- 绑定关系新增不得修改现有 `OwnerInfo.bind_status` 字段的语义（该字段当前记录设备/PLC 绑定状态，非用户账号绑定状态）
- 新增字段/表须与现有字段区分命名，避免歧义（见 OQ-06）

#### REQ-BIND-004：绑定状态查询（小程序端）

role=user 的用户应能通过小程序查询自己当前的绑定状态（是否已绑定、绑定到哪个 specific_part）。端点：`/api/miniapp/bind/status/`。

#### REQ-BIND-005：绑定规则

绑定操作须执行以下校验规则：
- unique_id 必须在 OwnerInfo 中存在
- 其他绑定规则（见 OQ-03：一对一 vs 一对多）待用户确认后补充

---

### 3.3 业主管理页"账号绑定"展示（web 端）

#### REQ-OWNER-001：业主管理页新增"账号绑定"状态列

web 端业主管理页（`OwnerManagementView.vue`）应在现有列基础上新增"账号绑定"列，显示：
- **已关联账号**：该 unique_id 已被某 User 账号绑定（可显示绑定的用户名或仅显示"已关联"）
- **未关联账号**：尚无 User 账号绑定此 unique_id

**重要说明**：此列与现有 `bind_status` 列（设备/PLC 绑定状态）语义不同，须使用不同列标题，如"业主账号"或"用户关联"，避免混淆。

**合规引用**：此需求会新增 web 端展示内容（但不修改现有列/功能），理论上不改变现有 web 行为，但仍列为 OQ-08 供确认。

#### REQ-OWNER-002：业主管理页绑定状态筛选（可选增强）

web 端业主管理页可增加按"账号绑定"状态筛选的能力。优先级低于 REQ-OWNER-001，可后期实施。

---

### 3.4 方舟智能体聊天（小程序端 user）

#### REQ-CHAT-001：小程序端接入 LangGraph 聊天

role=user 应能在小程序端通过 WebSocket 接入方舟智能体聊天（LangGraph 路径），体验与 web 端一致。

**注意**：当前 LangGraph 聊天的 WebSocket 鉴权机制需核实是否已在小程序端 v1.5.0 中实现。若已实现，本需求仅增加数据隔离约束层；若未实现，需补充鉴权。

#### REQ-CHAT-002：三恒专家提问放行

role=user 向三恒知识专家（`search_sanheng_knowledge` 工具）提问时，**不受数据隔离约束**——三恒知识库是通用知识（三恒系统原理/参数/故障码），与业主专有数据无关，应完整放行。

#### REQ-CHAT-003：方舟智能体身份注入

当 role=user 发起聊天时，系统必须向 LangGraph 编排图注入当前用户的 `specific_part`（从绑定关系查询），作为本次会话的"数据范围上下文"。若 user 尚未绑定专有部分，应在聊天前提示用户先完成绑定，或在响应中告知无法访问系统数据。

---

### 3.5 数据隔离（最关键约束）

#### REQ-ISO-001：能耗专家工具强制范围过滤

当 role=user 的用户使用能耗专家工具时：
- `get_usage_daily`、`get_realtime_params`、`set_device_params`、`trigger_refresh` 的 `specific_part` 参数必须在工具调用层强制覆盖为用户绑定的 `specific_part`，不允许 LLM 自行传入其他值
- `get_dashboard_summary` 若查全局汇总，需评估是否对 user 开放（见 OQ-09）

**实现机制**：在 LangGraph 编排图层（`orchestrator.py` 或工具包装层）注入用户数据范围上下文，在工具调用前校验/覆盖 `specific_part` 参数。此为强约束，不依赖 LLM 遵守提示词。

#### REQ-ISO-002：巡检专家工具强制范围过滤

当 role=user 使用巡检专家工具时：
- `get_plc_status()` 当前返回全部 PLC，对 user 应限制到其绑定的 specific_part 对应的 PLC（由 `OwnerInfo.plc_ip_address` 字段关联）
- `get_fault_summary()` 应限制到用户绑定的 specific_part，不返回其他专有部分的故障

**实现机制**：同 REQ-ISO-001，在工具调用层注入过滤。

#### REQ-ISO-003：写操作范围强制校验

`set_device_params` 和 `trigger_refresh` 的 interrupt 确认门通过后，执行层必须再次校验 `specific_part` 是否为当前 user 绑定的专有部分（防止 interrupt 确认环节被绕过）。

#### REQ-ISO-004：三恒专家豁免

`search_sanheng_knowledge` 工具调用不受数据范围过滤约束。三恒知识库为通用知识，任何 user 均可查询全库。

#### REQ-ISO-005：数据范围定义

`specific_part`（如"3-1-7-702"）是业主数据隔离的核心粒度。通过 `OwnerInfo` 的以下字段可关联到具体设备：
- `unique_id`：screenMAC，绑定标识
- `ip_address`：设备 IP
- `plc_ip_address`：PLC IP

涉及数据隔离的表（按 specific_part 字段过滤）：
- `api_plclatestdata`（PLCLatestData.specific_part）
- `api_device_param_history`（DeviceParamHistory.specific_part）
- `usage_daily`、`usage_monthly`（UsageQuantityDaily/Monthly.specific_part）
- `api_fault_event`（FaultEvent.specific_part）
- `api_condensation_warning_event`（CondensationWarningEvent.specific_part）

---

### 3.6 巡检范围隔离

#### REQ-INSP-001：巡检结果查看限制

role=user 通过小程序查询巡检状态（FaultEvent.inspection_status、CondensationWarningEvent.inspection_status）时，仅返回其绑定 specific_part 的记录。

#### REQ-INSP-002：按需巡检触发限制

若小程序未来支持用户触发按需巡检，role=user 仅能对自己绑定的 specific_part 触发，系统应在触发接口校验 specific_part 归属（见 OQ-10）。

---

## 4. 非功能需求

### NFR-SEC-001：绑定接口防刷

绑定接口（`/api/miniapp/bind/`）应有频率限制，防止暴力枚举 unique_id。

### NFR-SEC-002：微信 openid 保密

openid 不得出现在任何前端可见的 URL 参数或日志中；后端存储时不加密但不对外暴露。

### NFR-ISO-001：数据隔离不依赖 LLM

数据范围过滤必须在代码层（工具调用前）强制执行，不依赖提示词约束 LLM 行为。这是硬约束，不接受"通过提示词告知 LLM 只查自己的数据"作为实现方案。

### NFR-COMPAT-001：零 web 回归

本版本所有后端改动须通过现有 1702 个测试（已知 6 个待定失败除外），新增改动不引入新的测试失败。

### NFR-PERF-001：绑定查询性能

`/api/miniapp/bind/status/` 端点响应时间应在 200ms 内（SQLite 测试环境参考，生产 MySQL 应更快）。

---

## 5. 角色与权限矩阵

| 功能 | admin | operator | user（业主/小程序） | 匿名 |
|------|-------|----------|---------------------|------|
| 账号密码注册（小程序） | - | - | 允许 | 允许 |
| 微信一键注册/登录 | - | - | 允许 | 允许 |
| 扫码/输入 MAC 绑定 | - | - | 允许（仅自己） | 禁止 |
| 查询自己绑定状态 | - | - | 允许 | 禁止 |
| 查看业主管理页"账号绑定"列 | 允许 | 允许 | 禁止（web） | 禁止 |
| 方舟聊天（小程序） | - | - | 允许（数据受限） | 禁止 |
| 查询自己专有部分数据 | - | - | 允许（仅自己） | 禁止 |
| 查询其他专有部分数据 | 允许 | 允许 | **禁止** | 禁止 |
| 三恒知识查询 | 允许 | 允许 | 允许 | 禁止 |
| 触发写操作（自己部分） | - | - | 允许（经确认门） | 禁止 |
| 触发写操作（他人部分） | - | - | **禁止** | 禁止 |

---

## 6. 接口清单（新增）

以下为本版本需新增的 API 端点（全部在 `/api/miniapp/` 命名空间下）：

| 端点 | 方法 | 鉴权 | 功能 |
|------|------|------|------|
| `/api/miniapp/auth/register/` | POST | AllowAny | 账号密码注册（role 强制=user） |
| `/api/miniapp/auth/wechat/` | POST | AllowAny | 微信一键登录/注册（code 换 Token） |
| `/api/miniapp/bind/` | POST | IsOwnerUser | 扫码/输入 MAC 绑定专有部分 |
| `/api/miniapp/bind/status/` | GET | IsOwnerUser | 查询当前用户绑定状态 |

**鉴权类 `IsOwnerUser`**：新建，仅允许 role=user 且已登录的用户访问（与现有 `IsAdminUser`、`IsOperatorOrAbove` 并列）。

**中间件白名单扩展**：`UserRoleApiGuardMiddleware.ALLOWLIST` 须新增 `/api/miniapp/` 路径前缀放行（或修改中间件逻辑支持路径前缀匹配）——此改动须评估对安全约束的影响（见 OQ-11）。

---

## 7. 数据模型变更（需求层描述，架构阶段细化）

### 7.1 新增：微信账号关联【已定：方案 B】

存储 `User.id` ↔ `WeChat openid` 的关联，**采用方案 B：新建 `WechatBinding` 表**（user FK + openid + unionid + created_at）。理由：本版本已需新建 `OwnerUserBinding` 关联表，独立表零侵入 `CustomUser`、扩展性更好。（OQ-01 已决）

### 7.2 新增：User ↔ OwnerInfo 账号绑定【已定：独立关联表，多对多】

存储 `User` ↔ `OwnerInfo` 的绑定，**采用独立关联表 `OwnerUserBinding`**（user FK + owner FK + bound_at + active 标志）。

**关键约束（OQ-03 / OQ-04 已决，均为一对多 ⇒ 多对多）**：
- 一个 user 可绑定**多个** specific_part（业主持有多套房产）
- 一个 specific_part 可被**多个** user 绑定（家庭成员各自账号共享）
- ⇒ 关系为**多对多**，禁止用 User 或 OwnerInfo 上的单一 FK 实现，必须用关联表
- ⇒ 数据隔离过滤条件为 `specific_part IN (该 user 的绑定集合)`
- ⇒ 聊天/巡检涉及具体房间操作时，若 user 绑定多个 specific_part，需在会话内先选定/澄清当前操作的房间（见 REQ-CHAT-003）

### 7.3 现有字段语义保护【OQ-06 已决：方案 A，保持原语义】

`OwnerInfo.bind_status`（"已绑定"/"未绑定"）当前表示**设备/PLC 绑定状态**，**本版本不修改其语义、写入逻辑或现有 web 展示**。"账号绑定"状态通过新表 `OwnerUserBinding` 体现，在 web 业主管理页**新增一列独立展示**（REQ-OWNER-001）。

**用户补充事实（2026-06-25）**：现有业主管理页的"是否绑定"列（即 `bind_status`）目前**全部显示"已绑定"，且无实际业务在使用**（vestigial 列）。本版本保持该列原样不动；是否清理/移除该 vestigial 列属于**独立决策**，会改动 web 行为，不纳入 v1.8.0 默认范围，需另行确认（记为遗留项 LEGACY-01）。

---

## 8. 决策记录（OPEN QUESTIONS 已全部确认）

用户已于 2026-06-25 逐条确认下列 12 项。以下为最终决策，作为架构阶段的硬输入。

| 编号 | 主题 | 最终决策 | 对 web 影响 |
|------|------|----------|-------------|
| OQ-01 | 微信 openid 存储 | **方案 B**：新建独立表 `WechatBinding`，零侵入 `CustomUser` | 无（新表） |
| OQ-02 | 绑定状态查询入口 | **不动 `/api/auth/me/`**，用独立端点 `/api/miniapp/bind/status/` | 无（保护现有端点响应结构） |
| OQ-03 | 一个 user 绑几个专有部分 | **一对多**：user 可绑多个 specific_part | 无 |
| OQ-04 | 一个专有部分被几个 user 绑 | **一对多**：可共享。⇒ 与 OQ-03 合为**多对多**，用 `OwnerUserBinding` 关联表 | 无 |
| OQ-05 | 二维码来源 | **现场已有码**，二维码直接编码 `unique_id`；**web 端零新增** | 无 |
| OQ-06 | `bind_status` 语义 | **方案 A**：保持原语义不变，账号绑定走新表，web 新增独立列展示 | 无 |
| OQ-07 | 解绑 | **业主自助解绑（小程序）+ admin 可强制解绑**；解绑后可重新绑定其他部分 | admin 强解入口为 web 新增功能（详见下方说明） |
| OQ-08 | web 业主管理页"账号绑定"列 | **本版本实施**（需求#4）：新增独立"账号绑定"列，不改现有列 | 仅新增列，不改现有列/筛选/编辑行为 |
| OQ-09 | `get_dashboard_summary` 对 user | **默认**：对 user 不返回全局看板；汇总限定其绑定部分，若工具难低成本范围化则对 user 屏蔽该工具 | 无（仅 user 路径） |
| OQ-10 | 按需巡检触发 | **仅查看/问询（经聊天）**，本版本不做主动触发；REQ-INSP-002 降级为未来扩展 | 无 |
| OQ-11 | 中间件放行方式 | **`/api/miniapp/` 前缀整体放行** + 各端点强制配 `IsOwnerUser` 权限类 | 中间件改动，但仅放行新命名空间，不影响现有 6 条白名单 |
| OQ-12 | 微信 AppID/Secret | **已有注册小程序 + 凭证**，微信一键登录纳入本版本；凭证经 `.env` 注入后端 | 无 |

### 8.1 由决策派生的关键约束（架构阶段必须落实）

1. **多对多绑定模型**：`OwnerUserBinding` 关联表是 OQ-03/04 的唯一正确实现，禁止单 FK。隔离过滤一律 `specific_part IN (绑定集合)`。
2. **多绑定下的会话房间选择**（REQ-CHAT-003 增强）：user 绑定多个 specific_part 时，涉及具体房间的查询/写操作/巡检，编排图须先确定"当前会话目标房间"（用户指定或系统追问澄清），再注入隔离过滤；不得默认对全部绑定房间执行写操作。
3. **OQ-07 解绑的 web 影响**：admin 在 web 端强制解绑入口属 web 新增能力，须确保不改动现有业主管理页其他行为；业主自助解绑仅经 `/api/miniapp/` 端点，不触碰 web。
4. **OQ-08 与 LEGACY-01**：新增"账号绑定"列须与现有 vestigial 的"是否绑定"（`bind_status`）列在标题与数据来源上明确区分；现有 vestigial 列保持不动。是否清理 vestigial 列为独立遗留项 LEGACY-01，不在本版本。

### 8.2 遗留项（不在 v1.8.0 范围，留待独立确认）

| 编号 | 内容 |
|------|------|
| LEGACY-01 | 现有业主管理页 vestigial 的"是否绑定"列（`bind_status` 全为"已绑定"、无业务使用）是否清理/移除——会改 web 行为，需独立决策 |

---

## 9. 不在范围内的显式排除项

| 排除项 | 说明 |
|--------|------|
| 微信模板消息/订阅消息推送 | 非刚需，本版本不实施 |
| 手机号一键登录 | 需微信授权，流程更复杂，本版本不实施 |
| 业主端自助创建/修改/删除 OwnerInfo 记录 | 业主信息由 admin 维护，user 仅绑定 |
| 多 specific_part 绑定的聊天路由逻辑 | 依赖 OQ-03 确认，在架构阶段设计 |
| web 端新增"生成二维码"功能 | 依赖 OQ-05 确认，可能不在本版本范围 |

---

*文档结束。请用户重点审阅第 8 节 OPEN QUESTIONS（OQ-01 至 OQ-12），逐条回复确认方向后进入架构阶段。*
