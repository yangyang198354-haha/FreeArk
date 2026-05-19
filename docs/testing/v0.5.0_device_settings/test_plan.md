<file_header>
  <author_agent>sub_agent_test_engineer</author_agent>
  <timestamp>2026-05-20T00:00:00+08:00</timestamp>
  <project_name>FreeArk-DeviceSettings-v0.5.0</project_name>
  <version>1.0.0</version>
  <input_files>
    <file>docs/requirements/requirements_spec_v0.5.0_device_settings.md</file>
    <file>docs/requirements/user_stories_v0.5.0_device_settings.md</file>
    <file>docs/development/v0.5.0_device_settings/implementation_plan.md</file>
    <file>docs/development/v0.5.0_device_settings/code_review_report.md</file>
    <file>FreeArkWeb/backend/freearkweb/api/views_device_settings.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/param_value_label.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py</file>
    <file>FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue</file>
  </input_files>
  <phase>PHASE_07</phase>
  <status>APPROVED</status>
</file_header>

---

# 测试计划

**项目**：FreeArk 设备设置页面增量变更  
**版本**：v0.5.0  
**关联需求**：`requirements_spec_v0.5.0_device_settings.md`  
**关联用户故事**：`user_stories_v0.5.0_device_settings.md`  
**关联评审报告**：`code_review_report.md`（GROUP_C PASS_WITH_CONDITIONS，FR-001 OPEN）  
**日期**：2026-05-20  
**状态**：APPROVED

---

## 1. 测试目标与范围

### 1.1 测试目标

1. 验证 4 项功能需求（REQ-FUNC-001~004）及其 19 条验收标准（AC）均有对应测试用例覆盖。
2. 验证 GROUP_C MINOR Finding FR-001（`el-input-number` 清空后 `String(undefined)` 提交）的边界行为，并提供最终处置建议。
3. 建立回归防护网，确保 v0.5.0 变更不破坏现有水力模块/主温控其他字段的读写行为。
4. 验证非功能需求（幂等性、安全性、向后兼容性）。

### 1.2 测试范围（in scope）

| 测试层次 | 覆盖模块 |
|---------|---------|
| 单元测试 | `_is_writable()`（v0.5.0 新增后缀/精确名）、`get_value_options()`、`get_display_value()`、`seed_device_config` 幂等性 |
| 集成测试 | `GET /api/device-settings/params/{specific_part}/`、`POST /api/device-settings/write/`、`DeviceSettingsBatchWriteSerializer` |
| FR-001 边界 | serializer 对 "undefined"/""/None 的行为；前端推荐修复方案验证 |
| 回归测试 | 现有 _switch/_temp_setting 字段可写性；只读字段保护；is_active 过滤 |

### 1.3 测试范围（out of scope）

- MQTT Broker 实际连通性测试（使用 Mock，不连接生产 Broker）
- PLC 寄存器实际写入验证（S7 协议层不在 Django 测试层覆盖范围内）
- 前端 Vue 组件自动化测试（受 Jest/Vitest 环境限制，本轮以逻辑推导形式覆盖）
- 数据库迁移测试（本次无 schema 变更）
- 其他视图页面（非设备设置页面）

---

## 2. 测试策略

### 2.1 测试层次与工具

| 层次 | 工具 | 数据库 | 说明 |
|-----|------|-------|------|
| 单元测试 | Django TestCase | SQLite in-memory | 不依赖外部服务，纯函数逻辑 |
| 集成测试 | DRF APIClient + Django TestCase | SQLite in-memory | 测试 HTTP 层 + ORM + 序列化器 |
| MQTT 隔离 | `unittest.mock.patch` | — | 替换 `_get_mqtt_client`，mock publish |
| 前端逻辑 | 代码审查 + 逻辑推导 | — | dirtyFields 状态机逻辑，无运行时环境 |

### 2.2 门控规则（串行通过率要求）

- 单元测试通过率必须 **≥ 80%** 方可继续执行集成测试。
- 集成测试通过率必须 **≥ 90%**。
- FR-001 专项测试：全部通过（5 条）。
- CRITICAL 级别 finding：数量必须为 0。

### 2.3 测试数据策略

- 所有测试使用 Django TestCase 的事务回滚机制，每个测试方法独立隔离。
- 测试用数据（OwnerInfo、DeviceConfig、PLCLatestData）均在 setUp 或测试方法内创建。
- 不依赖生产数据库中的任何数据。

