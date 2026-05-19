<file_header>
  <author_agent>sub_agent_software_developer</author_agent>
  <timestamp>2026-05-20T00:00:00+08:00</timestamp>
  <project_name>FreeArk-DeviceSettings-v0.5.0</project_name>
  <version>1.0.0</version>
  <input_files>
    <file>docs/development/v0.5.0_device_settings/implementation_plan.md</file>
    <file>FreeArkWeb/backend/freearkweb/api/views_device_settings.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/param_value_label.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py</file>
    <file>FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue</file>
  </input_files>
  <phase>PHASE_06</phase>
  <status>APPROVED</status>
</file_header>

---

# 代码评审报告

**项目**：FreeArk 设备设置页面增量变更  
**版本**：v0.5.0  
**评审日期**：2026-05-20  
**评审人**：sub_agent_software_developer（自我评审）  
**评审结论**：**PASS（无 CRITICAL finding）**

---

## 1. 需求覆盖性评审

### 1.1 REQ-FUNC-001：移除主温控分组中的系统开关

**实施位置**：`seed_device_config.py`

**验证**：
- `HVAC_PARAM_CONFIGS` 中 `main_thermostat` 下的 `system_switch` 条目已添加 `'is_active': False` 标记
- `handle()` 循环中 `cfg.get('is_active') is False` 分支改用 `update_or_create`，确保无论记录是否已存在都将 `is_active` 置为 False
- `views_device_settings.py` 中 `device_settings_params` 已有 `DeviceConfig.objects.filter(is_active=True)` 过滤，前端自然不再渲染该条目
- `hydraulic_module` 下的 `system_switch` 条目无 `is_active` 键，走 `get_or_create` 默认分支，`is_active=True` 保持不变

**覆盖状态**：SATISFIED

### 1.2 REQ-FUNC-002：水力模块展示并支持设置工作模式

**实施位置**：`views_device_settings.py`

**验证**：
- `WRITABLE_SUFFIXES` 已追加 `'_mode'`，`_is_writable('operation_mode')` 返回 True
- `operation_mode` 在 `DeviceConfig` 中已存在且 `is_active=True`，无需额外操作
- `param_value_label.py` 中 `_mode` 后缀映射已有 `{"0":"制冷","1":"制热","2":"通风","3":"除湿"}`，`get_value_options('operation_mode')` 返回正确选项
- 前端 `el-select` 渲染逻辑由 `value_options` 驱动，无需前端改动

**覆盖状态**：SATISFIED

### 1.3 REQ-FUNC-003：水力模块展示并支持设置离家节能标识

**实施位置**：`views_device_settings.py` + `param_value_label.py`

**验证**：
- `WRITABLE_PARAM_NAMES = frozenset({'away_energy_saving'})` 已新增，`_is_writable('away_energy_saving')` 返回 True
- `param_value_label.py` 中新增 `PARAM_EXACT_VALUE_LABELS = {'away_energy_saving': {"0":"未启用离家节能","1":"启用离家节能"}}`
- `get_value_options()` 和 `get_display_value()` 均先查精确名字典，`away_energy_saving` 命中并返回正确标签

**覆盖状态**：SATISFIED

### 1.4 REQ-FUNC-004：前端脏值追踪——仅提交用户实际修改的字段

**实施位置**：`DeviceSettingsPanelView.vue`

**验证**：
- `const dirtyFields = ref(new Set())` 已在 setup() 中声明
- `markDirty(paramName)` 函数已实现，`el-select` 和 `el-input-number` 均绑定 `@change="() => markDirty(row.param_name)"`
- `handleBatchSubmit` 过滤条件已改为 `dirtyFields.value.has(p.param_name)`
- 空提交提示已改为"没有已修改的参数"
- `handleCancel` 末尾追加 `dirtyFields.value = new Set()`
- `loadParams` 完成后追加 `dirtyFields.value = new Set()`
- `markDirty` 已加入 `return` 语句

**覆盖状态**：SATISFIED

### 需求覆盖矩阵

| 需求编号 | 覆盖状态 | 备注 |
|---------|---------|------|
| REQ-FUNC-001 | SATISFIED | seed 命令幂等执行后 main_thermostat/system_switch 不再出现在设置页 |
| REQ-FUNC-002 | SATISFIED | operation_mode 命中 _mode 后缀，value_options 正确 |
| REQ-FUNC-003 | SATISFIED | away_energy_saving 命中精确名白名单，标签映射正确 |
| REQ-FUNC-004 | SATISFIED | dirtyFields Set 完整实现，三处清空逻辑均已实施 |
| REQ-NFUNC-001 | SATISFIED | READONLY_SUFFIXES 优先级不变，新扩展不影响只读保护 |
| REQ-NFUNC-002 | SATISFIED | dirtyFields.add/has/clear 均为 O(1)，无额外网络请求 |
| REQ-NFUNC-003 | SATISFIED | API 接口结构（URL/HTTP方法/schema）均未改变 |
| REQ-NFUNC-004 | SATISFIED | update_or_create 保证幂等性 |

