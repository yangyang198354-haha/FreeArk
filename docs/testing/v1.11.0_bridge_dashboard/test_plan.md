<file_header>
  <project_name>FreeArk_BridgeDashboard</project_name>
  <flow_mode>PARTIAL_FLOW</flow_mode>
  <group_id>GROUP_D</group_id>
  <phase_id>PHASE_07</phase_id>
  <author_agent>sub_agent_test_engineer</author_agent>
  <inception_timestamp>2026-07-08T00:00:00Z</inception_timestamp>
  <status>DRAFT</status>
  <input_files>
    <file path="docs/requirements/v1.11.0_bridge_dashboard/user_stories.md" status="APPROVED" />
    <file path="docs/implementation/v1.11.0_bridge_dashboard/implementation_plan.md" status="APPROVED" />
    <file path="docs/implementation/v1.11.0_bridge_dashboard/code_review_report.md" status="APPROVED" />
  </input_files>
</file_header>

# 测试计划 — v1.11.0 Bridge Dashboard（舰桥仪表盘重写）

**文档编号**：TEST-PLAN-v1110-BD-001
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-07-08
**关联文档**：user_stories.md (6 US, 31 AC), implementation_plan.md (11 MOD)

---

## 1. 测试策略

### 1.1 测试目标

验证 v1.11.0 舰桥仪表盘重写的 4 个质量维度：

| 维度 | 目标 | 验证方式 |
|------|------|---------|
| 功能正确性 | 31 条 AC 全部覆盖，无未处理异常路径 | 单元测试 + 集成测试 + E2E 场景分析 |
| 后端零回归 | 现有 Django 测试套件零新增失败 | 全量运行 2098 测试比对基线 |
| API 兼容性 | 新增 `getDashboardDeviceFaultSummary()` 不破坏现有机端 | API 签名检查 |
| 数据安全 | 无敏感数据泄露、Token 鉴权完整、角色隔离有效 | 安全审计检查清单 |

### 1.2 测试范围

**In-Scope（本测试计划覆盖）：**
- 前端 composable 纯函数逻辑（useBridgeDashboard.js 6 个内部聚合函数 + useAnimationControl.js 状态转换）
- 后端回归测试（全量 2098 测试，确认 v1.11.0 变更零回归）
- API 封装签名兼容性验证（api.js 新增方法不影响现有机端）
- 用户故事验收标准覆盖性审查（31 AC x 级别分类）

**Out-of-Scope（不在本测试计划范围内）：**
- 微信小程序真机 E2E 测试（需要 WeChat 开发者工具/真机，测试环境不可用）
- uni-app 构建产物验证（需要 `npm run dev:mp-weixin`，当前未配置）
- 视觉像素级对比测试（AC-02-01~02-05 为视觉主观标准，标记 NOT_TESTABLE）
- 性能压测（30s 轮询为成熟模式，组件性能已验证）
- admin/operator 路径功能测试（声明为 100% 保留且零改动）

### 1.3 测试环境

| 组件 | 环境 |
|------|------|
| 后端测试 | Django test runner + SQLite（自动切换，FREEARK_POC_MOCK 模式） |
| 前端单元测试 | Node.js 22+，纯 JS 无框架依赖 |
| 数据库 | SQLite（测试专用，符合 [INF-1] 约束） |
| 网络 | 无外部依赖（所有 API 调用被 mock/跳过） |

### 1.4 覆盖率目标

| 测试级别 | 门控阈值 | 说明 |
|---------|---------|------|
| 单元测试（前端纯函数） | >= 80% | 6 个聚合函数 + useAnimationControl 状态机 |
| 后端回归测试 | 零新增失败 | 对比已知 6 个待定失败 + 1 个环境编码错误 |
| 集成测试（API 签名） | >= 90% | api.js 所有方法签名兼容性 |

---

## 2. 测试用例清单

### 2.1 单元测试用例（TC-UNIT-*）