---

## 3. 测试用例清单

### 3.1 单元测试用例（UT-*）

#### 3.1.1 _is_writable 单元测试（UT-W-*）

| 用例 ID | 描述 | 关联 AC | 预期结果 |
|--------|------|---------|---------|
| UT-W-01 | operation_mode 命中 _mode 后缀 → 可写 | REQ-FUNC-002, ADR-09 | True |
| UT-W-02 | 任意 _mode 后缀参数可写（后缀泛化） | REQ-FUNC-002 | True |
| UT-W-03 | _mode 不被 READONLY_SUFFIXES 拦截 | REQ-NFUNC-001 | True |
| UT-W-04 | away_energy_saving 精确名命中 WRITABLE_PARAM_NAMES | REQ-FUNC-003, ADR-09 | True |
| UT-W-05 | 精确名不做包含匹配（away_energy_saving_extra 不可写） | ADR-09 | False |
| UT-W-06 | 只读后缀优先于可写后缀（some_switch_error） | REQ-NFUNC-001 | False |
| UT-W-07 | _temperature 始终只读（回归） | REQ-NFUNC-001 | False |
| UT-W-08 | _fault 只读（回归） | REQ-NFUNC-001 | False |
| UT-W-09 | _alert 只读（回归） | REQ-NFUNC-001 | False |
| UT-W-10 | _error 只读（回归） | REQ-NFUNC-001 | False |
| UT-W-11 | _temp_setting 仍可写（回归） | REQ-NFUNC-003 | True |
| UT-W-12 | _switch 仍可写（回归，含 system_switch） | REQ-NFUNC-003 | True |
| UT-W-13 | central_energy_supply 不可写（ADR-09 副作用检查） | ADR-09 | False |
| UT-W-14 | _humidity 只读（回归） | REQ-NFUNC-001 | False |
| UT-W-15 | _dew_point_setting 只读（回归） | REQ-NFUNC-001 | False |

#### 3.1.2 param_value_label 单元测试（UT-VL-*）

| 用例 ID | 描述 | 关联 AC | 预期结果 |
|--------|------|---------|---------|
| UT-VL-01 | operation_mode 返回四个选项（制冷/制热/通风/除湿） | AC-002-02 | 4 个选项，标签正确 |
| UT-VL-02 | away_energy_saving 精确名优先，返回两个选项 | AC-003-02, ADR-09 | 2 个选项，标签正确 |
| UT-VL-03 | _switch 后缀返回关/开选项（回归） | AC-001-02 | ≥2 个选项 |
| UT-VL-04 | 未匹配参数名返回空列表 | — | [] |
| UT-VL-05 | 精确名优先于后缀匹配（ADR-09 优先级） | ADR-09 | 精确名标签 |
| UT-VL-06 | operation_mode=0 → display_value='制冷' | AC-002-01 | '制冷' |
| UT-VL-07 | operation_mode=1 → display_value='制热' | AC-002-01 | '制热' |
| UT-VL-08 | operation_mode=99 → 原值透传 | AC-002-04 | '99' |
| UT-VL-09 | away_energy_saving=1 → '启用离家节能' | AC-003-01 | '启用离家节能' |
| UT-VL-10 | away_energy_saving=0 → '未启用离家节能' | AC-003-01 | '未启用离家节能' |
| UT-VL-11 | raw_value=None → '—'（PLC 无数据） | AC-003-01 | '—' |
| UT-VL-12 | _switch 参数 display_value 正确（回归） | AC-001-02 | '关'/'开' |
| UT-VL-13 | _temp_setting 参数 display_value 含单位 | — | 含'℃' |

#### 3.1.3 seed_device_config 幂等性单元测试（UT-SD-*）

| 用例 ID | 描述 | 关联 AC | 预期结果 |
|--------|------|---------|---------|
| UT-SD-01 | 重复 update_or_create(is_active=False) 不产生重复记录 | REQ-NFUNC-004 | count=1, is_active=False |
| UT-SD-02 | 重复 get_or_create 不产生重复记录 | REQ-NFUNC-004 | count=1 |
| UT-SD-03 | 旧 is_active=True 记录被 update_or_create 强制更新为 False | REQ-FUNC-001, REQ-NFUNC-004 | is_active=False |
| UT-SD-04 | --reset 模式后重建无残留重复 | REQ-NFUNC-004 | count=1 |

#### 3.1.4 序列化器兼容性测试（UT-SER-*）

