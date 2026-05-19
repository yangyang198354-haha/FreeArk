<file_header>
  <author_agent>sub_agent_software_developer</author_agent>
  <timestamp>2026-05-20T00:00:00+08:00</timestamp>
  <project_name>FreeArk-DeviceSettings-v0.5.0</project_name>
  <version>1.0.0</version>
  <input_files>
    <file>docs/requirements/requirements_spec_v0.5.0_device_settings.md</file>
    <file>docs/architecture/architecture_design_v0.5.0_device_settings.md</file>
    <file>docs/architecture/module_design_v0.5.0_device_settings.md</file>
    <file>FreeArkWeb/backend/freearkweb/api/views_device_settings.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/param_value_label.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py</file>
    <file>FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue</file>
  </input_files>
  <phase>PHASE_05</phase>
  <status>APPROVED</status>
</file_header>

---

# 实施计划文档

**项目**：FreeArk 设备设置页面增量变更  
**版本**：v0.5.0  
**日期**：2026-05-20  
**作者**：sub_agent_software_developer

---

## 1. 实施总览

本次 v0.5.0 涉及 4 个文件的精准代码改动，全部为增量修改，无新增文件，无 DB 迁移。

| 文件 | 改动类型 | 改动规模 | 关联需求 | 状态 |
|------|---------|---------|---------|------|
| `api/views_device_settings.py` | 扩展可写性判断逻辑 | 5 行 | REQ-FUNC-002, REQ-FUNC-003, REQ-NFUNC-001 | 已实施 |
| `api/param_value_label.py` | 新增精确名标签映射 | 12 行 | REQ-FUNC-003 | 已实施 |
| `api/management/commands/seed_device_config.py` | DeviceConfig 激活状态修正 | 15 行 | REQ-FUNC-001, REQ-NFUNC-004 | 已实施 |
| `frontend/src/views/DeviceSettingsPanelView.vue` | 脏值追踪逻辑 | 18 行 | REQ-FUNC-004, REQ-NFUNC-002 | 已实施 |

---

## 2. 各文件改动明细

### 2.1 views_device_settings.py（MOD-01）

**改动位置**：文件头部常量区 + `_is_writable()` 函数体

**改动内容**：

```python
# 改动 1：WRITABLE_SUFFIXES 追加 '_mode'
WRITABLE_SUFFIXES = ('_temp_setting', '_switch', '_mode')

# 改动 2：新增 WRITABLE_PARAM_NAMES 精确名白名单
WRITABLE_PARAM_NAMES = frozenset({'away_energy_saving'})

# 改动 3：_is_writable() 逻辑扩展
def _is_writable(param_name: str) -> bool:
    if any(param_name.endswith(s) for s in READONLY_SUFFIXES):
        return False
    return (param_name in WRITABLE_PARAM_NAMES or
            any(param_name.endswith(s) for s in WRITABLE_SUFFIXES))
```

**效果验证**：
- `_is_writable('operation_mode')` → True（`_mode` 后缀命中）
- `_is_writable('away_energy_saving')` → True（精确名白名单命中）
- `_is_writable('living_room_temperature')` → False（只读后缀优先排除）
- `_is_writable('central_energy_supply')` → False（不在白名单，不匹配任何 WRITABLE 后缀）

### 2.2 param_value_label.py（MOD-02）

**改动位置**：模块顶部 + `get_value_options()` + `get_display_value()`

**改动内容**：
- 新增 `PARAM_EXACT_VALUE_LABELS` 字典，存放精确参数名到标签的映射
- `get_value_options()` 和 `get_display_value()` 均先查精确名字典，再降级到后缀匹配

**效果验证**：
- `get_value_options('away_energy_saving')` → `[{"raw":"0","label":"未启用离家节能"},{"raw":"1","label":"启用离家节能"}]`
- `get_display_value('away_energy_saving', '1')` → `"启用离家节能"`
- `get_value_options('operation_mode')` → 制冷/制热/通风/除湿（后缀匹配，不变）

