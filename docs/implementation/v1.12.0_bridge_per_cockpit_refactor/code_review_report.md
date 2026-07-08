<file_header>
  <project_name>v1.12.0_bridge_per_cockpit_refactor</project_name>
  <file_name>code_review_report.md</file_name>
  <file_type>implementation</file_type>
  <author>sub_agent_software_developer</author>
  <created_at>2026-07-08T12:00:00+08:00</created_at>
  <version>1.0.0</version>
  <status>WRITTEN</status>
  <upstream_inputs>
    <input path="docs/architecture/v1.12.0_bridge_per_cockpit_refactor/module_design.md" status="APPROVED"/>
    <input path="docs/architecture/v1.12.0_bridge_per_cockpit_refactor/architecture_design.md" status="APPROVED"/>
  </upstream_inputs>
</file_header>

# 代码评审报告 — 小程序舰桥 per-座舱重构

**文档编号**: CODE-REVIEW-v1.12.0-BPCR-001
**项目名称**: FreeArk — 小程序舰桥 per-座舱重构
**版本**: 1.0.0
**创建日期**: 2026-07-08
**作者**: sub_agent_software_developer

---

## 评审摘要

- **评审文件总数**: 2（1 新增 + 1 修改）
- **总行数**: ~640 行（新增 195 行 + 修改 ~445 行）
- **5维总体评分**:
  - Correctness: 9.5/10
  - Security: 10/10
  - Performance: 9.5/10
  - Maintainability: 9.0/10
  - Test Coverage (可测试性): 9.0/10
- **Finding 统计**: CRITICAL 0 条 | MAJOR 0 条 | MINOR 1 条

---

## 按模块评审详情

---

### MOD-FAULT-UTILS: faultUtils.js

**文件**: `miniprogram/utils/faultUtils.js`
**行数**: 195 行

- **Correctness: 10/10**
  
  所有接口正确实现了 module_design.md 定义的 IFC-FU-001 至 IFC-FU-005 契约。
  
  - `FAULT_PARAM_NAMES` Set 包含 26 个字段，与 `fault_utils.py` frozenset 逐字对齐，包含注释标注的 5 个分组（客厅/书房/主卧/儿童房/第四儿童房温控面板 + 新风机 + 水利/能耗/空气品质 + PLC通信故障）。
  - `ERROR_N_PATTERN` = `/^error_\d+$/`，无 `u` flag（华为安卓兼容），与后端 `_ERROR_N_PATTERN` 等价。
  - `FRESH_AIR_FAULT_BITS` 9 项，与 `DeviceCardsView.vue` 顺序一致。
  - `SYSTEM_SUB_KEYS` 4 项，与 `DeviceCardsView.vue` 一致。
  - `isFaultParam()` — Set.has() O(1) + RegExp.test()，与后端 `is_fault_param()` 等价。
  - `countFaultsForRow()` — null/undefined/0 早返回 → 0；fresh_air_fault_status → popcount（`toString(2).split('1').length - 1`）；isFaultParam → 1。NaN 安全：Number(value) 后 isNaN 检查。
  - `computeFaultCount()` — 遍历数组累加 `countFaultsForRow`，对非数组/null 输入安全返回 0。
  - `expandFreshAirFaultBits()` — 9 元素数组，`(v >> bitIndex) & 1` 位运算，NaN/input 安全（默认 0）。
  - `isFaultValueForDisplay()` — null/0 早返回 → false；fresh_air_fault_status 单独处理；isFaultParam 覆盖 remaining fault + error_\d+。

- **Security: 10/10**
  
  纯函数模块，零外部依赖、零 I/O、零网络请求、零 DOM 操作。无注入风险、无凭证暴露风险、无用户数据泄露风险。

