<!--
  file_type:    user_stories
  version:      v1.12.0
  project:      FreeArk
  module:       miniprogram_param_settings_redesign
  date:         2026-06-29
  status:       APPROVED（OQ-01~OQ-06 已于 2026-06-29 经用户确认；详见 requirements_spec.md §5）
  author:       sub_agent_requirement_analyst
  depends_on:   requirements_spec.md（同目录），v1.10.0 user_stories.md（APPROVED）
-->

# 用户故事清单 — v1.12.0 微信小程序参数设置页重设计

**版本**：v1.12.0_miniprogram_param_settings_redesign
**日期**：2026-06-29
**状态**：APPROVED（OQ-01~OQ-06 已确认；US-05 手动刷新改为"每次进入后台静默刷新"，见下）
**配套**：`requirements_spec.md`（同目录）

> 验收标准采用 Given / When / Then 格式，动词用主动态，条件用「Given 已知 xxx」。
> 角色默认为**业主（role=user）**。
> 标注「[继承 v1.10.0]」的故事和验收标准，行为须与 v1.10.0 APPROVED 版本保持一致。

---

## 用户角色地图（Actor × Feature Matrix）

| Actor | 面板列表渲染 | tab1 设置 | tab2 详细 | 骨架缓存 | 动态面板 | 写确认 | 零回归 |
|-------|------------|---------|---------|---------|---------|--------|-------|
| 业主（role=user） | US-01 | US-02 | US-03 | US-04 US-05 | US-06 | US-07 | — |
| web 运维/管理员 | — | — | — | — | — | — | US-08 |

---

## 用户故事详情

---

**US-01: 查看某设备/房间面板的参数（面板列表首次加载）**

- **用户故事**：As a 业主，I want to 进入参数设置页时立即看到按设备/房间类型组织的面板列表（主机/新风/主温控/各房间），so that 我可以快速定位到目标设备或房间，查看或修改其参数，不必在设备编号卡片中筛选。
- **关联需求**：REQ-FUNC-001、REQ-FUNC-005、REQ-FUNC-006、REQ-FUNC-007
- **优先级**：Must Have

**验收标准：**

- AC-01-01（骨架缓存命中，面板列表首次渲染）
  - Given 已知业主已登录，已绑定至少一个 specific_part，该 specific_part 的骨架缓存有效（TTL 未过期）
  - When 业主进入参数设置页
  - Then 在 300ms 内，页面渲染出面板列表：按「主机 → 新风 → 主温控 → 各房间（顺序与骨架 rooms 一致）」纵向排列；面板标题正确显示（主机/新风/主温控 用固定中文名，各房间面板标题取自 `room.room_name`）；各面板内参数名称行已呈现，参数值显示「采集中…」占位

- AC-01-02（骨架缓存未命中，首次进入）
  - Given 已知业主已登录，已绑定至少一个 specific_part，骨架缓存不存在或 TTL 已过期
  - When 业主进入参数设置页
  - Then 页面显示骨架加载指示器，从后端拉取 `GET /api/miniapp/owner/structure/?specific_part=...` 成功后，渲染面板列表，同时将骨架数据写入端侧本地缓存，后续进入参数页将命中缓存

- AC-01-03（MQTT 连接后实时值叠加）
  - Given 已知骨架面板列表已渲染，MQTT 连接已建立，页面已订阅 `/screen/upload/screen/to/cloud/{screenMac}`
  - When 收到 `DeviceStatusUpdate` 报文（含 deviceSn 和 attrTag/attrValue 列表）
  - Then 对应面板中匹配该 deviceSn 的参数行，其参数值从「采集中…」更新为实际值（格式化展示，如 on/off→开/关，cold→制冷，26.0→26.0 ℃），骨架不重绘，仅值区域更新

- AC-01-04（无绑定房间）
  - Given 已知业主未绑定任何 specific_part
  - When 业主进入参数设置页
  - Then 页面显示「您还没有绑定专有部分」提示，并提供「去绑定」入口，不渲染任何面板