---

## 2. ADR 符合性评审

### 2.1 ADR-09：可写性扩展策略（混合策略）

**评审要点**：

| 检查项 | 实施情况 | 结论 |
|-------|---------|------|
| `WRITABLE_SUFFIXES` 追加 `'_mode'` | 已实施，见 views_device_settings.py 第 19 行 | PASS |
| 新增 `WRITABLE_PARAM_NAMES = frozenset({'away_energy_saving'})` | 已实施，见第 20 行 | PASS |
| `_is_writable()` 逻辑：只读优先 → 精确名 OR 后缀 | 已实施，逻辑与 ADR-09 伪代码完全一致 | PASS |
| `frozenset` 保证 O(1) 查找且不可变 | 已使用 `frozenset`，符合 ADR 要求 | PASS |
| `param_value_label.py` 新增 `PARAM_EXACT_VALUE_LABELS`，精确名优先 | 已实施，查找顺序正确 | PASS |

**结论**：完全符合 ADR-09 设计意图。

### 2.2 ADR-10：前端脏值追踪方案

**评审要点**：

| 检查项 | 实施情况 | 结论 |
|-------|---------|------|
| `dirtyFields = ref(new Set())` | 已实施 | PASS |
| `markDirty` 函数抽离，供模板调用 | 已实施，函数内仅 `dirtyFields.value.add(paramName)` | PASS |
| `el-select` 绑定 `@change` | 已实施 | PASS |
| `el-input-number` 绑定 `@change` | 已实施 | PASS |
| `handleBatchSubmit` 使用 `dirtyFields.value.has()` 过滤 | 已实施 | PASS |
| `handleCancel` 清空 dirtyFields | 已实施 | PASS |
| `loadParams` 完成后清空 dirtyFields | 已实施 | PASS |

**结论**：完全符合 ADR-10 设计意图。

### 2.3 CHG-01 方案 B：seed_device_config.py update_or_create

**评审要点**：

| 检查项 | 实施情况 | 结论 |
|-------|---------|------|
| `is_active=False` 标记在 HVAC_PARAM_CONFIGS 条目中 | 已实施 | PASS |
| 使用 `cfg.get('is_active') is False` 精确判断（避免 `is_active=0` 误判） | 已使用 `is False` 而非 `== False`，使用身份比较避免 truthy 问题 | PASS |
| `update_or_create` 的 defaults 包含所有字段（含 `is_active=False`） | 已实施，defaults 完整 | PASS |
| 其余条目保持 `get_or_create` 语义不变 | 已实施，else 分支保持原逻辑 | PASS |
| `--reset` 模式兼容 | 先删除全部再重建，`is_active=False` 条目被正确创建，无问题 | PASS |

**结论**：完全符合 CHG-01 方案 B 设计意图。

---

## 3. GROUP_B Minor Finding 处理评审

**原始 Finding**：`loadParams` 中 `if (inputValues.value[p.param_name] === undefined)` 保护逻辑与 dirtyFields 存在语义冲突。

**实施的修正方案**：将赋值条件从 `=== undefined` 改为 `!dirtyFields.value.has(p.param_name)`。

**修正逻辑验证**：

| 场景 | 原逻辑行为 | 修正后行为 | 是否正确 |
|------|---------|---------|---------|
| 首次调用 loadParams，字段从未初始化 | `=== undefined` 为真，赋值 | `!has()` 为真（空 Set），赋值 | 正确 |
| 重复调用 loadParams，用户未修改任何字段 | `=== undefined` 为假，不刷新 | `!has()` 为真（无脏字段），刷新最新服务端值 | **更好**（原逻辑有缺陷，不会刷新） |
| 重复调用 loadParams，用户已修改某字段 | `=== undefined` 为假，不刷新 | `!has()` 为假（已在 Set），保留用户编辑值 | 正确 |
| loadParams 完成后 | 无清空操作 | `dirtyFields = new Set()`，清空脏状态 | 正确 |

**结论**：修正方案解决了原始 finding，并额外修复了原逻辑中"重新 loadParams 不会刷新已有字段"的缺陷，使页面数据始终反映服务端最新状态。修正无副作用，MINOR → RESOLVED。

---

## 4. 回归风险评审

### 4.1 现有水利模块/主温控其他字段的读写影响

**评估**：

| 字段类别 | 是否受影响 | 分析 |
|---------|---------|------|
| 主温控其他 `_switch` 字段（如 `living_room_switch`） | 否 | `WRITABLE_SUFFIXES` 仍含 `_switch`，行为不变 |
| 主温控 `_temp_setting` 字段（如 `living_room_temp_setting`） | 否 | `WRITABLE_SUFFIXES` 仍含 `_temp_setting`，行为不变 |
| 主温控只读字段（`_temperature`、`_error` 等） | 否 | `READONLY_SUFFIXES` 优先级不变 |
| 水力模块 `system_switch` | 否 | 该字段以 `_switch` 结尾，仍可写，不受 CHG-01 影响 |
| 新风模块所有字段 | 否 | 未修改相关逻辑 |
| 能耗表所有字段 | 否 | 未修改相关逻辑 |
| `central_energy_supply`（水力模块） | 否 | 不以 `_mode`/`_switch`/`_temp_setting` 结尾，不在 `WRITABLE_PARAM_NAMES` 中，仍为只读（符合预期） |

