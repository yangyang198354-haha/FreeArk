# 需求规格说明书

**项目**：FreeArk — 物联网设备管控平台
**版本**：v0.5.1
**需求包**：mode 枚举对齐 + 集中能源供给字段设置
**文件状态**：PENDING_FINAL_CONFIRM — 澄清问题已全部答复，等待用户最终 CONFIRM
**作者**：requirement-analyst (via PM Orchestrator)
**日期**：2026-05-20

---

## 1. 背景与动因

v0.5.0 完成水利模块字段调整（提交 778a6fd）后，代码审查发现运行模式（operation_mode）枚举在三个位置存在不一致，导致：

- 后端 `param_value_label.py` 以 0 为起点，前端 `DeviceCardsView.vue` 以 1 为起点，PLC 写管理器仅支持 1/2/3（无除湿）。
- `plc_data_viewer_gui.py` 注释明确承认 mode=4（除湿）在写入时静默降级为制冷，存在数据一致性风险。
- `plc_config.json` 中 `operation_mode` 字段无枚举注释，维护者无法从配置文件直接了解合法取值范围。

此外，`central_energy_supply` 字段已在 `plc_config.json`（DB14 offset=103, byte）和 `seed_device_config.py` 中存在，但：

- 前端 `DeviceCardsView.vue` 仅以 `v===0 ? '无' : '有'` 展示（二值布尔语义），与业务期望的三值枚举（制冷/制热/无）不符。
- 设备设置面板（`DeviceSettingsPanelView.vue`）当前测试明确断言其不可写（`test_UT_W_13`、`test_IT_REG_06`）。
- PLC 写管理器中无 `central_energy_supply` 独立写入实现；`write_mode_for_building` 当前将同一 mode 值同时写入 `operation_mode` 与 `central_energy_supply`，行为与业务预期不符。

---

## 2. 需求范围

### 2.1 版本边界

| 包含 | 不包含 |
|------|--------|
| mode 枚举三层对齐（前端/后端/datacollection） | 其他参数枚举重构 |
| plc_config.json 枚举注释补充 | 数据库 Schema 结构变更 |
| central_energy_supply 设置页面下拉支持 | 能源统计报表功能 |
| central_energy_supply PLC 写入实现 | 多设备批量模式切换的 UI 改版 |
| operation_mode 与 central_energy_supply 写入解耦 | 数据库迁移脚本 |

### 2.2 不变更项

- PLC 寄存器地址（operation_mode: DB14/offset=89；central_energy_supply: DB14/offset=103）保持不变。
- 已有认证、权限、MQTT 通信架构不变。
- v0.5.0 已实现的脏值追踪机制复用。
- `seed_device_config.py` 的设备类型归属不变（`central_energy_supply` 仍归 `hydraulic_module`，不扩展到其他设备类型）。

---

## 3. 功能需求

### REQ-FUNC-001：operation_mode 枚举统一为从 1 起

**来源**：任务背景 § 枚举零点错位
**优先级**：P0（数据一致性缺陷，必修）

**规范**：系统所有位置的运行模式枚举必须统一为：

| 值 | 含义 |
|----|------|
| 1  | 制冷 |
| 2  | 制热 |
| 3  | 通风 |
| 4  | 除湿 |

**影响位置（必须全部修改，缺一不可）**：

| # | 文件 | 当前错误 | 修改目标 |
|---|------|---------|---------|
| 1 | `FreeArkWeb/backend/freearkweb/api/param_value_label.py:5` | `{"0":"制冷","1":"制热","2":"通风","3":"除湿"}` | `{"1":"制冷","2":"制热","3":"通风","4":"除湿"}` |
| 2 | `FreeArkWeb/frontend/src/views/DeviceCardsView.vue:312` | 已是从 1 起，确认第 4 项除湿与后端对齐 | 保持 `{1:'制冷',2:'制热',3:'通风',4:'除湿'}` |
| 3 | `datacollection/plc_write_manager.py:47-49` | 仅 1/2/3，无 MODE_DEHUMIDIFICATION | 新增 `MODE_DEHUMIDIFICATION = 4`，有效值列表扩展为 `[1,2,3,4]` |
| 4 | `datacollection/plc_write_manager.py:140-148`（注释） | 方法注释写"3=通风" | 更新为"1=制冷，2=制热，3=通风，4=除湿" |
| 5 | `plc_config.json:27-34` | `operation_mode` 无枚举说明 | 新增 `"enum_values": {"1":"制冷","2":"制热","3":"通风","4":"除湿"}` 注释字段 |

