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
    <file>docs/requirements/requirements_spec_v0.5.0_device_settings.md</file>
  </input_files>
  <phase>PHASE_02</phase>
  <status>DRAFT</status>
</file_header>

---

# 用户故事清单

**项目**：FreeArk 设备设置页面增量变更  
**版本**：v0.5.0  
**关联需求规格**：`requirements_spec_v0.5.0_device_settings.md`  
**日期**：2026-05-20  
**状态**：DRAFT

---

## 概览

| US 编号 | 标题 | 关联需求 | AC 数量 |
|--------|------|---------|--------|
| US-001 | 移除主温控分组的冗余系统开关 | REQ-FUNC-001 | 3 |
| US-002 | 在水力模块中设置工作模式 | REQ-FUNC-002 | 4 |
| US-003 | 在水力模块中设置离家节能标识 | REQ-FUNC-003 | 4 |
| US-004 | 仅提交用户修改过的设备参数 | REQ-FUNC-004 | 5 |
| US-005 | 取消操作时清除所有未提交的修改 | REQ-FUNC-004 | 3 |

---

## US-001：移除主温控分组的冗余系统开关

**故事描述**：  
作为设备管理员，当我打开设备设置页面时，我不希望在"主温控"分组中看到"系统开关"，因为系统开关已经在"水力模块"分组中作为唯一入口提供，重复展示会造成混淆和误操作。

**关联需求**：REQ-FUNC-001  
**优先级**：高

### AC-001-01：主温控分组不再显示系统开关

```
Given 设备管理员打开某设备的设备设置页面
When 页面完成加载，展开"主温控"折叠区域
Then "主温控"分组的参数列表中不包含"系统开关"（param_name=system_switch）行
  And 页面无报错，其余主温控参数（如客厅开关、设定温度等）正常显示
```

### AC-001-02：水力模块分组仍保留系统开关

```
Given 设备管理员打开某设备的设备设置页面
When 页面完成加载，展开"水力模块"折叠区域
Then "水力模块"分组中仍显示"系统开关"（param_name=system_switch）行
  And 系统开关的当前值正常读取并显示（来自 plc_latest_data）
  And 用户可通过该行的下拉选择器修改并提交系统开关的值
```

### AC-001-03：后端接口不返回 main_thermostat 下的 system_switch

```
Given 系统数据库中 DeviceConfig 表 param_name=system_switch, sub_type=main_thermostat 的记录 is_active=False
When 前端调用 GET /api/device-settings/params/{specific_part}/
Then 响应 JSON 中 groups 数组内 sub_type=main_thermostat 的对象，其 params 数组不包含 param_name=system_switch 的条目
  And 响应 JSON 中 sub_type=hydraulic_module 的对象，其 params 数组仍包含 param_name=system_switch 的条目
```

---

## US-002：在水力模块中设置工作模式

**故事描述**：  
作为设备管理员，当我需要调整水力模块的运行工况时，我希望能在"水力模块"分组中看到"工作模式"字段，并通过下拉菜单从制冷、制热、通风、除湿四个选项中选择一个写入 PLC，而不必通过其他途径操作。

**关联需求**：REQ-FUNC-002  
**优先级**：高

### AC-002-01：水力模块分组显示工作模式字段

```
Given 设备管理员打开某设备的设备设置页面
When 页面完成加载，展开"水力模块"折叠区域
Then "水力模块"分组中显示一行参数名为"模式"（param_name=operation_mode）的条目
  And 该行"当前值"列显示当前 PLC 寄存器的人类可读值（如"制冷"、"制热"等）
  And 该行"设置值"列显示一个下拉选择器
```

### AC-002-02：工作模式下拉展示四个选项

```
Given 设备管理员在水力模块分组中看到"模式"字段的下拉选择器
When 用户点击展开该下拉选择器
Then 下拉选项按顺序包含：制冷（value=0）、制热（value=1）、通风（value=2）、除湿（value=3）
  And 下拉默认选中值与"当前值"列显示一致
```

### AC-002-03：选择新工作模式并提交成功写入 PLC