- AC-01-05（多 specific_part 绑定）
  - Given 已知业主绑定了多个 specific_part（如两套房）
  - When 业主进入参数设置页
  - Then 页面以每个 specific_part 独立展示其面板列表（如按套户分组/分区），或提供套户切换方式，具体交互方式为实现层决策 [INFERRED — requires PM confirmation on multi-unit display]

---

**US-02: 在 tab1「设置」中修改主要参数并下发（写链路）**

- **用户故事**：As a 业主，I want to 在某个设备/房间面板的 tab1「设置」中找到主要可写参数、调整目标值、点击下发，so that 对应设备的参数快速生效，操作路径比逐条设备查找更简洁。
- **关联需求**：REQ-FUNC-002、REQ-FUNC-003、REQ-FUNC-008
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- AC-02-01（进入 tab1，看到主要可写属性控件）
  - Given 已知业主进入某面板（如「主机」面板），MQTT 已连接并收到该 deviceSn 的 DeviceStatusUpdate
  - When 业主点击 tab1「设置」
  - Then tab1 展示该设备主要可写属性的编辑控件（控件类型与当前值取自 `writable_attrs` 配置和 DeviceStatusUpdate 实时值）；开关类用 toggle，枚举类用选择器，数值类用步进器/数值输入

- AC-02-02（修改参数值，仅发生变化的项进入下发列表）
  - Given 已知 tab1 已展示控件，业主修改若干参数值（未修改其他参数）
  - When 业主确认修改并点击「下发更改」
  - Then 仅值发生变化的属性进入下发列表，未修改的属性不发送；UI 立即进入「下发中…」状态

- AC-02-03（DeviceWrite 报文正确构造）
  - Given 已知业主点击「下发更改」，下发列表非空
  - When 客户端处理下发请求
  - Then 客户端用后端下发的 screenMac（= 该 specific_part 的 OwnerInfo.unique_id）构造 DeviceWrite 报文：`header.name="DeviceWrite"`, `header.screenMac={screenMac}`, `payload.data.deviceSn={deviceSn}`, `payload.data.items=[{attrTag, attrValue}]`（attrValue 用语义串，不用 ×10 整数）；报文 publish 到 `/screen/service/cloud/to/screen/{screenMac}`

- AC-02-04（写确认：成功路径）
  - Given 已知 DeviceWrite 报文已发出，客户端正在监听 DeviceStatusUpdate
  - When 在 8s 内收到该 deviceSn 的 DeviceStatusUpdate，目标 attrTag 的 attrValue 变为目标值
  - Then tab1 中该参数行显示新值，UI 提示「下发成功」；该参数的 pending 编辑状态清除

- AC-02-05（写确认：超时路径）
  - Given 已知 DeviceWrite 报文已发出
  - When 8s 内未收到该 attrTag 变为目标值的 DeviceStatusUpdate
  - Then UI 提示「未确认，请重试或刷新」，不假报成功；该参数的 pending 编辑状态保留，用户可重试

- AC-02-06（部分成功：批量下发时）
  - Given 已知批量下发 N 个属性，其中 M 个成功确认、(N-M) 个超时
  - When 下发流程完成
  - Then UI 提示「部分成功（M/N）」，各属性分别显示成功/超时状态

---

**US-03: 在 tab2「详细」中查看设备所有属性（含只读）的当前值**

- **用户故事**：As a 业主，I want to 在某个设备/房间面板的 tab2「详细」中查看该设备的全部属性（包括温度、湿度、故障告警等只读属性），so that 我无需跳转其他页面即可了解设备的完整运行状态。
- **关联需求**：REQ-FUNC-002、REQ-FUNC-004
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- AC-03-01（tab2 展示全部属性：可写 + 只读）
  - Given 已知业主进入某面板，MQTT 已连接并收到该 deviceSn 的 DeviceStatusUpdate
  - When 业主点击 tab2「详细」
  - Then tab2 展示该 deviceSn 所有已收到的 attrTag 及其当前值（不限于可写白名单）；可写属性显示当前值并标注「可设置」徽章，只读属性显示当前值并标注「只读」徽章；tab2 不提供任何编辑控件

