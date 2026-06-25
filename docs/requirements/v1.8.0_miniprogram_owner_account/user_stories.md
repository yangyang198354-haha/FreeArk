# 用户故事清单

**版本**：v1.8.0_miniprogram_owner_account  
**日期**：2026-06-25  
**状态**：APPROVED — OPEN QUESTIONS 已于 2026-06-25 全部确认（见 requirements_spec.md 第 8 节决策记录）  
**作者**：requirement-analyst (SDLC Agent)

---

## 说明

- 角色标注：**user**（业主/小程序端）/ **admin** / **operator** / **system**
- 标注 `[OQ-XX]` 的用户故事依赖对应 OPEN QUESTION 确认后才能进入实施
- Given/When/Then 中的断言为验收标准，架构/开发完成后由 test-engineer 对照实施

---

## 模块 A：注册与登录

---

### US-AUTH-001：账号密码注册（小程序端）
**角色**：user（未注册的业主）

**用户故事**：  
作为一名想使用微信小程序查看自己三恒设备信息的业主，我希望能通过账号密码方式注册一个业主账号，以便在小程序内登录并访问属于我的数据。

**验收标准**：

**场景 1：正常注册成功**  
Given 用户打开小程序注册页面，填写合法用户名（未被占用）、密码（满足强度要求）  
When 用户提交注册表单，调用 `/api/miniapp/auth/register/`  
Then 系统创建新用户，role 为 `user`（无论表单是否传入其他 role 值均强制为 user）  
And 响应返回 HTTP 201，包含 Token 和用户基本信息（username、role）  
And 用户可直接使用该 Token 访问小程序端白名单接口

**场景 2：用户名已存在**  
Given 用户填写的用户名已被其他账号占用  
When 用户提交注册表单  
Then 响应返回 HTTP 400，错误信息明确指出"用户名已存在"  
And 不创建新用户

**场景 3：密码不匹配**  
Given 用户两次输入的密码不一致  
When 用户提交注册表单  
Then 响应返回 HTTP 400，错误信息为"两次输入的密码不匹配"

**场景 4：注册后 role 为 user，web 端 API 被拦截**  
Given 用户通过上述注册获得 Token  
When 用户携带该 Token 访问任何 `/api/`（非白名单）web 业务端点（如 `/api/owners/`）  
Then 响应返回 HTTP 403，拒绝访问  
And web 端现有 admin/operator 用户的访问不受影响

---

### US-AUTH-002：微信一键注册/登录（新用户）
**角色**：user（未注册的业主），**system**

**用户故事**：  
作为一名初次使用小程序的业主，我希望通过微信授权一键完成注册，无需手动填写用户名密码，以降低注册门槛。

**验收标准**：

**场景 1：微信新用户自动注册**  
Given 用户的微信 openid 从未在系统中出现  
When 用户点击"微信登录"，小程序调用 `wx.login()` 获取 code 并发送至 `/api/miniapp/auth/wechat/`  
Then 后端成功向微信服务器换取 openid  
And 系统自动创建新 User（role=user，username 系统生成）  
And openid 与新 User 关联存储  
And 响应返回 HTTP 201，包含 Token 和用户信息  
And 用户可使用该 Token 访问小程序端白名单接口

**场景 2：微信已注册用户直接登录**  
Given 用户的微信 openid 已关联到某 User 账号  
When 用户点击"微信登录"，小程序发送 code 至 `/api/miniapp/auth/wechat/`  
Then 系统找到关联 User，签发 Token  
And 响应返回 HTTP 200，包含 Token 和用户信息  
And 不创建新用户

**场景 3：微信服务器换码失败**  
Given 微信服务器返回 code 无效或已过期  
When 后端调用微信 API 失败  
Then 响应返回 HTTP 400，包含"微信授权失败，请重试"的错误信息  
And 不创建任何账号

[OQ-01 确认后补充：openid 存储在哪个表/字段]  
[OQ-12 确认后补充：AppID/AppSecret 注入方式]

---

### US-AUTH-003：查询当前用户绑定状态
**角色**：user

**用户故事**：  
作为已登录的业主用户，我希望能查询自己是否已绑定专有部分，以及绑定到哪个房间，以便了解当前账号的访问范围。

**验收标准**：

