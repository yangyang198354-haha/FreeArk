<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-05-20T00:00:00+08:00</timestamp>
  <project_name>FreeArk-DeviceSettings-v0.5.0</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>docs/requirements/requirements_spec_v0.5.0_device_settings.md</file>
    <file>docs/requirements/user_stories_v0.5.0_device_settings.md</file>
    <file>docs/architecture/architecture_design_v0.5.0_device_settings.md</file>
    <file>docs/architecture/module_design.md</file>
    <file>FreeArkWeb/backend/freearkweb/api/views_device_settings.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/param_value_label.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py</file>
    <file>FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue</file>
  </input_files>
  <phase>PHASE_04</phase>
  <status>DRAFT</status>
</file_header>

---

# 模块设计增量文档

**文档编号**：ARCH-MODULE-v0.5.0-device-settings  
**项目名称**：FreeArk 设备设置页面增量变更  
**版本**：v0.5.0  
**基线模块版本**：v0.4.0-APPROVED（`docs/architecture/module_design.md`）  
**日期**：2026-05-20  
**状态**：DRAFT

---

## 1. 模块变更总览

本次 v0.5.0 变更涉及 4 个文件的精准改动，全部为增量修改，不新增文件，不改变模块拓扑。

```
[变更文件]
├── 后端
│   ├── api/views_device_settings.py          ← MOD-01：可写性规则扩展
│   ├── api/param_value_label.py              ← MOD-02：精确名标签映射扩展
│   └── api/management/commands/
│       └── seed_device_config.py             ← MOD-03：DeviceConfig 激活状态修正
└── 前端
    └── frontend/src/views/
        └── DeviceSettingsPanelView.vue        ← MOD-04：脏值追踪逻辑
```

---

## 2. MOD-01：views_device_settings.py 模块 Diff

### 2.1 变更范围

**文件**：`FreeArkWeb/backend/freearkweb/api/views_device_settings.py`  
**关联需求**：REQ-FUNC-002, REQ-FUNC-003, REQ-NFUNC-001  
**关联 ADR**：ADR-09  

### 2.2 精确改动说明

**改动 1：扩展 WRITABLE_SUFFIXES 常量**

```python
# 变更前（第 19 行）
WRITABLE_SUFFIXES = ('_temp_setting', '_switch')

# 变更后
WRITABLE_SUFFIXES = ('_temp_setting', '_switch', '_mode')
```

说明：追加 `'_mode'` 使 `operation_mode` 命中后缀匹配，`_is_writable('operation_mode')` 返回 True。

**改动 2：新增 WRITABLE_PARAM_NAMES 精确名白名单**

```python
# 在 WRITABLE_SUFFIXES 行之后新增（第 20 行插入）
WRITABLE_PARAM_NAMES = frozenset({'away_energy_saving'})
```

说明：精确名白名单，使用 `frozenset` 保证 O(1) 查找，不可变避免运行时误修改。

**改动 3：扩展 _is_writable() 函数逻辑**

```python
# 变更前（第 26-29 行）
def _is_writable(param_name: str) -> bool:
    if any(param_name.endswith(s) for s in READONLY_SUFFIXES):
        return False
    return any(param_name.endswith(s) for s in WRITABLE_SUFFIXES)

# 变更后
def _is_writable(param_name: str) -> bool:
    if any(param_name.endswith(s) for s in READONLY_SUFFIXES):
        return False
    return (param_name in WRITABLE_PARAM_NAMES or
            any(param_name.endswith(s) for s in WRITABLE_SUFFIXES))
```

说明：精确名白名单检查和后缀匹配为 OR 关系，只读排除优先级不变。

### 2.3 不改动部分

- `device_settings_params` 函数：无需改动，现有 `_is_writable()` 调用（第 155 行）和 `get_value_options()` 调用（第 171 行）自动处理新字段
- `device_settings_write` 函数：无需改动，现有 `_is_writable()` 校验（第 207 行）自动拒绝非法写入
- 其余所有函数：不变

### 2.4 验证点

