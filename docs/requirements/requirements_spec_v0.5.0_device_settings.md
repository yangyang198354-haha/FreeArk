<file_header>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <timestamp>2026-05-20T00:00:00+08:00</timestamp>
  <project_name>FreeArk-DeviceSettings-v0.5.0</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue</file>
    <file>FreeArkWeb/backend/freearkweb/api/views_device_settings.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/param_value_label.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/serializers_device_settings.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/models.py</file>
    <file>datacollection/resource/plc_config.json</file>
  </input_files>
  <phase>PHASE_01</phase>
  <status>DRAFT</status>
</file_header>

---

# 需求规格说明书

**项目**：FreeArk 设备设置页面增量变更  
**版本**：v0.5.0  
**基线版本**：v0.4.7（feat: 写成功同步 plc_latest_data，UI 立即可见）  
**文档编号**：REQ-SPEC-v0.5.0-device-settings  
**日期**：2026-05-20  
**状态**：DRAFT

---

## 1. 背景与范围

### 1.1 项目背景

FreeArk 是一套楼宇/工业控制系统，前端（Vue 3 + Element Plus）通过 MQTT-WebSocket 与后端（Django REST Framework）通信，后端通过 MQTT 下发写入指令至 `freeark-task-scheduler` 服务，由后者通过 S7 协议写入西门子 PLC 寄存器（DB14）。

"设备设置页面"（`DeviceSettingsPanelView.vue`）当前实现：
- 调用 `GET /api/device-settings/params/{specific_part}/` 加载所有可写参数，按 `sub_type` 分组折叠展示
- 可写参数判定由后端 `_is_writable()` 函数控制，当前可写后缀为 `_temp_setting`、`_switch`
- 点击"提交"时将所有 `inputValues` 中值不为 null/undefined 的字段全量发送至 `POST /api/device-settings/write/`
- 写入结果通过 MQTT-WS ACK 主题（`/datacollection/plc/write/ack/{specific_part}`）异步回显

### 1.2 本次变更范围

本次变更仅涉及设备设置页面的以下四个方向，**不涉及**其他功能模块：

| 变更方向 | 简述 |
|---------|------|
| CHG-01 | 去重系统开关：移除主温控分组中的冗余系统开关 |
| CHG-02 | 新增模式选择：水力模块可设置工作模式（制冷/制热/通风/除湿） |
| CHG-03 | 新增离家节能标识：水力模块可设置离家节能开关 |
| CHG-04 | 增量保存改造：仅对用户修改过的字段执行写入（脏值追踪） |

### 1.3 明确不在本次变更范围内

- PLC 寄存器布局（plc_config.json 中的 offset、db_num、data_type）不做变更
- 除 `main_thermostat`、`hydraulic_module` 外的其他 sub_type 分组不受影响
- MQTT 通信协议、topic 结构、ACK 流程不变
- 后端数据库模型（除 DeviceConfig 激活状态外）不做迁移变更
- 用户认证与权限逻辑不变
- 除设备设置页面以外的其他视图页面不受影响

---

## 2. 现状代码分析

### 2.1 system_switch 冗余问题

**来源**：`seed_device_config.py` 分析

`system_switch` 在 `HVAC_PARAM_CONFIGS` 列表中出现两次：

| 序号 | param_name | sub_type | display_name |
|-----|-----------|---------|-------------|
| 1 | system_switch | main_thermostat | 系统开关 |
| 2 | system_switch | hydraulic_module | 系统开关 |

`plc_config.json` 中 `system_switch` 仅有一条定义：`db_num=14, offset=91, data_type=byte`。

两个 `DeviceConfig` 条目指向同一 PLC 寄存器，导致设备设置页面中"主温控"和"水力模块"分组均显示"系统开关"，操作其中任意一个效果相同，存在用户认知歧义。

### 2.2 operation_mode 可写性问题

**来源**：`seed_device_config.py` + `views_device_settings.py` + `param_value_label.py`