**场景 1：查询已绑定用户**  
Given 用户已登录（role=user）且已完成专有部分绑定  
When 用户调用 `/api/miniapp/bind/status/`  
Then 响应返回 HTTP 200，包含 `bound: true`、`specific_part`（如"3-1-7-702"）、`location_name`（坐落描述）

**场景 2：查询未绑定用户**  
Given 用户已登录（role=user）但尚未绑定任何专有部分  
When 用户调用 `/api/miniapp/bind/status/`  
Then 响应返回 HTTP 200，包含 `bound: false`，其余字段为 null

**场景 3：未登录用户被拒绝**  
Given 请求不携带有效 Token  
When 调用 `/api/miniapp/bind/status/`  
Then 响应返回 HTTP 401 或 403

---

## 模块 B：专有部分绑定

---

### US-BIND-001：扫码绑定专有部分
**角色**：user

**用户故事**：  
作为已登录的业主，我希望通过小程序扫描设备上的二维码，快速绑定我的专有部分（房间），以便系统知道哪些数据属于我。

**验收标准**：

**绑定规则（已定，多对多）**：一个 user 可绑多个 specific_part；一个 specific_part 可被多个 user 绑定。绑定关系存于 `OwnerUserBinding` 关联表。

**场景 1：扫码成功绑定**  
Given 用户已登录（role=user）  
And 二维码内容对应的 unique_id 在 OwnerInfo 表中存在  
When 用户扫描二维码，小程序解析出 unique_id 并调用 `POST /api/miniapp/bind/`，传入 `unique_id`  
Then 系统在 `OwnerUserBinding` 中建立 User ↔ OwnerInfo 绑定记录（active）  
And 响应返回 HTTP 200，包含 `specific_part` 和 `location_name`  
And 用户后续查询 `/api/miniapp/bind/status/` 的绑定列表中包含该专有部分

**场景 2：invalid unique_id**  
Given 二维码内容的 unique_id 在 OwnerInfo 表中不存在  
When 用户扫描并提交  
Then 响应返回 HTTP 404，错误信息"未找到对应的专有部分，请确认二维码是否有效"  
And 不建立绑定关系

**场景 3：重复绑定同一专有部分（幂等）**  
Given 当前 user 已绑定该 unique_id（同一 user 重复扫同一码）  
When 用户再次提交绑定请求  
Then 系统不新增重复记录，响应返回 HTTP 200（幂等），绑定状态不变

**场景 4：该专有部分已被其他 user 绑定（多对多允许）**  
Given 该 unique_id 已被另一 user 绑定（如家庭成员）  
And 当前 user 尚未绑定该 unique_id  
When 当前 user 提交绑定请求  
Then 系统允许并新建当前 user 的绑定记录（不冲突、不覆盖他人绑定）  
And 响应返回 HTTP 200

---

### US-BIND-002：手动输入 MAC 地址绑定
**角色**：user

**用户故事**：  
作为已登录的业主，当我无法扫码（如二维码损坏/不清晰）时，我希望能手动输入设备 MAC 地址来完成绑定，保证绑定方式的可达性。

**验收标准**：

**场景 1：输入正确 MAC 绑定成功**  
Given 用户已登录（role=user）  
And 用户输入的 MAC 地址格式合法（如 XX:XX:XX:XX:XX:XX 或纯十六进制）  
And 该 MAC 地址对应的 unique_id 在 OwnerInfo 中存在  
When 用户提交，调用 `POST /api/miniapp/bind/`，传入 `unique_id`  
Then 系统建立绑定关系，响应结果与 US-BIND-001 场景 1 相同

**场景 2：MAC 格式非法**  
Given 用户输入的 MAC 地址格式不合法  
When 用户提交  
Then 响应返回 HTTP 400，错误信息"MAC 地址格式不正确"  
And 不查询数据库，不建立绑定关系

**场景 3：输入 MAC 在系统中不存在**  
Given 用户输入的 MAC 地址格式合法但在 OwnerInfo 中不存在  
When 用户提交  
Then 响应返回 HTTP 404，错误信息与 US-BIND-001 场景 2 一致

---

### US-BIND-003：绑定接口防频率滥用
**角色**：system

**用户故事**：  
作为系统，需要防止恶意用户暴力枚举 unique_id（MAC 地址），以保护业主数据安全。

