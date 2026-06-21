<!--
file_header:
  project: FreeArk_TempParamFix
  document: implementation_plan.md
  version: 1.0.0
  status: APPROVED
  author_agent: sub_agent_software_developer
  created_at: 2026-06-21
  description: 温度显示与步进控件修复——实现计划
-->

# 实现计划
**项目**：FreeArk_TempParamFix  
**版本**：1.0.0  
**状态**：APPROVED  
**日期**：2026-06-21

---

## 一、变更文件清单

| 文件路径 | 变更类型 | 关联需求 |
|---------|---------|---------|
| `FreeArkWeb/backend/freearkweb/api/param_value_label.py` | 修改 `get_display_value` 函数 | REQ-FUNC-001 |
| `FreeArkWeb/backend/freearkweb/api/tests/test_device_settings_v050.py` | 更新 `test_UT_VL_13` 断言 | REQ-FUNC-001 |
| `FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue` | 替换温度控件、添加换算逻辑 | REQ-FUNC-002~006 |
| `FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.test.js` | 新增前端单元测试 | US-001~007 |

---

## 二、后端实现（param_value_label.py）

### 2.1 修改内容

在 `get_display_value` 函数末尾（后缀匹配循环之后、通用单位处理之前）插入 `_temp_setting` 专属换算分支：

```python
# v0.6.0: _temp_setting 参数存储放大 10 倍的整数，展示时须 ÷10 保留一位小数
if param_name.endswith("_temp_setting"):
    try:
        display_val = f"{float(raw_value) / 10:.1f}"
        return f"{display_val} ℃"
    except (TypeError, ValueError):
        # raw_value 非数字时安全兜底
        return f"{raw_str} ℃"
```

### 2.2 不影响范围

- `_temperature`（只读）：仍走通用 `PARAM_UNITS` 分支，原样返回
- `_humidity`：同上
- 枚举参数（`_switch`/`_mode`/精确名）：在更早的分支中命中，不到达此处
- `raw_value=None`：在函数开头 `if raw_value is None: return "—"` 已处理

---

## 三、前端实现（DeviceSettingsPanelView.vue）

### 3.1 边界映射（TEMP_BOUNDS_MAP，REQ-FUNC-006）

在 `<script>` 最顶部、组件定义之外，集中定义常量：

```js
const TEMP_BOUNDS_MAP = {
  living_room_temp_setting:          { min: 16.0, max: 30.0, step: 0.5 },
  bedroom_temp_setting:              { min: 16.0, max: 30.0, step: 0.5 },
  study_room_temp_setting:           { min: 16.0, max: 30.0, step: 0.5 },
  children_room_temp_setting:        { min: 16.0, max: 30.0, step: 0.5 },
  fourth_children_room_temp_setting: { min: 16.0, max: 30.0, step: 0.5 },
  supply_air_temp_setting:           { min: 10.0, max: 30.0, step: 0.5 },
}
const TEMP_BOUNDS_DEFAULT = { min: 16.0, max: 30.0, step: 0.5 }
```

### 3.2 温度步进控件（模板，REQ-FUNC-002/003）

替换原 `el-input-number`，对 `_temp_setting` 参数使用自定义步进控件：

```html
<div v-else-if="row.param_name.endsWith('_temp_setting')" class="temp-stepper">
  <el-button size="small"
    :disabled="inputValues[row.param_name] <= getTempBounds(row.param_name).min"
    @click="stepTemp(row.param_name, -1)">－</el-button>
  <span class="temp-display">{{ formatTempDisplay(inputValues[row.param_name]) }}</span>
  <el-button size="small"
    :disabled="inputValues[row.param_name] >= getTempBounds(row.param_name).max"
    @click="stepTemp(row.param_name, +1)">＋</el-button>
</div>
```

`span.temp-display` 为只读展示框，无 `input`，天然禁止键盘输入（REQ-FUNC-002，AC-005）。

### 3.3 初始化展示值（loadParams，REQ-FUNC-002 初始化）

```js
} else if (p.param_name.endsWith('_temp_setting')) {
  // 底层整数 ÷10 转为展示值（℃）
  inputValues.value[p.param_name] = (rawInt !== null && rawInt !== undefined)
    ? Math.round(Number(rawInt)) / 10
    : getTempBounds(p.param_name).min
}
```

### 3.4 步进函数（stepTemp，浮点精度保证）

用整数算术避免 JS 浮点精度问题：

```js
const stepInt = Math.round(bounds.step * 10)  // 0.5 → 5
const newInt = currentInt + delta * stepInt
const clampedInt = Math.max(minInt, Math.min(maxInt, newInt))
inputValues.value[paramName] = clampedInt / 10
```

### 3.5 提交反向换算（handleBatchSubmit，REQ-FUNC-004）

```js
if (p.param_name.endsWith('_temp_setting')) {
  newValue = String(Math.round(inputValues.value[p.param_name] * 10))
} else {
  newValue = String(inputValues.value[p.param_name])
}
```

---

## 四、测试文件（DeviceSettingsPanelView.test.js）

38 个纯函数单元测试，覆盖：
- `TEMP_BOUNDS_MAP` 边界映射（3 项）
- `rawIntToDisplayTemp` 初始化（4 项）
- `formatTempDisplay` 格式化（4 项）
- `stepTempPure` 步进逻辑（9 项）
- 禁用逻辑（4 项）
- `tempDisplayToSubmitValue` 反向换算（7 项）
- 非温度参数不受影响（5 项）
- 浮点精度保证（2 项）

---

## 五、不变层确认

- 后端 API 接口格式（`/api/device-settings/params/` 和 `/api/device-settings/write/`）：未改
- PLC 底层存储格式：未改
- 枚举参数（`_switch`/`_mode`/`away_energy_saving`/`central_energy_supply`）：走 `el-select`，逻辑不变
- 只读参数过滤机制：未改
