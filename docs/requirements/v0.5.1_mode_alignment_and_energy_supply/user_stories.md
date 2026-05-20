# 用户故事清单

**项目**：FreeArk — 物联网设备管控平台
**版本**：v0.5.1
**需求包**：mode 枚举对齐 + 集中能源供给字段设置
**文件状态**：PENDING_FINAL_CONFIRM — 所有澄清问题已答复，等待用户最终 CONFIRM
**关联需求**：requirements_spec.md（同目录）
**日期**：2026-05-20

---

## US-001：运维人员查看设备运行模式标签正确

**关联需求**：REQ-FUNC-001
**优先级**：P0

作为**运维人员**，
我希望**在设备卡片和设置面板中看到准确的运行模式标签**，
以便**我能确认设备当前处于制冷/制热/通风/除湿哪种状态，而不是看到错误的"制冷"当"除湿"**。

### 验收标准（Given / When / Then）

**AC-001-01：后端标签从 1 起正确返回**
- Given 后端 `param_value_label.py` 已将 `_mode` 映射更新为 `{"1":"制冷","2":"制热","3":"通风","4":"除湿"}`
- When API 返回 `operation_mode` 的 `display_value`，原始值为 1
- Then 返回标签为 `"制冷"`

**AC-001-02：后端不再识别 key=0**
- Given 后端 `_mode` 映射已移除 key `"0"`
- When 查询 `get_display_value("operation_mode", 0)`
- Then 返回原始值字符串 `"0"`（无匹配标签），不返回 `"制冷"`

**AC-001-03：前端卡片展示除湿标签**
- Given `DeviceCardsView.vue` 中 modes 映射为 `{1:'制冷',2:'制热',3:'通风',4:'除湿'}`
- When 设备数据中 `operation_mode` 原始值为 4
- Then 页面展示 `除湿`，不展示 `undefined` 或空白

**AC-001-04：plc_config.json 含枚举注释**
- Given 开发者打开 `plc_config.json`
- When 查看 `operation_mode` 字段
- Then 能看到 `enum_values` 注释字段，包含 4 个枚举项（1/2/3/4）

---

## US-002：运维人员在设置面板选择除湿模式并成功写入 PLC

**关联需求**：REQ-FUNC-001、REQ-FUNC-002
**优先级**：P0

作为**运维人员**，
我希望**在设备设置面板选择"除湿"模式后，PLC 实际接收到值 4**，
以便**设备真正进入除湿运行状态，而不是因静默降级导致意外制冷**。

### 验收标准

**AC-002-01：写管理器接受 mode=4**
- Given `PLCWriteManager` 已新增 `MODE_DEHUMIDIFICATION = 4`
- When 调用 `write_mode_for_building(building_file, mode=4)`
- Then 方法不抛出"无效模式值"错误，正常向 PLC 写入值 4

**AC-002-02：验证列表包含 4**
- Given `plc_write_manager.py` 中 mode 有效值校验逻辑
- When mode=4 传入
- Then 通过校验（不被拒绝），写入继续

**AC-002-03：除湿不再降级为制冷**
- Given `datacollection/plc_data_viewer_gui.py` 已移除降级逻辑
- When 代码静态审查
- Then 不存在将 mode=4 映射为 1 的任何代码路径

**AC-002-04：写入结果可验证**
- Given 测试环境中 PLC 模拟器（或 mock）
- When 通过界面提交 mode=4
- Then 写入日志记录"写入 operation_mode=4"，PLC 寄存器值变为 4

---

## US-003：运维人员在设备设置面板查看并设置集中能源供给

**关联需求**：REQ-FUNC-003
**优先级**：P1

作为**运维人员**，
我希望**在水力模块设备的设置面板中看到「集中能源供给」下拉框，并能选择制冷/制热/无三种状态提交写入**，
以便**我可以通过平台控制集中能源的供给模式，无需直接操作 PLC 硬件**。

### 验收标准

**AC-003-01：设置面板渲染下拉框**
- Given 用户打开任意 `hydraulic_module` 类型设备的设置面板
- When 页面加载完成
- Then 「集中能源供给」行展示为下拉框，选项包含「制冷」「制热」「无」三项（不是输入框）

**AC-003-02：选项与 PLC 值对应**
- Given 下拉框选项列表
- When 检查 `value_options` 数据
- Then `[{raw:"1",label:"制冷"},{raw:"2",label:"制热"},{raw:"3",label:"无"}]`