- **Performance: 9/10**
  
  - `FAULT_PARAM_NAMES` 使用 `Set` 实现 O(1) 成员判断（26 个元素）。
  - `countFaultsForRow` popcount 使用 `toString(2).split('1').length - 1`（O(log n) 位宽），9-bit 场景下可忽略。可用 `BigInt` + 循环优化但当前值域不需要。
  - `computeFaultCount` O(n) 遍历。座舱单子系统参数通常 < 50 个，性能充足。
  - `expandFreshAirFaultBits` 固定 9 次循环，O(1)。
  - 减分项：`toString(2).split('1').length - 1` 在极端大值（> 2^31）时有精度问题，但 `fresh_air_fault_status` 为 9-bit 位域（值域 0-511），JS Number 完全安全。本项不构成实际问题。

- **Maintainability: 9/10**
  
  - 所有函数为纯函数，输入输出确定，无副作用，易于单元测试。
  - 每个常量和函数标注了同步来源（`fault_utils.py` / `DeviceCardsView.vue`），便于前后端规则同步。
  - `SUB_TYPE_TO_ID` / `ID_TO_SUB_TYPE` 提供双向映射，避免多处硬编码。
  - `SUBSYSTEM_NAMES` 在 faultUtils.js 中导出但在 useBridgeDashboard.js 中保留本地副本（向后兼容）。如后续统一可将 useBridgeDashboard.js 改为导入。
  - 减分项：`FAULT_PARAM_NAMES` 注释分组清晰但 26 个值未按字母排序（保持了后端 frozenset 的分组顺序，有利于逐组对账）。

- **Test Coverage (可测试性): 9.5/10**
  
  - 所有函数为纯函数，输入输出确定，可直接用 Jest/Vitest 测试。
  - 无全局状态、无副作用、无时间依赖。
  - 减分项：当前无配套单元测试文件（测试属于 test_engineer 职责，本代理不产出测试代码）。

---

### MOD-BD-002: useBridgeDashboard.js

**文件**: `miniprogram/composables/useBridgeDashboard.js`
**行数**: ~445 行（原 731 行，净减少 ~286 行）

- **Correctness: 9/10**
  
  所有变更正确实现了 module_design.md 的变更摘要表和 IFC 契约。
  
  - **删除项验证**：
    - `ENERGY_KEYWORDS` 常量 — 已删除（L26-29 旧）。
    - `PRODUCT_MAP` 常量 — 已删除（L32-36 旧）。
    - `isEnergyRelated()` — 已删除（L63-67 旧）。
    - `deriveEnergyStatus()` — 已删除（L88-145 旧，净移除 58 行）。
    - `aggregateRoomStatus` 孤儿房间追加逻辑（L238-259 旧）— 已删除。
  - **_doFetch 索引重新编号**：逐一核对 6 个 `results[N]` 引用：
    - results[0] → Structure ✓（索引未变）
    - results[1] → Fault events（旧 results[3]）✓
    - results[2] → Condensation（旧 results[4]）✓
    - results[3] → Bindings（旧 results[5]）✓
    - results[4] → Realtime params（旧 results[6]）✓
    - results[5] → Connectivity（旧 results[7]）✓
  - **aggregateSubsystemStatus 重写**：
    - 接收 `(structure, realtimeParams)` 替代旧 4 参数 ✓
    - `SYSTEM_SUB_KEYS` 交集过滤实现动态子系统显示 ✓
    - REQ-NFUNC-004 降级：structure 为空 → 回退 SYSTEM_SUB_KEYS 全量 ✓
    - REQ-NFUNC-004 降级：realtime 为空 → 所有子系统 status='idle' ✓
    - 使用 `computeFaultCount` 替代手动判定 ✓
  - **filterFaultEventsByCompartment 重写**：
    - 子系统匹配：device_sn 集合（基于 structure.system_devices sub_type 过滤）替代 product_code ✓
    - 新增 `structureCache` 参数，opencCompartment 传入 `_structureCache` ✓
  - **_buildCompartmentParams 加强**：
    - 子系统匹配：`ID_TO_SUB_TYPE[compartment.id]` 映射替代 `productMap` ✓
    - 移除 energy 补偿逻辑（旧 L651-669）✓
    - 集成 `expandFreshAirFaultBits` + `isFaultValueForDisplay` ✓
  - **openCompartment 类型检测**：
    - 旧：`compartment.type || (compartment.productCode !== undefined ? 'subsystem' : 'room')`
    - 新：`compartment.type || (ID_TO_SUB_TYPE[compartment.id] ? 'subsystem' : 'room')`
    - 修正原因：新 SubsystemState 不再包含 productCode 字段 ✓
  - **hasAnyData 条件**：`faultSummary` 已移除，改为 `structure || faultEvents.length > 0` ✓
  - **全局错误检查**：键集合从 `['structure', 'device-summary', 'fault-events']` 改为 `['structure', 'realtime-params', 'fault-events']`（使用 `.some()` 替代旧 `.every()` — 修正逻辑错误：旧代码当所有 key 都有错误才触发全局错误，新代码任一 critical key 有错误即触发）✓