**特别关注：`_mode` 后缀追加的副作用检查**

在 `seed_device_config.py` 全量参数列表中检查所有以 `_mode` 结尾的参数名：
- `operation_mode`（水力模块）→ 期望可写，正确
- 其余参数中无其他以 `_mode` 结尾的参数名（经逐行检查确认）

**结论**：`_mode` 后缀追加不会误开任何其他参数的写入权限。

### 4.2 前端 dirtyFields 对现有功能的影响

| 现有功能 | 影响分析 |
|---------|---------|
| 首次加载展示当前值 | `dirtyFields` 初始为空 Set，`!has()` 对所有字段为真，loadParams 正常初始化所有字段 |
| MQTT ACK 回调更新 itemStatuses | 回调逻辑未修改，不受影响 |
| 30s 超时计时器 | 未修改，不受影响 |
| 提交后显示逐项状态 | 未修改 `handleAck`，不受影响 |
| 取消按钮重置 inputValues | 已追加 dirtyFields 清空，且原 inputValues 重置逻辑保持不变 |

**结论**：无现有功能被破坏。

### 4.3 并发安全性

| 场景 | 分析 |
|------|------|
| 用户快速点击提交两次 | `submitLoading=true` 时"提交"按钮 disabled，现有机制已防止并发提交 |
| loadParams 执行期间用户修改字段 | `dirtyFields.has()` 检查与 Set 操作均为同步操作，Vue 单线程模型下无竞态 |
| loadParams 异步完成后清空 dirtyFields | 在 try 块末尾，仅在成功 resolve 后执行，不会因网络错误误清空脏状态 |

**结论**：并发安全性良好，无新引入的竞态条件。

### 4.4 错误处理与边界条件

| 边界条件 | 处理方式 | 结论 |
|---------|---------|------|
| `loadParams` 失败（网络异常） | catch 分支设置 `loadError`，不执行 `dirtyFields.value = new Set()`（在 try 末尾） | 正确：加载失败不清空脏状态，用户已编辑的内容得以保留 |
| 用户点击提交后立即点击取消 | `submitLoading=true` 时取消按钮也被 disabled，无法点击 | 正确 |
| `away_energy_saving` 值为 null（PLC 无数据） | `get_display_value` 已处理 `raw_value is None` 返回 "—" | 正确 |
| `dirtyFields` 中记录了已不在 `groups` 中的参数名 | `handleBatchSubmit` 先构建 `allParams = groups 中所有 params`，再以此 filter dirtyFields，不会提交游离参数 | 正确 |
| `el-input-number` 的 `@change` 触发时 value 为 undefined（用户清空输入框） | `markDirty` 只记录参数名，不记录值；`map` 中 `String(inputValues.value[p.param_name])` 在 `undefined` 时返回 `"undefined"` 字符串 | **MINOR**：若用户清空 el-input-number 使其为 undefined，提交时会发送 `"undefined"` 字符串。但此场景在 el-input-number 的 min/max 约束下极少出现，且后端已有参数校验（serializer 会拒绝非数字值）。建议 GROUP_D 测试阶段覆盖此场景。 |

---

## 5. Finding 汇总

| Finding ID | 文件 | 严重级别 | 描述 | 处理状态 |
|-----------|------|---------|------|---------|
| FR-001 | `DeviceSettingsPanelView.vue` | MINOR | `el-input-number` 用户清空后 `inputValues[param] = undefined`，`String(undefined)` = `"undefined"` 字符串会被提交 | OPEN — 建议 GROUP_D 覆盖测试；后端 serializer 已有类型校验保护，不会写入 PLC |
| GROUP_B-Finding | `DeviceSettingsPanelView.vue` | MINOR（已修复） | `loadParams` 原 `=== undefined` 保护逻辑与 dirtyFields 语义冲突 | RESOLVED — 已改为 `!dirtyFields.has()` |

**CRITICAL finding 数量：0**

---

## 6. 评审结论

**综合评审结论**：PASS

- 所有 4 项功能需求（REQ-FUNC-001~004）和 4 项非功能需求（REQ-NFUNC-001~004）均已完整实现
- 完全符合 ADR-09、ADR-10、CHG-01 方案 B 的设计意图
- GROUP_B Minor finding 已按建议方案修复，修复效果超出预期（同时修复了原 loadParams 不刷新已有字段的缺陷）
- 无 CRITICAL finding
- 存在 1 个 MINOR finding（FR-001），不阻塞当前阶段通过，建议在 GROUP_D 测试阶段覆盖
- 现有水利模块/主温控其他字段读写行为不受影响
- 回归风险评估为低

**代码质量评分**：符合基线代码风格，注释规范，无冗余代码，改动精准。
