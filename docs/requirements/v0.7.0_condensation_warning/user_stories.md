# 用户故事

```
file_header:
  document_id: US-v0.7.0-CW
  title: 结露预警管理页面 — 用户故事
  author_agent: PM Orchestrator (PARTIAL_FLOW, 需求阶段)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.7.0-condensation-warning
  created_at: 2026-05-29
  last_updated: 2026-05-30 (v0.3.0)
  status: APPROVED
  references:
    - docs/requirements/v0.7.0_condensation_warning/requirements_spec.md
    - docs/requirements/v0.6.0_fault_management/user_stories.md
    - docs/requirements/v0.6.4_fault_mgmt_room_column/user_stories.md
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-29 | 初始草稿，US-CW-01~US-CW-08；开放问题 OQ-01~OQ-11 同 requirements_spec.md |
| 0.2.0-APPROVED | 2026-05-30 | 按用户裁决定稿：OQ-01~OQ-11 全部落地；更新 AC 措辞以消除所有"待裁决"引用；调整 AC-CW-01-01/03/04 以反映快照字段规则和「回复」语义；无新增用户故事（US-CW-01~08 完整保留） |
| 0.3.0-APPROVED | 2026-05-30 | DEV-CHECK-01/02 确认后更新：修订 AC-CW-01-01（system_switch 同报文取值 → 跨报文兜底的双路径行为明确化）；新增 AC-CW-01-08（system_switch 跨设备取值专项 AC，明确兜底来自关联水力模块最近已知值）。 |

---

## 角色定义

| 角色 | 描述 |
|------|------|
| **运维人员** | 负责平台日常维护、故障响应、设备巡检的后台工作人员 |
| **物业管理员** | 管理多户住宅的物业人员，需要关注哪些房间存在结露风险 |
| **系统管理员** | 负责平台配置、服务运维（systemd 管理、日志查看）的技术人员 |

---

## 用户故事清单

共 8 条用户故事（US-CW-01 ~ US-CW-08），P0：3 条，P1：3 条，P2：1 条，P0（基础设施）：1 条。

---

### US-CW-01：结露预警事件自动持久化

**作为** 运维人员，
**我希望** 系统能自动从 MQTT 上报的设备状态报文中识别 `condensation_alarm` 字段，并将结露预警事件连同触发时刻的环境参数快照一起保存到数据库，
**以便** 我可以追溯任意住户何时发生过结露风险，以及当时的露点温度、NTC 温度、湿度和系统开关状态。

**优先级**：P0（核心需求，其他故事的基础）

**验收标准**：

- **AC-CW-01-01（正常预警入库，含快照字段）**
  - Given：`freeark-condensation-consumer` 服务正在运行，MQTT broker 连接正常
  - When：收到一条 `DeviceStatusUpdate` 报文，其中某设备的 `items[]` 包含 `condensation_alarm` 值为非零（如 `"1"`），同时携带 `dew_point_temp`、`NTC_temp`、`humidity` 字段，且同一报文同一 deviceSn 的 `items[]` 中也含 `system_switch`（如 260001 设备的完整报文）
  - Then：`condensation_warning_event` 表中新增一条记录；`is_active=True`；`first_seen_at` 记录服务器接收时间；`specific_part` 正确映射到对应房号；`dew_point_temp`、`ntc_temp`、`humidity` 取自同一 MQTT 报文同一 deviceSn 的 `items[]` 快照值写入；`system_switch` 直接取自同一报文的 `system_switch` attrTag 值；`condensation_alarm_value` 记录原始值（如 "1"）

- **AC-CW-01-02（快照字段缺失时 NULL 兜底）**
  - Given：收到一条 `DeviceStatusUpdate` 报文，`condensation_alarm` 非零，但报文 `items[]` 中无 `dew_point_temp` 或 `humidity` 字段
  - When：T1 INSERT 执行
  - Then：缺失字段写入 NULL；其余字段正常写入；不报错、不丢弃该预警记录

- **AC-CW-01-03（重复报文不重复插入）**
  - Given：进程内内存表已有 `(specific_part="3-1-7-702", device_sn="22554") → (event_id=N, is_active=True)`
  - When：再次收到同一设备的 `condensation_alarm="1"` 报文
  - Then：不新增 DB 记录（T2 路径）；仅更新内存中的 `last_seen_at`；`condensation_warning_event` 表行数不变

- **AC-CW-01-04（设备自动恢复写回，即「已回复」）**
  - Given：内存表中某设备处于活跃预警状态（is_active=True）
  - When：收到该设备的 `condensation_alarm="0"` 报文（设备恢复正常）
  - Then：`condensation_warning_event` 中对应记录被 UPDATE：`is_active=False`（「已回复」），`recovered_at` 记录恢复时间，`last_seen_at` 写回内存中的最后活跃值；**不需要任何人工操作**

- **AC-CW-01-05（未识别 MAC 的容错）**
  - Given：收到某 screenMAC 的报文，该 MAC 不在 OwnerInfo 表中
  - Then：记录 WARNING 日志（如 "未找到 screenMAC=xxxx 对应的 specific_part，跳过"）；不写入 DB；服务继续运行不崩溃

- **AC-CW-01-06（进程重启后状态机重建）**
  - Given：`freeark-condensation-consumer` 进程因任意原因重启
  - When：进程启动完成（Django setup() + ORM 可用后）
  - Then：从 `condensation_warning_event` 表加载所有 `is_active=True` 的记录（LIMIT 10000），重建进程内内存表；重建后收到已活跃预警的 `condensation_alarm="1"` 报文时，走 T2 路径（不重复 INSERT）；journald 日志显示"状态机重建完成，共加载 N 条活跃预警"

- **AC-CW-01-07（无法解析的 condensation_alarm 值容错）**
  - Given：收到报文，`condensation_alarm` 值无法转换为 int（如空字符串、非数字字符串）
  - When：消费服务处理该条目
  - Then：视为正常态（不触发 T1 或 T3），记录 WARNING 日志；服务继续运行不崩溃

- **AC-CW-01-08（system_switch 跨设备取值 — 温控面板触发时的兜底行为）**
  > 本 AC 对应 DEV-CHECK-02 已确认约束：温控面板（product_code 120003）的触发报文中通常不含 system_switch，该字段来自同 specific_part 的水力模块（260001/270001/10016 等）。
  - **AC-CW-01-08a（触发报文无 system_switch 时，取关联水力模块最近已知值）**
    - Given：收到温控面板（如 product_code 120003，deviceSn 22549）的 `condensation_alarm` 非零报文，该报文 `items[]` 中**无** `system_switch` attrTag
    - When：T1 INSERT 执行
    - Then：消费侧查询同 `specific_part` 关联水力模块的最近已知 `system_switch` 值（数据来源由架构设计确定，见需求 §6.3 ARCH-PENDING-01）；若查到有效值，写入 `condensation_warning_event.system_switch`；若查不到，写入 `"unknown"`；`dew_point_temp`、`ntc_temp`、`humidity` 仍正常取自触发报文
  - **AC-CW-01-08b（system_switch 完全不可用时的兜底）**
    - Given：触发报文无 system_switch，且同 specific_part 无任何水力模块历史记录（或关联关系尚未建立）
    - When：T1 INSERT 执行
    - Then：`system_switch` 字段写入 `"unknown"`；预警记录正常插入，不因 system_switch 缺失而丢弃或报错；日志记录"specific_part=xxx 未找到关联水力模块的 system_switch 历史值，写入 unknown"

---

### US-CW-02：结露预警管理页面——基础展示

**作为** 运维人员，
**我希望** 在「设备管理」菜单下有一个「结露预警」子页面，能以列表形式查看所有结露预警事件，
**以便** 我快速了解哪些住户当前存在或历史上发生过结露风险。

**优先级**：P0

**验收标准**：

- **AC-CW-02-01（菜单导航入口）**
  - Given：用户已登录，位于任意页面
  - When：展开左侧导航「设备管理」子菜单
  - Then：子菜单显示三项：「设备列表」、「故障管理」、「结露预警」（新增，排列在故障管理之后）

- **AC-CW-02-02（页面可访问）**
  - Given：用户点击「结露预警」菜单项
  - When：页面加载完成
  - Then：路由切换到 `/device-management/condensation-warnings`；页面标题显示「结露预警」；默认加载最近 7 天、`is_active=true` 的预警记录（"未回复"状态）

- **AC-CW-02-03（列表字段完整）**
  - Given：`condensation_warning_event` 表中存在若干条记录
  - When：用户查看列表
  - Then：每行显示以下 12 列：房号、房间、大屏是否在线、系统开关、预警类型、预警内容、露点温度、NTC 温度、湿度、预警发生时间、最后活跃、恢复时间；NULL 字段显示 "-"

- **AC-CW-02-04（分页功能）**
  - Given：数据库中存在超过 20 条满足当前过滤条件的记录
  - When：默认加载第一页
  - Then：每页显示 20 条；显示总记录数；支持切换每页条数（10/20/50）；可翻页

---

### US-CW-03：按回复状态筛选

**作为** 运维人员，
**我希望** 可以按「未回复（活跃中）/ 已回复（已恢复）/ 全部」筛选结露预警记录，
**以便** 我快速聚焦于需要关注的活跃预警，或复盘历史已恢复预警。

> **语义说明**：「未回复」= `is_active=True`（设备仍处于结露报警状态）；「已回复」= `is_active=False`（设备已自动恢复正常）。「回复」不代表人工操作，仅指设备状态恢复。

**优先级**：P0

**验收标准**：

- **AC-CW-03-01（默认只看未回复）**
  - Given：用户首次打开「结露预警」页面
  - When：页面加载完成
  - Then：回复状态控件默认选中「未回复」；列表只显示 `is_active=True` 的记录

- **AC-CW-03-02（切换到「已回复」）**
  - Given：用户在回复状态控件中选择「已回复」
  - When：筛选生效
  - Then：列表只显示 `is_active=False` 的记录（设备已自动恢复）；每条记录的「恢复时间」列均有非空值

- **AC-CW-03-03（切换到「全部」）**
  - Given：用户在回复状态控件中选择「全部」
  - When：筛选生效
  - Then：列表显示所有记录（不按 `is_active` 过滤）；活跃记录「恢复时间」列显示 "-"

- **AC-CW-03-04（控件形态）**
  - Given：用户查看回复状态控件区域
  - When：页面渲染完成
  - Then：控件为 `<el-radio-group>` 三按钮样式，与故障管理页的回复状态控件风格一致

---

### US-CW-04：按房号筛选

**作为** 物业管理员，
**我希望** 可以按房号精确筛选结露预警记录，
**以便** 我快速找到特定住户的预警历史。

**优先级**：P1

**验收标准**：

- **AC-CW-04-01（CascadingSelector 控件）**
  - Given：用户打开「结露预警」页面
  - When：查看房号筛选控件
  - Then：房号筛选使用 `CascadingSelector` 三级联动（楼栋→单元→房号），与故障管理页风格一致

- **AC-CW-04-02（楼栋级别筛选）**
  - Given：用户通过 CascadingSelector 选择楼栋「3」
  - When：执行查询
  - Then：列表只显示 `specific_part` 以 `"3-"` 开头的预警记录

- **AC-CW-04-03（具体房号精确筛选）**
  - Given：用户通过 CascadingSelector 选择「3 栋 1 单元 702」
  - When：执行查询（前端传参 `specific_part=3-1-702`，3 段格式）
  - Then：后端将 3 段格式映射为 4 段过滤逻辑（`startswith='3-1-'` AND `endswith='-702'`）；列表只显示对应房间的预警记录

- **AC-CW-04-04（清空房号筛选）**
  - Given：用户已选择某房号，现在清空 CascadingSelector
  - When：查询执行
  - Then：房号条件取消，列表显示其他过滤条件匹配的全部记录

---

### US-CW-05：按时间段筛选

**作为** 运维人员，
**我希望** 可以按「预警发生时间」筛选一个时间段内的预警记录，
**以便** 我复盘某段时间内的结露预警分布情况。

**优先级**：P1

**验收标准**：

- **AC-CW-05-01（默认时间范围）**
  - Given：用户首次打开「结露预警」页面
  - When：页面加载完成
  - Then：时间段过滤器默认填入「最近 7 天」（起止时间自动计算）；列表按此范围过滤

- **AC-CW-05-02（自定义时间段）**
  - Given：用户通过日期范围选择器选择自定义时间段（如 2026-05-01 至 2026-05-29）
  - When：查询执行
  - Then：列表只显示 `first_seen_at` 落在所选范围内的预警记录

- **AC-CW-05-03（时间范围跨越多月）**
  - Given：用户选择一个跨 30 天以上的时间段
  - When：查询执行
  - Then：后端正确处理较大时间范围（不报 500 错误）；返回该范围内的全部记录（分页）

---

### US-CW-06：大屏在线状态展示

**作为** 运维人员，
**我希望** 在结露预警列表中能看到每个住户大屏当前是否在线，
**以便** 我判断结露预警所在住户的通信链路是否正常。

**优先级**：P1

**验收标准**：

- **AC-CW-06-01（在线状态准确）**
  - Given：某住户（specific_part="3-1-7-702"）的大屏在最近 15 分钟内发过心跳（`ScreenConnectivityStatus.last_seen_at` 距今 ≤ 15 分钟）
  - When：用户查看该住户对应的预警记录行
  - Then：「大屏是否在线」列显示「在线」（绿色文字/标签）

- **AC-CW-06-02（离线状态准确）**
  - Given：某住户的大屏超过 15 分钟未发心跳，或 `ScreenConnectivityStatus` 表中无该住户记录
  - When：用户查看该住户对应的预警记录行
  - Then：「大屏是否在线」列显示「离线」（灰色文字/标签）

- **AC-CW-06-03（列表每行均实时计算）**
  - Given：用户查看结露预警列表，不论时间段过滤如何设置
  - When：页面加载或刷新
  - Then：「大屏是否在线」列对当前页每行均展示，反映查询时刻的实时在线状态（不受 first_seen_at 历史时间影响）

---

### US-CW-07：系统服务稳定运行

**作为** 系统管理员，
**我希望** `freeark-condensation-consumer` 服务能持续稳定运行，自动重连 MQTT broker，并在进程重启后快速恢复状态，
**以便** 不遗漏任何结露预警事件。

**优先级**：P0

**验收标准**：

- **AC-CW-07-01（systemd 服务注册）**
  - Given：服务已部署到生产树莓派
  - When：执行 `sudo systemctl status freeark-condensation-consumer`
  - Then：服务状态为 `active (running)`；`Restart=on-failure` 已配置

- **AC-CW-07-02（MQTT 断连自动重连）**
  - Given：MQTT broker 因网络抖动短暂断开
  - When：broker 恢复正常
  - Then：`freeark-condensation-consumer` 自动重连，重连后继续正常消费消息；journald 日志可见重连过程

- **AC-CW-07-03（进程重启恢复）**
  - Given：执行 `sudo systemctl restart freeark-condensation-consumer`
  - When：进程重启完成并加载状态机
  - Then：journald 日志显示状态机重建记录（如 "状态机重建完成，共加载 N 条活跃预警"）；随后收到的预警报文被正确处理（T2 路径，不重复 INSERT）

---

### US-CW-08：数据清理服务

**作为** 系统管理员，
**我希望** `condensation_warning_event` 表能自动清理 90 天以前的已恢复预警记录，
**以便** 数据表不会无限膨胀，影响数据库性能。

**优先级**：P2

**验收标准**：

- **AC-CW-08-01（定时执行）**
  - Given：`freeark-condensation-cleanup` 服务和 timer 已部署
  - When：每天 03:30 定时触发
  - Then：执行 Django management command `condensation_cleanup`；journald 日志记录本次清理行数和耗时

- **AC-CW-08-02（90 天边界正确）**
  - Given：`condensation_warning_event` 表中存在 `first_seen_at` 早于 90 天前、且 `is_active=False` 的记录
  - When：清理服务执行
  - Then：上述记录被硬删除；`first_seen_at` 在 90 天内的记录不受影响

- **AC-CW-08-03（活跃记录豁免）**
  - Given：`condensation_warning_event` 表中存在 `first_seen_at` 早于 90 天前、且 `is_active=True` 的记录（长期活跃未恢复的预警）
  - When：清理服务执行
  - Then：上述记录**不被删除**（活跃预警始终保留，无论多久）

- **AC-CW-08-04（分批执行防大事务）**
  - Given：待清理记录超过 1000 条
  - When：清理服务执行
  - Then：分批删除，每批 ≤ 1000 条；不产生单次大事务锁表；整体清理在合理时间内完成

---

## 附录：与故障管理用户故事的对照

以下对照说明本版本用户故事与故障管理（v0.6.0 + v0.6.1~v0.6.4）用户故事的继承关系：

| 本版本 US | 对应故障管理 US | 复用程度 | 主要差异 |
|-----------|-------------|---------|---------|
| US-CW-01 | US-FM-01 | 高度复用 | 触发字段由多故障码改为单字段 `condensation_alarm`；新增快照字段于 T1 INSERT 时写入：dew_point_temp/ntc_temp/humidity 取自触发报文同 deviceSn，**system_switch 跨设备取关联水力模块最近已知值**（已确认约束，DEV-CHECK-02）；新增 AC-CW-01-08 专项覆盖此行为；「回复」锚定为设备自动恢复（is_active 语义完全一致） |
| US-CW-02 | US-FM-03 | 高度复用 | 列定义不同（新增大屏在线/系统开关/露点温度等，去除 fault_code/fault_type/severity） |
| US-CW-03 | US-FM-UX-04 | 完全复用 | 三态 radio-group，「未回复/已回复/全部」UI 标签与故障管理「未恢复/已恢复/全部」仅标签名不同，底层均为 is_active 过滤 |
| US-CW-04 | US-FM-UX-02 | 完全复用 | CascadingSelector + 段数映射逻辑完全一致 |
| US-CW-05 | US-FM-01（时间范围部分） | 完全复用 | 时间范围过滤器逻辑一致 |
| US-CW-06 | 无对应 | **新增** | 大屏在线状态展示为结露预警专有需求，列表每行实时计算 |
| US-CW-07 | US-FM-01（服务稳定性部分） | 高度复用 | 服务名称不同；状态机 key 无 fault_code 维度 |
| US-CW-08 | US-FM-09 | 完全复用 | 服务名称不同，清理策略完全一致（90 天，活跃豁免，分批 1000 条） |
