<file_header>
  <project_name>v1.12.0_bridge_per_cockpit_refactor</project_name>
  <file_name>test_plan.md</file_name>
  <file_type>testing</file_type>
  <author>sub_agent_test_engineer</author>
  <created_at>2026-07-08T18:00:00+08:00</created_at>
  <version>1.0.0</version>
  <status>WRITTEN</status>
  <upstream_inputs>
    <input path="docs/requirements/v1.12.0_bridge_per_cockpit_refactor/user_stories.md" status="APPROVED"/>
    <input path="docs/implementation/v1.12.0_bridge_per_cockpit_refactor/implementation_plan.md" status="APPROVED"/>
    <input path="docs/implementation/v1.12.0_bridge_per_cockpit_refactor/code_review_report.md" status="APPROVED"/>
  </upstream_inputs>
</file_header>

# 测试计划 — 小程序舰桥 per-座舱重构

**文档编号**: TEST-PLAN-v1.12.0-BPCR-001
**项目名称**: FreeArk — 小程序舰桥 per-座舱重构
**版本**: 1.0.0
**创建日期**: 2026-07-08
**作者**: sub_agent_test_engineer

---

## 测试策略

### 测试目标

验证 v1.12.0 舰桥 per-座舱重构的两个核心模块：
1. **MOD-FAULT-UTILS** (`faultUtils.js`)：与后端 `fault_utils.py` 等效的故障判定纯函数
2. **MOD-BD-002** (`useBridgeDashboard.js`)：per-座舱 PLC 参数驱动的子系统/房间状态聚合逻辑

### 测试范围

**In-Scope（在测试范围内）：**
- faultUtils.js 全部 5 个公开函数 (IFC-FU-001 ~ IFC-FU-005) + 6 个导出常量
- useBridgeDashboard.js 内部纯函数：`aggregateSubsystemStatus`、`aggregateRoomStatus`、`computeOverallStatus`、`filterFaultEventsByCompartment`、`_buildCompartmentParams`、`_buildSingleDeviceParams`
- 34 组验收标准 (AC-01-01 ~ AC-08-05) 的对应测试场景
- 故障字段识别、故障计数、新风 bit 展开的正确性
- 子系统动态显示、房间结构驱动的正确性
- 抽屉参数构建的对齐性

**Out-of-Scope（不在测试范围内）：**
- Vue 组件渲染测试（index.vue、SubsystemCompartment、RoomCompartment、FaultDrawer 均不修改，无回归风险）
- API 集成测试（API 端点本身未修改，仅调用方式改变）
- E2E 微信小程序真机测试（需要微信开发者工具环境，不在此次纯逻辑测试范围）
- 后端测试（本次为纯前端变更）
- admin/operator 路径（代码审查确认零修改）

### 测试环境

| 项目 | 值 |
|------|-----|
| 运行环境 | Node.js (>=18)，物理机 Windows 11 |
| 测试数据库 | 不适用（纯前端逻辑测试，无 DB） |
| 测试框架 | 自定义轻量断言（零依赖，`node` 直接运行） |
| Mock 策略 | bridgeDashboard 测试使用内联 mock 数据 |
| 容器技术 | 禁止使用（INF-2） |

### 覆盖率目标

| 测试级别 | 门控阈值 | 说明 |
|---------|---------|------|
| 单元测试 (UNIT) | >= 80% | faultUtils.js 纯函数 + useBridgeDashboard.js 内部纯函数 |
| 集成测试 (INT) | >= 90% | 跨模块聚合逻辑（faultUtils → useBridgeDashboard） |
| E2E 测试 | Critical path 100% | Must Have 故事的 E2E 用例（AC-01-04, AC-05-05, AC-07-07） |

---

## 测试用例清单

### 测试用例分类规则