```
Given 当前水力模块工作模式为"制冷"（operation_mode=0）
When 用户将下拉选择器改为"制热"（value=1），然后点击"提交"按钮
Then 前端发送 POST /api/device-settings/write/ 请求，items 中包含 {param_name: "operation_mode", new_value: "1"}
  And 等待 MQTT ACK 回执后，提交状态显示"成功"（或包含 operation_mode 的写入成功记录）
  And 页面"当前值"列刷新显示"制热"
```

### AC-002-04：对 operation_mode 发起非法值写入时后端拒绝

```
Given 后端 WRITABLE_SUFFIXES 已包含 _mode 后缀
When 某客户端发送 POST /api/device-settings/write/ 请求，items 中包含 {param_name: "operation_mode", new_value: "99"}
Then 后端接受该请求（参数名合法），将值透传至 PLC 写入流程
  And PLC 侧对非法值的处理由设备固件决定（超出范围值由 PLC 忽略或保留），后端不做业务层枚举校验
  And PLCWriteRecord 记录 new_value="99" 以供审计追溯
```

> 说明：后端仅做参数名白名单校验，值范围校验由 PLC 固件负责，与现有其他参数行为一致。

---

## US-003：在水力模块中设置离家节能标识

**故事描述**：  
作为设备管理员，当用户外出时，我希望能在设备设置页面的"水力模块"分组中找到"离家节能标识"字段，通过选择"启用"或"未启用"来通知 PLC 进入相应的节能状态，而不是通过手动修改寄存器。

**关联需求**：REQ-FUNC-003  
**优先级**：高

### AC-003-01：水力模块分组显示离家节能标识字段

```
Given 设备管理员打开某设备的设备设置页面
When 页面完成加载，展开"水力模块"折叠区域
Then "水力模块"分组中显示一行参数名为"离家节能标识"（param_name=away_energy_saving）的条目
  And 该行"当前值"列显示人类可读标签（"未启用离家节能" 或 "启用离家节能"）
  And 该行"设置值"列显示一个包含两个选项的下拉选择器
```

### AC-003-02：离家节能标识下拉展示两个选项

```
Given 设备管理员在水力模块分组中看到"离家节能标识"字段的下拉选择器
When 用户点击展开该下拉选择器
Then 下拉选项包含：未启用离家节能（value=0）、启用离家节能（value=1）
  And 下拉默认选中值与"当前值"列显示一致
```

### AC-003-03：设置离家节能并提交成功写入 PLC

```
Given 当前离家节能标识为"未启用"（away_energy_saving=0）
When 用户将下拉选择器改为"启用离家节能"（value=1），然后点击"提交"按钮
Then 前端发送 POST /api/device-settings/write/ 请求，items 中包含 {param_name: "away_energy_saving", new_value: "1"}
  And 等待 MQTT ACK 后，写入结果显示成功
  And 页面"当前值"列刷新显示"启用离家节能"
```

### AC-003-04：后端校验 away_energy_saving 为可写参数

```
Given 后端已通过白名单或后缀扩展将 away_energy_saving 纳入可写范围
When 某客户端发送 POST /api/device-settings/write/ 请求，items 包含 {param_name: "away_energy_saving", new_value: "0"}
Then 后端不返回 400 错误（"参数不在可写白名单中"）
  And 请求正常进入 PLC 写入流程
```

---

## US-004：仅提交用户修改过的设备参数

**故事描述**：  
作为设备管理员，当我在设备设置页面修改了部分参数后，我希望点击"提交"时系统只将我实际修改过的参数写入 PLC，没有被我动过的参数不应该被重复下发，以避免不必要的 PLC 总线操作和冗余写入记录。

**关联需求**：REQ-FUNC-004  
**优先级**：高

### AC-004-01：未做任何修改时提交无效

```
Given 设备管理员打开设备设置页面并完成参数加载
When 用户未修改任何参数，直接点击"提交"按钮
Then 页面显示提示"没有可提交的参数"（或"没有已修改的参数"）
  And 不发送任何 POST /api/device-settings/write/ 请求
  And 页面不显示写入成功/失败状态
```

### AC-004-02：仅修改一个参数时只提交该参数

