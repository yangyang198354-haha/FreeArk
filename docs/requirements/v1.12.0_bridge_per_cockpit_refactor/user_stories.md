# 用户故事清单

**文档编号**: US-LIST-v1.12.0-BPCR-001
**项目名称**: FreeArk — 小程序舰桥 per-座舱重构
**版本**: 0.1.0
**状态**: APPROVED
**创建日期**: 2026-07-08
**作者**: sub_agent_requirement_analyst
**配套**: `requirements_spec.md`（同目录）

> 验收标准采用 Given / When / Then 格式。本清单覆盖 **owner（role=user）唯一角色** 在舰桥仪表盘上，涉及子系统状态 per-座舱重构的全部交互场景。

---

## 用户角色地图（Actor x Feature Matrix）

| 角色 | 新风 per-座舱 | 水力 per-座舱 | 空气品质 per-座舱 | 能耗 per-座舱 | 子系统动态显示 | 房间动态显示 | 抽屉对齐 Web | 新风 bit 展开 |
|------|-------------|-------------|-----------------|-------------|--------------|------------|-------------|--------------|
| owner | US-01 | US-02 | US-03 | US-04 | US-05 | US-06 | US-07 | US-08 |

---

## US-01：业主查看自己座舱的新风模块状态

**用户故事**：As a 业主，I want to 在舰桥页面看到的新风模块状态来自我自己座舱的新风机 PLC 实时参数，so that 我看到的故障信息是我家自己的设备状态，而不是全小区的汇总。

**关联需求**：REQ-FUNC-001、REQ-FUNC-012

**优先级**：Must Have

**故事点**：待开发团队评估

**验收标准：**

- **AC-01-01** 新风有故障
  - Given 当前座舱（specific_part）的新风机 PLC 实时参数中 `fresh_air_unit_communication_error = 1`
  - When 业主进入舰桥页面
  - Then "新风模块"隔舱显示红色/橙红色故障状态（色值 `#ff315d`），故障计数显示对应数量

- **AC-01-02** 新风正常
  - Given 当前座舱的新风机所有故障字段（`fresh_air_unit_stop_error`、`fresh_air_unit_communication_error`）均为 0 或 null，且 `fresh_air_fault_status` 所有 bit 均为 0
  - When 业主进入舰桥页面
  - Then "新风模块"隔舱显示正常状态（青蓝色霓虹线 `#2ff4e0`），无故障计数

- **AC-01-03** 新风机 bit 故障
  - Given 当前座舱的 `fresh_air_fault_status = 5`（bit 0 风机状态故障 + bit 2 进风温度传感器故障 同时激活，popcount = 2）
  - When 业主进入舰桥页面
  - Then "新风模块"隔舱显示故障状态，故障计数为 2

- **AC-01-04** 不同座舱新风状态不同
  - Given 座舱 A 的新风机所有故障字段为 0；座舱 B 的 `fresh_air_unit_communication_error = 1`
  - When 业主切换到座舱 A
  - Then "新风模块"显示正常状态
  - When 业主切换到座舱 B
  - Then "新风模块"显示故障状态

- **AC-01-05** 新风机参数不可用
  - Given 当前座舱的 `getOwnerRealtimeParams(sp)` 返回成功但数据中不含新风设备相关参数
  - When 业主进入舰桥页面
  - Then 若 structure 中有新风设备 → "新风模块"显示正常状态（无故障即正常）；若 structure 中无新风设备 → 不显示新风模块隔舱（见 US-05）

---

## US-02：业主查看自己座舱的水力模块状态

**用户故事**：As a 业主，I want to 在舰桥页面看到的水力模块状态来自我自己座舱的水力模块 PLC 实时参数，so that 不同座舱的水力模块状态各自独立，互不干扰。

**关联需求**：REQ-FUNC-002、REQ-FUNC-012

**优先级**：Must Have

**故事点**：待开发团队评估

**验收标准：**

- **AC-02-01** 水力模块有故障
  - Given 当前座舱的水力模块 PLC 实时参数中 `hydraulic_module_low_temp_error = 1`
  - When 业主进入舰桥页面
  - Then "水力模块"隔舱显示红色/橙红色故障状态，故障计数为 1

- **AC-02-02** 水力模块正常
  - Given 当前座舱的水力模块 `hydraulic_module_low_temp_error = 0`
  - When 业主进入舰桥页面
  - Then "水力模块"隔舱显示正常状态（青蓝色霓虹线），无故障计数