聚焦 `useBridgeDashboard.js` 内部的 6 个纯函数和 `useAnimationControl.js` 的 4 个状态方法。

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 | 测试数据 | 备注 |
|-------|--------|--------|------|------|---------|------|---------|---------|------|
| TC-UNIT-001 | US-01 | AC-01-01 | UNIT | severityToStatus: error -> fault | 输入 severity="error" | 调用 severityToStatus("error") | 返回 "fault" | "error" | 基础映射 |
| TC-UNIT-002 | US-01 | AC-01-02 | UNIT | severityToStatus: warning -> warning | 输入 severity="warning" | 调用 severityToStatus("warning") | 返回 "warning" | "warning" | 基础映射 |
| TC-UNIT-003 | US-01 | AC-01-03 | UNIT | severityToStatus: unknown -> normal | 输入 severity="unknown" | 调用 severityToStatus("unknown") | 返回 "normal" | "unknown" | 未知降级 |
| TC-UNIT-004 | US-01 | AC-01-03 | UNIT | severityToStatus: null -> normal | 输入 severity=null | 调用 severityToStatus(null) | 返回 "normal" | null | 空值降级 |
| TC-UNIT-005 | US-01 | AC-01-07 | UNIT | severityToStatus: condensation -> warning | 输入 severity="condensation" | 调用 severityToStatus("condensation") | 返回 "warning" | "condensation" | 结露视为预警 |
| TC-UNIT-006 | US-01 | AC-01-05 | UNIT | computeOverallStatus: 任一子系统 fault -> fault | subsystems=[{status:"fault"}], rooms=[{status:"normal"}] | 调用 computeOverallStatus | {level:"fault", text:"告警"} | 混合状态 | 取最严重 |
| TC-UNIT-007 | US-01 | AC-01-02 | UNIT | computeOverallStatus: 无fault有warning -> warning | subsystems=[{status:"normal"}], rooms=[{status:"warning"}] | 调用 computeOverallStatus | {level:"warning", text:"预警"} | 仅预警 | 取最严重 |
| TC-UNIT-008 | US-01 | AC-01-03 | UNIT | computeOverallStatus: 全部normal -> normal | systems和rooms全为normal | 调用 computeOverallStatus | {level:"normal", text:"正常"} | 全正常 | 正常状态 |
| TC-UNIT-009 | US-01 | AC-01-04 | UNIT | computeOverallStatus: 全idle -> syncing | systems和rooms全为idle | 调用 computeOverallStatus | {level:"syncing", text:"等待数据"} | 全idle | 同步中 |
| TC-UNIT-010 | US-06 | AC-06-01 | UNIT | computeOverallStatus: 空数组 -> normal | subsystems=[], rooms=[] | 调用 computeOverallStatus | {level:"normal", text:"正常"} | 空数组 | 边界条件 |
| TC-UNIT-011 | US-01 | AC-01-05 | UNIT | aggregateSubsystemStatus: fresh_air 有故障 -> fault | faultSummary有fresh_air_unit.fault_count=3 | 调用 aggregateSubsystemStatus | 新风子系统 status="fault", faultCount=3 | fresh_air_unit:{fault_count:3} | 子系统故障 |
| TC-UNIT-012 | US-01 | AC-01-06 | UNIT | aggregateSubsystemStatus: hydraulic 无故障 -> normal | faultSummary有hydraulic_module.fault_count=0 | 调用 aggregateSubsystemStatus | 水力子系统 status="normal", faultCount=0 | hydraulic_module:{fault_count:0} | 子系统正常 |
| TC-UNIT-013 | US-01 | AC-01-05 | UNIT | aggregateSubsystemStatus: 空响应 -> 全部normal | faultSummary=null | 调用 aggregateSubsystemStatus(null, null, []) | 4个子系统都生成，status均为"normal"或"idle"(energy) | null | 容错处理 |
| TC-UNIT-014 | US-01 | AC-01-09 | UNIT | deriveEnergyStatus: PLC全部在线+无故障 -> normal | plcRate={online_count:5,total_count:5}, faultEvents=[] | 调用 deriveEnergyStatus | status="normal", faultCount=0, warningCount=0 | 全在线 | PLC正常 |
| TC-UNIT-015 | US-01 | AC-01-09 | UNIT | deriveEnergyStatus: PLC部分离线 -> warning | plcRate={online_count:2,total_count:5} | 调用 deriveEnergyStatus | status="warning" | 部分离线 | PLC预警 |
| TC-UNIT-016 | US-01 | AC-01-09 | UNIT | deriveEnergyStatus: PLC全部离线 -> fault | plcRate={online_count:0,total_count:5} | 调用 deriveEnergyStatus | status="fault" | 全离线 | PLC告警 |
| TC-UNIT-017 | US-01 | AC-01-05 | UNIT | deriveEnergyStatus: PLC正常+能效故障 -> fault | plcRate正常, faultEvents含能效error事件 | 调用 deriveEnergyStatus | status="fault" (worseStatus of normal+fault) | 混合 | 故障优先 |
| TC-UNIT-018 | US-01 | AC-01-02 | UNIT | deriveEnergyStatus: 仅能效预警 -> warning | 能效warning事件+无error, PLC无数据 | 调用 deriveEnergyStatus | status="warning" | 仅预警 | 预警状态 |
| TC-UNIT-019 | US-01 | AC-01-05 | UNIT | isEnergyRelated: 匹配 "电度" 关键词 | event.device_type_label="电度计量" | 调用 isEnergyRelated | true | "电度计量" | 中文关键词 |
| TC-UNIT-020 | US-01 | AC-01-05 | UNIT | isEnergyRelated: 匹配 "energy" 关键词 | event.device_type_label="energy meter" | 调用 isEnergyRelated | true | "energy meter" | 英文关键词 |
| TC-UNIT-021 | US-01 | AC-01-05 | UNIT | isEnergyRelated: 不匹配 | event.device_type_label="新风机组" | 调用 isEnergyRelated | false | "新风机组" | 无关设备 |
| TC-UNIT-022 | US-01 | AC-01-05 | UNIT | isEnergyRelated: null字段 -> false | event没有device_type_label | 调用 isEnergyRelated | false | null字段 | 边界条件 |
| TC-UNIT-023 | US-01 | AC-01-07 | UNIT | aggregateRoomStatus: 房间有故障 -> fault | structure含客厅, faultEvents含客厅error事件 | 调用 aggregateRoomStatus | 客厅status="fault", faultCount=1 | 1 error事件 | 房间故障 |
| TC-UNIT-024 | US-01 | AC-01-08 | UNIT | aggregateRoomStatus: 房间无事件 -> normal | structure含书房, faultEvents不含书房事件 | 调用 aggregateRoomStatus | 书房status="normal", faultCount=0 | 无事件 | 房间正常 |
| TC-UNIT-025 | US-01 | AC-01-07 | UNIT | aggregateRoomStatus: 房间有预警 -> warning | structure含主卧, faultEvents含主卧warning+condensation | 调用 aggregateRoomStatus | 主卧status="warning", warningCount=2 | 2 warning | 房间预警 |
| TC-UNIT-026 | US-01 | AC-01-07 | UNIT | aggregateRoomStatus: 无structure但有faultEvents -> 补充房间 | structure.rooms=[], faultEvents含"客厅"error | 调用 aggregateRoomStatus | 结果包含客厅(status="fault") | event-only room | 容错：事件中的房间也展示 |
| TC-UNIT-027 | US-01 | AC-01-07 | UNIT | aggregateRoomStatus: structure为null -> 返回空数组 | structure=null | 调用 aggregateRoomStatus(null, [], 0) | 返回 [] | null | 边界条件 |
| TC-UNIT-028 | US-01 | AC-01-07 | UNIT | groupFaultEventsByRoom: 2个房间各1个事件 -> Map size=2 | faultEvents含2个房间各1个事件 | 调用 groupFaultEventsByRoom | Map有2个entry | 2房间2事件 | 分组逻辑 |
| TC-UNIT-029 | US-01 | AC-01-07 | UNIT | groupFaultEventsByRoom: 空数组 -> 空Map | faultEvents=[] | 调用 groupFaultEventsByRoom([]) | Map有0个entry | [] | 边界条件 |
| TC-UNIT-030 | US-01 | AC-01-07 | UNIT | groupFaultEventsByRoom: null -> 空Map | faultEvents=null | 调用 groupFaultEventsByRoom(null) | Map size=0 | null | 边界条件 |
| TC-UNIT-031 | US-03 | AC-03-01 | UNIT | filterFaultEventsByCompartment: 子系统-新风过滤 | faultEvents有product_code=130004的事件 | filterByCompartment(faultEvents, {type:"subsystem",id:"fresh-air"}) | 仅返回product_code=130004的事件 | 混合事件列表 | 按product_code过滤 |
| TC-UNIT-032 | US-03 | AC-03-02 | UNIT | filterFaultEventsByCompartment: 房间-主卧过滤 | faultEvents含room_name="主卧"的事件 | filterByCompartment(faultEvents, {type:"room",name:"主卧"}) | 仅返回room_name="主卧"的事件 | 混合事件列表 | 按room_name过滤 |
| TC-UNIT-033 | US-03 | AC-03-01 | UNIT | filterFaultEventsByCompartment: energy子系统 | faultEvents含能效相关事件 | filterByCompartment(faultEvents, {type:"subsystem",id:"energy"}) | 返回isEnergyRelated(event)===true的事件 | 混合事件列表 | 能耗关键词过滤 |
| TC-UNIT-034 | US-03 | AC-03-01 | UNIT | filterFaultEventsByCompartment: 未知子系统 -> [] | 未知subsystem id | filterByCompartment([...], {type:"subsystem",id:"unknown"}) | 返回 [] | 有效事件列表 | 边界条件 |
| TC-UNIT-035 | US-03 | AC-03-01 | UNIT | filterFaultEventsByCompartment: null compartment -> [] | compartment=null | filterByCompartment([...], null) | 返回 [] | 有效事件列表 | 边界条件 |
| TC-UNIT-036 | US-03 | AC-03-01 | UNIT | filterFaultEventsByCompartment: null events -> [] | faultEvents=null | filterByCompartment(null, validCompartment) | 返回 [] | null | 边界条件 |
| TC-UNIT-037 | US-04 | AC-04-04 | UNIT | useAnimationControl: pause -> animationsPaused=true | 初始false | anim.pause() | animationsPaused=true | 无 | 动画暂停 |
| TC-UNIT-038 | US-04 | AC-04-04 | UNIT | useAnimationControl: resume -> animationsPaused=false | 先pause再resume | anim.resume() | animationsPaused=false | 无 | 动画恢复 |
| TC-UNIT-039 | US-04 | AC-04-04 | UNIT | useAnimationControl: onHide -> pause | 初始运行态 | anim.onHide() | animationsPaused=true | 无 | 退出场景 |
| TC-UNIT-040 | US-04 | AC-04-04 | UNIT | useAnimationControl: onShow -> resume | 暂停态 | anim.onShow() | animationsPaused=false | 无 | 返回场景 |

