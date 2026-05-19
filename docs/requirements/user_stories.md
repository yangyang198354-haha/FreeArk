# 用户故事清单

**文档编号**: REQ-US-DEVICE-SETTINGS-001  
**项目名称**: FreeArk 设备参数设置功能  
**版本**: 0.4.0-APPROVED  
**状态**: APPROVED（v0.4.0：2026-05-19 Q10~Q12 决策落地；PM 门控通过）  
**创建日期**: 2026-05-19  
**最后更新**: 2026-05-19  
**作者**: requirement-analyst (via pm-orchestrator)

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0 | 2026-05-19 | 初始草稿 |
| 0.2.0 | 2026-05-19 | Open Questions Q1~Q9 决策落地，移除占位符 |
| 0.3.0-APPROVED | 2026-05-19 | 端口确认 32797；US-9 移除回滚 G/W/T；审核通过，已生产部署（commit b260f25） |
| 0.4.0-DRAFT | 2026-05-19 | 生产实测反馈调整：P1/P2 Bug 修复验收；P3 人类可读 UI；P4 批量下发交互；P5 仅显示可写属性。修订 US-2、US-3、US-4、US-6；新增 US-4 的批量下发 AC。 |
| 0.4.0-APPROVED | 2026-05-19 | Q10~Q12 决策落地：US-3/US-4 批量下发明确为"一条 MQTT 多 item"；US-3/US-4 标签明确"由后端 API 返回"；US-9 验收追加"显示原始值 + 标签（如 `1 (开)`）"。PM 门控通过，状态升级为 APPROVED。 |

---

## 说明

- 每条用户故事（US）与需求规格 `requirements_spec.md` 中对应的 FR/NFR 编号交叉引用。
- 所有 Open Questions（Q1-Q9）已全部决策落地，本文档已移除所有 `[依赖 OPEN-Q-XX]` 占位符。
- 角色：**操作员** = 所有已登录用户（`admin` 或 `user` 角色均等权限，Q8 决策）。

---

## US-1 操作列入口

**用户故事**  
作为一名操作员，我希望在设备列表的操作列看到"设置"按钮，以便我能快速进入某户的参数设置界面。

**来源需求**: FR1-1, FR1-2, FR1-3

**验收标准（Given / When / Then）**

```
Given: 操作员已登录，处于"设备管理 > 设备列表"页面
When:  操作员查看某一行设备记录
Then:  操作列中显示"设置"按钮（位于"设备面板"和"PLC历史"按钮旁）

Given: 操作员未登录（直接访问设备列表 URL）
When:  页面加载
Then:  "设置"按钮不渲染（或整页跳转至登录）

Given: 操作员已登录
When:  操作员点击某行的"设置"按钮
Then:  打开设置面板（弹窗或抽屉），面板标题包含该行的 specific_part 标识
       加载指示器（spinner）在参数数据加载期间展示
```

---

## US-2 打开设置面板查看当前值

**用户故事**  
作为一名操作员，我希望打开某户的设置面板后，能够看到主温控和各子面板的**可写参数**分组及其当前值，以便我了解当前状态再决定是否修改。

**来源需求**: FR2-1, FR2-2, FR2-3, FR2-4, FR2-5

**v0.4.0 变更**: P5（仅显示可写属性）

**验收标准（Given / When / Then）**

```
Given: 操作员点击了某行的"设置"按钮
When:  设置面板打开完成（数据加载成功）
Then:  面板内按子设备类型分组展示参数列表（如"主温控"、"书房-温控面板"、"次卧-温控面板"等）
       【P5】面板内仅显示 is_writable=true 的可写参数；is_writable=false 的只读参数（露点、故障、实测温湿度等）不在面板内出现
       每个可写参数显示：显示名（中文）+ 当前值（来自 plc_latest_data 的最新数据）
       当前值对应 PLCLatestData.value，为最近一次采集值；若无数据则显示"-"

Given: 某可写参数在 plc_latest_data 中无记录（设备从未上报该参数）
When:  设置面板加载该参数
Then:  当前值显示"-"或"暂无数据"，不显示错误

Given: 设置面板加载数据时后端接口返回错误（如 500）
When:  加载失败
Then:  面板展示错误提示（如"加载参数失败，请刷新重试"），提供"刷新"操作

Given: 某枚举类可写参数（如"系统开关"）的 select_values_json 为空或 null
When:  面板加载该参数的下拉控件
Then:  【P1 Bug 修复】下拉框不显示空选项，而是在控件位置展示"选项加载失败，请检查 DeviceAttrDef 配置"的提示文案
```