- `operation_mode` 已在 `hydraulic_module` 分组中注册（display_name='模式'）
- `plc_config.json`：`db_num=14, offset=89, data_type=byte`
- `param_value_label.py` 已存在 `_mode` 后缀映射：`{"0":"制冷","1":"制热","2":"通风","3":"除湿"}`
- 但 `views_device_settings.py` 中 `WRITABLE_SUFFIXES = ('_temp_setting', '_switch')`，`operation_mode` 不满足任一后缀，`_is_writable()` 返回 False，导致该字段被后端过滤，不出现在设置页面

### 2.3 away_energy_saving 可写性与展示问题

**来源**：`seed_device_config.py` + `views_device_settings.py` + `param_value_label.py`

- `away_energy_saving` 已在 `hydraulic_module` 分组中注册（display_name='离家节能标识'）
- `plc_config.json`：`db_num=14, offset=105, data_type=byte`
- `param_value_label.py` 中无 `away_energy_saving` 的专属映射（不以 `_switch`/`_mode` 结尾）
- `_is_writable()` 对其返回 False（不满足 `_temp_setting` 或 `_switch` 后缀）
- 导致该字段不可设置，且即便展示也缺乏人性化标签（0/1 含义不明）

### 2.4 批量提交逻辑现状

**来源**：`DeviceSettingsPanelView.vue`，第 143–199 行

```
handleBatchSubmit() {
  changedItems = allParams.filter(p => inputValues[p.param_name] !== undefined && !== null)
  // 过滤条件仅排除 null/undefined，未区分"用户是否实际修改过"
  api.post('/api/device-settings/write/', { specific_part, items: changedItems })
}
```

当前行为：每次点击"提交"将所有已加载的可写参数全量下发 PLC，无论用户是否实际修改了对应字段。这导致：
1. 对未改动字段产生无效 PLC 写入操作，增加 PLC 总线负载
2. 写入历史记录（PLCWriteRecord）包含大量无实质意义的记录，干扰审计

---

## 3. 功能需求

### REQ-FUNC-001：移除主温控分组中的系统开关

- **来源**：用户原始需求 CHG-01
- **描述**：在设备设置页面中，"主温控"（`sub_type=main_thermostat`）分组不再展示"系统开关"（`param_name=system_switch`）。"水力模块"（`sub_type=hydraulic_module`）分组中的"系统开关"保持不变，作为唯一入口。
- **实现约束**：应通过将 `DeviceConfig` 表中 `param_name=system_switch, sub_type=main_thermostat` 的记录 `is_active` 设为 `False` 来实现，而非物理删除（以保留审计可追溯性）。`seed_device_config.py` 中对应条目应同步标记（或在 `--reset` 模式下不再创建）。
- **影响范围**：
  - 后端：`seed_device_config.py`（更新 `main_thermostat` 下的 `system_switch` 为 `is_active=False`）
  - 后端：`views_device_settings.py`（`device_settings_params` 视图已有 `is_active=True` 过滤，无需额外修改）
  - 前端：无需代码变更（后端过滤后前端自然不再渲染该条目）

### REQ-FUNC-002：在水力模块中展示并支持设置工作模式

- **来源**：用户原始需求 CHG-02
- **描述**：在"水力模块"（`sub_type=hydraulic_module`）分组中，展示"工作模式"（`param_name=operation_mode`）字段，用户可从以下四个选项中选择一个值并写入 PLC：
  - `0` → 制冷
  - `1` → 制热
  - `2` → 通风
  - `3` → 除湿
- **前端展示**：使用下拉选择器（`el-select`），选项由 `value_options` 提供（已由 `param_value_label.py` 的 `_mode` 映射生成）
- **实现约束**：
  - 后端 `WRITABLE_SUFFIXES` 需扩展，增加 `_mode` 后缀，使 `_is_writable('operation_mode')` 返回 `True`
  - `operation_mode` 已在 `DeviceConfig` 中注册且 `is_active=True`，不需要新增 DeviceConfig 条目
  - `param_value_label.py` 中 `_mode` 映射已存在，前端 `value_options` 将自动填充
