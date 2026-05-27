# 用户故事与验收标准

```
file_header:
  document_id: REQ-US-v0.5.3-FCC
  title: 设备列表「故障数量」列 + OpenClaw 故障查询工具 — 用户故事
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: v0.5.3-fault-count-column
  created_at: 2026-05-26
  status: DRAFT
  references:
    - docs/requirements/v0.5.3_fault_count_column/requirements_spec.md
    - FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue
    - FreeArkWeb/frontend/src/views/DeviceCardsView.vue
    - agents/freeark-skill/SKILL.md
```

---

## US-FC-01：运维人员一眼识别哪些户有故障

**角色**：运维人员  
**需求编号**：REQ-FUNC-FC-01, REQ-FUNC-FC-02

> **作为**运维人员，  
> **我希望**在「设备列表」页能直接看到每个专有部分的当前故障数量，  
> **以便于**快速定位需要优先处理的户，不必逐一进入设备面板检查。

### 验收标准（Given / When / Then）

**AC-FC-01-01：正常有无故障的户显示绿色 0**

- Given：我已登录 FreeArk 管理界面，进入「设备列表」页
- When：某专有部分（如 `3-1-7-702`）的所有子设备当前无任何故障（`PLCLatestData` 中所有 `comm_fault_timeout` = 0，所有 `error_<N>` = 0）
- Then：该行「故障数量」列显示数字 `0`，字体颜色为绿色（CSS class `.status-ok` 或等效内联样式 `color: var(--color-success)`）

**AC-FC-01-02：有故障的户显示红色非零数字**

- Given：我已登录 FreeArk 管理界面，进入「设备列表」页
- When：某专有部分（如 `3-1-8-802`）的子设备中有 3 个故障位（例如 `living_room_temp_sensor_error=1`、`fresh_air_unit_communication_error=1`、`comm_fault_timeout=1`）
- Then：该行「故障数量」列显示数字 `3`，字体颜色为红色（CSS class `.status-fault` 或等效内联样式 `color: var(--color-danger)`）

**AC-FC-01-03：「故障数量」列插入正确位置**

- Given：我查看「设备列表」页的表格列
- When：页面完全加载
- Then：「故障数量」列位于「运行模式」列右侧，「操作」列左侧，列宽约 100px，列头文字居中对齐

**AC-FC-01-04：无数据时显示占位符**

- Given：某专有部分在 `PLCLatestData` 中没有任何参数记录（如新入网但未收到 MQTT 数据）
- When：该行出现在设备列表中
- Then：「故障数量」列显示 `—`（Em dash），不显示 0 也不显示错误

**AC-FC-01-05：翻页后故障数量随新数据更新**

- Given：我在「设备列表」第 1 页查看故障数量
- When：我翻到第 2 页
- Then：第 2 页每行的故障数量数据正确对应该行的专有部分，不出现数据错位或复用第 1 页缓存数据的情况

---

## US-FC-02：故障数量统计口径与设备面板一致

**角色**：运维人员 / 系统质检员  
**需求编号**：REQ-FUNC-FC-03

> **作为**系统质检员，  
> **我希望**设备列表的故障数量统计口径与设备面板展示的故障定义完全一致，  
> **以便于**两个页面的数据互相印证，避免运维人员产生困惑。

### 验收标准

**AC-FC-02-01：故障数量与设备面板故障数一致**

- Given：专有部分 `3-1-7-702` 的设备面板（`DeviceCardsView.vue`）显示 5 个参数为「故障」状态（红色文字）
- When：我在设备列表页查看同一专有部分的「故障数量」列
- Then：显示数字 `5`，与设备面板的故障参数总数一致（误差 ≤ 0，需完全相同）

**AC-FC-02-02：新风机故障位域展开计数与面板一致**

- Given：新风机 `fresh_air_fault_status` 的值使得位 0（风机状态故障）和位 2（进风温度传感器故障）被置 1，共 2 个故障
- When：我查看该专有部分在设备列表和设备面板的故障信息
- Then：设备列表「故障数量」计为 2（与设备面板展示的 2 个红色故障行一致）

> 注：新风机故障位域的展开方式由架构阶段确认（见开放问题 OQ-03），本 AC 作为最终验收目标。

**AC-FC-02-03：comm_fault_timeout 故障纳入计数**

- Given：某专有部分的 `comm_fault_timeout` 参数在 `PLCLatestData` 中值为 `1`（PLC 通信故障）
- When：我查看设备列表中该行的「故障数量」
- Then：该故障被计入总数（即总数 ≥ 1）

---

## US-FC-03：API 查询单个专有部分的故障详情

**角色**：运维人员 / OpenClaw AI 助手  
**需求编号**：REQ-FUNC-FC-05