**注（Q2 已决策）**: 可写参数（渲染输入控件）：`*_temp_setting`（温度设定类）、`*_switch`（开关类）。只读参数（仅展示值）：`*_dew_point_setting`（露点）、`*_error`/`*_alert`（故障类）、`*_temperature`/`*_humidity`（实测传感器值）。**【P5】只读参数在设置面板中完全不渲染，既不显示控件也不显示文本行。** 后端在参数列表接口中返回 `is_writable` 字段，前端据此过滤。

---

## US-3 修改主温控参数并下发

**用户故事**  
作为一名操作员，我希望在设置面板中修改主温控（如客厅温度设定）的参数值，并一次性统一下发至 PLC，以便对系统进行远程调控。

**来源需求**: FR3-1, FR3-2, FR3-4, FR3-5, FR3-6, FR2-6, FR2-7

**v0.4.0 变更**: P3（人类可读 UI）、P4（批量下发交互）

**验收标准（Given / When / Then）**

```
Given: 设置面板已打开，显示"主温控"分组中的可写参数列表
When:  面板加载完成
Then:  【P3/Q11】枚举类参数（如"系统开关"）的当前值显示人类可读标签（如"开"/"关"），而非 0/1；标签**由后端 API 返回**（`display_value` 字段），前端直接渲染，不做业务映射
       【P3/Q11】"系统开关"的下拉控件选项列表显示"开"/"关"，而非数字；选项来自后端 API 返回的 `value_options: [{raw, label}]`（由 `param_value_label.py` 常量驱动），前端不维护映射逻辑
       【P1】"系统开关"下拉框有可选项（不为空）
       数值类参数（如温度设定）显示数字值 + 单位（如"22 ℃"）

Given: 设置面板已打开，操作员修改了一个或多个主温控可写参数值
When:  操作员点击面板底部/顶部的单一"提交"按钮
Then:  【P4/Q10】所有已修改的字段在同一次操作中统一下发，以**一条 MQTT 命令**（payload 含 `items` 数组，单个 `request_id`）发送，不循环逐字段下发
       "提交"按钮进入 loading 状态（防止重复点击）
       后端接收到请求，生成单一 request_id，向 MQTT broker 发布批量写命令消息（含所有已修改字段的 `items`）
       后端立即返回 202 Accepted，UI 提示"命令已下发，等待结果..."

Given: 操作员修改了部分字段值，但改变主意不想提交
When:  点击"取消"按钮
Then:  【P4】面板内所有已修改但未提交的字段恢复为加载时的当前值，"提交"按钮不被触发

Given: 操作员输入了超出参数值域范围的值（如温度设定超出 DeviceAttrDef.num_value_json 定义的允许区间）
When:  点击"提交"按钮
Then:  前端校验拦截，显示"输入值超出范围（允许范围：X ~ Y）"，不发起后端请求

Given: 后端向 MQTT broker 发布命令失败（broker 不可达）
When:  点击"提交"后后端返回 503
Then:  【P2 Bug 修复】UI 展示具体失败分类（见 FR4-4 三类错误），而非笼统"下发通道异常"
       "提交"按钮恢复为可点击状态，操作员输入的值保留在控件中供重试
```

---

## US-4 修改某个子面板参数并下发

**用户故事**  
作为一名操作员，我希望在设置面板中切换到某个子面板（如书房），修改其开关或温度设定，一次性统一下发，以便精细化控制各房间的暖通状态。

**来源需求**: FR2-1, FR2-6, FR2-7, FR3-1, FR3-2, FR3-6

**v0.4.0 变更**: P1（枚举下拉空值 Bug）、P3（人类可读）、P4（批量下发交互）

**验收标准（Given / When / Then）**