### 2.2 集成测试用例（TC-INT-*）

聚焦 API 封装签名兼容性和模块间接口契约。

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 | 测试数据 | 备注 |
|-------|--------|--------|------|------|---------|------|---------|---------|------|
| TC-INT-001 | US-01 | AC-01-05 | INT | getDashboardDeviceFaultSummary 签名兼容性 | api.js 已加载 | 检查 api.getDashboardDeviceFaultSummary 类型 | typeof === "function"，参数为空箭头函数 () => http.get(...) | api 对象 | MOD-BD-011 |
| TC-INT-002 | ALL | ALL | INT | api.js 所有现有方法未被修改 | api.js 原始签名基线 | 对比 getDashboardPlcOnlineRate 等18个方法 | 签名未变，仅新增 getDashboardDeviceFaultSummary | api.js 全量 | 零回归 |
| TC-INT-003 | US-04 | AC-04-01 | INT | useBridgeDashboard 暴露22个 IFC | 模块设计 IFC-BD-002-01~22 | 检查 composable 返回值 | state(14个reactive属性)+6个methods+3个computed | 模块返回对象 | 接口契约 |
| TC-INT-004 | US-04 | AC-04-04 | INT | useAnimationControl 暴露5个 IFC | 模块设计 IFC-BD-003-01~05 | 检查 composable 返回值 | animationsPaused+pause+resume+onShow+onHide | 模块返回对象 | 接口契约 |
| TC-INT-005 | US-01 | AC-01-05 | INT | aggregateSubsystemStatus 输出4个子系统 | 各类输入 | 调用后检查返回数组.length | === 4 (fresh-air, hydraulic, air-quality, energy) | 正常输入 | 输出完整性 |
| TC-INT-006 | US-01 | AC-01-09 | INT | deriveEnergyStatus 数据源标注 | plcRate或faultEvents有数据 | 检查返回的 dataSource 字段 | 非空字符串，描述数据来源 | 各种输入 | 调试用字段 |