```
Given 设备管理员打开设备设置页面，页面有 N 个可写参数（N > 1）
When 用户仅修改了其中 1 个参数（例如将 system_switch 从 0 改为 1）
  And 用户点击"提交"按钮
Then 前端发送 POST /api/device-settings/write/ 请求
  And 请求体中 items 数组长度为 1，且只包含被修改的那个参数
  And 其他 N-1 个参数不在 items 中
```

### AC-004-03：同时修改多个参数时全部提交

```
Given 设备管理员打开设备设置页面
When 用户修改了 K 个不同参数（K > 1）
  And 用户点击"提交"按钮
Then 前端发送 POST /api/device-settings/write/ 请求
  And 请求体中 items 数组长度为 K，包含所有被修改的参数
  And 未被修改的参数不在 items 中
```

### AC-004-04：多次修改同一参数只记录最终值

```
Given 设备管理员将某参数（如 operation_mode）先从 0 改为 1，再从 1 改为 2
When 用户点击"提交"按钮
Then 前端发送的 items 中该参数只出现一次，new_value 为最终值（"2"）
  And 不产生重复条目
```

### AC-004-05：页面重新加载后脏状态清空

```
Given 设备管理员修改了若干参数但尚未提交
When 用户点击页面上的"刷新"操作（或 loadParams 被再次调用）完成重新加载
Then dirtyFields 被清空，恢复为"无修改"初始状态
  And 此后未做新修改直接点击"提交"，页面显示"没有已修改的参数"提示
```

---

## US-005：取消操作时清除所有未提交的修改

**故事描述**：  
作为设备管理员，当我在设备设置页面调整了若干参数后改变主意，我希望点击"取消"按钮后，所有未提交的修改都被撤销——输入框恢复到服务端当前值，并且脏状态也被清除，下次如果我直接点"提交"不会产生任何写入操作。

**关联需求**：REQ-FUNC-004  
**优先级**：中

### AC-005-01：取消后输入框恢复服务端当前值

```
Given 设备管理员修改了若干参数（如将 system_switch 从 0 改为 1，operation_mode 从 0 改为 2）
When 用户点击"取消"按钮
Then 所有输入控件的显示值恢复为服务端最后一次加载时的值（system_switch 显示 0，operation_mode 显示 0）
  And 提交状态标签（batchStatus）被清除
```

### AC-005-02：取消后脏状态清空，再次提交无效

```
Given 设备管理员已修改若干参数，然后点击"取消"
When 用户在取消后未做任何新的修改，直接点击"提交"
Then 页面显示"没有已修改的参数"（或等效提示）
  And 不发送任何 POST /api/device-settings/write/ 请求
```

### AC-005-03：取消后用户可重新修改并正常提交

```
Given 设备管理员点击"取消"后，脏状态已被清空
When 用户重新修改一个参数（如将 operation_mode 从 0 改为 1）
  And 用户点击"提交"
Then 前端仅提交本次新修改的 operation_mode 字段
  And 取消前的修改不被包含在请求中
```

---

## 附录：验收标准覆盖矩阵

| 功能需求 | 覆盖 US | 覆盖 AC | 正向场景 | 边界/异常场景 |
|---------|-------|-------|---------|------------|
| REQ-FUNC-001（去重系统开关） | US-001 | AC-001-01, AC-001-02, AC-001-03 | AC-001-01, AC-001-02 | AC-001-03（接口层验证） |
| REQ-FUNC-002（工作模式选择） | US-002 | AC-002-01, AC-002-02, AC-002-03, AC-002-04 | AC-002-01, AC-002-02, AC-002-03 | AC-002-04（非法值边界） |
| REQ-FUNC-003（离家节能标识） | US-003 | AC-003-01, AC-003-02, AC-003-03, AC-003-04 | AC-003-01, AC-003-02, AC-003-03 | AC-003-04（后端白名单验证） |
| REQ-FUNC-004（增量保存） | US-004, US-005 | AC-004-01~05, AC-005-01~03 | AC-004-02, AC-004-03, AC-005-03 | AC-004-01（空提交）, AC-004-04（重复修改）, AC-004-05（刷新重置）, AC-005-02 |