```
Given: 设置面板已打开，操作员切换至"书房-温控面板"分组
When:  面板该分组加载完成
Then:  【P3】枚举类参数当前值显示人类可读标签（如"开"/"关"）
       【P1】"开关"类下拉控件有可选项（"开"/"关"），不为空
       【P5】只读属性（露点、实测温湿度、故障）不显示在面板内

Given: 操作员将"开关"（如 study_room_switch）从"关"修改为"开"，同时修改"设定温度"值，点击"提交"
When:  操作员点击单一"提交"按钮
Then:  【P4/Q10】两个修改**以一条 MQTT 命令**统一下发，payload 中 `items` 数组包含两个字段，共用单一 request_id（不循环发 N 条命令，不逐字段下发）
       同 US-3 的下发流程（生成 request_id，发布 MQTT，返回 202）
       下发成功回执到达后，UI 更新两个参数的当前值，均显示人类可读标签（标签由后端 `value_options` 映射，Q11）

Given: 操作员修改了书房面板多个参数后点击"取消"
When:  点击"取消"
Then:  【P4】所有已修改参数的控件恢复为本次面板加载时的值，不发起下发请求

Given: 某个子面板在 DeviceConfig 中定义但 plc_config.json 中无对应地址映射
When:  操作员尝试下发该参数
Then:  写入应用报错，回执 MQTT 消息 success=false，UI 展示"该参数暂不支持远程设置"
       （批量下发时该参数写入失败，其他参数的成功/失败状态独立展示，不互相影响）

Given: 同一 specific_part 下多个子面板的参数同时被修改（操作员一次修改了多个输入框后点击"提交"）
When:  提交批量下发
Then:  【Q10 已决策】以**一条 MQTT 命令多 item**下发，`items` 数组包含所有已修改参数，共用单一 request_id；记录至 plc_write_record 表的方式由架构阶段决策（1 条 request_id 对应 N 行，还是 1 行含 items JSON），见架构文档
       （Q7 决策：无需加锁，独立 request_id 保证幂等即可）
```

---

## US-5 自动刷新看到写入结果

**用户故事**  
作为一名操作员，我希望设置面板能自动刷新参数值，使我在下发命令后无需手动刷新页面即可看到最新写入结果。

**来源需求**: FR5-1, FR5-2, FR5-3, FR5-4, FR5-5, NFR-1-1

**验收标准（Given / When / Then）**

```
Given: 设置面板打开
When:  面板完成初始化
Then:  前端通过 MQTT-over-WebSocket 连接 broker 的 WebSocket 端口，
       订阅 /datacollection/plc/write/ack/{specific_part}，
       订阅成功标识可见（可选：面板右上角显示"实时连接中"状态指示器）

Given: 设置面板处于打开状态，MQTT-over-WebSocket 订阅已建立
When:  收到来自 broker 的回执推送消息
Then:  对应参数的当前值立即更新，UI 刷新不重置操作员正在编辑但未下发的输入框内容

Given: 操作员已下发某参数修改命令（US-3 或 US-4），PLC 写入成功
When:  写入应用发布成功回执消息（FR4-3），WebSocket 推送到达前端
Then:  UI 在用户点击"确认"后 ≤ 10 秒内呈现：
       该参数当前值更新为写入后的新值，写入状态标识为"成功"（如绿色对勾）

Given: 操作员已下发命令，但 30 秒内未收到任何回执
When:  客户端侧超时计时器到达
Then:  UI 对该参数写入状态显示"等待超时"，"确认"按钮恢复为可点击状态，提供"重试"操作

Given: 操作员在面板打开期间关闭弹窗（或导航至其他页面）
When:  弹窗关闭
Then:  WebSocket 订阅断开，释放连接资源，不在后台保持订阅
```

---

## US-6 写入失败的提示与重试

**用户故事**  
作为一名操作员，我希望在 PLC 写入失败时收到**明确定位失败原因**的错误提示，并能直接重试，而无需重新打开设置面板重新输入。

**来源需求**: NFR-2-1, NFR-2-2, NFR-2-3, NFR-3-1, FR4-4

**v0.4.0 变更**: P2（错误分类，区分三类失败原因）

**验收标准（Given / When / Then）**

