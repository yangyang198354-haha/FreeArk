<!--
  file: docs/testing/v1.11.2_miniapp_room_display/test_report.md
  version: v1.11.2
  feature: miniapp_room_display
  author_agent: sub_agent_test_engineer
  created_at: 2026-06-28
  executed_at: 2026-06-28
  status: DRAFT
  input_refs:
    - docs/testing/v1.11.2_miniapp_room_display/test_plan.md
    - FreeArkWeb/backend/freearkweb/api/tests/test_miniapp_owner_v1120.py
-->

# 测试报告 — v1.11.2 小程序温控面板房间名显示

---

## 1. 执行摘要

| 项目 | 值 |
|------|---|
| 执行日期 | 2026-06-28 |
| 执行人 | sub_agent_test_engineer |
| 测试套件 | `api.tests.test_miniapp_owner_v1120` |
| 执行命令 | `PYTHONUTF8=1 FREEARK_POC_MOCK=1 python manage.py test api.tests.test_miniapp_owner_v1120 --settings=freearkweb.test_settings --verbosity=2` |
| 执行时长 | 0.044s |
| 总用例数 | 11 |
| **通过（PASS）** | **11** |
| **失败（FAIL）** | **0** |
| 错误（ERROR） | 0 |
| 跳过（SKIP） | 0 |
| 阻塞（BLOCKED）| 0 |

### 通过率计算

- **单元测试通过率**：pass / (pass + fail) = 3 / (3 + 0) = **100.0%** ≥ 门控阈值 80% → **GATE PASSED**
- **集成测试通过率**：pass / (pass + fail) = 8 / (8 + 0) = **100.0%** ≥ 门控阈值 90% → **GATE PASSED**
- **整体通过率**：11 / (11 + 0) = **100.0%**

**算术校验**：total(11) = pass(11) + fail(0) + skip(0) + blocked(0) = 11 ✓

---

## 2. 真实测试运行原始输出（verbosity=2）

```
Creating test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
Found 11 test(s).
Operations to perform:
  Synchronize unmigrated apps: channels, corsheaders, messages, rest_framework, staticfiles
  Apply all migrations: admin, api, auth, authtoken, contenttypes, sessions
[... migrations applied ...]
Applying sessions.0001_initial...

test_tc_unit_001_constant_existence_and_correctness (api.tests.test_miniapp_owner_v1120.PanelDisplayMapConstantTest.test_tc_unit_001_constant_existence_and_correctness)
TC-UNIT-001: PANEL_DISPLAY_MAP 共 4 个键，每个映射值正确。 ... ok
test_tc_unit_002_counterintuitive_mapping_assertions (api.tests.test_miniapp_owner_v1120.PanelDisplayMapConstantTest.test_tc_unit_002_counterintuitive_mapping_assertions)
TC-UNIT-002: 反直觉映射专项断言（最高风险防串房）。 ... ok
test_tc_unit_003_fallback_behavior_for_non_panel_keys (api.tests.test_miniapp_owner_v1120.PanelDisplayMapConstantTest.test_tc_unit_003_fallback_behavior_for_non_panel_keys)
TC-UNIT-003: PANEL_DISPLAY_MAP.get() fallback 行为——非 panel 键返回 fallback 值。 ... ok
test_panel_study_room_display_is_shufang (api.tests.test_miniapp_owner_v1120.TC_INTG_001_PanelStudyRoomDisplayTest.test_panel_study_room_display_is_shufang)
panel_study_room display 应为'书房'，不含'-温控面板'后缀。 ... ok
test_panel_bedroom_display_is_ciwu_not_zhuwu (api.tests.test_miniapp_owner_v1120.TC_INTG_002_PanelBedroomDisplayTest.test_panel_bedroom_display_is_ciwu_not_zhuwu)
panel_bedroom display 应为'次卧'，且明确不为'主卧'（最高风险串房场景）。 ... ok
test_panel_children_room_display_is_zhuwu_not_ertongfang (api.tests.test_miniapp_owner_v1120.TC_INTG_003_PanelChildrenRoomDisplayTest.test_panel_children_room_display_is_zhuwu_not_ertongfang)
panel_children_room display 应为'主卧'，且明确不为'儿童房'（第二高风险串房场景）。 ... ok
test_panel_fourth_children_display_is_ertongfang (api.tests.test_miniapp_owner_v1120.TC_INTG_004_PanelFourthChildrenDisplayTest.test_panel_fourth_children_display_is_ertongfang)
panel_fourth_children display 应为'儿童房'（四房户型专属）。 ... ok
test_main_thermostat_display_is_db_value (api.tests.test_miniapp_owner_v1120.TC_INTG_005_MainThermostatFallbackTest.test_main_thermostat_display_is_db_value)
main_thermostat display 应保持 DB 原值'主温控'，不被 PANEL_DISPLAY_MAP 覆写。 ... ok
test_fresh_air_display_is_db_value (api.tests.test_miniapp_owner_v1120.TC_INTG_006_FreshAirFallbackTest.test_fresh_air_display_is_db_value)
fresh_air display 应保持 DB 原值'新风机组'，不被 PANEL_DISPLAY_MAP 覆写。 ... ok
test_all_four_panels_display_correct_and_distinct (api.tests.test_miniapp_owner_v1120.TC_INTG_007_FourRoomAllPanelsDisplayTest.test_all_four_panels_display_correct_and_distinct)
四房户型：4 个 panel sub_type 的 display 均正确，且互不相同（完整防串房验证）。 ... ok
test_three_room_has_no_panel_fourth_children (api.tests.test_miniapp_owner_v1120.TC_INTG_008_ThreeRoomNoPanelFourthChildrenTest.test_three_room_has_no_panel_fourth_children)
三房户型（无书房）不应返回 panel_fourth_children sub_type。 ... ok

----------------------------------------------------------------------
Ran 11 tests in 0.044s

OK
Destroying test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
 OK
System check identified no issues (0 silenced).
```