- **UNIT**：Given/When/Then 仅涉及单个函数/方法/类的行为（faultUtils.js 纯函数、useBridgeDashboard.js 内部纯函数）
- **INT**：涉及两个或多个模块的协作（faultUtils + useBridgeDashboard 聚合逻辑，使用 mock 数据）
- **E2E**：完整用户操作路径（座舱切换、抽屉交互 — 需要运行时环境）

### 测试用例总表

#### 第1组：faultUtils.js 常量验证 (UNIT)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-UNIT-001 | US-01~04, US-08 | AC-01-01, AC-08-05 | UNIT | FAULT_PARAM_NAMES 包含 26 个字段 | 无 | 检查 Set.size 和所有具名字段 | size=26，全部 5 组字段存在 |
| TC-UNIT-002 | US-01~04 | AC-01-01, AC-04-01 | UNIT | FAULT_PARAM_NAMES 包含 5 个分组 | 无 | 检查温控面板(20)、新风机(2)、水力/能耗/空品(3)、PLC通信(1) | 5 组全部包含 |
| TC-UNIT-003 | US-01~04 | AC-01-01 | UNIT | ERROR_N_PATTERN 正则匹配 | 无 | 测试 'error_82', 'error_703', 'error_', 'error_abc', 'error0' | 仅数字后缀匹配 |
| TC-UNIT-004 | US-08 | AC-08-04, AC-08-05 | UNIT | FRESH_AIR_FAULT_BITS 9 项名称和顺序 | 无 | 检查数组长度和每项名称 | 9 项，名称与 AC-08-05 完全一致 |
| TC-UNIT-005 | US-05 | AC-05-01 | UNIT | SYSTEM_SUB_KEYS 4 项 | 无 | 检查数组内容 | [fresh_air, energy_meter, hydraulic_module, air_quality] |
| TC-UNIT-006 | US-05, US-07 | AC-05-01, AC-07-01 | UNIT | SUB_TYPE_TO_ID 和 ID_TO_SUB_TYPE 双向映射 | 无 | 正向映射后反向映射 | 恒等映射，4 个子系统均可往返 |

#### 第2组：isFaultParam (IFC-FU-001) (UNIT)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-UNIT-010 | US-01 | AC-01-01 | UNIT | 具名故障字段返回 true | 无 | isFaultParam('fresh_air_unit_communication_error') | true |
| TC-UNIT-011 | US-01 | AC-01-01 | UNIT | error_N 正则匹配返回 true | 无 | isFaultParam('error_82') | true |
| TC-UNIT-012 | US-01 | AC-01-01 | UNIT | error_N 多位数匹配 | 无 | isFaultParam('error_703') | true |
| TC-UNIT-013 | US-01 | AC-01-02 | UNIT | 非故障字段返回 false | 无 | isFaultParam('coil_inlet_temp') | false |
| TC-UNIT-014 | US-01 | AC-01-03 | UNIT | fresh_air_fault_status 不在此函数覆盖 | 无 | isFaultParam('fresh_air_fault_status') | false（由 countFaultsForRow 单独处理） |
| TC-UNIT-015 | US-01 | AC-01-01 | UNIT | 非字符串输入安全 | 无 | isFaultParam(null), isFaultParam(undefined), isFaultParam(123) | 全部返回 false |