**验收标准**：

**场景 1：短时间内超出频率限制**  
Given 同一用户（同一 Token）在 1 分钟内发起超过 N 次（N 待定，建议 10 次）绑定请求  
When 再次请求  
Then 响应返回 HTTP 429，错误信息"请求过于频繁，请稍后重试"  
And 正常频率内的其他用户不受影响

---

### US-BIND-004：解绑专有部分
**角色**：user，admin

**用户故事**（OQ-07 已定：业主自助解绑 + admin 可强制解绑）：  
作为业主，我希望能解绑某个专有部分（例如绑错了或不再持有），解绑后可重新绑定其他部分；作为管理员，我希望能在 web 端强制解绑异常的账号绑定。

**验收标准**：

**场景 1：业主自助解绑（小程序）**  
Given 用户已登录（role=user）且已绑定某 specific_part  
When 用户调用 `POST /api/miniapp/unbind/`，传入要解绑的 unique_id  
Then 系统将该 `OwnerUserBinding` 记录置为失效（解绑）  
And 该 user 后续查询绑定列表不再包含该专有部分  
And 该 user 对该专有部分的数据访问立即失效

**场景 2：解绑后可重新绑定其他部分**  
Given 用户已解绑某 specific_part  
When 用户扫码/输入 MAC 绑定另一个有效 unique_id  
Then 绑定成功，新绑定生效

**场景 3：admin web 端强制解绑**  
Given admin 在 web 端发现某异常账号绑定  
When admin 通过 web 端执行强制解绑  
Then 对应 `OwnerUserBinding` 记录失效  
And 该操作不影响业主管理页其他现有行为（无 web 回归）

**场景 4：解绑不属于自己的绑定（越权防护）**  
Given role=user 用户尝试解绑一条不属于自己的绑定记录  
When 提交解绑请求  
Then 响应返回 HTTP 403/404，拒绝操作，不影响他人绑定

---

## 模块 C：业主管理页增强（web 端）

---

### US-OWNER-001：业主管理页展示"账号绑定"状态
**角色**：admin，operator

**用户故事**：  
作为运维管理员，我希望在业主管理页能看到每个专有部分是否已有业主用户账号与之绑定，以便了解小程序注册推广进展和管理异常绑定。

**验收标准**：

**场景 1：展示已关联账号的专有部分**  
Given admin 或 operator 登录 web 端，打开业主管理页  
And 某 OwnerInfo 记录的 unique_id 已被一个或多个 User 账号绑定  
When 页面加载完成  
Then 该行显示新增"账号绑定"列，内容为"已关联"（或显示绑定用户名）  
And 现有"绑定状态"列（设备绑定状态）内容不变，语义不受影响

**场景 2：展示未关联账号的专有部分**  
Given 某 OwnerInfo 记录的 unique_id 尚未被任何 User 账号绑定  
When 页面加载完成  
Then 该行"账号绑定"列显示"未关联"

**场景 3：现有 web 功能无回归**  
Given admin/operator 正常使用业主管理页（搜索/过滤/编辑/同步）  
When 任何现有操作执行  
Then 所有现有功能行为与 v1.7.0 完全一致  
And 现有"绑定状态"筛选器仍按设备绑定状态过滤，结果不受新增"账号绑定"列影响

[OQ-08] 确认本需求是否在 v1.8.0 实施

---

## 模块 D：方舟智能体聊天（小程序端，数据隔离）

---

### US-CHAT-001：user 角色接入方舟智能体聊天
**角色**：user

**用户故事**：  
作为已登录的业主，我希望在小程序内能与方舟智能体对话，就像 web 端运维人员一样，以便通过自然语言查询我家的设备状态和能耗情况。

**验收标准**：

**场景 1：已绑定用户正常发起对话**  
Given 用户已登录（role=user）且已绑定 specific_part（如"3-1-7-702"）  
When 用户通过小程序 WebSocket 发起聊天消息  
Then WebSocket 连接成功建立，消息正常送达 LangGraph 编排图  
And 聊天响应正常返回到小程序端

**场景 2：未绑定用户发起对话**  
Given 用户已登录（role=user）但尚未绑定任何 specific_part  
When 用户发起聊天消息涉及设备/能耗/巡检数据查询  
Then 智能体告知用户"您尚未绑定专有部分，无法查询设备数据，请先完成绑定"  
And 对于三恒知识提问（不涉及设备数据），仍正常响应

