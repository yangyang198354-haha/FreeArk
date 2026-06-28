<!--
  file: docs/testing/v1.11.2_miniapp_room_display/test_plan.md
  version: v1.11.2
  feature: miniapp_room_display
  author_agent: sub_agent_test_engineer
  created_at: 2026-06-28
  status: DRAFT
  input_refs:
    - docs/development/v1.11.2_miniapp_room_display/user_stories.md (status=DRAFT, PM confirmed APPROVED)
    - docs/development/v1.11.2_miniapp_room_display/implementation_plan.md (status=DRAFT, PM confirmed APPROVED)
    - docs/architecture/v1.11.2_miniapp_room_display/module_design.md
-->

# 测试计划 — v1.11.2 小程序温控面板房间名显示

---

## 1. 测试目标

验证 v1.11.2 引入的 `PANEL_DISPLAY_MAP` 常量及其在 `OwnersRealtimeParamsView` 中的应用，确保：

1. 4 个温控面板 sub_type（`panel_study_room` / `panel_bedroom` / `panel_children_room` / `panel_fourth_children`）的 `display` 字段通过 API 响应正确返回纯房间名（书房 / 次卧 / 主卧 / 儿童房），去除"-温控面板"后缀。
2. **反直觉映射（最高风险）** 正确实现：`panel_bedroom` → 次卧（非主卧），`panel_children_room` → 主卧（非儿童房）。
3. 系统级 sub_type（`main_thermostat`、`fresh_air` 等）的 `display` 保持 DB 原值，fallback 行为正确。
4. 三房户型（无书房）不返回 `panel_fourth_children`，四房户型 4 个 panel 同时正确显示。

---

## 2. 测试范围

### 2.1 范围内（In-Scope）

| 组件 | 路径 | 变更类型 |
|------|------|---------|
| `PANEL_DISPLAY_MAP` 常量 | `api/views_miniapp_device_settings.py` | 新增（变更 2） |
| `display` 字段覆写逻辑 | `api/views_miniapp_device_settings.py:279` | 修改（变更 3） |
| API 端点响应 | `GET /api/miniapp/owner/realtime-params/` | 行为变更 |
| 户型过滤集成 | `api/utils_room_filter.py`（只读依赖） | 验证现有行为 |

**覆盖用户故事**：US-01（P0）/ US-02（P0）/ US-03（P0）

### 2.2 范围外（Out-of-Scope）

| 排除项 | 理由 |
|--------|------|
| Web 端 `GET /api/device/realtime-params/` | 独立视图，不引用 `PANEL_DISPLAY_MAP`，US-04 范围确认 |
| `param-settings.vue` 参数设置页 | 不使用 `sub_type_display`（OQ-01 CLOSED） |
| 前端 `device-panel.vue` 渲染层 | API 响应结构不变，前端零改动 |
| `get_available_sub_types()` 户型过滤逻辑 | 现有逻辑正确，v1.11.2 不修改 |
| E2E（浏览器/小程序真机）| 超出本次测试范围，API 集成测试已覆盖关键路径 |

---

## 3. 测试分层策略

| 层级 | 标签 | 工具 | 覆盖率目标 | 门控阈值 |
|------|------|------|-----------|---------|
| 单元测试 | `@tag('unit')` | Django `TestCase`，直接 import 常量 | 100%（3/3 用例） | ≥ 80% |
| 集成测试 | `@tag('integration', 'panel_display')` | Django `TestCase` + `APIClient`，SQLite 内存 DB | 100%（8/8 用例） | ≥ 90% |
| E2E 测试 | 不适用 | — | 不适用 | 不适用 |

> **E2E 不适用说明**：本次改动集中于单一后端视图函数的单行逻辑修改，API 集成测试已完整覆盖从请求到响应的全链路（含权限验证、户型过滤、display 字段覆写）。前端不变，无需浏览器级 E2E。标注 `[NOT_TESTABLE — no frontend change, API integration covers full request-response chain]`。

---

## 4. 执行环境

| 项目 | 值 |
|------|---|
| Python | 3.11（`C:/Users/胖子熊/AppData/Local/Programs/Python/Python311/python.exe`）|
| Django 设置 | `freearkweb.test_settings` |
| 数据库 | SQLite 内存数据库（`file:memorydb_default?mode=memory&cache=shared`）|
| 测试数据隔离 | Django `TestCase`（每个测试方法前 SAVEPOINT，测试后回滚）|
| 环境变量 | `PYTHONUTF8=1 FREEARK_POC_MOCK=1` |
| 执行命令 | `python manage.py test api.tests.test_miniapp_owner_v1120 --settings=freearkweb.test_settings --verbosity=2` |
| 缓存清理 | 每个集成测试 `setUp/tearDown` 均调用 `invalidate_room_filter_cache()` |

---

## 5. 测试用例汇总表

### 5.1 单元测试（3 个）

| TC-ID | 测试类 / 方法 | 测试点 | 关联 US | 关联 AC | 风险级别 |
|-------|-------------|--------|--------|--------|---------|
| TC-UNIT-001 | `PanelDisplayMapConstantTest.test_tc_unit_001_constant_existence_and_correctness` | PANEL_DISPLAY_MAP 共 4 个键，4 个映射值均正确，系统级 sub_type 不在 map 中 | US-02 | AC-02-01, AC-02-02, AC-02-03, AC-02-04 | 低 |
| TC-UNIT-002 | `PanelDisplayMapConstantTest.test_tc_unit_002_counterintuitive_mapping_assertions` | 反直觉映射专项断言：panel_bedroom≠'主卧'，panel_children_room≠'儿童房' | US-02 | AC-02-02, AC-02-03 | **高** |
| TC-UNIT-003 | `PanelDisplayMapConstantTest.test_tc_unit_003_fallback_behavior_for_non_panel_keys` | `.get()` fallback 行为正确；系统级 key 不在 map | US-03 | AC-03-01, AC-03-02 | 中 |