- **AC-02-03** 无座舱隔离
  - Given 座舱 A 的 `hydraulic_module_low_temp_error = 1`；座舱 B 的 `hydraulic_module_low_temp_error = 0`
  - When 业主查看座舱 B
  - Then "水力模块"显示正常状态
  - When 业主查看座舱 A
  - Then "水力模块"显示故障状态

---

## US-03：业主查看自己座舱的空气品质模块状态

**用户故事**：As a 业主，I want to 在舰桥页面看到的空气品质模块状态来自我自己座舱的空气品质传感器 PLC 实时参数，so that 我看到的空气品质告警反映的是我自己家的空气质量传感器状态。

**关联需求**：REQ-FUNC-003、REQ-FUNC-012

**优先级**：Must Have

**故事点**：待开发团队评估

**验收标准：**

- **AC-03-01** 空气品质传感器通信故障
  - Given 当前座舱的 `air_quality_sensor_communication_error = 1`
  - When 业主进入舰桥页面
  - Then "空气品质"隔舱显示故障状态，故障计数为 1

- **AC-03-02** 空气品质正常
  - Given 当前座舱的 `air_quality_sensor_communication_error = 0`
  - When 业主进入舰桥页面
  - Then "空气品质"隔舱显示正常状态，无故障计数

---

## US-04：业主查看自己座舱的能耗模块状态（来自 PLC 参数，非全局聚合）

**用户故事**：As a 业主，I want to 在舰桥页面看到的能耗模块状态来自我自己座舱的能耗表 PLC 实时参数，so that 能耗状态反映的是我家的电表设备状况，而不是小区整体的 PLC 在线率。

**关联需求**：REQ-FUNC-004、REQ-FUNC-010、REQ-FUNC-012

**优先级**：Must Have

**故事点**：待开发团队评估

**验收标准：**

- **AC-04-01** 能耗表通信故障
  - Given 当前座舱的能耗表 PLC 参数中 `energy_meter_status_communication_error = 1`
  - When 业主进入舰桥页面
  - Then "能耗中枢"隔舱显示故障状态，故障计数至少为 1

- **AC-04-02** 能耗正常
  - Given 当前座舱的能耗表所有故障字段均为 0（`energy_meter_status_communication_error = 0`，且无匹配 `error_\d+` 的非零字段）
  - When 业主进入舰桥页面
  - Then "能耗中枢"隔舱显示正常状态，无故障计数

- **AC-04-03** 能耗状态不受全局 PLC 在线率影响
  - Given 全局 PLC 在线率显示 50% 的 PLC 离线（小区级），但当前座舱的能耗表 `energy_meter_status_communication_error = 0`
  - When 业主进入舰桥页面
  - Then "能耗中枢"隔舱显示正常状态（座舱自己的能耗设备正常）

- **AC-04-04** 能耗状态不受小区其他户设备影响
  - Given 小区其他户的能耗表出现通信故障（FaultEvent 表中有 energy 相关记录），但当前座舱的能耗表所有故障字段为 0
  - When 业主进入舰桥页面
  - Then "能耗中枢"隔舱显示正常状态（不受其他户影响）

---

## US-05：子系统模块按座舱实际设备动态显示

**用户故事**：As a 业主，I want to 舰桥页面只显示我座舱实际安装了的子系统模块，so that 不会看到与我户无关的模块（如没有装新风的户型不显示新风模块）。

**关联需求**：REQ-FUNC-005、REQ-FUNC-011

**优先级**：Must Have

**故事点**：待开发团队评估

**验收标准：**

- **AC-05-01** 全设备座舱
  - Given 当前座舱的 `getOwnerStructure(sp)` 返回的 system_devices 包含 fresh_air、energy_meter、hydraulic_module、air_quality 四种设备
  - When 业主进入舰桥页面
  - Then 子系统隔舱区显示全部 4 个模块（新风、水力、空气品质、能耗）

- **AC-05-02** 缺少新风设备
  - Given 当前座舱的 system_devices 不包含 fresh_air 类型设备
  - When 业主进入舰桥页面
  - Then 子系统隔舱区不显示"新风模块"，仅显示该座舱实际拥有的子系统

- **AC-05-03** 缺少水力模块设备
  - Given 当前座舱的 system_devices 不包含 hydraulic_module 类型设备
  - When 业主进入舰桥页面
  - Then 子系统隔舱区不显示"水力模块"

- **AC-05-04** 单一子系统座舱
  - Given 当前座舱的 system_devices 仅包含 fresh_air 一种设备
  - When 业主进入舰桥页面
  - Then 子系统隔舱区仅显示"新风模块"一个隔舱