> **作为**运维人员（或代表我行动的 AI 助手），  
> **我希望**能通过 REST API 查询指定专有部分的当前故障数量和故障明细，  
> **以便于**快速获取精确的故障信息用于排查和上报。

### 验收标准

**AC-FC-03-01：成功查询单个专有部分**

- Given：已登录用户（Token 有效），专有部分 `3-1-7-702` 在系统中存在且有 2 个故障
- When：发起请求 `GET /api/devices/fault-count/?specific_part=3-1-7-702`
- Then：响应状态码 200，响应体包含 `"fault_count": 2` 及 `fault_details` 数组（含 2 条故障记录），`success: true`

**AC-FC-03-02：批量查询多个专有部分**

- Given：已登录用户，查询 `3-1-7-702,3-1-7-703,3-1-7-704` 三个专有部分
- When：发起请求 `GET /api/devices/fault-count/?specific_part=3-1-7-702,3-1-7-703,3-1-7-704`
- Then：响应状态码 200，`data` 数组包含 3 个对象，每个对象有独立的 `fault_count` 和 `fault_details`

**AC-FC-03-03：未登录时返回 401**

- Given：未登录（无 Token 或 Token 无效）
- When：发起请求 `GET /api/devices/fault-count/?specific_part=3-1-7-702`
- Then：响应状态码 401，不返回故障数据

**AC-FC-03-04：specific_part 不存在时返回对应标记**

- Given：已登录用户，查询不存在的 specific_part `99-9-9-999`
- When：发起请求 `GET /api/devices/fault-count/?specific_part=99-9-9-999`
- Then：响应状态码 200，`data` 数组该条目 `fault_count: null`（表示无法获取数据），不影响其他条目的正常返回

**AC-FC-03-05：查询超过 50 个时返回 400**

- Given：已登录用户，查询参数包含 51 个以逗号分隔的 specific_part
- When：发起请求
- Then：响应状态码 400，错误信息说明上限为 50 个

---

## US-FC-04：OpenClaw AI 助手查询故障数量

**角色**：使用 OpenClaw 的运维人员  
**需求编号**：REQ-FUNC-FC-06

> **作为**使用 OpenClaw AI 助手的运维人员，  
> **我希望**能用自然语言询问哪些设备有故障、某户的故障情况，  
> **以便于**不记得具体 specific_part 格式或 API 路径时也能快速获取信息。

### 验收标准

**AC-FC-04-01：询问单户故障数**

- Given：我在 OpenClaw 聊天界面
- When：我询问"702 的故障情况怎么样？"或"查一下 3-1-7-702 的故障数"
- Then：OpenClaw 调用 `freeark_get_fault_count` 工具，回复该户当前故障数量及故障参数名列表（如"当前 3 个故障：客厅温度传感器故障、新风机通讯故障、PLC 通信故障"）

**AC-FC-04-02：询问全系统故障汇总**

- Given：我在 OpenClaw 聊天界面
- When：我询问"哪些户有故障？"或"当前故障汇总"
- Then：OpenClaw 调用 `freeark_get_fault_summary` 工具，回复有故障的专有部分列表（按故障数降序），最多显示前 10~20 条并注明总数

**AC-FC-04-03：询问特定楼栋故障**

- Given：我在 OpenClaw 聊天界面
- When：我询问"3 号楼有哪些故障？"
- Then：OpenClaw 调用 `freeark_get_fault_summary` 工具（传入 `building=3`），只返回 3 号楼的有故障专有部分列表

**AC-FC-04-04：无故障时的正确回复**

- Given：我询问"702 有没有故障？"
- When：`freeark_get_fault_count` 返回 `fault_count: 0`
- Then：OpenClaw 回复"702（3-1-7-702）当前无故障"，不做错误的故障告警

**AC-FC-04-05：API 调用失败时的优雅降级**

- Given：freeark-backend 服务异常导致 API 返回 5xx
- When：OpenClaw 调用 `freeark_get_fault_count` 失败
- Then：OpenClaw 回复"当前无法获取故障信息（后端服务异常），请稍后重试或检查 `freeark-backend` 服务状态"，不崩溃不卡死

---

## US-FC-05：故障数量实时更新（缓存一致性）

**角色**：运维人员  
**需求编号**：REQ-NFR-FC-01, REQ-NFR-FC-03

> **作为**实时监控设备状态的运维人员，  
> **我希望**「设备列表」中的故障数量能反映最新的设备状态（在合理延迟范围内），  
> **以便于**尽快发现新发生的故障。

### 验收标准

**AC-FC-05-01：故障数量数据时效（OQ-01 裁决后修订）**