- AC-03-02（tab2 中不可发起写操作）
  - Given 已知业主在 tab2「详细」中查看属性
  - When 业主在 tab2 中点击任意属性行
  - Then 不触发任何写操作；可写属性行可提供「前往 tab1 设置」跳转提示（可选），但不在 tab2 内直接展示编辑控件

- AC-03-03（实时值自动刷新）
  - Given 已知 tab2 已展示属性值，MQTT 持续推送 DeviceStatusUpdate
  - When 收到该 deviceSn 新的 DeviceStatusUpdate
  - Then tab2 中对应 attrTag 的值自动更新为最新值，无需手动刷新

- AC-03-04（值未收到时的占位显示）
  - Given 已知 tab2 已打开，但尚未收到该 deviceSn 的任何 DeviceStatusUpdate
  - When 业主查看 tab2
  - Then 各属性值显示「采集中…」占位；不显示空白或 undefined

---

**US-04: 骨架缓存命中时秒级渲染（性能）**

- **用户故事**：As a 业主，I want to 再次进入参数设置页时面板骨架立即呈现（无需等待网络），so that 页面不因骨架加载延迟而出现长时间白屏，操作体验流畅。
- **关联需求**：REQ-FUNC-005、REQ-FUNC-006、REQ-NFUNC-007
- **优先级**：Should Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- AC-04-01（缓存命中时骨架渲染时间 ≤ 300ms）
  - Given 已知业主此前已成功进入参数设置页（骨架缓存已写入），TTL 未过期
  - When 业主再次进入参数设置页
  - Then 从进入页面到面板骨架（面板标题、参数名称行）完整渲染完毕，耗时 ≤ 300ms；骨架渲染期间不发出 structure 接口请求（缓存命中路径）

- AC-04-02（骨架渲染不等待 MQTT 实时值）
  - Given 已知骨架已从缓存渲染完成
  - When MQTT 连接尚未建立或 DeviceStatusUpdate 尚未到达
  - Then 骨架渲染完成，各参数值显示「采集中…」占位；页面不因 MQTT 未连接而阻塞骨架显示

- AC-04-03（两阶段独立进行：骨架渲染与值叠加不互相阻塞）
  - Given 已知骨架已渲染，MQTT 连接建立中
  - When 收到第一条 DeviceStatusUpdate
  - Then 该 deviceSn 对应面板的参数值从「采集中…」更新为实际值；其他尚未收到值的面板保持「采集中…」，不触发骨架重绘

---

**US-05: 骨架缓存失效与刷新**

- **用户故事**：As a 业主，I want to 在骨架缓存过期或设备结构发生变化时能刷新到最新的设备/房间列表，so that 参数设置页展示的面板结构与我实际绑定的设备保持一致。
- **关联需求**：REQ-FUNC-005、REQ-FUNC-009
- **优先级**：Must Have（自动失效刷新 + 每次进入后台静默刷新）；手动刷新入口 ❌ 不做（OQ-03 确认）
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- AC-05-01（TTL 过期后自动重新拉取骨架）
  - Given 已知骨架缓存存在，但 TTL 已过期（正常情况下 24h 过期；sync_status=pending 时 5min 过期）
  - When 业主进入参数设置页
  - Then 系统从后端重新拉取 `GET /api/miniapp/owner/structure/?specific_part=...`；拉取成功后更新面板列表，并将新骨架写入缓存；拉取过程中若已有过期缓存数据，优先用过期缓存渲染骨架（降级策略，见 AC-05-04）

- AC-05-02（sync_status=pending 时 5min TTL）
  - Given 已知骨架响应中 sync_status=pending（设备尚未同步完成）
  - When 写入缓存
  - Then 该缓存 TTL 设为 5 分钟；面板显示「设备结构尚未就绪，请等待初始化后刷新」提示