- **AC-05-05** 座舱切换时模块动态变化
  - Given 座舱 A 有新风和水力；座舱 B 仅有空气品质
  - When 业主从座舱 A 切换到座舱 B
  - Then 子系统隔舱区从显示"新风 + 水力"变为仅显示"空气品质"

---

## US-06：房间按座舱实际结构动态显示

**用户故事**：As a 业主，I want to 舰桥页面显示的房间列表与我座舱的实际房间结构一致，so that 不会看到户型不存在的房间隔舱，也不会漏掉实际有的房间。

**关联需求**：REQ-FUNC-006

**优先级**：Must Have

**故事点**：待开发团队评估

**验收标准：**

- **AC-06-01** 房间列表与结构一致
  - Given 当前座舱的 `getOwnerStructure(sp)` 返回 4 个房间：主卧、书房、客厅、儿童房
  - When 业主进入舰桥页面
  - Then 房间隔舱区显示 4 个房间，名称与结构数据一致

- **AC-06-02** 不同户型房间不同
  - Given 座舱 A 有 5 个房间（含主卧、书房、客厅、儿童房、第四儿童房）；座舱 B 有 3 个房间（仅主卧、客厅、书房）
  - When 业主切换到座舱 A
  - Then 房间隔舱区显示 5 个房间
  - When 业主切换到座舱 B
  - Then 房间隔舱区显示 3 个房间

- **AC-06-03** 房间隔舱反映该房间设备故障
  - Given 当前座舱结构中有"主卧"房间，该房间内的设备在 FaultEvent 中有 2 条活跃故障
  - When 业主进入舰桥页面
  - Then "主卧"房间隔舱显示故障状态（红色/橙红闪烁线），故障计数为 2

---

## US-07：点击子系统卡片弹出参数抽屉对齐 Web 设备面板

**用户故事**：As a 业主，I want to 点击舰桥子系统卡片时弹出的抽屉展示内容与 Web 设备面板对应子系统一致，so that 我在手机上看到的设备参数和运维人员在电脑上看到的完全相同。

**关联需求**：REQ-FUNC-007、REQ-FUNC-013

**优先级**：Must Have

**故事点**：待开发团队评估

**验收标准：**

- **AC-07-01** 新风抽屉展示新风设备参数
  - Given 业主已进入舰桥页面，当前座舱有新风机设备
  - When 业主点击"新风模块"子系统隔舱
  - Then FaultDrawer 抽屉弹出，设备参数区展示新风机设备的 PLC 参数列表，参数名称（display_name）和数值与 Web `DeviceCardsView.vue` fresh_air 列一致

- **AC-07-02** 水力模块抽屉展示水力设备参数
  - Given 当前座舱有水力模块设备
  - When 业主点击"水力模块"子系统隔舱
  - Then 抽屉展示水力模块设备 PLC 参数，与 Web hydraulic_module 列一致

- **AC-07-03** 空气品质抽屉展示传感器参数
  - Given 当前座舱有空气品质传感器设备
  - When 业主点击"空气品质"子系统隔舱
  - Then 抽屉展示空气品质传感器 PLC 参数，与 Web air_quality 列一致

- **AC-07-04** 能耗抽屉展示能耗表参数
  - Given 当前座舱有能耗表设备
  - When 业主点击"能耗中枢"子系统隔舱
  - Then 抽屉展示能耗表 PLC 参数，与 Web energy_meter 列一致

- **AC-07-05** 故障参数红色高亮
  - Given 抽屉展示的设备参数中，`fresh_air_unit_communication_error` 的值为 1（非零故障）
  - When 业主查看抽屉参数列表
  - Then 该参数行以红色/橙红色高亮显示（与赛博朋克故障色系 `#ff315d` 一致）

- **AC-07-06** 正常参数青蓝色
  - Given 抽屉展示的设备参数中，`coil_inlet_temp` 的值为 220（正常温度值，非故障字段）
  - When 业主查看抽屉参数列表
  - Then 该参数行以青蓝色或白色正常显示

- **AC-07-07** 抽屉关闭
  - Given 抽屉已经打开
  - When 业主点击关闭按钮或下滑手势关闭抽屉
  - Then 抽屉关闭，舰桥页面恢复显示子系统隔舱和房间隔舱

---

## US-08：新风机故障位域在抽屉中展开为具名故障

**用户故事**：As a 业主，I want to 在查看新风机参数时看到 `fresh_air_fault_status` 被展开为具体的中文故障名称，so that 我不需要自己计算二进制位域就能理解新风机出了什么故障。