**AC-003-03：选择「制冷」并提交写入成功**
- Given 用户在下拉框选择「制冷」（值=1）
- When 点击「提交」按钮
- Then PLC DB14 offset=103 写入值为 1，页面显示「全部写入成功」

**AC-003-04：选择「无」并提交主动关闭阀门（Q1 已落实）**
- Given 用户在下拉框选择「无」（值=3）
- When 点击「提交」按钮
- Then PLC DB14 offset=103 **主动写入值 3**，触发阀门关闭指令；不得跳过写入或写入其他值

**AC-003-05：非法值被后端拒绝**
- Given 后端 API 接收到 `central_energy_supply` 值为 0 或 4
- When 执行写入权限与值域校验
- Then 返回 HTTP 400，错误信息说明合法范围为 1-3

**AC-003-06：脏值追踪正常工作**
- Given 用户修改「集中能源供给」下拉框选项
- When 未点击提交直接离开或取消
- Then 「提交」按钮变为激活状态（或有脏值提示），与 v0.5.0 脏值追踪行为一致

---

## US-004：设备卡片正确展示集中能源供给三值状态

**关联需求**：REQ-FUNC-003
**优先级**：P1

作为**运维人员**，
我希望**在设备卡片概览中看到「集中能源供给」显示制冷/制热/无，而不是「有/无」二值**，
以便**快速了解当前集中能源供给模式**。

### 验收标准

**AC-004-01：前端卡片三值展示**
- Given `DeviceCardsView.vue` 中 `central_energy_supply` 展示逻辑已更新
- When 设备数据中 `central_energy_supply` 原始值为 1
- Then 展示 `制冷`

**AC-004-02：值=2 展示制热**
- Given 同上
- When 原始值为 2
- Then 展示 `制热`

**AC-004-03：值=3 展示无**
- Given 同上
- When 原始值为 3
- Then 展示 `无`

**AC-004-04：历史值=0 兼容展示为「无」（Q5 已落实）**
- Given PLC 设备寄存器存储旧值 0（改造前写入）
- When 卡片加载
- Then 展示 `无`（归并到无语义，不崩溃，不展示 `undefined` 或 `0`）

---

## US-005：后端测试同步覆盖新可写状态（开发者视角）

**关联需求**：REQ-FUNC-003、REQ-NFR-002
**优先级**：P1（配套需求，保障回归安全）

作为**开发者**，
我希望**后端测试用例同步更新，准确反映 `central_energy_supply` 从不可写变为可写后的行为**，
以便**CI 测试能正确保护可写白名单变更，防止后续代码回退**。

### 验收标准

**AC-005-01：原断言不可写的测试用例更新**
- Given `test_UT_W_13_central_energy_supply_not_writable` 和 `test_IT_REG_06_central_energy_supply_not_writable`
- When 执行测试套件
- Then 上述两个用例已更新为断言可写（`assertTrue(_is_writable('central_energy_supply'))`），或被替换为新用例

**AC-005-02：新增枚举值域测试**
- Given 后端写入 API
- When 传入 `central_energy_supply=0`
- Then 返回 400（0 不在合法枚举值 1/2/3 内）

**AC-005-03：新增正向写入测试**
- Given 后端写入 API（mock PLC）
- When 传入 `central_energy_supply=2`（制热）
- Then 返回 202，写入任务入队成功

---

## 故事优先级汇总

| 故事 | 标题摘要 | 优先级 | 关联需求 | 开放问题依赖 |
|------|---------|--------|---------|------------|
| US-001 | 运行模式标签正确展示 | P0 | REQ-FUNC-001 | 无 |
| US-002 | 除湿模式正确写入 PLC | P0 | REQ-FUNC-001/002 | 无 |
| US-003 | 设置面板三值下拉写入 | P1 | REQ-FUNC-003 | 无（Q1/Q2 已闭合） |
| US-004 | 卡片三值展示 | P1 | REQ-FUNC-003 | 无（Q5 已闭合） |
| US-005 | 后端测试同步更新 | P1 | REQ-NFR-002 | 无 |

---

*文件状态：PENDING_FINAL_CONFIRM。所有澄清问题（Q1-Q5）已答复并落实于各 AC 中，无开放依赖项。等待用户发出最终 CONFIRM 信号后，本文档升级为 APPROVED 并进入 system-architect 阶段。在此之前，不启动任何架构设计或开发工作。*