| 用例 ID | 描述 | 关联 AC | 预期结果 |
|--------|------|---------|---------|
| UT-SER-01 | operation_mode 可出现在 items，serializer 通过 | AC-002-03 | is_valid=True |
| UT-SER-02 | away_energy_saving 可出现在 items，serializer 通过 | AC-003-03 | is_valid=True |
| UT-SER-03 | 混合 v0.5.0 参数批量写入被接受 | AC-004-03 | is_valid=True, 3 items |

### 3.2 集成测试用例（IT-REQ-*）

#### 3.2.1 REQ-FUNC-001 集成测试

| 用例 ID | 描述 | 关联 AC | 预期结果 |
|--------|------|---------|---------|
| IT-REQ001-01 | API 返回的 main_thermostat 组不含 system_switch | AC-001-01, AC-001-03 | 无 system_switch |
| IT-REQ001-02 | hydraulic_module 组仍包含 system_switch | AC-001-02, AC-001-03 | 含 system_switch |
| IT-REQ001-03 | 主温控其他可写参数正常显示 | AC-001-01（不影响其余字段） | 含 living_room_temp_setting |
| IT-REQ001-04 | main_thermostat/system_switch is_active=False，UI 层无法选取 | AC-001-03 | params 不含该参数 |

#### 3.2.2 REQ-FUNC-002 集成测试

| 用例 ID | 描述 | 关联 AC | 预期结果 |
|--------|------|---------|---------|
| IT-REQ002-01 | 水力模块出现 operation_mode 字段 | AC-002-01 | 含 operation_mode |
| IT-REQ002-02 | operation_mode value_options 包含四选项 | AC-002-02 | 4 个，标签完整 |
| IT-REQ002-03 | operation_mode=0 当前值 display_value='制冷' | AC-002-01 | '制冷' |
| IT-REQ002-04 | POST write/{operation_mode=1} 返回 202 | AC-002-03 | 202, PLCWriteRecord 新增 |
| IT-REQ002-05 | 四个合法值均可写入（0/1/2/3） | AC-002-03 | 各返回 202 |
| IT-REQ002-06 | 非法值 99 后端不拒绝（透传） | AC-002-04 | 202, new_value='99' |

#### 3.2.3 REQ-FUNC-003 集成测试

| 用例 ID | 描述 | 关联 AC | 预期结果 |
|--------|------|---------|---------|
| IT-REQ003-01 | 水力模块出现 away_energy_saving 字段 | AC-003-01 | 含 away_energy_saving |
| IT-REQ003-02 | away_energy_saving value_options 包含两选项 | AC-003-02 | 2 个，标签正确 |
| IT-REQ003-03 | away_energy_saving=0 display_value='未启用离家节能' | AC-003-01 | '未启用离家节能' |
| IT-REQ003-04 | POST write/{away_energy_saving=1} 返回 202 | AC-003-03, AC-003-04 | 202 |
| IT-REQ003-05 | POST write/{away_energy_saving=0} 返回 202 | AC-003-03 | 202 |
| IT-REQ003-06 | _is_writable('away_energy_saving') = True（白名单确认） | AC-003-04 | True |

#### 3.2.4 REQ-FUNC-004 集成测试

| 用例 ID | 描述 | 关联 AC | 预期结果 |
|--------|------|---------|---------|
| IT-REQ004-01 | 单字段写入仅创建 1 条 PLCWriteRecord | AC-004-02 | count=1 |
| IT-REQ004-02 | 3 字段写入创建 3 条 PLCWriteRecord | AC-004-03 | count=3 |
| IT-REQ004-03 | 前端去重后仅发最终值，后端 1 条记录 | AC-004-04 | count=1, new_value='2' |
| IT-REQ004-04 | 空 items 被 serializer 拒绝（后端保护层） | AC-004-01 | 400 |
| IT-REQ004-05 | MQTT payload 中 items 只含已提交字段，未改动字段不出现 | AC-004-02 | payload 中无 system_switch |

#### 3.2.5 回归测试（IT-REG-*）