```
Given: 操作员已提交下发，MQTT 通道不可达（broker 连接失败，后端返回 503）
When:  后端接口返回失败
Then:  【P2 Bug 修复】UI 展示"下发失败：MQTT 通道不可达，请检查 broker 连接状态"（对应 FR4-4 类型①）
       不记录任何写入操作记录（命令未下发成功）
       "提交"按钮恢复为可点击，操作员输入值保留

Given: 操作员已提交下发，MQTT 命令已发布，但 PLCWriteSubscriber 未消费（超时无回执）
When:  前端 30 秒超时计时器到达
Then:  【P2 Bug 修复】UI 对该参数显示"下发失败：PLCWriteSubscriber 未响应，请检查 datacollection 服务状态"（对应 FR4-4 类型②）
       "提交"按钮恢复可点击，提供"重试"操作

Given: 操作员已提交下发，PLCWriteSubscriber 收到命令但 PLC 写入失败（snap7 超时/地址错误）
When:  写入应用发布失败回执（FR4-4，success=false，error_message="PLC_WRITE_FAILED: {detail}"）
Then:  【P2 Bug 修复】UI 对该参数显示"写入失败：{snap7 原始错误信息}"（对应 FR4-4 类型③）
       "重试"按钮可点击，点击后以相同参数值重新发起下发流程
       错误状态不影响面板内其他参数的展示和操作（批量下发时每个参数独立显示各自的成功/失败状态）

Given: 操作员点击"重试"
When:  重新下发命令
Then:  系统以新的 request_id 重新发布 MQTT 命令，行为与 US-3 的"提交"流程完全相同

Given: MQTT broker 不可达，后端接口返回 503
When:  操作员点击"提交"
Then:  【P2 Bug 修复】UI 展示具体错误分类（见上方 MQTT 通道不可达 AC），不再笼统显示"下发通道异常"
       操作员输入的值保留在输入框中，供重试使用
```

---

## US-7 PLC 写入应用侧：订阅 / 写值 / 回执 / 落库

**用户故事**  
作为 PLC 写入应用（`datacollection` 进程），我希望订阅写命令 MQTT topic、解析命令、写入 PLC、发布回执并落库，以完成从 Web 到 PLC 的完整写入链路。

**来源需求**: FR4-1, FR4-2, FR4-3, FR4-4, FR4-5, FR4-6, NFR-3-3

**验收标准（Given / When / Then）**

```
Given: PLC 写入应用已启动并订阅写命令 topic /datacollection/plc/write/command/{specific_part}
When:  收到一条有效的写命令消息（含 specific_part、param_name、value、request_id）
Then:  从 plc_config.json 查找 param_name 对应的 db_num、offset、data_type
       通过 snap7 调用 write_db_data(db_num, offset, value, data_type) 写入 PLC

Given: snap7 写入调用成功（返回 success=True）
When:  写入完成
Then:  向回执 topic /datacollection/plc/write/ack/{specific_part} 发布消息：
       { request_id, specific_part, param_name, value, success: true, written_at }
       更新 plc_write_record 表对应记录：status=success，acked_at=written_at

Given: snap7 写入失败（连接失败、超时、地址错误等）
When:  写入失败
Then:  向回执 topic /datacollection/plc/write/ack/{specific_part} 发布消息：
       { request_id, specific_part, param_name, success: false, error_message }
       更新 plc_write_record 表对应记录：status=failed，error_message 填写失败原因

Given: 收到已处理过的 request_id（重复消息）
When:  尝试写入
Then:  幂等检查（查询操作记录表是否已有该 request_id 的记录），
       若已存在：跳过 PLC 写入，直接以原有记录内容重新发布回执（或静默忽略）
       若不存在：正常执行写入流程

Given: 命令消息中的 param_name 不在 plc_config.json 中
When:  收到该消息
Then:  不尝试 PLC 写入，立即发布回执（success=false，error_message="param_name 未定义"）
       记录操作记录（success=false）
```

---

## US-8 权限与审计

**用户故事**  
作为系统管理员，我希望所有设置操作都有操作人记录，以便在出现问题时进行追溯。

**来源需求**: NFR-4-1, NFR-4-2, FR6

**验收标准（Given / When / Then）**