### 2.3 E2E 测试用例（TC-E2E-*）

聚焦完整用户操作路径。**注意：由于测试环境无WeChat开发者工具/真机，以下E2E用例作为场景验收检查清单，实际执行状态标注为 DEFERRED。**

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 | 测试数据 | 备注 |
|-------|--------|--------|------|------|---------|------|---------|---------|------|
| TC-E2E-001 | US-01 | AC-01-01~03 | E2E | 业主进入舰桥看到整体健康状态 | 用户已登录，绑定1个座舱，有活跃故障 | 进入舰桥页面 | HealthIndicator 显示红色"告警"，菱形LED发光 | 含fault数据的座舱 | 完整链路 |
| TC-E2E-002 | US-02 | AC-02-01~02 | E2E | 战舰透视图完整渲染 | 页面加载完成 | 查看页面结构 | 自上而下：舰首铭牌→子系统dock→动力脊线→房间网格→舰尾引擎 | 正常数据 | 视觉验收 |
| TC-E2E-003 | US-03 | AC-03-01 | E2E | 点击子系统隔舱弹出故障抽屉 | 新风隔舱有3条故障 | 点击新风隔舱 | 半屏抽屉弹出，显示3条故障记录（设备名+故障类型+严重程度+描述） | 3条error事件 | 点击交互 |
| TC-E2E-004 | US-03 | AC-03-03 | E2E | 点击正常隔舱显示"运行正常" | 空气品质子系统无故障 | 点击空气品质隔舱 | 抽屉显示"该子系统运行正常" | 0故障数据 | 空状态 |
| TC-E2E-005 | US-03 | AC-03-04 | E2E | 关闭故障抽屉 | 抽屉已打开 | 点击遮罩/下拉手柄/返回手势 | 抽屉关闭，返回舰桥页面 | 任意抽屉状态 | 关闭交互 |
| TC-E2E-006 | US-04 | AC-04-01 | E2E | 30秒自动刷新后隔舱颜色更新 | 初始无故障，30s后产生新故障 | 停留页面30s | 隔舱从绿色变为红色，计数更新 | 动态故障数据 | 轮询验证 |
| TC-E2E-007 | US-04 | AC-04-03 | E2E | 下拉手动刷新 | 页面已加载 | 执行下拉手势 | 显示刷新指示器，重新请求API，更新隔舱 | 正常数据 | 手动刷新 |
| TC-E2E-008 | US-05 | AC-05-01 | E2E | 多座舱切换 | 绑定3个座舱 | 选择座舱B | 页面数据切换为座舱B的房间和数据 | 3个bindings | 座舱切换 |
| TC-E2E-009 | US-05 | AC-05-03 | E2E | 单座舱时隐藏picker | 仅绑定1个座舱 | 进入页面 | picker不显示 | 1个binding | 条件渲染 |
| TC-E2E-010 | US-06 | AC-06-01 | E2E | 单个API失败不白屏 | device-fault-summary返回500 | 进入页面 | 子系统显示"数据不可用"，房间正常 | 模拟500 | 容错降级 |
| TC-E2E-011 | US-06 | AC-06-02 | E2E | 全部API失败展示错误横幅 | 全部4个API返回错误 | 进入页面 | 错误横幅显示，隔舱结构保留但不填充数据 | 全部500 | 全失败容错 |