#### 第3组：countFaultsForRow (IFC-FU-002) (UNIT)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-UNIT-020 | US-01 | AC-01-01 | UNIT | 新风机通信故障计为 1 | 无 | countFaultsForRow('fresh_air_unit_communication_error', 1) | 1 |
| TC-UNIT-021 | US-01 | AC-01-02 | UNIT | 故障字段值为 0 不计 | 无 | countFaultsForRow('fresh_air_unit_communication_error', 0) | 0 |
| TC-UNIT-022 | US-01 | AC-01-02 | UNIT | null/undefined 值安全 | 无 | countFaultsForRow('fresh_air_unit_communication_error', null) | 0 |
| TC-UNIT-023 | US-01 | AC-01-03 | UNIT | fresh_air_fault_status=5 popcount | 无 | countFaultsForRow('fresh_air_fault_status', 5) | 2（bit 0 + bit 2） |
| TC-UNIT-024 | US-08 | AC-08-02 | UNIT | fresh_air_fault_status=260 popcount | 无 | countFaultsForRow('fresh_air_fault_status', 260) | 2（bit 2 + bit 8） |
| TC-UNIT-025 | US-08 | AC-08-01 | UNIT | fresh_air_fault_status=1 popcount | 无 | countFaultsForRow('fresh_air_fault_status', 1) | 1（bit 0） |
| TC-UNIT-026 | US-08 | AC-08-03 | UNIT | fresh_air_fault_status=511 popcount | 无 | countFaultsForRow('fresh_air_fault_status', 511) | 9（全部 9 bit） |
| TC-UNIT-027 | US-08 | AC-08-03 | UNIT | fresh_air_fault_status=0 不计 | 无 | countFaultsForRow('fresh_air_fault_status', 0) | 0 |
| TC-UNIT-028 | US-02 | AC-02-01 | UNIT | 水力模块故障计为 1 | 无 | countFaultsForRow('hydraulic_module_low_temp_error', 1) | 1 |
| TC-UNIT-029 | US-02 | AC-02-02 | UNIT | 水力模块正常不计 | 无 | countFaultsForRow('hydraulic_module_low_temp_error', 0) | 0 |
| TC-UNIT-030 | US-03 | AC-03-01 | UNIT | 空气品质通信故障计为 1 | 无 | countFaultsForRow('air_quality_sensor_communication_error', 1) | 1 |
| TC-UNIT-031 | US-03 | AC-03-02 | UNIT | 空气品质正常不计 | 无 | countFaultsForRow('air_quality_sensor_communication_error', 0) | 0 |
| TC-UNIT-032 | US-04 | AC-04-01 | UNIT | 能耗表通信故障计为 1 | 无 | countFaultsForRow('energy_meter_status_communication_error', 1) | 1 |
| TC-UNIT-033 | US-04 | AC-04-02 | UNIT | 能耗表正常不计 | 无 | countFaultsForRow('energy_meter_status_communication_error', 0) | 0 |
| TC-UNIT-034 | US-01 | AC-01-01 | UNIT | error_82 故障值计为 1 | 无 | countFaultsForRow('error_82', 1) | 1 |
| TC-UNIT-035 | US-01 | AC-01-02 | UNIT | error_N 值为 0 不计 | 无 | countFaultsForRow('error_82', 0) | 0 |
| TC-UNIT-036 | US-01 | AC-01-02 | UNIT | 非故障正常值不计 | 无 | countFaultsForRow('coil_inlet_temp', 220) | 0 |
| TC-UNIT-037 | US-01 | — | UNIT | NaN 值安全 | 无 | countFaultsForRow('fresh_air_fault_status', NaN) | 0 |

#### 第4组：computeFaultCount (IFC-FU-003) (UNIT)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-UNIT-040 | US-01 | AC-01-02 | UNIT | 空数组返回 0 | 无 | computeFaultCount([]) | 0 |
| TC-UNIT-041 | US-01 | AC-01-02 | UNIT | null/非数组输入安全 | 无 | computeFaultCount(null) | 0 |
| TC-UNIT-042 | US-01 | AC-01-02 | UNIT | 全部正常参数返回 0 | 无 | computeFaultCount([{paramName:'coil_inlet_temp',value:220},{paramName:'coil_outlet_temp',value:180}]) | 0 |
| TC-UNIT-043 | US-01 | AC-01-01 | UNIT | 一个故障参数返回 1 | 无 | computeFaultCount([{paramName:'fresh_air_unit_stop_error',value:1}]) | 1 |
| TC-UNIT-044 | US-01 | AC-01-03 | UNIT | 混合：bit 故障 + 普通故障 | 无 | computeFaultCount([{paramName:'fresh_air_fault_status',value:5},{paramName:'fresh_air_unit_communication_error',value:1}]) | 3（popcount=2 + 1 = 3） |
| TC-UNIT-045 | US-01 | AC-01-01 | UNIT | 多个故障参数累加 | 无 | computeFaultCount([{paramName:'fresh_air_unit_stop_error',value:1},{paramName:'fresh_air_unit_communication_error',value:1}]) | 2 |