---

## 3. 逐用例结果表

### 3.1 单元测试（TC-UNIT-*）

| TC-ID | 测试方法 | 关联 AC | 结果 | 说明 |
|-------|---------|--------|------|------|
| TC-UNIT-001 | `test_tc_unit_001_constant_existence_and_correctness` | AC-02-01, AC-02-02, AC-02-03, AC-02-04 | **PASS** | PANEL_DISPLAY_MAP 4 个键，4 个值均正确，系统级 sub_type 不在 map 中 |
| TC-UNIT-002 | `test_tc_unit_002_counterintuitive_mapping_assertions` | AC-02-02, AC-02-03 | **PASS** | panel_bedroom='次卧'（非'主卧'），panel_children_room='主卧'（非'儿童房'）|
| TC-UNIT-003 | `test_tc_unit_003_fallback_behavior_for_non_panel_keys` | AC-03-01, AC-03-02 | **PASS** | fallback 行为正确，3 个系统级 sub_type 均不在 map 中 |

**单元测试小计：Total 3 | Pass 3 | Fail 0 | Skip 0 | Blocked 0**
**通过率：3 / (3 + 0) = 100.0%**

### 3.2 集成测试（TC-INTG-*）

| TC-ID | 测试方法 | 关联 AC | 测试数据 | 结果 | 实际 display 值 |
|-------|---------|--------|---------|------|---------------|
| TC-INTG-001 | `test_panel_study_room_display_is_shufang` | AC-02-01 | 三房户型 + panel_study_room config(sub_type_display='书房-温控面板') | **PASS** | '书房' |
| TC-INTG-002 | `test_panel_bedroom_display_is_ciwu_not_zhuwu` | AC-02-02 | 三房户型 + panel_bedroom config(sub_type_display='次卧-温控面板') | **PASS** | '次卧'（且 ≠ '主卧' 已验证）|
| TC-INTG-003 | `test_panel_children_room_display_is_zhuwu_not_ertongfang` | AC-02-03 | 三房户型 + panel_children_room config(sub_type_display='主卧-温控面板') | **PASS** | '主卧'（且 ≠ '儿童房' 已验证）|
| TC-INTG-004 | `test_panel_fourth_children_display_is_ertongfang` | AC-02-04 | 四房户型 + panel_fourth_children config(sub_type_display='儿童房-温控面板') | **PASS** | '儿童房' |
| TC-INTG-005 | `test_main_thermostat_display_is_db_value` | AC-03-01 | main_thermostat config(sub_type_display='主温控')，无 DeviceFloor | **PASS** | '主温控'（DB 原值，未被覆写）|
| TC-INTG-006 | `test_fresh_air_display_is_db_value` | AC-03-02 | fresh_air config(sub_type_display='新风机组')，无 DeviceFloor | **PASS** | '新风机组'（DB 原值，未被覆写）|
| TC-INTG-007 | `test_all_four_panels_display_correct_and_distinct` | AC-01-02, AC-02-01~04 | 四房户型，4 个 config，4 个 PLCLatestData | **PASS** | {panel_study_room:'书房', panel_bedroom:'次卧', panel_children_room:'主卧', panel_fourth_children:'儿童房'} — 4 值互不相同 |
| TC-INTG-008 | `test_three_room_has_no_panel_fourth_children` | AC-01-03 | 三房户型，3 个 config + PLCLatestData | **PASS** | panel_fourth_children 不在响应中；三房 display：书房/次卧/主卧 均正确 |