- AC-05-03（每次进入后台静默刷新 —— OQ-03 确认，取代手动刷新入口）
  - Given 已知骨架缓存命中（TTL 30 天内），业主进入参数设置页
  - When 页面用缓存秒开渲染面板后
  - Then 系统**后台静默**重新拉取 `GET /api/miniapp/owner/structure/`，成功后覆盖缓存并更新面板（不阻塞已渲染骨架，不显示全屏加载）；因此"杀掉小程序后重新进入"即可获得最新设备结构，无需手动刷新按钮

- AC-05-04（网络拉取失败时的降级行为）
  - Given 已知骨架 TTL 已过期，且本次从后端拉取失败（网络不可达或接口错误，重试 3 次耗尽）
  - When 系统完成重试
  - Then 若存在过期缓存数据，使用过期缓存渲染面板列表，并显示「设备结构可能已过时」提示；若无任何缓存数据，显示错误提示「获取设备结构失败，请检查网络后重试」，提供手动重试按钮

---

**US-06: 动态面板——某房间/设备不存在时不渲染**

- **用户故事**：As a 业主，I want to 参数设置页只展示我绑定套户中实际存在的设备/房间面板，so that 页面不出现无内容的空面板，避免误操作。
- **关联需求**：REQ-FUNC-001、REQ-FUNC-007
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- AC-06-01（预设设备类型不存在时面板不渲染）
  - Given 已知业主绑定的 specific_part 骨架数据中，不存在 productCode=130004（新风）的设备
  - When 系统渲染面板列表
  - Then 「新风」面板不出现在面板列表中；其他存在的预设面板正常渲染，顺序不受影响

- AC-06-02（房间面板按骨架数据动态渲染）
  - Given 已知骨架数据中 `structure.rooms` 只有两个条目（如主卧、次卧）
  - When 系统渲染面板列表
  - Then 仅渲染「主卧」和「次卧」两个房间面板；不渲染「书房」「儿童房」或其他硬编码名称的空面板

- AC-06-03（所有预设类型均存在时全部渲染）
  - Given 已知骨架数据中，主机/新风/主温控（各一个设备）和四个房间均有对应设备数据
  - When 系统渲染面板列表
  - Then 渲染全部 7 个面板：主机、新风、主温控、主卧、次卧、书房、儿童房（或按实际 room_name）

- AC-06-04（room_name 为空时的 fallback）
  - Given 已知骨架数据中某条 rooms 记录的 `room_name` 字段为空或 null，`ori_room_name` 有值
  - When 渲染该房间面板标题
  - Then 面板标题使用 `ori_room_name`；若 `ori_room_name` 也为空，显示「未知房间」

---

**US-07: 写确认反馈（继承 v1.10.0 US-04）[继承 v1.10.0]**

- **用户故事**：As a 业主，I want to 在点击下发后能清楚看到参数是「下发中」「成功」还是「超时未确认」，so that 我能判断是否需要重试，不会被假成功误导。
- **关联需求**：REQ-FUNC-008、REQ-NFUNC-003、REQ-NFUNC-005
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- AC-07-01（下发后 ≤2s 给出已提交反馈）
  - Given 已知业主在 tab1「设置」中完成参数修改
  - When 业主点击「下发更改」
  - Then 在 ≤2s 内，UI 进入「下发中…」状态（按钮灰化/加载指示），向用户反馈已提交

- AC-07-02（成功确认路径）
  - Given 已知 DeviceWrite 报文已通过 MQTT 发出
  - When 在 8s 内，监听到该 deviceSn 的 DeviceStatusUpdate，目标 attrTag 的 attrValue 与目标值一致
  - Then UI 显示「下发成功」提示，对应参数行的当前值更新为新值，pending 编辑状态清除

- AC-07-03（超时未确认路径）
  - Given 已知 DeviceWrite 报文已发出
  - When 8s 超时，未收到目标 attrTag 变为目标值的确认
  - Then UI 显示「未确认，请重试或刷新」；该参数的 pending 编辑状态保留（用户不丢失修改值，可重试）；不标记为成功，不假报完成

- AC-07-04（broker 不可达时明确失败）
  - Given 已知 MQTT broker 不可达或 publish 未获 PUBACK
  - When 业主尝试下发
  - Then 返回明确失败提示（如「设备通道连接失败」），不进入「下发中…」状态，不标记任何成功