#### 第5组：expandFreshAirFaultBits (IFC-FU-004) (UNIT)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-UNIT-050 | US-08 | AC-08-01 | UNIT | 单个 bit (value=1) | 无 | expandFreshAirFaultBits(1) | bit 0 active=true，其余 false |
| TC-UNIT-051 | US-08 | AC-08-02 | UNIT | 多个 bit (value=260) | 无 | expandFreshAirFaultBits(260) | bit 2,8 active=true，其余 false |
| TC-UNIT-052 | US-08 | AC-08-03 | UNIT | 所有 bit 正常 (value=0) | 无 | expandFreshAirFaultBits(0) | 全部 9 个 active=false |
| TC-UNIT-053 | US-08 | AC-08-03 | UNIT | 全 bit 激活 (value=511) | 无 | expandFreshAirFaultBits(511) | 全部 9 个 active=true |
| TC-UNIT-054 | US-08 | AC-08-01 | UNIT | null 输入安全 (视为 0) | 无 | expandFreshAirFaultBits(null) | 全部 active=false |
| TC-UNIT-055 | US-08 | AC-08-01 | UNIT | NaN 输入安全 (视为 0) | 无 | expandFreshAirFaultBits(NaN) | 全部 active=false |
| TC-UNIT-056 | US-08 | AC-08-04 | UNIT | bit 名称与 Web 端一致 | 无 | 检查 FRESH_AIR_FAULT_BITS 数组 | 9 个名称与 AC-08-05 一致 |
| TC-UNIT-057 | US-08 | AC-08-05 | UNIT | 返回数组长度恒为 9 | 无 | expandFreshAirFaultBits(任意值) | length=9 |

#### 第6组：isFaultValueForDisplay (IFC-FU-005) (UNIT)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-UNIT-060 | US-07 | AC-07-05 | UNIT | 故障参数非零值 → 高亮 | 无 | isFaultValueForDisplay('fresh_air_unit_communication_error', 1) | true |
| TC-UNIT-061 | US-07 | AC-07-06 | UNIT | 正常参数 → 不高亮 | 无 | isFaultValueForDisplay('coil_inlet_temp', 220) | false |
| TC-UNIT-062 | US-07 | AC-07-06 | UNIT | null 值 → 不高亮 | 无 | isFaultValueForDisplay('fresh_air_unit_communication_error', null) | false |
| TC-UNIT-063 | US-07 | AC-07-06 | UNIT | 0 值 → 不高亮 | 无 | isFaultValueForDisplay('fresh_air_unit_communication_error', 0) | false |
| TC-UNIT-064 | US-08 | AC-08-01 | UNIT | fresh_air_fault_status 非零 → 高亮 | 无 | isFaultValueForDisplay('fresh_air_fault_status', 5) | true |
| TC-UNIT-065 | US-08 | AC-08-03 | UNIT | fresh_air_fault_status=0 → 不高亮 | 无 | isFaultValueForDisplay('fresh_air_fault_status', 0) | false |
| TC-UNIT-066 | US-07 | AC-07-05 | UNIT | error_82 非零值 → 高亮 | 无 | isFaultValueForDisplay('error_82', 1) | true |

