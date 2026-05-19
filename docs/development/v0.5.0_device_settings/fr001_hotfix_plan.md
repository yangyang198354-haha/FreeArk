<file_header>
  <author_agent>sub_agent_software_developer</author_agent>
  <timestamp>2026-05-20T02:00:00+08:00</timestamp>
  <project_name>FreeArk-DeviceSettings-v0.5.0</project_name>
  <version>1.0.0</version>
  <input_files>
    <file>docs/development/v0.5.0_device_settings/code_review_report.md</file>
    <file>docs/testing/v0.5.0_device_settings/integration_test_report.md</file>
    <file>FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue</file>
  </input_files>
  <phase>HOTFIX_FR001</phase>
  <status>APPROVED</status>
</file_header>

---

# FR-001 Hotfix 实施计划与决策记录

**项目**：FreeArk 设备设置页面增量变更  
**版本**：v0.5.0  
**Finding ID**：FR-001  
**Finding 来源**：GROUP_C 代码评审报告 §4.4  
**Finding 严重级别**：MINOR  
**日期**：2026-05-20  

---

## 1. 问题重述

### 1.1 根本原因

`el-input-number` 组件在用户清空输入框（删除所有字符）后，Element Plus 将 `v-model` 绑定的响应式值置为 `undefined`。

当此时 `@change` 事件触发，`markDirty(row.param_name)` 被调用，将该字段名加入 `dirtyFields` Set。随后用户点击"提交"时，`handleBatchSubmit` 仅按 `dirtyFields.has(p.param_name)` 过滤，并不检查值的合法性，因此将 `String(undefined)` = `"undefined"` 字符串放入 payload 提交到后端。

### 1.2 影响范围

| 参数类型 | 是否受影响 | 说明 |
|---------|---------|------|
| `el-select` 参数（枚举型，如 `operation_mode`、`away_energy_saving`） | 否 | el-select 不会产生 undefined 值，选项固定 |
| `el-input-number` 参数（数值型，如 `living_room_temp_setting`） | **是** | 用户清空时 value = undefined |

### 1.3 已有保护层评估

- 后端 `WriteItemSerializer.new_value` 为 `CharField(max_length=50)`，`"undefined"` 字符串（9字符）通过校验，不被拒绝
- 后端采用"透传 PLC"策略（与 AC-002-04 一致），不做枚举数值校验
- 该值被写入 `PLCWriteRecord`，并通过 MQTT 发送给 PLC；PLC 固件可能忽略非法数值，但存在不确定的写入副作用风险

---

## 2. 修复方案决策

### 2.1 候选方案评估

**方案 A：在 handleBatchSubmit 的 filter 链追加 undefined/null 过滤**

```js
// 在现有 dirtyFields.has(p.param_name) 过滤之后追加
.filter(p => inputValues.value[p.param_name] !== undefined
          && inputValues.value[p.param_name] !== null)
```

- 优点：改动最小，仅 2 行
- 缺点（存在语义矛盾）：字段仍留在 `dirtyFields` 中（被标记为"已修改"），但值为 undefined，在用户取消提交、重新修改前，该字段的"脏"状态会持续存在。若用户点击"取消"，`handleCancel` 会清空 `dirtyFields`，但若用户只是更换其他字段后再次提交，第二次提交仍会试图提交这个"undefined 脏字段"并被过滤——语义上勉强可行，但有认知负担

**方案 B：在 markDirty 中检测值，清空时从 dirtyFields 移除**

```js
const markDirty = (paramName) => {
  const val = inputValues.value[paramName]
  if (val === undefined || val === null) {
    dirtyFields.value.delete(paramName)  // 清空 = 取消修改
  } else {
    dirtyFields.value.add(paramName)
  }
}
```

- 优点：从根本上解决语义矛盾——"将 input-number 清空"被定义为"撤销对该字段的修改"，不是一种"提交空值"的修改。dirtyFields 始终只包含有有效值的字段，语义清晰
- 缺点：修改点在 markDirty，而非 handleBatchSubmit，与 FR-001 任务描述中"在 filter 链后追加"的主方向略有出入，需要额外说明

**方案 C（组合方案，本次采纳）：方案 B 为主 + 方案 A 作为防御性后盾**

在 `markDirty` 中加入值检测（方案 B），使 dirtyFields 的语义保持纯净。同时在 `handleBatchSubmit` 的 `.map()` 阶段对 `new_value` 做防御性兜底（方案 A 的简化形式），确保即使 dirtyFields 中意外存在 undefined 值的字段，也不会产生 "undefined" 字符串。

### 2.2 最终决策

**采纳方案 C（markDirty 语义修正 + handleBatchSubmit 防御性过滤双重保护）**

**决策理由：**