| 验证场景 | 期望结果 |
|---------|---------|
| `_is_writable('operation_mode')` | `True`（`_mode` 后缀命中） |
| `_is_writable('away_energy_saving')` | `True`（精确名命中） |
| `_is_writable('living_room_switch')` | `True`（`_switch` 后缀命中，不变） |
| `_is_writable('living_room_temperature')` | `False`（`_temperature` 只读后缀优先排除） |
| `_is_writable('living_room_temp_setting')` | `True`（`_temp_setting` 后缀命中，不变） |
| `_is_writable('hydraulic_module_low_temp_error')` | `False`（`_error` 只读后缀优先排除） |
| `_is_writable('central_energy_supply')` | `False`（不在白名单，不匹配任何 WRITABLE 后缀） |

---

## 3. MOD-02：param_value_label.py 模块 Diff

### 3.1 变更范围

**文件**：`FreeArkWeb/backend/freearkweb/api/param_value_label.py`  
**关联需求**：REQ-FUNC-003  
**关联 ADR**：ADR-09（§4 标签映射扩展）

### 3.2 精确改动说明

**改动 1：新增 PARAM_EXACT_VALUE_LABELS 精确名字典**

```python
# 在 PARAM_VALUE_LABELS 字典之前新增
PARAM_EXACT_VALUE_LABELS = {
    'away_energy_saving': {"0": "未启用离家节能", "1": "启用离家节能"},
}
```

**改动 2：get_value_options() 增加精确名优先查找**

```python
# 变更前
def get_value_options(param_name: str) -> list:
    for suffix, mapping in PARAM_VALUE_LABELS.items():
        if param_name.endswith(suffix):
            return [{"raw": k, "label": v} for k, v in mapping.items()]
    return []

# 变更后
def get_value_options(param_name: str) -> list:
    # 精确名优先
    if param_name in PARAM_EXACT_VALUE_LABELS:
        return [{"raw": k, "label": v} for k, v in PARAM_EXACT_VALUE_LABELS[param_name].items()]
    # 后缀匹配降级
    for suffix, mapping in PARAM_VALUE_LABELS.items():
        if param_name.endswith(suffix):
            return [{"raw": k, "label": v} for k, v in mapping.items()]
    return []
```

**改动 3：get_display_value() 增加精确名优先查找**

```python
# 变更前
def get_display_value(param_name: str, raw_value) -> str:
    if raw_value is None:
        return "—"
    raw_str = str(raw_value)
    for suffix, mapping in PARAM_VALUE_LABELS.items():
        if param_name.endswith(suffix):
            return mapping.get(raw_str, raw_str)
    unit = ""
    for suffix, u in PARAM_UNITS.items():
        if param_name.endswith(suffix):
            unit = f" {u}"
            break
    return f"{raw_str}{unit}"

# 变更后
def get_display_value(param_name: str, raw_value) -> str:
    if raw_value is None:
        return "—"
    raw_str = str(raw_value)
    # 精确名优先
    if param_name in PARAM_EXACT_VALUE_LABELS:
        return PARAM_EXACT_VALUE_LABELS[param_name].get(raw_str, raw_str)
    # 后缀匹配降级
    for suffix, mapping in PARAM_VALUE_LABELS.items():
        if param_name.endswith(suffix):
            return mapping.get(raw_str, raw_str)
    unit = ""
    for suffix, u in PARAM_UNITS.items():
        if param_name.endswith(suffix):
            unit = f" {u}"
            break
    return f"{raw_str}{unit}"
```

### 3.3 验证点

| 调用 | 期望结果 |
|------|---------|
| `get_value_options('away_energy_saving')` | `[{"raw": "0", "label": "未启用离家节能"}, {"raw": "1", "label": "启用离家节能"}]` |
| `get_display_value('away_energy_saving', '0')` | `"未启用离家节能"` |
| `get_display_value('away_energy_saving', '1')` | `"启用离家节能"` |
| `get_display_value('away_energy_saving', None)` | `"—"` |
| `get_value_options('operation_mode')` | `[{"raw": "0", "label": "制冷"}, {"raw": "1", "label": "制热"}, {"raw": "2", "label": "通风"}, {"raw": "3", "label": "除湿"}]`（后缀匹配，不变） |
| `get_value_options('living_room_switch')` | `[{"raw": "0", "label": "关"}, {"raw": "1", "label": "开"}]`（后缀匹配，不变） |

