<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-05-20T00:00:00+08:00</timestamp>
  <project_name>FreeArk-DeviceSettings-v0.5.0</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>docs/requirements/requirements_spec_v0.5.0_device_settings.md</file>
    <file>docs/requirements/user_stories_v0.5.0_device_settings.md</file>
    <file>docs/architecture/architecture_design.md</file>
    <file>docs/architecture/module_design.md</file>
    <file>FreeArkWeb/backend/freearkweb/api/views_device_settings.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/param_value_label.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py</file>
    <file>FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue</file>
  </input_files>
  <phase>PHASE_03</phase>
  <status>DRAFT</status>
</file_header>

---

# 架构设计增量文档

**文档编号**：ARCH-DESIGN-v0.5.0-device-settings  
**项目名称**：FreeArk 设备设置页面增量变更  
**版本**：v0.5.0  
**基线架构版本**：v0.4.0-APPROVED（`docs/architecture/architecture_design.md`）  
**日期**：2026-05-20  
**状态**：DRAFT  
**作者**：sub_agent_system_architect  
**输入文档**：  
- `requirements_spec_v0.5.0_device_settings.md`（REQ-FUNC-001~004，REQ-NFUNC-001~004）  
- `user_stories_v0.5.0_device_settings.md`（US-001~005）  
- `docs/architecture/architecture_design.md`（v0.4.0-APPROVED 基线）  
- `docs/architecture/module_design.md`（v0.4.0-APPROVED 基线）

---

## 1. 变更范围声明

本文档仅描述 **v0.5.0 相对于 v0.4.7 基线的增量架构决策**。v0.4.0 中已确定的所有架构选择（ADR-01~ADR-08、MQTT 拓扑、端到端时序、PLCWriteSubscriber 设计等）保持不变，**本文档不重述基线架构**。

### 1.1 本次涉及的 4 项变更的架构性质分类

| 变更编号 | 需求编号 | 架构性质 | 是否需要新 ADR |
|---------|---------|---------|--------------|
| CHG-01 | REQ-FUNC-001 | 数据层配置变更（DeviceConfig.is_active） | 否——无新架构决策，纯数据操作 |
| CHG-02 | REQ-FUNC-002 | 后端可写性规则扩展（WRITABLE_SUFFIXES 追加 `_mode`） | ADR-09（可写性扩展策略） |
| CHG-03 | REQ-FUNC-003 | 后端可写性规则扩展（精确参数名白名单）+ 标签映射扩展 | ADR-09（同上，合并讨论） |
| CHG-04 | REQ-FUNC-004 | 前端状态管理扩展（dirtyFields Set） | ADR-10（脏值追踪方案） |

---

## 2. 架构决策记录（ADR）

### ADR-09：可写性扩展策略——后缀匹配 vs 精确名白名单的混合方案

**问题**：  
需要将 `operation_mode`（后缀 `_mode`）和 `away_energy_saving`（无通用后缀）同时纳入可写范围，在扩展 `_is_writable()` 函数时需要决定采用何种扩展策略，同时确保不破坏已有的安全性约束（REQ-NFUNC-001）。

**现状分析**：  
当前 `views_device_settings.py` 的 `_is_writable()` 实现为双重检查：先排除 `READONLY_SUFFIXES`，再正向匹配 `WRITABLE_SUFFIXES`。`away_energy_saving` 既不以任何 READONLY_SUFFIX 结尾，也不以任何 WRITABLE_SUFFIX 结尾，因此返回 False。

```python
# 当前实现（v0.4.7）
WRITABLE_SUFFIXES = ('_temp_setting', '_switch')
READONLY_SUFFIXES = ('_temperature', '_humidity', '_dew_point_setting', '_error', '_alert', '_fault')

def _is_writable(param_name: str) -> bool:
    if any(param_name.endswith(s) for s in READONLY_SUFFIXES):
        return False
    return any(param_name.endswith(s) for s in WRITABLE_SUFFIXES)
```

**方案对比**：