- Given：某专有部分的 PLC 发生新故障，`PLCLatestDataHandler` 已将最新状态写入 `plc_latest_data` 表
- When：运维人员等待最多 **60 秒**后刷新「设备列表」页（或翻页再翻回）
- Then：该行故障数量已反映最新故障状态（即故障数最多有 **60 秒缓存延迟**，由 TTL 控制）

> 注：数据来源为 `plc_latest_data` 表（OQ-01 裁决：不依赖 MQTT 事件驱动失效）；实际延迟 = 缓存剩余 TTL + 用户下次翻页/刷新时间。

**AC-FC-05-02：故障恢复后数量归零**

- Given：某专有部分之前有 2 个故障，设备故障恢复后 `PLCLatestDataHandler` 已将恢复状态写入 `plc_latest_data`（故障字段变为正常值）
- When：运维人员等待最多 **60 秒**后刷新「设备列表」
- Then：该行故障数量变为 0（绿色），不继续显示已恢复的故障

**AC-FC-05-03：大屏离线时故障数量不自动清零**

- Given：某专有部分的大屏离线（未推送 MQTT），最后记录的故障数量为 3
- When：运维人员查看设备列表
- Then：故障数量仍显示 3（最后已知状态），不因大屏离线而清零；`updated_at` 字段反映该数据的时效（非当前时间）

---

## US-FC-06：性能约束（设备列表加载速度不显著退化）

**角色**：运维人员  
**需求编号**：REQ-NFR-FC-01

> **作为**日常使用「设备列表」页的运维人员，  
> **我希望**新增「故障数量」列后页面加载速度没有明显变慢（感知上不超过 +0.5 秒），  
> **以便于**不影响日常操作效率。

### 验收标准

**AC-FC-06-01：列表页加载时间不显著退化**

- Given：生产环境 MySQL 192.168.31.98:3306 在正常负载下
- When：请求 `/api/device-management/device-list/?page=1&page_size=20`（含 `fault_count` 字段）
- Then：P95 响应时间 ≤ 800ms（缓存热状态），无缓存时 ≤ 1200ms

**AC-FC-06-02：不触发 device_param_history 查询**

- Given：查询「设备列表」（含故障数量）
- When：后端执行 SQL 查询
- Then：MySQL 慢查询日志 / explain 分析中不出现 `device_param_history` 表的全表扫描

---

## 开放问题与待澄清项（OQ）

以下问题在需求/架构确认时需要与业务方或技术负责人确认，影响开发实现：

| 编号 | 问题描述 | 影响范围 | 优先级 |
|------|---------|---------|--------|
| OQ-01 | `FAULT_PARAMS` 中的具体参数名（如 `living_room_temp_sensor_error`）与 MQTT 报文中的 `error_<N>` 字段是否有直接的 1:1 映射？还是 PLC 固件将 `error_<N>` 字段解析后存入了带有具体含义的 `param_name`？ | 影响故障判定逻辑的实现方式 | 高 |
| OQ-02 | 故障数量是否需要按严重程度加权（如通讯故障权重 > 传感器故障权重）？当前需求定义为等权重计数。 | 影响 REQ-FUNC-FC-03 | 中 |
| OQ-03 | 新风机 `fresh_air_fault_status` 的故障位域（`FRESH_AIR_FAULT_BITS`，9 位）在设备列表故障计数中，是统计非零位数（最多 9）还是仅判断整体非零（计 1）？ | 影响 AC-FC-02-02 | 高 |
| OQ-04 | 「故障数量」列是否需要支持点击列头排序（按故障数量降序）？v0.5.3-FCC 暂不实现，但后续是否有需求？ | 影响前端列配置（若后续需要则需在后端 API 加 sort 参数支持） | 低 |
| OQ-05 | 「故障数量」列是否需要支持点击数字直接跳转到该户的设备面板（故障详情）？ | 影响前端交互设计 | 低 |
| OQ-06 | `freeark_get_fault_summary` 工具是否需要支持按 screenMAC 查询（即查某个大屏所有子设备的故障）？当前设计以 `specific_part` 为查询维度。 | 影响 OpenClaw 工具参数设计 | 中 |
| OQ-07 | 缓存策略选择：是用 Django 进程内缓存（无需额外基础设施），还是 Redis？生产环境（树莓派）目前是否已有 Redis？ | 影响架构设计 | 高 |
| OQ-08 | 故障数量是否需要在「设备列表」页面实时自动刷新（WebSocket 推送），还是仅在翻页/刷新时更新？ | 影响前端实现复杂度 | 中 |
| OQ-09 | `freeark_tool.py` 脚本目前通过 FreeArk REST API 调用，故障查询工具是否走内网 API（`http://127.0.0.1:<port>/api/...`），还是走外网地址？ | 影响 OpenClaw 工具实现配置 | 中 |