---

## 4. MOD-03：seed_device_config.py 模块 Diff

### 4.1 变更范围

**文件**：`FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py`  
**关联需求**：REQ-FUNC-001, REQ-NFUNC-004  
**关联分析**：架构设计 §3 CHG-01 方案 B

### 4.2 精确改动说明

**改动 1：HVAC_PARAM_CONFIGS 中 main_thermostat/system_switch 条目增加 is_active 标记**

```python
# 变更前（第 67-73 行）
{
    'param_name': 'system_switch',
    'display_name': '系统开关',
    'group': 'hvac',
    'sub_type': 'main_thermostat',
    'group_display': '暖通',
    'sub_type_display': '主温控',
},

# 变更后
{
    'param_name': 'system_switch',
    'display_name': '系统开关',
    'group': 'hvac',
    'sub_type': 'main_thermostat',
    'group_display': '暖通',
    'sub_type_display': '主温控',
    'is_active': False,    # CHG-01：主温控下的系统开关不再展示（水力模块保留）
},
```

**改动 2：handle() 方法中增加对 is_active=False 标记条目的特殊处理**

```python
# 变更前（第 767-786 行）
for cfg in HVAC_PARAM_CONFIGS:
    obj, created = DeviceConfig.objects.get_or_create(
        param_name=cfg['param_name'],
        sub_type=cfg['sub_type'],
        defaults={
            'display_name': cfg['display_name'],
            'group': cfg['group'],
            'group_display': cfg['group_display'],
            'sub_type_display': cfg['sub_type_display'],
            'is_active': True,
        },
    )
    if created:
        created_count += 1
        self.stdout.write(...)
    else:
        skipped_count += 1
        self.stdout.write(...)

# 变更后
for cfg in HVAC_PARAM_CONFIGS:
    # 若条目明确标记了 is_active=False，使用 update_or_create 强制更新（不跳过）
    if cfg.get('is_active') is False:
        obj, created = DeviceConfig.objects.update_or_create(
            param_name=cfg['param_name'],
            sub_type=cfg['sub_type'],
            defaults={
                'display_name': cfg['display_name'],
                'group': cfg['group'],
                'group_display': cfg['group_display'],
                'sub_type_display': cfg['sub_type_display'],
                'is_active': False,
            },
        )
        action = 'deactivated(created)' if created else 'deactivated(updated)'
        self.stdout.write(
            f'  [{action}] {cfg["param_name"]} -> {cfg["sub_type"]} (is_active=False)'
        )
        if created:
            created_count += 1
        # 注：update 不计入 skipped_count，单独统计（此处简化处理归入 created_count 体系外）
    else:
        # 默认行为：get_or_create，跳过已存在记录（保持原有幂等语义）
        obj, created = DeviceConfig.objects.get_or_create(
            param_name=cfg['param_name'],
            sub_type=cfg['sub_type'],
            defaults={
                'display_name': cfg['display_name'],
                'group': cfg['group'],
                'group_display': cfg['group_display'],
                'sub_type_display': cfg['sub_type_display'],
                'is_active': True,
            },
        )
        if created:
            created_count += 1
            self.stdout.write(
                f'  [created] {cfg["param_name"]} -> {cfg["sub_type"]} ({cfg["display_name"]})'
            )
        else:
            skipped_count += 1
            self.stdout.write(f'  [skipped] {cfg["param_name"]} already exists')
```

### 4.3 幂等性保证（REQ-NFUNC-004）

| 场景 | 行为 |
|------|------|
| 首次执行（无记录） | `update_or_create` 创建 `is_active=False` 记录 |
| 再次执行（记录已存在且 `is_active=False`） | `update_or_create` 更新为 `is_active=False`（实际无变化），无副作用 |
| 再次执行（记录已存在且被手动改回 `is_active=True`）| `update_or_create` 重新设为 `is_active=False`，符合预期 |
| `--reset` 模式执行 | 先删除全部记录，重建时 `is_active=False` 条目被正确创建 |