| 方案 | 说明 | 优点 | 缺点 |
|------|------|------|------|
| **A（选定）** 混合策略：后缀匹配 + 精确名白名单 | 扩展 `WRITABLE_SUFFIXES` 追加 `_mode`；新增 `WRITABLE_PARAM_NAMES` 集合存放精确名（如 `away_energy_saving`） | 语义清晰（通用规则走后缀，特例走白名单）；安全性可控（精确名白名单不会因新字段命名恰好匹配后缀而误开权限） | 需要维护两个数据结构；新增特例字段时需手动加入白名单 |
| B 纯后缀扩展：为 `away_energy_saving` 单独定义虚拟后缀 | 将字段改名为 `away_energy_saving_switch` 或将 `away_energy_saving` 硬认为以 `_saving` 结尾 | 保持单一后缀匹配逻辑 | 改字段名会影响 DeviceConfig / plc_config.json / PLCLatestData 等多处；`_saving` 后缀无语义 |
| C 完全精确名白名单 | 废弃后缀匹配，全部改为精确名 | 明确无歧义 | 白名单维护量大，且需要对所有已有 `_switch`/`_temp_setting` 字段逐一录入，改动范围大 |

**决策**：选择**方案 A（混合策略）**。  
- `WRITABLE_SUFFIXES` 新增 `'_mode'`，使所有 `*_mode` 后缀参数均可写（当前仅 `operation_mode` 一个，满足 REQ-FUNC-002）。  
- 新增 `WRITABLE_PARAM_NAMES = frozenset({'away_energy_saving'})`，`_is_writable()` 的正向匹配逻辑改为：先检查精确名白名单，再检查后缀匹配（两者任意一个命中即可写）。  
- `READONLY_SUFFIXES` 不变，只读排除规则优先级仍高于所有正向匹配（安全第一原则，满足 REQ-NFUNC-001）。

**修改后的 `_is_writable()` 伪代码**：

```python
WRITABLE_SUFFIXES = ('_temp_setting', '_switch', '_mode')          # 新增 '_mode'
WRITABLE_PARAM_NAMES = frozenset({'away_energy_saving'})           # 新增精确名白名单
READONLY_SUFFIXES = ('_temperature', '_humidity', '_dew_point_setting', '_error', '_alert', '_fault')  # 不变

def _is_writable(param_name: str) -> bool:
    # 只读规则优先（安全第一）
    if any(param_name.endswith(s) for s in READONLY_SUFFIXES):
        return False
    # 精确名白名单 OR 后缀匹配，任一命中即可写
    return (param_name in WRITABLE_PARAM_NAMES or
            any(param_name.endswith(s) for s in WRITABLE_SUFFIXES))
```

**影响范围**：  
- 唯一修改文件：`FreeArkWeb/backend/freearkweb/api/views_device_settings.py`  
- 行数级改动（约 3 行：常量声明 2 行 + 函数体逻辑 1 行）  
- `device_settings_write` 中对 `_is_writable` 的调用（用于校验写入请求）自动生效，无需额外改动  
- 前端：无需任何改动（下拉渲染逻辑已通用，基于 `value_options` 驱动）

---

### ADR-10：前端脏值追踪方案

**问题**：  
需要在前端实现"仅提交用户实际修改的字段"语义（REQ-FUNC-004）。需要决定跟踪脏状态的数据结构及其与现有 `inputValues` 的协作方式。

**现状分析**：  
当前 `DeviceSettingsPanelView.vue` 的 `handleBatchSubmit()` 过滤条件为"值不为 null/undefined"，等价于全量提交所有已加载的可写字段，无法区分"用户主动改过"与"保持原值"。

**方案对比**：

| 方案 | 说明 | 优点 | 缺点 |
|------|------|------|------|
| **A（选定）** 显式 `dirtyFields` Set | 新增 `const dirtyFields = ref(new Set())`；用户触发 `el-select`/`el-input-number` change 事件时将 `param_name` 加入 Set；`handleBatchSubmit` 过滤 `param_name in dirtyFields` | 语义明确（Set 内即为脏字段，无歧义）；O(1) 查找；不侵入 `inputValues` 逻辑；易于测试 | 需要在每个输入控件上注册 `@change`/`@update:modelValue` 事件 |
| B 快照比对 | 加载时记录 `originalValues` 快照，提交时与 `inputValues` 做深比对 | 无需修改控件事件绑定 | 浮点/字符串类型比对需要类型归一处理；快照占用额外内存；比对逻辑复杂度 O(n) |
| C Vue watch 自动追踪 | 对 `inputValues` 做 `watch(inputValues, ...)` 深监听，自动检测变化字段 | 无需手动事件绑定 | Vue 深监听对大对象有性能开销；无法区分"程序初始化赋值"和"用户交互赋值"（会误将 `loadParams` 初始化赋值也标记为脏） |