**验收标准（AC）**：
- Given 后端 `param_value_label.py` 的 `_mode` 映射，When 查询 key=`"0"`，Then 无对应标签（不存在）。
- Given 后端映射，When 查询 key=`"1"`，Then 返回 `"制冷"`；key=`"4"` 返回 `"除湿"`。
- Given PLC 写管理器，When 传入 mode=4，Then 不触发 `无效模式` 错误，正常写入 PLC 寄存器值 4。
- Given `plc_config.json`，When 读取 `operation_mode` 字段，Then 能看到包含 4 个枚举值的注释字段。

---

### REQ-FUNC-002：消除除湿静默降级

**来源**：任务背景 § 除湿在 PLC 写管理器无实现
**优先级**：P0（静默数据错误，必修）

**规范**：`datacollection/plc_data_viewer_gui.py:479-482` 中将除湿降级为制冷的逻辑必须移除或替换。修改后，当用户选择 mode=4（除湿）时，PLC 写管理器直接写入值 4，不做降级。

**AC**：
- Given 用户在界面选择"除湿"（mode=4），When 提交写入，Then PLC 实际写入值为 4（非 1）。
- Given `plc_data_viewer_gui.py`，When 代码审查，Then 不存在将 mode=4 映射为 1 的逻辑。

---

### REQ-FUNC-003：central_energy_supply 设置页面三值下拉支持

**来源**：任务背景 § 新增集中能源供给字段
**优先级**：P1（新功能）

**规范（已含全部澄清答复，定稿）**：

`central_energy_supply` 字段在设备设置面板（`DeviceSettingsPanelView.vue`）中以三值枚举下拉框方式可设置：

| PLC 写入值 | UI 显示标签 | 语义说明 |
|-----------|------------|---------|
| 1 | 制冷 | 集中供冷，阀门开启至制冷模式 |
| 2 | 制热 | 集中供热，阀门开启至制热模式 |
| 3 | 无 | **主动关闭阀门**，向 PLC 写入值 3，触发阀门关闭指令 |

> **Q1 答复已落实**：值=3「无」语义为**主动关闭阀门**，而非空闲不操作。PLC 写入须下发值 3 以触发阀门关闭，验收标准须验证该写入行为。

**设备类型范围**：
- 仅限 `hydraulic_module`（水力模块）。`seed_device_config.py` 现有归属不变，不扩展到其他设备类型。（Q2 答复已落实）

**影响位置（全部须修改）**：

| 位置 | 当前状态 | 修改目标 |
|------|---------|---------|
| `param_value_label.py` | 无 `central_energy_supply` 精确映射 | 在 `PARAM_EXACT_VALUE_LABELS` 新增 `'central_energy_supply': {"1":"制冷","2":"制热","3":"无"}` |
| `param_value_label.py` 可写白名单 | 不可写 | 加入可写字段列表 |
| `DeviceCardsView.vue:316` | `v===0?'无':'有'` | 改为三值枚举展示 `{1:'制冷',2:'制热',3:'无'}`，值=0 展示为「无」（见 Q5） |
| `plc_write_manager.py` | 无独立 `central_energy_supply` 写入实现 | 新增单字段独立写入支持，值域 1/2/3，写 DB14 offset=103 |
| 后端写入权限校验 | 拒绝写入 | 放行写入（通过精确名白名单机制） |
| 后端测试 | `test_UT_W_13`、`test_IT_REG_06` 断言不可写 | 更新为断言可写，并补充三值枚举写入测试 |