**场景 3：绑定多个专有部分时的房间选择（OQ-03/04 多对多派生）**  
Given 用户已登录（role=user）且绑定了多个 specific_part（如"3-1-7-702"与"3-1-8-803"）  
When 用户发起涉及具体房间的查询或写操作，但未指明是哪一套  
Then 智能体先追问/要求用户选定当前操作的目标房间（仅限其绑定集合内）  
And 仅在选定后将该 specific_part 注入隔离过滤再执行  
And 写操作绝不默认对全部绑定房间批量执行

---

### US-CHAT-002：三恒专家提问（无数据隔离限制）
**角色**：user

**用户故事**：  
作为业主，我希望能向三恒系统专家提问（如"三恒系统的新风设定温度是多少度合适？"），获得专业知识解答，而不受我的数据访问范围限制。

**验收标准**：

**场景 1：三恒知识提问正常响应**  
Given 用户已登录（role=user，无论是否绑定）  
When 用户提问涉及三恒系统原理、参数设置、故障码等知识性内容  
Then 路由器将请求分发给三恒知识专家（`search_sanheng_knowledge` 工具）  
And 知识库检索结果正常返回，不因 user 角色而受限  
And 系统不要求该查询必须关联到某个 specific_part

**场景 2：三恒知识专家工具不注入 specific_part 过滤**  
Given 用户是 role=user  
When 系统调用 `search_sanheng_knowledge(query)` 工具  
Then 工具调用参数不包含 specific_part 或 owner 范围限制  
And 工具对全量知识库进行向量检索

---

### US-CHAT-003：能耗专家数据访问强制范围限制
**角色**：user，**system**

**用户故事**：  
作为系统，当业主用户（role=user）通过方舟智能体查询能耗数据时，必须在工具调用层强制将数据范围限制在该用户绑定的 specific_part，防止越权访问其他业主数据。

**验收标准**：

**场景 1：user 查询自己专有部分能耗（正常）**  
Given 用户已登录（role=user）且绑定 specific_part="3-1-7-702"  
When 用户问"我家本月用电多少？"，路由到能耗专家，触发 `get_usage_daily` 工具  
Then 工具调用中 `specific_part` 参数值为"3-1-7-702"（用户绑定值）  
And 响应数据仅为"3-1-7-702"的能耗数据

**场景 2：user 试图查询其他专有部分能耗（应被阻断）**  
Given 用户绑定 specific_part="3-1-7-702"  
When 用户消息中明确指定"帮我查 3-1-5-501 的能耗"（另一用户的房间）  
Then 系统工具调用层强制将 specific_part 覆盖/替换为用户绑定值"3-1-7-702"  
And 响应只返回用户自己的数据，或告知"只能查询您自己专有部分的数据"  
And 不返回"3-1-5-501"的任何数据

**场景 3：数据隔离不依赖提示词**  
Given 任何 role=user 的用户  
When 系统处理该用户的工具调用请求  
Then specific_part 范围限制由代码在工具调用前强制注入，而非仅靠 LLM 遵守系统提示词

---

### US-CHAT-004：实时参数查询范围限制
**角色**：user，**system**

**用户故事**：  
作为系统，当业主用户查询设备实时参数（温度/湿度/CO₂）时，必须只返回其绑定专有部分的传感器数据。

**验收标准**：

**场景 1：查询实时参数**  
Given 用户绑定 specific_part="3-1-7-702"  
When 用户问"我家现在温度多少？"，触发 `get_realtime_params` 工具  
Then 工具调用 `specific_part="3-1-7-702"`，返回该专有部分的实时数据  
And 不返回任何其他专有部分的数据

---

### US-CHAT-005：写操作（设备参数修改）范围限制
**角色**：user，**system**

**用户故事**：  
作为系统，当业主用户通过方舟智能体发起写操作（如修改设备参数）时，必须在 interrupt 确认门通过后的执行阶段再次校验 specific_part，确保写入范围不超出用户绑定的专有部分。

**验收标准**：