### 2.3 seed_device_config.py（MOD-03）

**改动位置**：`HVAC_PARAM_CONFIGS` 列表中 main_thermostat/system_switch 条目 + `handle()` 方法循环体

**改动内容**：
- `main_thermostat` 下的 `system_switch` 条目增加 `'is_active': False` 标记
- `handle()` 循环中增加分支：对带 `is_active=False` 标记的条目改用 `update_or_create`（强制更新）

**幂等性保证**：
- 首次执行：`update_or_create` 创建 `is_active=False` 记录
- 重复执行：`update_or_create` 更新为 `is_active=False`（无副作用）
- `--reset` 模式：先删除全部，重建时 `is_active=False` 条目被正确创建

### 2.4 DeviceSettingsPanelView.vue（MOD-04）

**改动位置**：script setup 区 + 模板控件事件绑定 + return 语句

**改动内容**（含 GROUP_B Minor finding 修正）：

| 改动编号 | 位置 | 内容 |
|---------|------|------|
| 1 | setup() 状态区 | 新增 `const dirtyFields = ref(new Set())` |
| 2 | `loadParams` 前 | 新增 `markDirty(paramName)` 辅助函数 |
| 3 | `loadParams` 赋值逻辑 | 原 `if (inputValues[p] === undefined)` 改为 `if (!dirtyFields.has(p))`（GROUP_B Minor finding 修正） |
| 4 | `loadParams` try 块末尾 | 追加 `dirtyFields.value = new Set()`（清空脏状态） |
| 5 | `handleBatchSubmit` | 过滤条件从"值不为 null/undefined"改为"param_name in dirtyFields" |
| 6 | `handleBatchSubmit` | 空提示语从"没有可提交的参数"改为"没有已修改的参数" |
| 7 | `handleCancel` 末尾 | 追加 `dirtyFields.value = new Set()` |
| 8 | 模板 `el-select` | 新增 `@change="() => markDirty(row.param_name)"` |
| 9 | 模板 `el-input-number` | 新增 `@change="() => markDirty(row.param_name)"` |
| 10 | `return` 语句 | 追加 `markDirty` |

**GROUP_B Minor finding 修正说明**：

原架构设计中 `loadParams` 的保护逻辑为 `if (inputValues.value[p.param_name] === undefined)`，这仅在字段从未被初始化时才赋值，重新调用 `loadParams` 时不会用服务端最新值刷新已有字段。当用户有未提交的修改时（`dirtyFields` 非空），重新 load 实际上不应覆盖用户正在编辑的值，但当用户没有修改时应该拿到最新值。

修正方案：将条件从 `=== undefined` 改为 `!dirtyFields.value.has(p.param_name)`：
- 有脏修改的字段：保留用户编辑中的值（不从服务端刷新）
- 无脏修改的字段：始终从服务端最新值刷新（包括首次加载和后续重新加载）
- loadParams 完成后统一清空 dirtyFields，所有字段恢复干净状态

这个修正比原始 `=== undefined` 逻辑更健壮，且语义更清晰。

---

## 3. 部署注意事项

1. **后端无需 DB 迁移**：仅 `seed_device_config.py` 数据变更，执行方式：
   ```bash
   python manage.py seed_device_config
   # 或全量重建：
   python manage.py seed_device_config --reset
   ```

2. **前端需重新构建**：
   ```bash
   cd FreeArkWeb/frontend && npm run build
   ```

3. **执行顺序**：先部署后端代码（Django 重启），再执行 seed 命令，最后部署前端静态文件。

---

## 4. 不涉及的文件（明确排除）

| 文件 | 排除原因 |
|------|---------|
| `api/serializers_device_settings.py` | 接口结构不变 |
| `api/models.py` | `is_active` 字段已存在，无 schema 变更 |
| `datacollection/resource/plc_config.json` | PLC 寄存器布局不变 |
| `api/urls.py` | 路由不变 |
| `api/migrations/` | 无 DB schema 变更 |
| 其他 Vue 文件 | 不受影响 |