- **Security: 10/10**
  
  - 无硬编码凭证、无生产数据库连接串。
  - 所有数据来自后端 API（通过 `api.js` → `http.js` → `uni.request`），Token 注入由 `http.js` 统一管理。
  - 无 `Docker SDK` 调用（符合 INF-2 约束）。
  - 无 `\p{}` Unicode 正则（符合华为安卓兼容约束）。
  - 无用户输入直接拼接 SQL/HTML。
  - PLC 参数数据仅用于前端展示判定，不写回后端。

- **Performance: 10/10**
  
  - 移除 2 个全局 API 调用（`getDashboardDeviceFaultSummary` + `getDashboardPlcOnlineRate`），每次轮询减少 2 次 HTTP 请求。
  - `aggregateSubsystemStatus` 复杂度 O(D + P)，D = system_devices 数量（通常 < 20），P = PLC 参数总数（通常 < 200/座舱）。
  - `filterFaultEventsByCompartment` 子系统匹配使用 `Set.has()` O(1) 替代旧 `product_code === ` O(1)（性能等价）。
  - `_buildCompartmentParams` 仅遍历当前隔舱相关设备参数，非全局遍历。
  - 所有聚合逻辑在 JS 主线程同步执行，无异步等待（纯计算）。

- **Maintainability: 9/10**
  
  - `_buildSingleDeviceParams` 提取为独立内部函数，避免 `_buildCompartmentParams` 过长。
  - `faultUtils` 导入使故障判定逻辑集中管理，`useBridgeDashboard` 不再内嵌判定规则。
  - 所有 v1.12.0 变更处标注了注释（`v1.12.0:` 前缀），便于 diff/code review 定位。
  - 公开接口（`start`, `stop`, `refresh`, `switchCockpit`, `openCompartment`, `closeCompartment`，`state` 字段签名）保持不变，消费者 `index.vue` 无需修改。
  - 减分项：`SUBSYSTEM_NAMES` 存在两份副本（faultUtils.js 导出 + useBridgeDashboard.js 本地定义）。后续可统一为导入。

- **Test Coverage (可测试性): 8.5/10**
  
  - 纯函数部分（`aggregateSubsystemStatus`, `aggregateRoomStatus`, `computeOverallStatus`, `filterFaultEventsByCompartment`, `_buildCompartmentParams`）均可独立测试：
    - 输入：structure、realtimeParams、faultEvents 对象
    - 输出：SubsystemState[]、RoomState[]、DeviceParamBlock[]
    - 测试场景：空 structure、空 realtime、部分设备、全设备、故障/正常混合
  - `_doFetch` 依赖 `api.*` + `Promise.allSettled`，需 mock 测试。
  - 减分项：当前无配套单元测试文件（测试属于 test_engineer 职责，本代理不产出测试代码）。

---

## Finding 清单

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-001 | MINOR | `miniprogram/utils/faultUtils.js:L181` | `isFaultValueForDisplay` 中 `isFaultParam()` 已覆盖 `ERROR_N_PATTERN` 匹配，`fresh_air_fault_status` 单独分支也覆盖了位域字段，隐性覆盖完整但缺少注释说明。建议在函数注释中补充说明"fresh_air_fault_status 不在 FAULT_PARAM_NAMES 中，故单独处理"。 | DOCUMENTED |

---