**关联需求**：REQ-FUNC-008

**优先级**：Must Have

**故事点**：待开发团队评估

**验收标准：**

- **AC-08-01** 单个 bit 故障
  - Given 当前座舱新风机 `fresh_air_fault_status = 1`（bit 0 风机状态故障激活）
  - When 业主打开新风子系统抽屉
  - Then 参数列表中显示"风机状态故障"为激活状态（红色高亮）

- **AC-08-02** 多个 bit 同时故障
  - Given 当前座舱新风机 `fresh_air_fault_status = 260`（bit 2 进风温度传感器故障 + bit 8 出风温度传感器故障，popcount = 2）
  - When 业主打开新风子系统抽屉
  - Then 参数列表中"进风温度传感器故障"和"出风温度传感器故障"均显示为激活状态

- **AC-08-03** 所有 bit 正常
  - Given 当前座舱新风机 `fresh_air_fault_status = 0`
  - When 业主打开新风子系统抽屉
  - Then 所有 9 个故障 bit 项均显示为正常状态（无红色高亮），或统一显示"无故障"

- **AC-08-04** Web 对齐
  - Given 同一个座舱的新风机，在 Web `DeviceCardsView.vue` 中 fresh_air 列显示 2 个故障 bit
  - When 业主在小程序打开新风子系统抽屉
  - Then 抽屉显示与 Web 展开结果一致（相同 bit 号、相同故障名称、相同数量）

- **AC-08-05** bit 名称与 Web 一致
  - Given 展开的 9 个故障 bit 名称
  - When 对照 Web `FRESH_AIR_FAULT_BITS` 定义
  - Then 名称顺序完全一致：[风机状态故障, 出风温度异常状态, 进风温度传感器故障, 回水温度传感器故障, 进水温度传感器故障, 加湿器故障, 新风水阀故障, 防冻保护故障, 出风温度传感器故障]

---

## 附录 A：故事与验收标准索引

| 故事 ID | 标题 | 验收标准数 | 关联需求 |
|---------|------|-----------|---------|
| US-01 | 业主查看自己座舱的新风模块状态 | 5 | REQ-FUNC-001, REQ-FUNC-012 |
| US-02 | 业主查看自己座舱的水力模块状态 | 3 | REQ-FUNC-002, REQ-FUNC-012 |
| US-03 | 业主查看自己座舱的空气品质模块状态 | 2 | REQ-FUNC-003, REQ-FUNC-012 |
| US-04 | 业主查看自己座舱的能耗模块状态（来自 PLC 参数） | 4 | REQ-FUNC-004, REQ-FUNC-010, REQ-FUNC-012 |
| US-05 | 子系统模块按座舱实际设备动态显示 | 5 | REQ-FUNC-005, REQ-FUNC-011 |
| US-06 | 房间按座舱实际结构动态显示 | 3 | REQ-FUNC-006 |
| US-07 | 点击子系统卡片弹出参数抽屉对齐 Web 设备面板 | 7 | REQ-FUNC-007, REQ-FUNC-013 |
| US-08 | 新风机故障位域在抽屉中展开为具名故障 | 5 | REQ-FUNC-008 |

**总计**：8 条用户故事，34 组验收标准

---

## 附录 B：验收标准覆盖率矩阵

| 需求 ID | 覆盖的验收标准 |
|---------|-------------|
| REQ-FUNC-001 | AC-01-01 ~ AC-01-05 |
| REQ-FUNC-002 | AC-02-01 ~ AC-02-03 |
| REQ-FUNC-003 | AC-03-01 ~ AC-03-02 |
| REQ-FUNC-004 | AC-04-01 ~ AC-04-04 |
| REQ-FUNC-005 | AC-05-01 ~ AC-05-05 |
| REQ-FUNC-006 | AC-06-01 ~ AC-06-03 |
| REQ-FUNC-007 | AC-07-01 ~ AC-07-07 |
| REQ-FUNC-008 | AC-08-01 ~ AC-08-05 |
| REQ-FUNC-009 | 由 US-01~04 间实验证（移除后各模块仍正常判定） |
| REQ-FUNC-010 | AC-04-03 ~ AC-04-04 |
| REQ-FUNC-011 | AC-05-01 ~ AC-05-05 |
| REQ-FUNC-012 | AC-01-01, AC-01-02, AC-02-01, AC-03-01, AC-04-01 |
| REQ-FUNC-013 | AC-07-01 ~ AC-07-07 |