#### 第7组：aggregateSubsystemStatus (INT)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-INT-001 | US-05 | AC-05-01 | INT | 全设备座舱 — 全部正常 | Mock structure 含 4 种 sub_type；realtime 全部参数为 0 | aggregateSubsystemStatus(structure, realtime) | 4 个子系统，全部 status='normal' |
| TC-INT-002 | US-01 | AC-01-01 | INT | 新风有故障 — 座舱隔离 | Mock structure 含 4 种子系统；realtime 中 fresh_air 设备 fresh_air_unit_communication_error=1 | aggregateSubsystemStatus(structure, realtime) | 新风 status='fault', faultCount=1；其余正常 |
| TC-INT-003 | US-01 | AC-01-03 | INT | 新风 bit 故障计数 | Mock realtime 中 fresh_air_fault_status=5 | aggregateSubsystemStatus(structure, realtime) | 新风 faultCount=2 |
| TC-INT-004 | US-01 | AC-01-05 | INT | 有 structure 无 realtime → idle | Mock structure 有设备；realtime 为空对象 | aggregateSubsystemStatus(structure, {}) | 子系统 status='idle'（非 normal，避免误导） |
| TC-INT-005 | US-05 | AC-05-02 | INT | 缺少新风设备 | Mock structure 仅含 3 种 sub_type（无 fresh_air） | aggregateSubsystemStatus(structure, realtime) | 仅 3 个子系统，无 'fresh-air' |
| TC-INT-006 | US-05 | AC-05-03 | INT | 缺少水力模块设备 | Mock structure 不含 hydraulic_module | aggregateSubsystemStatus(structure, realtime) | 不包含 'hydraulic' |
| TC-INT-007 | US-05 | AC-05-04 | INT | 单一子系统座舱 | Mock structure 仅含 fresh_air | aggregateSubsystemStatus(structure, realtime) | 仅 1 个子系统 'fresh-air' |
| TC-INT-008 | US-05 | AC-05-05 | INT | 座舱 A vs B 不同子系统 | 座舱 A structure 有 fresh_air+hydraulic_module；座舱 B 仅有 air_quality | 分别调用 aggregateSubsystemStatus | A 返回 2 个子系统；B 返回 1 个 |
| TC-INT-009 | US-02 | AC-02-01 | INT | 水力模块有故障 | Mock realtime 中 hydraulic_module_low_temp_error=1 | aggregateSubsystemStatus(structure, realtime) | 水力 status='fault', faultCount=1 |
| TC-INT-010 | US-02 | AC-02-02 | INT | 水力模块正常 | Mock realtime 中 hydraulic_module_low_temp_error=0 | aggregateSubsystemStatus(structure, realtime) | 水力 status='normal', faultCount=0 |
| TC-INT-011 | US-03 | AC-03-01 | INT | 空气品质传感器故障 | Mock realtime 中 air_quality_sensor_communication_error=1 | aggregateSubsystemStatus(structure, realtime) | 空气品质 status='fault' |
| TC-INT-012 | US-03 | AC-03-02 | INT | 空气品质正常 | Mock realtime 中 air_quality_sensor_communication_error=0 | aggregateSubsystemStatus(structure, realtime) | 空气品质 status='normal' |
| TC-INT-013 | US-04 | AC-04-01 | INT | 能耗表通信故障 | Mock realtime 中 energy_meter_status_communication_error=1 | aggregateSubsystemStatus(structure, realtime) | 能耗 status='fault' |
| TC-INT-014 | US-04 | AC-04-02 | INT | 能耗正常 | Mock realtime 中 energy_meter_status_communication_error=0 | aggregateSubsystemStatus(structure, realtime) | 能耗 status='normal' |
| TC-INT-015 | US-01 | AC-01-05 | INT | 空 structure 回退 | structure 为 null/空对象 | aggregateSubsystemStatus({}, realtime) | 回退显示 4 个子系统 (SYSTEM_SUB_KEYS) |
| TC-INT-016 | US-04 | AC-04-03 | INT | 能耗不受全局数据影响 | realtime 中能耗表通信正常；不传入任何全局聚合数据 | 验证函数签名不含 plcRate/faultSummary 参数 | 函数仅接收 (structure, realtimeParams) |