## 未解决的 CRITICAL 问题

无。

## 遗留 MAJOR 问题

无（0 条，满足门控要求 ≤3）。

---

## 合规校验清单

| # | 检查项 | 结果 |
|---|--------|------|
| 1 | 输入锚定：每个文件对应 module_design.md 中的 MOD-NNN | PASS |
| 2 | 输入锚定：每个方法对应一个 IFC-NNN | PASS |
| 3 | 输入锚定：无未定义模块的实现 | PASS |
| 4 | 逻辑一致：实现顺序遵循拓扑排序 | PASS（MOD-FAULT-UTILS → MOD-BD-002） |
| 5 | 逻辑一致：模块间调用与依赖关系一致 | PASS |
| 6 | 需求符合：所有 MOD-NNN 有对应代码实现 | PASS |
| 7 | 需求符合：所有 IFC-NNN 有完整方法实现 | PASS |
| 8 | 需求符合：无未修复 CRITICAL finding | PASS |
| 9 | 格式合规：implementation_plan.md 有合规 file_header | PASS |
| 10 | 格式合规：code_review_report.md 有合规 file_header | PASS |
| 11 | 格式合规：每个代码文件有顶部注释块 | PASS |
| 12 | 格式合规：测试代码未混入 src/ | PASS |
| 13 | ADR 遵循：ADR-001 至 ADR-008 全部遵循 | PASS |
| 14 | 架构偏差：无架构偏差 | PASS |
| 15 | 安全约束：无硬编码凭证 | PASS |
| 16 | 安全约束：无 Docker SDK 调用 | PASS |
| 17 | 安全约束：无 \p{} Unicode 正则 | PASS |
| 18 | 基础设施：数据库连接通过环境变量 | N/A（纯前端变更） |
| 19 | 视角约束：admin/operator 路径零修改 | PASS |
| 20 | 视觉约束：CSS/模板/动画零修改 | PASS |

---

## 覆盖需求验证

| 需求 ID | 实现状态 |
|---------|---------|
| REQ-FUNC-001 (新风 per-座舱) | aggregateSubsystemStatus + computeFaultCount + FAULT_PARAM_NAMES 覆盖 |
| REQ-FUNC-002 (水力 per-座舱) | 同上 |
| REQ-FUNC-003 (空气品质 per-座舱) | 同上 |
| REQ-FUNC-004 (能耗 per-座舱) | 同上 + 删除 deriveEnergyStatus/ENERGY_KEYWORDS |
| REQ-FUNC-005 (子系统动态显示) | SYSTEM_SUB_KEYS 交集过滤 |
| REQ-FUNC-006 (房间动态显示) | aggregateRoomStatus 移除孤儿房间 + 仅遍历 structure.rooms |
| REQ-FUNC-007 (抽屉对齐 Web) | _buildCompartmentParams sub_type 匹配 + _buildSingleDeviceParams |
| REQ-FUNC-008 (新风 bit 展开) | expandFreshAirFaultBits + _buildSingleDeviceParams 集成 |
| REQ-FUNC-009 (移除 fault-summary) | _doFetch 移除第 1 项 Promise |
| REQ-FUNC-010 (移除 PLC 在线率) | _doFetch 移除第 2 项 Promise + 删除 deriveEnergyStatus |
| REQ-FUNC-011 (子系统聚合重构) | aggregateSubsystemStatus 整体重写 |
| REQ-FUNC-012 (故障规则一致) | FAULT_PARAM_NAMES + countFaultsForRow + computeFaultCount 等效实现 |
| REQ-FUNC-013 (抽屉参数构建) | _buildCompartmentParams + _buildSingleDeviceParams 加强 |
| REQ-NFUNC-001 (admin/operator 不变) | index.vue 零修改 |
| REQ-NFUNC-002 (视觉风格保持) | CSS/模板不变 |
| REQ-NFUNC-003 (轮询保持) | POLL_INTERVAL_MS = 30000 不变 |
| REQ-NFUNC-004 (容错降级) | aggregateSubsystemStatus 回退逻辑 + subsystemErrors 新增键 |