**集成测试小计：Total 8 | Pass 8 | Fail 0 | Skip 0 | Blocked 0**
**通过率：8 / (8 + 0) = 100.0%**

---

## 4. 门控结论

| 门控条件 | 要求 | 实际 | 结论 |
|---------|------|------|------|
| 单元测试通过率 ≥ 80% | ≥ 80% | **100.0%** | **GATE PASSED** |
| 集成测试通过率 ≥ 90% | ≥ 90% | **100.0%** | **GATE PASSED** |
| US-01 有对应测试 | 必须 | TC-INTG-001~004, TC-INTG-007, TC-INTG-008 | **覆盖** |
| US-02 有对应测试 | 必须 | TC-UNIT-001~002, TC-INTG-001~004, TC-INTG-007 | **覆盖** |
| US-03 有对应测试 | 必须 | TC-UNIT-003, TC-INTG-005~006 | **覆盖** |

**最高风险串房场景验证结论**：
- AC-02-02（panel_bedroom → '次卧'，非'主卧'）：TC-UNIT-002 和 TC-INTG-002 双重验证，均 PASS。实现正确，无串房。
- AC-02-03（panel_children_room → '主卧'，非'儿童房'）：TC-UNIT-002 和 TC-INTG-003 双重验证，均 PASS。实现正确，无串房。
- AC-01-02（四房 4 值互不相同）：TC-INTG-007 验证通过。

---

## 5. 缺陷清单

无缺陷。所有 11 个测试用例均通过，未发现需要路由给 software_developer 的缺陷。

---

## 6. 不可测试项说明

| AC-ID | 原因 |
|-------|------|
| AC-04-01 | [NOT_TESTABLE — param-settings.vue 不使用 sub_type_display（OQ-01 CLOSED），代码核验已确认，此 AC 为约束性确认，无需运行时测试] |
| AC-04-02 | [NOT_TESTABLE — 参数设置写链路使用 product_code_role 配置，与 v1.11.2 改动无交集，无需运行时回归] |

---

## 7. 测试结论

v1.11.2 小程序温控面板房间名显示改动（`PANEL_DISPLAY_MAP` 常量新增 + 单行覆写逻辑）经 11 个测试用例全部验证通过。

**核心结论**：
1. 四个 panel sub_type 的 display 值均正确，与需求映射表严格一致。
2. 最高风险的反直觉映射（`panel_bedroom` → '次卧'，`panel_children_room` → '主卧'）通过常量层（TC-UNIT-002）和 API 层（TC-INTG-002 / TC-INTG-003）双重验证，无串房。
3. 系统级 sub_type fallback 行为正确，`main_thermostat` 和 `fresh_air` 的 display 保持 DB 原值，不受 PANEL_DISPLAY_MAP 影响。
4. 三房户型不返回 `panel_fourth_children`（现有过滤逻辑符合预期）。
5. 四房户型四个 panel 同时正确显示，display 值互不相同。

**建议 PM 决策**：本次测试结果满足所有门控要求，v1.11.2 可进入部署流程。

---

*文档结束 — 执行于 2026-06-28，11/11 测试通过（100%），0 缺陷，2 项 NOT_TESTABLE*