- AC-07-05（审计上报）
  - Given 已知一次下发流程（成功或超时）完成
  - When 流程结束
  - Then 调用 `POST /api/miniapp/device-settings/audit/` 上报审计记录（含 request_id、specific_part、screen_mac、device_sn、attr_tag、old_value、new_value、result）；上报失败不阻塞主流程，静默降级

---

**US-08: 零回归（继承 v1.10.0 US-09）[继承 v1.10.0]**

- **用户故事**：As a 现有 web 运维/管理员，I want to 本次小程序参数设置页重设计上线后，web 端参数设置和 datacollection S7 链路的行为与上线前完全一致，so that 现有运维工作流不受影响，生产系统保持稳定。
- **关联需求**：C-01、REQ-NFUNC-006
- **优先级**：Must Have
- **故事点**：N/A（约束型故事，无实现工作量）

**验收标准：**

- AC-08-01（web 参数设置接口零回归）
  - Given 已知 v1.12.0 已上线
  - When 运维人员在 web 端使用 `/api/device-settings/*` 接口下发参数
  - Then 接口行为、响应结构、鉴权逻辑与 v1.12.0 上线前完全一致；无任何接口变更

- AC-08-02（datacollection S7 写链路零回归）
  - Given 已知 v1.12.0 已上线
  - When datacollection 的 S7 写订阅器（plc_write_subscriber.py）运行
  - Then 其代码、配置、依赖均未被 v1.12.0 改动所影响；S7 写入正常执行

- AC-08-03（小程序 MQTT 写链路语义零变更）
  - Given 已知 v1.12.0 参数设置页发布
  - When 业主在小程序使用 tab1「设置」下发参数
  - Then DeviceWrite 报文格式、attrTag/attrValue 编码（语义串）、下发主题、写确认机制与 v1.10.0/v1.11.x 实现完全一致；仅 UI 组织方式改变，写链路无语义变更

- AC-08-04（后端接口无新增或变更）
  - Given 已知 v1.12.0 改动范围限于小程序前端代码
  - When 检查后端代码变更
  - Then `/api/miniapp/device-settings/config/`、`/api/miniapp/owner/realtime-params/`、`/api/miniapp/owner/structure/`、`/api/miniapp/device-settings/audit/` 均无接口逻辑变更（仅前端调用方式可能调整，接口本身零变更）

---

## 故事-OQ 依赖矩阵

| 故事 | 关键依赖 / OQ | 状态 |
|------|------------|------|
| US-01 | REQ-FUNC-007（动态面板）；OQ-04（区域一是否合并影响页面结构） | OQ-04 待确认 |
| US-02 | **OQ-01（tab1 主要属性字段，BLOCKING）**；AC-02-03 依赖 v1.10.0 DeviceWrite 协议实测结论 | OQ-01 待确认 |
| US-03 | OQ-04（tab2「详细」是否同时承载「我的房产」绑定信息） | OQ-04 待确认 |
| US-04 | OQ-02（骨架预取时机，影响首进页面的缓存命中率） | OQ-02 待确认 |
| US-05 | OQ-03（失效策略），OQ-03=A 时 AC-05-03（手动刷新）为 Could Have | OQ-03 待确认 |
| US-06 | OQ-06（主温控归属，影响面板渲染结构） | OQ-06 待确认 |
| US-07 | 继承 v1.10.0 OQ-05（无独立写回执，已实测确认）；继承 v1.10.0 OQ-07（值编码，已实测确认） | 无新阻塞 |
| US-08 | 约束型，无 OQ 依赖 | 无阻塞 |

> **✅ 2026-06-29：OQ-01~OQ-06 已全部确认（见 requirements_spec.md §5），所有故事进入开发态。** 已实现于 `miniprogram/subpackages/control/pages/param-settings.vue` + `utils/paramPanels.js`；纯逻辑单测见 `miniprogram/tests/param_settings_panels.spec.js`（25 用例全绿）。