**决策**：选择**方案 A（显式 `dirtyFields` Set）**，原因：  
1. 语义最清晰，Set 的 `add/has/clear` 操作均为 O(1)，满足 REQ-NFUNC-002（无性能退化）。  
2. 可精确区分"程序初始化赋值"（`loadParams` 中）和"用户交互赋值"（`@change` 事件中），方案 C 无法做到这一点。  
3. 不引入额外快照对象，内存占用最小。

**实现契约**：

```
dirtyFields 生命周期：
  初始化：loadParams 完成后，执行 dirtyFields.value = new Set()（清空）
  加入：用户触发 el-select 的 @change 或 el-input-number 的 @change 时，
        执行 dirtyFields.value.add(row.param_name)
  清空场景1：handleCancel 执行后，执行 dirtyFields.value = new Set()
  清空场景2：loadParams 完成后（含页面刷新），执行 dirtyFields.value = new Set()

handleBatchSubmit 过滤逻辑：
  changedItems = allParams
    .filter(p => dirtyFields.value.has(p.param_name))
    .map(p => ({ param_name: p.param_name, new_value: String(inputValues.value[p.param_name]) }))
  if (changedItems.length === 0) {
    ElMessage.warning('没有已修改的参数')
    return
  }
```

**与现有 `handleCancel` 的协同**：  
现有 `handleCancel` 已实现"重置 `inputValues` 为服务端当前值"，v0.5.0 新增"同时清空 `dirtyFields`"，两者语义对齐（取消 = 彻底撤销所有未提交修改）。

**影响范围**：  
- 唯一修改文件：`FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue`  
- 新增 1 个 `ref`：`dirtyFields`  
- 修改 3 处逻辑：`handleBatchSubmit`、`handleCancel`、`loadParams`  
- 模板中两处输入控件新增 `@change` 事件绑定（`el-select` 和 `el-input-number` 各一处）  
- 后端：无需任何改动（REQ-FUNC-004 明确说明后端天然兼容增量写入）

---

## 3. CHG-01 架构落点分析（REQ-FUNC-001）

**变更描述**：将 `DeviceConfig` 表中 `param_name=system_switch, sub_type=main_thermostat` 的 `is_active` 置为 `False`。

**为什么不需要新 ADR**：  
`is_active` 字段已存在于 `DeviceConfig` 模型（v0.4.0 已使用），`device_settings_params` 视图已有 `.filter(is_active=True)` 过滤（当前 `views_device_settings.py` 第 129 行），此变更只是修改一行数据的字段值，属于数据配置操作，不涉及代码结构或接口协议变更。

**实现路径**：  
`seed_device_config.py` 中 `main_thermostat` 分组下的 `system_switch` 条目需通过以下方式之一处理（ADR 结论：采用方案 B）：

| 方案 | 说明 | 风险 |
|------|------|------|
| A 直接从 `HVAC_PARAM_CONFIGS` 列表删除该条目 | 简洁，但历史数据库中已存在该记录将保持 `is_active=True`（seed 脚本使用 `get_or_create`，skip 已存在记录，不会将其设为 False） | 高——已部署数据库不会被修复 |
| **B（选定）** 保留条目但加入 `is_active=False` 覆盖逻辑 | 在 `handle()` 方法中，对该条目执行 `update_or_create`（而非 `get_or_create`），确保无论记录是否存在都将 `is_active` 设为 False | 低——幂等，满足 REQ-NFUNC-004 |
| C 新增专用 Django management command `deactivate_main_thermostat_switch` | 独立命令，与 seed 分离，部署时显式执行 | 低，但需要额外维护命令文件 |

**选定方案 B 的实现契约**：  
在 `seed_device_config.py` 的 `HVAC_PARAM_CONFIGS` 中，`main_thermostat` 下的 `system_switch` 条目增加 `'is_active': False` 标记。在 `handle()` 方法中，对带有该标记的条目改用 `update_or_create`（`defaults={'is_active': False, ...}`），使 `--reset` 和非 `--reset` 两种运行模式下均能正确设置 `is_active=False`。其余所有条目保持使用 `get_or_create`（维持幂等跳过语义，REQ-NFUNC-004）。

---

## 4. CHG-03 标签映射扩展架构落点（REQ-FUNC-003）