### 4.4 验证点

执行 `python manage.py seed_device_config` 后：
- `DeviceConfig.objects.filter(param_name='system_switch', sub_type='main_thermostat').values_list('is_active', flat=True)` 应返回 `[False]`
- `DeviceConfig.objects.filter(param_name='system_switch', sub_type='hydraulic_module').values_list('is_active', flat=True)` 应返回 `[True]`（不受影响）

---

## 5. MOD-04：DeviceSettingsPanelView.vue 模块 Diff

### 5.1 变更范围

**文件**：`FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue`  
**关联需求**：REQ-FUNC-004, REQ-NFUNC-002  
**关联 ADR**：ADR-10

### 5.2 精确改动说明

本节描述所有改动的精确位置和内容，以供开发人员按图索骥实施。

**改动 1：新增 dirtyFields ref（setup() 状态区）**

```javascript
// 在 const pendingBatchId = ref(null) 之后插入
const dirtyFields = ref(new Set())
```

**改动 2：模板 el-select 新增 @change 事件**

```vue
<!-- 变更前 -->
<el-select
  v-if="row.value_options && row.value_options.length > 0"
  v-model="inputValues[row.param_name]"
  size="small"
  style="width:150px"
>

<!-- 变更后 -->
<el-select
  v-if="row.value_options && row.value_options.length > 0"
  v-model="inputValues[row.param_name]"
  size="small"
  style="width:150px"
  @change="() => markDirty(row.param_name)"
>
```

**改动 3：模板 el-input-number 新增 @change 事件**

```vue
<!-- 变更前 -->
<el-input-number
  v-else
  v-model="inputValues[row.param_name]"
  size="small"
  :min="parseNumJson(row.num_value_json).min"
  :max="parseNumJson(row.num_value_json).max"
  :step="parseNumJson(row.num_value_json).step || 1"
  style="width:150px"
/>

<!-- 变更后 -->
<el-input-number
  v-else
  v-model="inputValues[row.param_name]"
  size="small"
  :min="parseNumJson(row.num_value_json).min"
  :max="parseNumJson(row.num_value_json).max"
  :step="parseNumJson(row.num_value_json).step || 1"
  style="width:150px"
  @change="() => markDirty(row.param_name)"
/>
```

**改动 4：新增 markDirty 辅助函数**

```javascript
// 在 loadParams 函数之前新增
const markDirty = (paramName) => {
  dirtyFields.value.add(paramName)
}
```

**改动 5：loadParams 完成后清空 dirtyFields**

```javascript
// 变更前（loadParams 中 try 块末尾）
groups.value.forEach(g => {
  g.params.forEach(p => {
    paramDisplayMap.value[p.param_name] = p.display_name
    if (inputValues.value[p.param_name] === undefined) {
      if (p.value_options && p.value_options.length > 0) {
        inputValues.value[p.param_name] = p.current_value !== null && p.current_value !== undefined
          ? String(p.current_value)
          : p.value_options[0]?.raw ?? ''
      } else {
        inputValues.value[p.param_name] = p.current_value
      }
    }
  })
})

// 变更后（新增最后一行）
groups.value.forEach(g => {
  g.params.forEach(p => {
    paramDisplayMap.value[p.param_name] = p.display_name
    if (inputValues.value[p.param_name] === undefined) {
      if (p.value_options && p.value_options.length > 0) {
        inputValues.value[p.param_name] = p.current_value !== null && p.current_value !== undefined
          ? String(p.current_value)
          : p.value_options[0]?.raw ?? ''
      } else {
        inputValues.value[p.param_name] = p.current_value
      }
    }
  })
})
dirtyFields.value = new Set()   // 重新加载后清空脏状态
```

注意：`loadParams` 使用 `if (inputValues.value[p.param_name] === undefined)` 保护，不覆盖已有值；`dirtyFields` 的清空在赋值之后执行，确保语义正确（加载完成 = 脏状态归零）。

**改动 6：handleBatchSubmit 替换过滤逻辑**