- **影响范围**：
  - 后端：`views_device_settings.py`（扩展 `WRITABLE_SUFFIXES`）
  - 前端：无需代码变更（下拉渲染逻辑已基于 `value_options` 通用实现）

### REQ-FUNC-003：在水力模块中展示并支持设置离家节能标识

- **来源**：用户原始需求 CHG-03
- **描述**：在"水力模块"（`sub_type=hydraulic_module`）分组中，展示"离家节能标识"（`param_name=away_energy_saving`）字段，用户可选择启用或未启用并写入 PLC：
  - `0` → 未启用离家节能
  - `1` → 启用离家节能
- **前端展示**：使用下拉选择器（`el-select`），选项由 `value_options` 提供
- **实现约束**：
  - 后端需将 `away_energy_saving` 纳入可写范围。推荐方案：在 `views_device_settings.py` 中建立专属白名单（`WRITABLE_PARAM_NAMES`），或扩展后缀匹配逻辑以兼容该字段命名
  - `param_value_label.py` 需新增 `away_energy_saving` 的专属 value_options 映射（`{"0":"未启用离家节能","1":"启用离家节能"}`）——**注意：此为按参数名精确匹配，不按后缀匹配**
  - `away_energy_saving` 已在 `DeviceConfig` 中注册且 `is_active=True`，不需要新增 DeviceConfig 条目
- **影响范围**：
  - 后端：`views_device_settings.py`（扩展可写性判断，使 `away_energy_saving` 可写）
  - 后端：`param_value_label.py`（新增 `away_energy_saving` 精确参数名映射）
  - 前端：无需代码变更

### REQ-FUNC-004：前端脏值追踪——仅提交用户实际修改的字段

- **来源**：用户原始需求 CHG-04
- **描述**：设备设置页面在用户点击"提交"时，应仅将用户在本次页面会话中实际修改过的字段包含在写入请求的 `items` 数组中；未被用户触碰过的字段不得下发至 PLC。
- **详细行为**：
  - **脏字段集合初始化**：页面完成参数加载（`loadParams` 完成）后，`dirtyFields`（`Set<string>`）初始化为空集
  - **标记脏字段**：当用户通过 `el-select` 或 `el-input-number` 修改某字段值时，将该字段的 `param_name` 加入 `dirtyFields`
  - **提交过滤**：`handleBatchSubmit` 中，`changedItems` 应为 `allParams` 中 `param_name in dirtyFields` 的子集，而非全量
  - **空提交保护**：若 `dirtyFields` 为空，点击"提交"应提示"没有已修改的参数"，不发送请求（与现有 `changedItems.length === 0` 逻辑一致）
  - **取消重置**：`handleCancel` 应在重置 `inputValues` 的同时清空 `dirtyFields`，将页面恢复至初始未修改状态
  - **重新加载重置**：调用 `loadParams` 完成后，`dirtyFields` 也应清空（因为已重新加载服务端最新值）
- **后端兼容性**：后端 `device_settings_write` 接口现有结构（接受 `items` 数组，逐项处理）天然兼容增量写入，**后端无需代码变更**。此改造是纯前端侧修改。
- **影响范围**：
  - 前端：`DeviceSettingsPanelView.vue`（新增 `dirtyFields` ref，修改 `handleBatchSubmit`、`handleCancel`、`loadParams` 逻辑）
  - 后端：无需变更

---

## 4. 非功能需求

### REQ-NFUNC-001：可写性扩展的安全性

- **来源**：代码现状分析（`views_device_settings.py` 现有白名单设计）
- **描述**：扩展可写参数范围（CHG-02、CHG-03）时，不得引入对已明确标记为只读的参数的写入能力。`READONLY_SUFFIXES`（`_temperature/_humidity/_dew_point_setting/_error/_alert/_fault`）约束不受影响。
- **验证方式**：针对 `_is_writable` 或等效白名单函数新增单元测试，覆盖新增参数名及已有只读后缀参数

### REQ-NFUNC-002：脏值追踪不影响现有读取性能