| 用例 ID | 描述 | 预期结果 |
|--------|------|---------|
| IT-REG-01 | 主温控 _switch 后缀字段仍可写 | True |
| IT-REG-02 | 主温控 _temp_setting 字段仍可写 | True |
| IT-REG-03 | 主温控只读字段仍只读（5类） | False（各类） |
| IT-REG-04 | living_room_switch 写入仍返回 202 | 202 |
| IT-REG-05 | 水力模块 system_switch 写入返回 202 | 202 |
| IT-REG-06 | central_energy_supply 不可写 | False |
| IT-REG-07 | 只读参数写入仍返回 400 | 400 |
| IT-REG-08 | is_active=False 参数不出现在 API 响应 | 无该参数 |

### 3.3 FR-001 边界测试（IT-FR1-*）

| 用例 ID | 描述 | 预期结果 |
|--------|------|---------|
| IT-FR1-01 | serializer 接受 "undefined" 字符串（后端不做枚举校验） | is_valid=True |
| IT-FR1-02 | "undefined" 值提交后端返回 202，记录 new_value="undefined" | 202，记录存在 |
| IT-FR1-03 | 空字符串 "" 被 serializer 拒绝 | is_valid=False |
| IT-FR1-04 | None 作为 new_value 被 serializer 拒绝 | is_valid=False |
| IT-FR1-05 | 推荐修复方案（undefined??''）产生空字符串，后端拒绝（双层保护） | is_valid=False |
| IT-FR1-06 | operation_mode=None display_value='—' | '—' |
| IT-FR1-07 | "undefined" 长度<50，确认风险点在 serializer 无法阻断 | len=9 < 50 |

---

## 4. 前端测试说明（逻辑推导方式）

由于本测试环境无法运行 Vitest/Jest 前端测试，dirtyFields 逻辑通过代码审查（code walkthrough）方式验证。以下逐一核查各关键路径：

### 4.1 markDirty / dirtyFields 状态机

| 场景 | 代码行 | 验证方式 | 结论 |
|-----|-------|---------|------|
| 首次 loadParams 后 dirtyFields 为空 | L149 `dirtyFields.value = new Set()` | 代码审查 | 正确 |
| el-select @change 触发 markDirty | L30 `@change="() => markDirty(row.param_name)"` | 代码审查 | 正确 |
| el-input-number @change 触发 markDirty | L47 `@change="() => markDirty(row.param_name)"` | 代码审查 | 正确 |
| handleBatchSubmit 用 dirtyFields.has() 过滤 | L167 `.filter(p => dirtyFields.value.has(...))` | 代码审查 | 正确 |
| 空 dirtyFields 时显示"没有已修改的参数" | L173-175 | 代码审查 | 正确 |
| handleCancel 清空 dirtyFields | L230 `dirtyFields.value = new Set()` | 代码审查 | 正确 |
| loadParams 完成后清空 dirtyFields | L149 | 代码审查 | 正确 |

### 4.2 AC 验收标准前端侧确认

| AC | 前端路径 | 确认结论 |
|----|---------|---------|
| AC-004-01（空提交无效） | changedItems.length===0 → ElMessage.warning | 已实现 |
| AC-004-02（仅修改1个字段提交1个） | dirtyFields.has() 过滤 | 已实现 |
| AC-004-03（K 个字段全提交） | 同上 | 已实现 |
| AC-004-04（多次修改取最终值） | dirtyFields 只记参数名，inputValues 存最终值 | 已实现 |
| AC-004-05（loadParams 后清空脏状态） | L149 | 已实现 |
| AC-005-01（取消后恢复服务端值） | handleCancel L214-226 | 已实现 |
| AC-005-02（取消后再提交无效） | dirtyFields 清空后 has() 全 false | 已实现 |
| AC-005-03（取消后可重新修改提交） | @change 触发 markDirty 重新记录 | 已实现 |

---

## 5. FR-001 处置方案

### 5.1 风险描述

`el-input-number` 组件在用户清空输入框后，`v-model` 绑定值变为 `undefined`。当用户触发 `@change` 事件时，`markDirty` 将该参数名加入 `dirtyFields`，后续 `handleBatchSubmit` 执行 `String(undefined)` = `"undefined"` 字符串并提交。

### 5.2 风险等级

**MINOR**（不阻塞 SDLC，但影响用户体验和数据质量）

原因：后端 serializer 接受 "undefined" 字符串（CharField max_length=50），不会返回 400。PLCWriteRecord 记录 new_value="undefined"。实际 PLC 写入时，任务调度器尝试将 "undefined" 解析为数值会失败，PLC 不会被误写。审计日志会留下 "undefined" 记录，干扰运维。

### 5.3 推荐修复方案

在 `handleBatchSubmit` 的 `.map` 阶段添加 undefined 值过滤：