1. **语义正确性**：el-input-number 清空在 UX 上等同于"不修改该字段"，应从 dirtyFields 移除，而非标记为"提交 undefined"。这与 `handleCancel` 重置 inputValues 后清空 dirtyFields 的设计意图一致——两者都是"恢复到服务端状态"的语义。
2. **防御纵深**：方案 A 的 filter 作为第二道防线，即使将来 markDirty 逻辑被其他路径绕过，handleBatchSubmit 仍不会发出无效值。
3. **最小化改动原则**：只修改 `markDirty` 函数和 `handleBatchSubmit` 的 filter 链，不引入新的响应式变量或事件监听，不改变任何 template 绑定。

### 2.3 不采纳理由记录

- 不单独使用方案 A：语义矛盾（dirtyFields 存在"值无效的脏字段"）
- 不单独使用方案 B：缺乏防御性后盾，单点保护；且 GROUP_D 测试报告中建议方案包含 filter 过滤

---

## 3. 修改清单（最小化 diff）

### 3.1 目标文件

`FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue`

### 3.2 变更点 1：markDirty 函数

**位置**：`setup()` 函数内，原 markDirty 函数体

**修改前：**
```js
const markDirty = (paramName) => {
  dirtyFields.value.add(paramName)
}
```

**修改后：**
```js
// v0.5.0 FR-001 fix: el-input-number 清空后 value=undefined，不应标记为有效修改
const markDirty = (paramName) => {
  const val = inputValues.value[paramName]
  if (val === undefined || val === null) {
    dirtyFields.value.delete(paramName)
  } else {
    dirtyFields.value.add(paramName)
  }
}
```

**变更说明**：
- 新增 2 行逻辑，移除 1 行（`dirtyFields.value.add(paramName)` 移入 else 分支）
- 不改变 el-select 行为（el-select 值始终为 string，不产生 undefined/null）
- 对已有 el-input-number 功能无影响：用户输入有效数值时，`val` 为 number，走 `else` 分支正常添加到 dirtyFields

### 3.3 变更点 2：handleBatchSubmit filter 链

**位置**：`handleBatchSubmit` 函数，`changedItems` 赋值语句

**修改前：**
```js
const changedItems = allParams
  .filter(p => dirtyFields.value.has(p.param_name))
  .map(p => ({
    param_name: p.param_name,
    new_value: String(inputValues.value[p.param_name]),
  }))
```

**修改后：**
```js
const changedItems = allParams
  .filter(p => dirtyFields.value.has(p.param_name))
  .filter(p => inputValues.value[p.param_name] !== undefined
            && inputValues.value[p.param_name] !== null)  // FR-001 防御性过滤
  .map(p => ({
    param_name: p.param_name,
    new_value: String(inputValues.value[p.param_name]),
  }))
```

**变更说明**：
- 追加 1 个 `.filter()` 调用，共 2 行
- 方案 B（markDirty 修正）已在上游移除 undefined 字段，此处 filter 正常不会拦截任何字段
- 作为防御性后盾：若 dirtyFields 中意外存在 undefined 值的字段，此处静默过滤，不发送

### 3.4 不修改的内容（显式声明）

以下内容明确不在本次 hotfix 范围内，保持不变：
- template 模板层的所有 `@change` 绑定（不引入额外的 handler）
- `loadParams` 函数逻辑
- `handleCancel` 函数逻辑
- `handleAck` 函数逻辑
- 任何后端文件（views_device_settings.py、serializers_device_settings.py 等）
- 任何 MQTT 相关逻辑

---

## 4. 验证路径

修复后，以下场景应按预期工作：

| 场景 | 修复前行为 | 修复后预期行为 |
|------|---------|------------|
| 用户清空 el-input-number 后点击提交 | "undefined" 字符串被提交 | 该字段被过滤，payload 不含该字段；若无其他脏字段，显示"没有已修改的参数" |
| 用户清空后重新输入有效值，点击提交 | 正常提交（偶发）| 正常提交（markDirty 在第二次输入时重新 add，值为有效数字） |
| 多字段混合：1字段修改 + 1字段清空 + 1字段未修改 | 修改字段 + "undefined" 字段被提交 | 仅修改字段被提交 |
| el-select 参数正常修改提交 | 正常 | 不受影响（el-select 无 undefined 产生路径） |
| 用户修改数值型参数后正常提交 | 正常 | 不受影响（有效数字值走 `else add` 分支） |

---

## 5. commit 信息

```
fix(frontend): FR-001 — el-input-number 清空不提交 undefined

- markDirty: 值为 undefined/null 时删除 dirtyFields，而非标记为脏
- handleBatchSubmit: 追加防御性 filter 过滤 undefined/null 值
- 不修改 template 层绑定及其他任何文件

Fixes: FR-001 (GROUP_C code_review_report §4.4)
Scope: FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue
```