**变更描述**：`param_value_label.py` 需为 `away_energy_saving` 新增精确参数名映射。

**现状**：`param_value_label.py` 当前仅支持后缀匹配（`PARAM_VALUE_LABELS` 字典的 key 均为后缀，如 `_switch`、`_mode`）。`away_energy_saving` 不以任何已定义后缀结尾，`get_value_options('away_energy_saving')` 当前返回 `[]`。

**扩展方案**（与 ADR-09 混合策略一致）：  
新增 `PARAM_EXACT_VALUE_LABELS` 字典，用于精确参数名到标签映射的存储，`get_value_options()` 和 `get_display_value()` 的查找顺序改为：先查精确名字典，再查后缀字典（精确名优先）。

```python
# 新增精确名映射字典
PARAM_EXACT_VALUE_LABELS = {
    'away_energy_saving': {"0": "未启用离家节能", "1": "启用离家节能"},
}

# get_value_options 修改后的查找顺序
def get_value_options(param_name: str) -> list:
    # 1. 先查精确名
    if param_name in PARAM_EXACT_VALUE_LABELS:
        return [{"raw": k, "label": v} for k, v in PARAM_EXACT_VALUE_LABELS[param_name].items()]
    # 2. 再查后缀
    for suffix, mapping in PARAM_VALUE_LABELS.items():
        if param_name.endswith(suffix):
            return [{"raw": k, "label": v} for k, v in mapping.items()]
    return []

# get_display_value 修改后的查找顺序（同理）
def get_display_value(param_name: str, raw_value) -> str:
    if raw_value is None:
        return "—"
    raw_str = str(raw_value)
    # 1. 先查精确名
    if param_name in PARAM_EXACT_VALUE_LABELS:
        return PARAM_EXACT_VALUE_LABELS[param_name].get(raw_str, raw_str)
    # 2. 再查后缀
    for suffix, mapping in PARAM_VALUE_LABELS.items():
        if param_name.endswith(suffix):
            return mapping.get(raw_str, raw_str)
    # 3. 单位后缀
    unit = ""
    for suffix, u in PARAM_UNITS.items():
        if param_name.endswith(suffix):
            unit = f" {u}"
            break
    return f"{raw_str}{unit}"
```

---

## 5. 完整模块变更矩阵（v0.5.0）

| 文件 | 变更类型 | 变更描述 | 关联需求 | 代码规模估计 |
|------|---------|---------|---------|------------|
| `api/views_device_settings.py` | 修改 | 1. `WRITABLE_SUFFIXES` 追加 `'_mode'`（1行）；2. 新增 `WRITABLE_PARAM_NAMES` 常量（1行）；3. `_is_writable()` 逻辑扩展（约 3 行） | REQ-FUNC-002, REQ-FUNC-003, REQ-NFUNC-001 | ~5 行改动 |
| `api/param_value_label.py` | 修改 | 1. 新增 `PARAM_EXACT_VALUE_LABELS` 字典（约 3 行）；2. `get_value_options()` 增加精确名查找分支（约 4 行）；3. `get_display_value()` 增加精确名查找分支（约 3 行） | REQ-FUNC-003 | ~10 行改动 |
| `api/management/commands/seed_device_config.py` | 修改 | 1. `HVAC_PARAM_CONFIGS` 中 `main_thermostat` 的 `system_switch` 条目增加 `'is_active': False` 标记（1行）；2. `handle()` 逻辑增加对 `is_active=False` 标记条目的 `update_or_create` 处理（约 10 行） | REQ-FUNC-001, REQ-NFUNC-004 | ~12 行改动 |
| `frontend/src/views/DeviceSettingsPanelView.vue` | 修改 | 1. 新增 `dirtyFields` ref（1行）；2. 模板 `el-select` 和 `el-input-number` 新增 `@change` 事件（2处，各约 1 行）；3. `handleBatchSubmit` 过滤逻辑替换（约 5 行）；4. `handleCancel` 追加 `dirtyFields` 清空（1行）；5. `loadParams` 完成后追加 `dirtyFields` 清空（1行） | REQ-FUNC-004, REQ-NFUNC-002 | ~12 行改动 |

**明确不改动的文件**（与需求规格 §5 一致）：