- **来源**：代码现状分析（`loadParams` 异步加载逻辑）
- **描述**：`dirtyFields` Set 的维护操作（add/clear/has）时间复杂度为 O(1)，不得引入页面可感知的性能退化（无新的网络请求、无额外渲染开销）。

### REQ-NFUNC-003：变更向后兼容

- **来源**：代码现状分析（现有 API 接口）
- **描述**：本次前后端变更应保持 API 接口结构不变（`GET /api/device-settings/params/` 和 `POST /api/device-settings/write/` 的请求/响应格式不变），确保不影响其他可能调用这些接口的客户端。

### REQ-NFUNC-004：seed_device_config.py 的幂等性保持

- **来源**：代码现状分析（`seed_device_config.py` 使用 `get_or_create`）
- **描述**：对 `seed_device_config.py` 的修改（标记 `main_thermostat` 下 `system_switch` 为 `is_active=False`）应在重复执行时保持幂等，不产生重复记录或错误状态。

---

## 5. 变更范围矩阵

| 变更编号 | 需求编号 | 影响层 | 影响文件 | 变更类型 |
|---------|---------|-------|---------|---------|
| CHG-01 | REQ-FUNC-001 | 后端 | `api/management/commands/seed_device_config.py` | 修改（标记 is_active=False） |
| CHG-02 | REQ-FUNC-002 | 后端 | `api/views_device_settings.py` | 修改（扩展 WRITABLE_SUFFIXES） |
| CHG-03 | REQ-FUNC-003 | 后端 | `api/views_device_settings.py` | 修改（扩展可写性判断） |
| CHG-03 | REQ-FUNC-003 | 后端 | `api/param_value_label.py` | 修改（新增精确参数名映射） |
| CHG-04 | REQ-FUNC-004 | 前端 | `frontend/src/views/DeviceSettingsPanelView.vue` | 修改（新增 dirtyFields 逻辑） |

**不受影响的文件**（明确排除）：
- `api/serializers_device_settings.py`：接口结构不变，serializer 无需修改
- `api/models.py`：数据模型不变（DeviceConfig.is_active 字段已存在）
- `datacollection/resource/plc_config.json`：PLC 寄存器布局不变
- 其他所有 Vue 视图文件

---

## 6. PLC 参数映射参考（信息性，不做变更）

以下为本次变更涉及的 PLC 参数当前状态（来源：`plc_config.json`，`seed_device_config.py`）：

| param_name | sub_type | display_name | DB | Offset | Type | 当前可写 | 变更后可写 |
|-----------|---------|-------------|----|----|------|--------|--------|
| system_switch | main_thermostat | 系统开关 | 14 | 91 | byte | 是 | 否（is_active=False） |
| system_switch | hydraulic_module | 系统开关 | 14 | 91 | byte | 是 | 是（不变） |
| operation_mode | hydraulic_module | 模式 | 14 | 89 | byte | 否 | 是（扩展后缀） |
| away_energy_saving | hydraulic_module | 离家节能标识 | 14 | 105 | byte | 否 | 是（白名单/扩展） |

---

## 7. 约束与假设

1. 假设 `DeviceConfig` 数据库中已存在 `param_name=system_switch, sub_type=main_thermostat` 的记录（由 `seed_device_config.py` 历史执行创建），本次变更通过 Django migration 或管理命令将其 `is_active` 置为 False。
2. 假设 `DeviceConfig` 数据库中已存在 `operation_mode` 和 `away_energy_saving` 的 `hydraulic_module` 记录且 `is_active=True`，无需新建。
3. `away_energy_saving` 的值语义：`0=未启用离家节能，1=启用离家节能`，基于同类 byte 型开关字段的惯例推断。**[INFERRED]**
4. 脏值追踪仅追踪用户在当前页面会话的交互，页面刷新或重新打开后不保留脏状态（无需持久化）。

> 注：本文档共 4 条功能需求、4 条非功能需求。[INFERRED] 标注项为 1 条（第7条假设3），占总需求条目的 12.5%——由于该推断有强烈的代码惯例支撑（byte 型字段普遍采用 0/1 开关语义），建议开发前由用户确认 away_energy_saving 的精确值含义。