**AC（定稿，含 Q1 主动关闭行为）**：
- Given 设备设置面板，When 加载 `hydraulic_module` 类型设备参数，Then「集中能源供给」行渲染为下拉框，选项为「制冷/制热/无」。
- Given 用户选择「制冷」（值=1）并提交，When PLC 写入完成，Then DB14 offset=103 写入值为 1。
- Given 用户选择「制热」（值=2）并提交，When PLC 写入完成，Then DB14 offset=103 写入值为 2。
- Given 用户选择「无」（值=3）并提交，When PLC 写入触发，Then DB14 offset=103 **主动写入值 3**，触发阀门关闭指令（不得跳过写入或写入任何其他值）。
- Given 传入值=0 或 >3，When 后端校验，Then 返回 400 Bad Request（非法枚举值，合法范围 1-3）。

---

### REQ-FUNC-004：operation_mode 与 central_energy_supply 写入解耦

**来源**：Q4 答复
**优先级**：P0（现有 Bug，`write_mode_for_building` 将同一值写入两字段行为错误）

**规范**：`plc_write_manager.py` 中 `write_mode_for_building` 方法须重构，**operation_mode 与 central_energy_supply 各自独立写入**：

| 字段 | 合法值域 | PLC 地址 |
|------|---------|---------|
| `operation_mode` | 1/2/3/4 | DB14, offset=89 |
| `central_energy_supply` | 1/2/3 | DB14, offset=103 |

两字段不再共用同一 mode 值，各自取值来源独立。

**AC**：
- Given `write_mode_for_building` 调用时传入 `operation_mode=3`（通风），When 执行写入，Then DB14 offset=89 写入 3，DB14 offset=103 **不受此次调用影响**（不同步写入）。
- Given `central_energy_supply` 独立写入接口，When 传入值=3，Then DB14 offset=103 写入 3（主动关闭阀门），operation_mode 不受影响。

---

## 4. 非功能需求

### REQ-NFR-001：向后兼容历史 mode=0 数据（过渡期兼容，不做迁移）

**决策（Q3 答复落实）**：不编写数据库迁移脚本。前端/后端展示层对历史旧值 0 做兼容映射：

- 后端：`param_value_label.py` 对 `operation_mode` 值=0 的记录，展示层映射为"制冷"（过渡期兼容，不修改数据库原始值）。
- 前端：DeviceCardsView.vue 对 mode=0 展示为"制冷"（兼容，不报错）。
- 数据库原始值 0 的记录保留，不触发任何数据迁移或批量更新。

### REQ-NFR-002：可写字段变更需同步测试

`central_energy_supply` 从不可写变为可写，属于权限扩大。需在集成测试中验证：写入越界值（如 0、4、99）时后端正确拒绝，防止无效值写入 PLC。

---

## 5. 澄清问题最终答复汇总（已全部闭合）

| # | 问题 | 最终决策 | 落实位置 |
|---|------|---------|---------|
| Q1 | 值=3「无」的语义 | **主动关闭阀门**，PLC 写入值 3 触发阀门关闭指令 | REQ-FUNC-003 AC、REQ-FUNC-004 AC |
| Q2 | 设备类型范围 | **仅 hydraulic_module**，不扩展 | REQ-FUNC-003 规范、REQ-FUNC-003 影响位置 |
| Q3 | 历史 mode=0 处理 | **过渡期兼容展示，不写迁移脚本** | REQ-NFR-001 |
| Q4 | write_mode_for_building 共写行为 | **operation_mode 与 central_energy_supply 独立写入** | REQ-FUNC-004（新增需求） |
| Q5 | 前端 PLC 旧值 0 展示 | **展示为「无」**（归并到无语义） | REQ-FUNC-003 影响位置（DeviceCardsView.vue） |

---

## 6. 约束与依赖

- **部署约束**：物理机部署（禁 Docker），生产服务器树莓派 192.168.31.51，部署通过 plink + git pull。
- **数据库**：生产用 MySQL（192.168.31.98:3306），测试用 SQLite。
- **前端框架**：Vue 3 + Element Plus，`DeviceSettingsPanelView.vue` 已有脏值追踪机制，本次复用。
- **PLC 通信**：snap7 库，DB14 数据块，offset 地址来自 `plc_config.json`。
- **当前版本**：基于 v0.5.0（提交 778a6fd）。

---

*文件状态：PENDING_FINAL_CONFIRM。所有澄清问题已答复并落实。等待用户发出最终 CONFIRM 信号后，本文档升级为 APPROVED 并进入 system-architect 阶段。在此之前，不启动任何架构设计或开发工作。*