| 文件 | 不改动原因 |
|------|---------|
| `api/serializers_device_settings.py` | 接口结构不变，serializer 无需修改 |
| `api/models.py` | 数据模型不变（`DeviceConfig.is_active` 字段已存在） |
| `datacollection/resource/plc_config.json` | PLC 寄存器布局不变（`operation_mode` offset=89，`away_energy_saving` offset=105 均已存在） |
| `api/urls.py` | API 路由不变 |
| `api/migrations/` | 无 DB schema 变更，无需新 migration |
| 其他前端 Vue 文件 | 不受影响 |
| `datacollection/plc_write_subscriber.py` | 无需修改，写入逻辑已通用处理 `items` 数组 |
| `api/mqtt_consumer.py` | 无需修改 |

---

## 6. 接口兼容性分析

### 6.1 GET /api/device-settings/params/{specific_part}/

**变化**：响应中 `groups` 数组的内容发生变化：
- `main_thermostat` 分组：`params` 中不再出现 `system_switch`（`is_active=False` 后端过滤）
- `hydraulic_module` 分组：`params` 中新增 `operation_mode`（`_mode` 后缀命中 `WRITABLE_SUFFIXES`）和 `away_energy_saving`（精确名命中 `WRITABLE_PARAM_NAMES`），两者均含 `value_options` 非空列表

**接口结构**：不变（URL、HTTP 方法、请求参数、响应格式均无变化）  
**向后兼容性**：响应内容变化（参数列表增减），但格式结构完全兼容（满足 REQ-NFUNC-003）

### 6.2 POST /api/device-settings/write/

**变化**：`operation_mode` 和 `away_energy_saving` 现在可以出现在 `items` 中而不返回 400  
**接口结构**：不变（URL、HTTP 方法、请求/响应 schema 均无变化）  
**向后兼容性**：完全兼容（满足 REQ-NFUNC-003）

---

## 7. 需求覆盖矩阵

| 需求编号 | 架构决策/落点 | 覆盖状态 |
|---------|-------------|---------|
| REQ-FUNC-001 | §3 CHG-01 落点：`seed_device_config.py` 方案 B（`update_or_create` + `is_active=False`）；`device_settings_params` 已有 `is_active=True` 过滤 | 已覆盖 |
| REQ-FUNC-002 | ADR-09：`WRITABLE_SUFFIXES` 追加 `'_mode'` | 已覆盖 |
| REQ-FUNC-003 | ADR-09：`WRITABLE_PARAM_NAMES` 精确名白名单；§4 `param_value_label.py` 精确名映射扩展 | 已覆盖 |
| REQ-FUNC-004 | ADR-10：`dirtyFields` Set，`loadParams`/`handleBatchSubmit`/`handleCancel` 三点协同 | 已覆盖 |
| REQ-NFUNC-001 | ADR-09：`READONLY_SUFFIXES` 优先级高于所有正向匹配，不受本次扩展影响 | 已覆盖 |
| REQ-NFUNC-002 | ADR-10：`dirtyFields` Set 操作均为 O(1)，无额外网络请求和渲染开销 | 已覆盖 |
| REQ-NFUNC-003 | §6 接口兼容性分析：URL、HTTP 方法、schema 均不变 | 已覆盖 |
| REQ-NFUNC-004 | §3 方案 B：`update_or_create` 保证幂等性 | 已覆盖 |

---

## 8. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| `_mode` 后缀误开其他参数的写入权限 | 低（当前 DeviceConfig 中以 `_mode` 结尾的参数仅 `operation_mode` 一个） | 中 | 开发后通过单元测试验证 `_is_writable` 对所有现有参数的返回值（REQ-NFUNC-001 验证要求）；`READONLY_SUFFIXES` 已有保护 |
| `seed_device_config.py` 修改在 `--reset` 模式下未正确将 `is_active` 置为 False | 低 | 中（主温控仍显示 system_switch） | `handle()` 中 `--reset` 分支先删除全部记录，重建时 `is_active=False` 条目将正确创建；非 `--reset` 分支通过 `update_or_create` 强制更新 |
| `dirtyFields` 在 `loadParams` 异步返回前被用户提交 | 极低 | 低（`submitLoading=true` 时按钮已 disabled） | 现有 `submitLoading` 机制已防止并发提交 |
| `away_energy_saving` 的精确名映射与未来新增同名后缀冲突 | 极低 | 低 | 精确名查找优先于后缀查找，不会被后缀规则覆盖 |