### 5.2 集成测试（8 个）

| TC-ID | 测试类 | 测试点 | 关联 US | 关联 AC | 前置条件 | 风险级别 |
|-------|--------|--------|--------|--------|---------|---------|
| TC-INTG-001 | `TC_INTG_001_PanelStudyRoomDisplayTest` | panel_study_room display='书房'，不含后缀 | US-01, US-02 | AC-02-01 | 三房户型（次卧/主卧/儿童房）| 低 |
| TC-INTG-002 | `TC_INTG_002_PanelBedroomDisplayTest` | panel_bedroom display='次卧' 且 ≠'主卧'（最高风险串房） | US-02 | AC-02-02 | 三房户型 | **高** |
| TC-INTG-003 | `TC_INTG_003_PanelChildrenRoomDisplayTest` | panel_children_room display='主卧' 且 ≠'儿童房'（第二高风险） | US-02 | AC-02-03 | 三房户型 | **高** |
| TC-INTG-004 | `TC_INTG_004_PanelFourthChildrenDisplayTest` | panel_fourth_children display='儿童房'（四房专属） | US-02 | AC-02-04 | 四房户型（书房/次卧/主卧/儿童房）| 中 |
| TC-INTG-005 | `TC_INTG_005_MainThermostatFallbackTest` | main_thermostat display 保持 DB 原值'主温控'，不被 map 覆写 | US-03 | AC-03-01 | 无 DeviceFloor/DeviceRoom（系统级始终可用）| 中 |
| TC-INTG-006 | `TC_INTG_006_FreshAirFallbackTest` | fresh_air display 保持 DB 原值'新风机组'，不被 map 覆写 | US-03 | AC-03-02 | 同 TC-INTG-005 | 中 |
| TC-INTG-007 | `TC_INTG_007_FourRoomAllPanelsDisplayTest` | 四房户型 4 个 panel 同时存在，display 均正确且互不相同 | US-01, US-02 | AC-01-02, AC-02-01~04 | 四房户型，4 DeviceConfig + 4 PLCLatestData | **高** |
| TC-INTG-008 | `TC_INTG_008_ThreeRoomNoPanelFourthChildrenTest` | 三房户型（无书房）不含 panel_fourth_children；三房 3 个 panel display 正确 | US-01 | AC-01-03 | 三房户型 | 中 |

---

## 6. 验收标准覆盖矩阵

| AC-ID | 描述摘要 | 覆盖 TC | 可测试性 |
|-------|---------|--------|---------|
| AC-01-01 | 面板卡片标题显示具体房间名（非"末端面板"）| TC-INTG-001~004, TC-INTG-007 | 可测试 |
| AC-01-02 | 四房户型 4 张卡片标题互不相同 | TC-INTG-007 | 可测试 |
| AC-01-03 | 三房户型 3 张卡片，不含"儿童房"（四房专属）| TC-INTG-008 | 可测试 |
| AC-02-01 | panel_study_room → '书房' | TC-UNIT-001, TC-INTG-001, TC-INTG-007, TC-INTG-008 | 可测试 |
| AC-02-02 | panel_bedroom → '次卧'（非'主卧'）| TC-UNIT-001, TC-UNIT-002, TC-INTG-002, TC-INTG-007 | 可测试 |
| AC-02-03 | panel_children_room → '主卧'（非'儿童房'）| TC-UNIT-001, TC-UNIT-002, TC-INTG-003, TC-INTG-007 | 可测试 |
| AC-02-04 | panel_fourth_children → '儿童房' | TC-UNIT-001, TC-INTG-004, TC-INTG-007 | 可测试 |
| AC-03-01 | main_thermostat display 不变 | TC-UNIT-003, TC-INTG-005 | 可测试 |
| AC-03-02 | fresh_air display 不变 | TC-UNIT-003, TC-INTG-006 | 可测试 |
| AC-03-03 | energy_meter 等其他系统级不变 | TC-UNIT-001（assertNotIn）, TC-UNIT-003（fallback）| 部分可测试（常量层验证） |
| AC-04-01 | 参数设置页不受 v1.11.2 改动影响 | [NOT_TESTABLE — 参数设置页不使用 sub_type_display，代码核验已确认（OQ-01 CLOSED），无需运行时测试] | 不可测试 |
| AC-04-02 | 参数设置页参数写入无回归 | [NOT_TESTABLE — 写链路使用 product_code_role 配置，与本次改动无交集（OQ-01 CLOSED）] | 不可测试 |

---

## 7. 测试文件位置

| 文件 | 路径 |
|------|------|
| 测试套件 | `FreeArkWeb/backend/freearkweb/api/tests/test_miniapp_owner_v1120.py` |
| 测试计划 | `docs/testing/v1.11.2_miniapp_room_display/test_plan.md`（本文件）|
| 测试报告 | `docs/testing/v1.11.2_miniapp_room_display/test_report.md` |

---

*文档结束 — 共 11 个测试用例（3 单元 + 8 集成），覆盖 10 组 AC，2 组 AC 标注 NOT_TESTABLE*