**场景 1：写操作正常流程（自己的设备）**  
Given 用户绑定 specific_part="3-1-7-702"  
When 用户请求"把我家温度设定调到 24 度"，触发 `set_device_params` 工具  
Then 工具调用中 specific_part 为"3-1-7-702"  
And 系统展示确认门，用户确认后执行  
And 执行层再次校验 specific_part="3-1-7-702" 与用户绑定一致，执行写入

**场景 2：写操作指向其他专有部分（应被阻断）**  
Given 用户绑定 specific_part="3-1-7-702"  
When 任何路径导致 `set_device_params(specific_part="3-1-5-501", ...)` 被触发  
Then 执行层拦截，返回错误"无权修改其他专有部分的设备参数"  
And 写操作不执行  
And 记录安全告警日志

---

## 模块 E：巡检范围隔离

---

### US-INSP-001：巡检专家查询结果范围限制
**角色**：user，**system**

**用户故事**：  
作为系统，当业主用户通过方舟智能体查询巡检/故障信息时，只能看到自己专有部分的巡检结果，不得获取其他业主的设备故障信息。

**验收标准**：

**场景 1：故障汇总查询（范围受限）**  
Given 用户绑定 specific_part="3-1-7-702"  
When 用户问"我家有没有故障？"，路由到巡检专家，触发 `get_fault_summary` 工具  
Then 工具调用参数过滤到用户绑定的 specific_part 对应范围（楼/单元）  
And 响应只包含"3-1-7-702"的故障信息，不暴露其他专有部分的故障数量或详情

**场景 2：PLC 状态查询（范围受限）**  
Given 用户绑定 specific_part="3-1-7-702"，对应 plc_ip_address 从 OwnerInfo 获取  
When 用户问"我家 PLC 在线吗？"，触发 `get_plc_status` 工具  
Then 系统只返回用户绑定专有部分对应的 PLC 状态，不返回全系统 PLC 列表  
And admin/operator 调用 `get_plc_status` 仍返回全量数据（无影响）

---

### US-INSP-002：巡检结果查看（按需巡检触发）
**角色**：user

**用户故事**（依赖 OQ-10）：  
作为业主，如果小程序支持触发按需巡检，我只能对自己绑定的专有部分触发，不能对其他业主的部分触发巡检。

**验收标准**：

**场景 1：触发自己专有部分的按需巡检**  
Given 用户绑定 specific_part="3-1-7-702"  
When 用户在小程序触发按需巡检，系统校验目标 specific_part  
Then 若目标为"3-1-7-702" → 允许触发  
And 若目标为其他 specific_part → 返回 HTTP 403，"无权对其他专有部分触发巡检"

[OQ-10] 确认按需巡检是否在本版本实施

---

## 用户故事数量汇总

| 模块 | 用户故事数 | 场景数 | 关联 OQ（均已确认） |
|------|-----------|-------|---------|
| A：注册与登录 | 3 | 9 | OQ-01, OQ-02, OQ-12 |
| B：专有部分绑定 | 4 | 12 | OQ-03, OQ-04, OQ-05, OQ-07 |
| C：业主管理页增强（web） | 1 | 3 | OQ-08 |
| D：方舟智能体聊天 | 5 | 11 | OQ-09 |
| E：巡检范围隔离 | 2 | 3 | OQ-10 |
| **合计** | **15** | **38** | — |

---

## 跨切面约束验收标准

以下为贯穿所有用户故事的系统级验收条件，任一失败即整体不通过：

**SYS-ACC-001（零 web 回归）**：现有 1702 个测试（6 个已知待定失败除外）执行结果无新增失败。

**SYS-ACC-002（角色隔离）**：任何携带 role=user Token 的请求，调用 `/api/`（非 miniapp 命名空间）任何非白名单端点，均收到 HTTP 403。

**SYS-ACC-003（数据隔离强制性）**：role=user 通过任何路径（含 LLM 工具调用）读写的 FreeArk 系统数据，specific_part 必须匹配其绑定值，且该限制由代码强制，不依赖 LLM 提示词。

**SYS-ACC-004（绑定原子性）**：绑定操作成功后，用户立即可通过 `/api/miniapp/bind/status/` 查询到正确的绑定状态（同一请求周期内可见）。

---

*文档结束。所有标注 [OQ-XX] 的场景须待对应 OPEN QUESTION 用户确认后补充或修订。*