```javascript
// 变更前
const changedItems = allParams
  .filter(p => {
    const v = inputValues.value[p.param_name]
    return v !== undefined && v !== null
  })
  .map(p => ({
    param_name: p.param_name,
    new_value: String(inputValues.value[p.param_name]),
  }))

if (changedItems.length === 0) {
  ElMessage.warning('没有可提交的参数')
  return
}

// 变更后
const changedItems = allParams
  .filter(p => dirtyFields.value.has(p.param_name))
  .map(p => ({
    param_name: p.param_name,
    new_value: String(inputValues.value[p.param_name]),
  }))

if (changedItems.length === 0) {
  ElMessage.warning('没有已修改的参数')
  return
}
```

说明：过滤条件从"值不为 null/undefined"改为"param_name 在 dirtyFields 中"；提示语从"没有可提交的参数"改为"没有已修改的参数"（与 REQ-FUNC-004 AC-004-01 文字一致）。

**改动 7：handleCancel 追加 dirtyFields 清空**

```javascript
// 变更前
const handleCancel = () => {
  groups.value.forEach(g => {
    g.params.forEach(p => {
      if (p.value_options && p.value_options.length > 0) {
        inputValues.value[p.param_name] = p.current_value !== null && p.current_value !== undefined
          ? String(p.current_value)
          : p.value_options[0]?.raw ?? ''
      } else {
        inputValues.value[p.param_name] = p.current_value
      }
    })
  })
  batchStatus.value = ''
  batchError.value = ''
  itemStatuses.value = []
}

// 变更后（追加最后一行）
const handleCancel = () => {
  groups.value.forEach(g => {
    g.params.forEach(p => {
      if (p.value_options && p.value_options.length > 0) {
        inputValues.value[p.param_name] = p.current_value !== null && p.current_value !== undefined
          ? String(p.current_value)
          : p.value_options[0]?.raw ?? ''
      } else {
        inputValues.value[p.param_name] = p.current_value
      }
    })
  })
  batchStatus.value = ''
  batchError.value = ''
  itemStatuses.value = []
  dirtyFields.value = new Set()  // 取消时清空脏状态
}
```

**改动 8：return 语句中暴露新函数/变量（供模板使用）**

```javascript
// 变更前
return {
  loading,
  loadError,
  groups,
  openGroups,
  inputValues,
  submitLoading,
  batchStatus,
  batchError,
  itemStatuses,
  loadParams,
  handleBatchSubmit,
  handleCancel,
  parseNumJson,
}

// 变更后（追加 markDirty）
return {
  loading,
  loadError,
  groups,
  openGroups,
  inputValues,
  submitLoading,
  batchStatus,
  batchError,
  itemStatuses,
  loadParams,
  handleBatchSubmit,
  handleCancel,
  parseNumJson,
  markDirty,
}
```

### 5.3 验证点（对应 AC）

| AC 编号 | 验证场景 | 期望行为 |
|---------|---------|---------|
| AC-004-01 | 页面加载完成后未修改任何参数，点击"提交" | `dirtyFields.size === 0`，显示"没有已修改的参数"，不发请求 |
| AC-004-02 | 修改 1 个参数后点击"提交" | `changedItems.length === 1`，请求 items 只含该参数 |
| AC-004-03 | 修改 K 个参数后点击"提交" | `changedItems.length === K`，请求 items 含所有修改参数 |
| AC-004-04 | 同一参数修改两次（0→1→2）后提交 | `dirtyFields` 中该参数只有一个条目，`inputValues` 为最终值 2，提交 items 中该参数 `new_value="2"` |
| AC-004-05 | 修改后调用 `loadParams` 完成 | `dirtyFields.size === 0`，再点"提交"显示"没有已修改的参数" |
| AC-005-01 | 修改若干参数后点"取消" | `inputValues` 恢复服务端值，`batchStatus` 清空 |
| AC-005-02 | 取消后直接点"提交" | `dirtyFields.size === 0`，显示"没有已修改的参数"，不发请求 |
| AC-005-03 | 取消后重新修改 1 个参数点"提交" | 仅提交该 1 个参数 |

---

## 6. 模块接口规格总结