```javascript
// 修复前
.map(p => ({
  param_name: p.param_name,
  new_value: String(inputValues.value[p.param_name]),
}))

// 修复后
.filter(p => dirtyFields.value.has(p.param_name))
.filter(p => inputValues.value[p.param_name] !== undefined && inputValues.value[p.param_name] !== null)
.map(p => ({
  param_name: p.param_name,
  new_value: String(inputValues.value[p.param_name]),
}))
```

或在 `markDirty` 调用时结合值检查（el-input-number 的 @change 回调签名已传入新值，可在此拦截）。

### 5.4 现有保护

- `el-input-number` 的 `min`/`max` 属性会限制用户输入范围，在有 `num_value_json` 的参数上，清空行为受控。
- 对于 `operation_mode` 和 `away_energy_saving`，这两个参数使用 `el-select`（不是 `el-input-number`），FR-001 不适用于这两个参数（选择器无法产生 undefined）。
- FR-001 实际影响范围仅限于使用 `el-input-number` 且用户主动清空的场景（如 `living_room_temp_setting` 等数值型参数）。

---

## 6. 测试执行命令

```bash
# 运行全部 v0.5.0 测试
cd FreeArkWeb/backend/freearkweb
python manage.py test api.tests.test_device_settings_v050 \
    --settings=freearkweb.test_settings --verbosity=2

# 仅单元测试
python manage.py test api.tests.test_device_settings_v050.IsWritableV050Tests \
    api.tests.test_device_settings_v050.ParamValueLabelTests \
    api.tests.test_device_settings_v050.SeedDeviceConfigIdempotencyTests \
    api.tests.test_device_settings_v050.SerializerV050CompatibilityTests \
    --settings=freearkweb.test_settings --verbosity=2

# 仅集成测试
python manage.py test api.tests.test_device_settings_v050.ReqFunc001SystemSwitchTests \
    api.tests.test_device_settings_v050.ReqFunc002OperationModeTests \
    api.tests.test_device_settings_v050.ReqFunc003AwayEnergySavingTests \
    api.tests.test_device_settings_v050.ReqFunc004DirtyFieldsTests \
    api.tests.test_device_settings_v050.RegressionProtectionTests \
    api.tests.test_device_settings_v050.FR001InputNumberUndefinedTests \
    --settings=freearkweb.test_settings --verbosity=2
```

---

## 7. 用例与 AC 覆盖矩阵

| AC 编号 | 关联用例 | 覆盖层次 |
|--------|---------|---------|
| AC-001-01 | IT-REQ001-01, IT-REG-08 | 集成 |
| AC-001-02 | IT-REQ001-02 | 集成 |
| AC-001-03 | IT-REQ001-01, IT-REQ001-02, IT-REQ001-04 | 集成 |
| AC-002-01 | IT-REQ002-01, IT-REQ002-03, UT-VL-06 | 集成+单元 |
| AC-002-02 | IT-REQ002-02, UT-VL-01 | 集成+单元 |
| AC-002-03 | IT-REQ002-04, IT-REQ002-05, UT-SER-01 | 集成+单元 |
| AC-002-04 | IT-REQ002-06, UT-VL-08 | 集成+单元 |
| AC-003-01 | IT-REQ003-01, IT-REQ003-03, UT-VL-09, UT-VL-10 | 集成+单元 |
| AC-003-02 | IT-REQ003-02, UT-VL-02 | 集成+单元 |
| AC-003-03 | IT-REQ003-04, IT-REQ003-05 | 集成 |
| AC-003-04 | IT-REQ003-06, UT-W-04 | 集成+单元 |
| AC-004-01 | IT-REQ004-04（后端保护层） | 集成 |
| AC-004-02 | IT-REQ004-01, IT-REQ004-05 | 集成 |
| AC-004-03 | IT-REQ004-02, UT-SER-03 | 集成+单元 |
| AC-004-04 | IT-REQ004-03 | 集成 |
| AC-004-05 | 前端代码审查（L149） | 逻辑推导 |
| AC-005-01 | 前端代码审查（L214-226） | 逻辑推导 |
| AC-005-02 | 前端代码审查（L230 + handleBatchSubmit） | 逻辑推导 |
| AC-005-03 | 前端代码审查（@change → markDirty） | 逻辑推导 |
| FR-001 | IT-FR1-01~IT-FR1-07（7条专项） | 集成+单元 |