---

## 3. 不可测试项

| AC-ID | 原因 | 备注 |
|-------|------|------|
| AC-02-01 | [NOT_TESTABLE — 视觉主观标准] 背景宇宙深空、星云星光、网格opacity 0.06、扫描线5s周期、引擎辉光均为CSS视觉效果，无法通过程序化断言验证"深邃"或"点缀"程度 | 代码审查可确认CSS规则存在 |
| AC-02-02 | [NOT_TESTABLE — 视觉布局] 页面结构自上而下：铭牌→dock→脊线→网格→引擎，为视觉布局，可通过代码审查验证DOM结构但无法通过自动化测试验证"呈现"效果 | 代码审查可确认DOM顺序 |
| AC-02-03 | [NOT_TESTABLE — 视觉一致性] 赛博朋克色调"深蓝、暗紫、霓虹青"及"发光轮廓线"为视觉主观标准，CSS色值可审查(#05070f/#2ff4e0/#7c3aed)但无法程序化断言"视觉一致性" | 代码审查可确认色值使用 |
| AC-02-04 | [NOT_TESTABLE — 需端到端环境] TabBar"舰桥"tab active态显示需要WeChat开发者工具/真机渲染，当前测试环境不可用 | 代码审查可确认ArkTabBar未修改 |
| AC-02-05 | [NOT_TESTABLE — 视觉主观] "不存在白色卡片、蓝色头、灰色底"为视觉验收标准，需人工在真机/开发者工具中确认 | 代码审查可确认无Material Design class名 |
| AC-01-11 | [NOT_TESTABLE — 代码审查] "不出现温度/kWh/湿度/CO2数值"需人工审查模板确保无对应数据绑定，单元测试可辅助验证RoomCompartment不接收此类props | 代码审查已通过（code_review_report.md） |
| AC-04-04 | [NOT_TESTABLE — 需端到端环境] "页面隐藏时停止轮询和动画"需要onHide生命周期事件，无法在Node.js单元测试中模拟 | 逻辑通过useAnimationControl单测验证 |
| AC-04-05 | [NOT_TESTABLE — 需网络模拟] "单API失败不锁全页"需要实际的Promise.allSettled网络失败场景，前端单元测试可验证逻辑但需端到端验证完整行为 | 逻辑通过aggregation函数设计验证 |

---

## 4. 回归测试策略

### 4.1 后端回归测试

**基线**：全量 Django 测试套件（2098 tests，SQLite + FREEARK_POC_MOCK 模式）

**已知待定失败（不视为回归）：**
- 6 个产品行为待定失败（见 project_test_suite_state.md）
- 1 个环境编码错误（Windows cp1252 + 中文log输出，非代码缺陷）

**执行策略**：
1. 运行 `python manage.py test --noinput --verbosity=1`
2. 收集 total / pass / fail / error / skip 计数
3. 对比本次结果与基线：若 fail+error 计数 <= 7（6+1已知），判定为 PASS

### 4.2 前端回归测试

API.js 签名兼容性：逐方法对比原始签名与新版本，确认仅新增 1 个方法（`getDashboardDeviceFaultSummary`）且无现有方法签名变更。

---

## 5. 门控条件

| 条件 | 阈值 | 验证方式 |
|------|------|---------|
| 单元测试通过率 | >= 80% | TC-UNIT-001 ~ TC-UNIT-040 PASS 计数 |
| 后端回归零新增失败 | fail+error <= 7 (已知) | Django test suite 结果比对 |
| API 签名兼容性 | 100% | api.js 方法签名对比 |
| 算术一致性 | total = pass + fail + skip + blocked | 测试报告 metrics 四则校验 |
| 需求覆盖 | 所有 US 至少有 1 个测试用例 | US x TC 矩阵对照 |

---

## 6. 知识库引用

| KB Entry | 应用场景 |
|----------|---------|
| KB: KE-REQ-003 | 骨架缓存与降级策略 — 指导 TC-E2E-010、TC-E2E-011 的容错场景设计 |
| KB: KE-REQ-004 | 业主端领域知识 — 指导 TC-UNIT-022~029 的房间状态聚合测试数据构造 |
| project_test_suite_state.md | 已知 6 个待定失败 + 测试标签分级，指导后端回归基线判定 |
| project_migration_drift_handwrite_scoped.md | 迁移漂移 — 测试建库方式确认 |