```
Given: 操作员（任意已登录角色）成功下发一条参数设置命令
When:  命令下发时（后端写入 plc_write_record）
Then:  plc_write_record 记录包含字段：operator（发起用户的 username）、specific_part、
       param_name、old_value（下发时快照）、new_value（目标值）、request_id、
       status=pending、created_at

Given: 未认证请求（无 Token）访问设置命令接口
When:  发起 POST 请求
Then:  后端返回 401 Unauthorized，不执行任何写操作，不发布任何 MQTT 消息

Given: 已登录的普通用户（role=user）尝试设置任意 specific_part 的设备
When:  发起设置请求（携带有效 Token）
Then:  后端正常处理，返回 202 Accepted
       （Q8 决策：所有登录用户均可写，不做 specific_part 所有权过滤）
```

---

---

## US-9 审计日志查询（只读）

**用户故事**  
作为一名操作员，我希望能查看历次参数设置操作的记录（含操作人、下发值、结果），以便追溯历史写入操作。

**来源需求**: FR6-1, FR6-2, FR6-3, FR6-4

**本期范围说明**：本期仅实现只读查询，不含回滚功能。回滚延后至下期（见 requirements_spec.md Out of Scope 第 6 条）。

**验收标准（Given / When / Then）**

```
Given: 已登录操作员进入"设置记录"查询页面
When:  页面加载
Then:  展示 plc_write_record 表中的记录列表，按 created_at 降序，每页 20 条
       列表展示：request_id、specific_part、param_name、old_value、new_value、
       operator、status、created_at、acked_at、error_message（失败时）
       【Q12】new_value 列展示格式为"原始值 (标签)"，如 `1 (开)` 或 `0 (关)`；若无对应标签则仅显示原始值；标签映射由后端 API 或前端调用 `param_value_label.py` 驱动
       列表不显示"回滚"按钮（本期只读）

Given: 操作员在查询条件中输入 specific_part="3-1-7-702"、时间范围=今天
When:  点击"查询"
Then:  返回符合条件的记录列表（specific_part 精确匹配，created_at 在今天范围内）
       空结果时展示"暂无记录"提示

Given: 操作员在记录列表中查看一条 status=failed 的记录
When:  查看该记录
Then:  error_message 字段展示失败原因（如"snap7 连接超时"）
```

---

## US-9-DEFERRED 审计日志回滚（延后至下期，不进入本期开发）

**状态**: DEFERRED — 不在本期实现范围内。

**用户故事（留存，下期实现）**  
作为一名操作员，我希望能对已成功的写入记录进行回滚，将参数恢复为写入前的值，以便快速纠错。

**原始验收标准（G/W/T）**：见 v0.2.0 历史版本。下期实现时需重新评审对应需求条目（FR6 回滚部分）。

---

## 用户故事与需求映射

| 用户故事 | 对应 FR/NFR | v0.4.0 变更 | Open Questions 状态 |
|---------|------------|------------|-------------------|
| US-1 | FR1-1, FR1-2, FR1-3 | 不变 | Q8 已决策 |
| US-2 | FR2-1~FR2-5 | **P1, P5 修订** | Q1, Q2 已决策；Q13 待开发排查 |
| US-3 | FR3-1, FR3-2, FR3-4, FR3-5, FR3-6, FR2-6, FR2-7 | **P1, P2, P3, P4 修订** | Q10 已决策（一条 MQTT 多 item）；Q11 已决策（后端常量文件） |
| US-4 | FR2-1, FR2-6, FR2-7, FR3-1, FR3-2, FR3-6 | **P1, P2, P3, P4, P5 修订** | Q10 已决策（一条 MQTT 多 item）；Q11 已决策（后端常量文件） |
| US-5 | FR5-1~FR5-5, NFR-1-1 | 不变 | Q5, Q6 已决策 |
| US-6 | NFR-2-1, NFR-2-2, NFR-2-3, NFR-3-1, FR4-4 | **P2 修订** | — |
| US-7 | FR4-1~FR4-6, NFR-3-3 | **P2, P3 修订** | Q3, Q4 已决策 |
| US-8 | NFR-4-1, NFR-4-2 | 不变 | Q8 已决策 |
| US-9 | FR6-1~FR6-4（只读） | **Q12 决策落地**（new_value 展示"原始值 + 标签"） | Q9、Q12 均已决策；回滚延后 |
| US-9-DEFERRED | FR6 回滚部分 | DEFERRED（下期） | DEFERRED（下期） |