### 6.1 _is_writable() 函数接口规格

```
函数名：_is_writable(param_name: str) -> bool
模块：api/views_device_settings.py
调用方：device_settings_params（GET 接口过滤）、device_settings_write（POST 接口校验）
行为变更：
  v0.4.7：仅后缀匹配
  v0.5.0：READONLY_SUFFIXES 排除 → 精确名白名单 OR 后缀匹配（任一为真返回 True）
新增可写参数：operation_mode（后缀 _mode）、away_energy_saving（精确名）
```

### 6.2 get_value_options() 函数接口规格

```
函数名：get_value_options(param_name: str) -> list[dict]
模块：api/param_value_label.py
调用方：views_device_settings.py（device_settings_params 中第 171 行）
行为变更：
  v0.4.7：仅后缀匹配，away_energy_saving 返回 []
  v0.5.0：精确名优先 → 后缀匹配降级，away_energy_saving 返回非空选项列表
```

### 6.3 handleBatchSubmit() 函数接口规格

```
函数名：handleBatchSubmit()
组件：DeviceSettingsPanelView.vue
行为变更：
  v0.4.7：changedItems = allParams.filter(值不为 null/undefined)
  v0.5.0：changedItems = allParams.filter(param_name in dirtyFields)
空提交提示语：v0.4.7 "没有可提交的参数" → v0.5.0 "没有已修改的参数"
```

---

## 7. 数据流变化说明

### 7.1 operation_mode 的完整数据流（v0.5.0 后）

```
前端加载：
GET /api/device-settings/params/{part}/
  → views_device_settings.py: _is_writable('operation_mode')
    → WRITABLE_SUFFIXES 中 '_mode' 命中 → True
  → get_value_options('operation_mode')
    → PARAM_VALUE_LABELS['_mode'] 命中 → [制冷/制热/通风/除湿]
  → 响应: operation_mode 在 hydraulic_module.params 中，含 value_options

前端展示：
  → el-select 渲染，选项 [制冷,制热,通风,除湿]
  → 当前值显示 display_value = get_display_value('operation_mode', plc_raw_value)

用户提交：
  → 用户选择"制热"(value=1) → @change → dirtyFields.add('operation_mode')
  → 点击"提交" → changedItems 含 {param_name:'operation_mode', new_value:'1'}
  → POST /api/device-settings/write/ → items:[{param_name:'operation_mode', new_value:'1'}]
  → 后端 _is_writable('operation_mode') = True → 通过校验 → MQTT publish → PLC 写入
```

### 7.2 away_energy_saving 的完整数据流（v0.5.0 后）

```
前端加载：
GET /api/device-settings/params/{part}/
  → views_device_settings.py: _is_writable('away_energy_saving')
    → READONLY_SUFFIXES 不命中 → 检查精确名白名单 → 'away_energy_saving' in WRITABLE_PARAM_NAMES → True
  → get_value_options('away_energy_saving')
    → PARAM_EXACT_VALUE_LABELS['away_energy_saving'] 命中 → [未启用离家节能/启用离家节能]
  → 响应: away_energy_saving 在 hydraulic_module.params 中，含 value_options

前端展示：
  → el-select 渲染，选项 [未启用离家节能, 启用离家节能]

用户提交：
  → 用户选择"启用离家节能"(value=1) → @change → dirtyFields.add('away_energy_saving')
  → 点击"提交" → changedItems 含 {param_name:'away_energy_saving', new_value:'1'}
  → POST /api/device-settings/write/ → 后端 _is_writable('away_energy_saving') = True → PLC 写入 offset=105
```

---

## 8. 无 DB Migration 说明

本次 v0.5.0 变更不产生任何 Django migration，原因：
1. `DeviceConfig.is_active` 字段已存在于 model（v0.4.0 已有）；CHG-01 仅修改数据值，不修改 schema。
2. 不新增任何 model 字段或新表。
3. `seed_device_config.py` 是 management command（数据初始化脚本），不是 migration，其执行不由 `manage.py migrate` 驱动。

部署时需手动执行：`python manage.py seed_device_config`（或附带 `--reset` 如需重建全量数据）。