#### 第8组：aggregateRoomStatus (INT)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-INT-020 | US-06 | AC-06-01 | INT | 4 房间无故障 | Mock structure.rooms 含 4 个房间；faultEvents 为空 | aggregateRoomStatus(structure, [], 0) | 4 个房间，全部 status='normal' |
| TC-INT-021 | US-06 | AC-06-02 | INT | 3 房间结构 | Mock structure.rooms 含 3 个房间 | aggregateRoomStatus(structure, [], 0) | 返回 3 个房间 |
| TC-INT-022 | US-06 | AC-06-03 | INT | 房间有活跃故障 | Mock structure.rooms 含"主卧"；faultEvents 含该房间 2 条 error | aggregateRoomStatus(structure, faultEvents, 0) | "主卧" status='fault', faultCount=2 |
| TC-INT-023 | US-06 | AC-06-01 | INT | 空结构 rooms | structure.rooms 为空数组 | aggregateRoomStatus({ rooms: [] }, [], 0) | 返回空数组 [] |
| TC-INT-024 | US-06 | AC-06-02 | INT | 不同座舱房间数不同 | 座舱 A 5 房间；座舱 B 3 房间 | 分别调用 | A 返回 5 个；B 返回 3 个 |

#### 第9组：computeOverallStatus (INT)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-INT-030 | US-01 | AC-01-02 | INT | 全部正常 → normal | 所有 subsystems status='normal'；rooms status='normal' | computeOverallStatus(subsystems, rooms) | { level: 'normal', text: '正常' } |
| TC-INT-031 | US-01 | AC-01-01 | INT | 任一故障 → fault | subsystems 中一个 status='fault' | computeOverallStatus(subsystems, rooms) | { level: 'fault', text: '告警' } |
| TC-INT-032 | US-06 | AC-06-03 | INT | 混合 fault+warning → fault | subsystems 含 fault；rooms 含 warning | computeOverallStatus(subsystems, rooms) | { level: 'fault', text: '告警' }（fault 优先） |
| TC-INT-033 | US-01 | — | INT | 全部 idle → syncing | 所有 subsystems status='idle'；rooms 为空 | computeOverallStatus(subsystems, []) | { level: 'syncing', text: '等待数据' } |
| TC-INT-034 | US-01 | — | INT | 空数组 → syncing | subsystems=[]；rooms=[] | computeOverallStatus([], []) | { level: 'syncing', text: '等待数据' } 或无数据状态 |

#### 第10组：filterFaultEventsByCompartment (INT)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-INT-040 | US-06 | AC-06-03 | INT | 按房间名过滤 | compartment.type='room', name='主卧'；faultEvents 含该房间故障 | filterFaultEventsByCompartment(events, comp, structure) | 返回该房间的故障事件 |
| TC-INT-041 | US-07 | AC-07-01 | INT | 按 subsystem device_sn 过滤 | compartment.type='subsystem', id='fresh-air'；structure 有 fresh_air 设备 | filterFaultEventsByCompartment(events, comp, structure) | 返回 device_sn 匹配的故障事件 |
| TC-INT-042 | US-07 | AC-07-01 | INT | 无匹配 → 空数组 | compartment.type='subsystem', id='fresh-air'；但 structure 无 fresh_air 设备 | filterFaultEventsByCompartment(events, comp, structure) | 返回 [] |
| TC-INT-043 | US-07 | AC-07-01 | INT | 空 faultEvents → 空数组 | faultEvents=[] | filterFaultEventsByCompartment([], comp, structure) | 返回 [] |

#### 第11组：_buildCompartmentParams (INT)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-INT-050 | US-07 | AC-07-01 | INT | 新风子系统抽屉参数 | compartment.type='subsystem', id='fresh-air'；structure 有 fresh_air 设备；realtime 有参数 | _buildCompartmentParams(compartment) | 返回 DeviceParamBlock 数组，含新风设备参数 |
| TC-INT-051 | US-07 | AC-07-02 | INT | 水力子系统抽屉参数 | compartment.type='subsystem', id='hydraulic' | _buildCompartmentParams(compartment) | 返回水力模块参数 |
| TC-INT-052 | US-07 | AC-07-03 | INT | 空气品质抽屉参数 | compartment.type='subsystem', id='air-quality' | _buildCompartmentParams(compartment) | 返回空气品质参数 |
| TC-INT-053 | US-07 | AC-07-04 | INT | 能耗抽屉参数 | compartment.type='subsystem', id='energy' | _buildCompartmentParams(compartment) | 返回能耗表参数 |
| TC-INT-054 | US-07 | AC-07-05 | INT | 故障参数 isFault=true | realtime 中 fresh_air_unit_communication_error=1 | _buildCompartmentParams(compartment) → attrs 中该 tag | isFault=true |
| TC-INT-055 | US-07 | AC-07-06 | INT | 正常参数 isFault=false | realtime 中 coil_inlet_temp=220 | _buildCompartmentParams(compartment) → attrs 中该 tag | isFault=false |
| TC-INT-056 | US-08 | AC-08-01 | INT | fresh_air_fault_status 展开 | realtime 中 fresh_air_fault_status=1 | _buildCompartmentParams(fresh-air) → attrs 中该 tag | expandedBits 存在，bit 0 active=true |
| TC-INT-057 | US-08 | AC-08-02 | INT | 多 bit 展开 | realtime 中 fresh_air_fault_status=260 | _buildCompartmentParams(fresh-air) | expandedBits bit 2,8 active=true |

#### 第12组：E2E 用例

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-E2E-001 | US-01 | AC-01-04 | E2E | 座舱切换后子系统状态变化 | 绑定 2 个座舱 | 切换座舱 A→B，检查 subsystems 数组 | 子系统列表随座舱变化 |
| TC-E2E-002 | US-07 | AC-07-07 | E2E | 抽屉打开与关闭 | 抽屉打开 | 调用 closeCompartment() | activeCompartment=null, compartmentParams=null |

---

## 不可测试项

| AC-ID | 原因 |
|-------|------|
| AC-04-03 (能耗不受全局 PLC 在线率影响) | 架构级保证 (ADR-008)：全局 API 调用已完全移除，`aggregateSubsystemStatus` 签名不含 plcRate 参数，函数仅接收 per-座舱数据。通过代码审查验证，无需运行时测试。 |
| AC-04-04 (能耗不受其他户设备影响) | 数据隔离由后端 `getOwnerRealtimeParams(sp)` 保证（per specific_part 过滤）。前端仅消费后端返回的该座舱数据，不做跨座舱聚合。通过架构设计保证。 |
| AC-07-07 (抽屉关闭) | UI 交互依赖 Vue 组件渲染。`closeCompartment()` 函数逻辑在 TC-E2E-002 中以逻辑层验证；手势/动画交互需微信开发者工具真机测试。 |

---

## 测试数据说明

### faultUtils 测试数据

- 所有测试使用内联常量（无需外部数据文件）
- 故障字段名来自 `FAULT_PARAM_NAMES` Set 的 26 个映射
- `fresh_air_fault_status` 的位域值覆盖边界：0, 1, 5, 260, 511

### useBridgeDashboard 测试数据

- Mock structure 对象包含 `system_devices`（含 sub_type, device_sn）和 `rooms`
- Mock realtimeParams 对象为 `{ [device_sn]: { paramName: value, ... } }` 结构
- Mock faultEvents 数组包含 `{ id, device_sn, room_name, severity, fault_type, ... }`

---

## 门控计划

```
Phase 1: UNIT tests (faultUtils.js)
  └─ 目标通过率 >= 80%
  └─ 若通过 → Phase 2
  └─ 若未通过 → 生成报告，请求修复

Phase 2: INT tests (useBridgeDashboard.js aggregation functions)
  └─ 目标通过率 >= 90%
  └─ 若通过 → Phase 3
  └─ 若未通过 → 生成报告，请求修复

Phase 3: E2E tests (critical paths)
  └─ 目标 critical path 100%
  └─ 生成综合报告
```
