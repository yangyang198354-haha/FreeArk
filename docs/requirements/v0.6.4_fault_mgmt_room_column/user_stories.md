# 用户故事

```
file_header:
  document_id: USER-STORIES-v0.6.4-FM-ROOM
  title: 故障管理 — 房间列 + 设备类型过滤重组 — 用户故事
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.6.4-FM-ROOM
  created_at: 2026-05-29
  status: DRAFT
  references:
    - docs/requirements/v0.6.4_fault_mgmt_room_column/requirements_spec.md
```

---

## US-FM-009：故障列表新增"房间"列

**As** 物业管理员，
**I want** 故障列表每行直接显示该故障设备所在的房间名称（如"主卧"、"客厅"），
**So that** 我无需记忆设备 SN 或查阅 PLC 配置表就能快速判断哪个住户哪个房间出了问题。

### Given / When / Then

**GWT-009-01（正常展示）**
- Given: 生产 `fault_event` 表中某故障行的 `room_name` = "主卧"
- When: 用户访问故障管理页并加载故障列表
- Then: 该行"房间"列展示"主卧"

**GWT-009-02（NULL 兜底）**
- Given: 某故障行的 `room_name` IS NULL（历史数据回填前或 device_sn 无关联）
- When: 用户访问故障管理页
- Then: 该行"房间"列展示 "-"，不显示空白或报错

**GWT-009-03（过滤器）**
- Given: 用户在房间过滤器中选择"主卧"
- When: 点击"查询"
- Then: 列表只展示 `room_name` = "主卧" 的故障行（其他房间的故障被过滤）

**GWT-009-04（列风格一致性）**
- Given: 用户查看故障管理表格
- When: 目视检查"房间"列的表头、列宽、字体、对齐方式
- Then: 与"故障类型"、"故障描述"等现有列视觉风格一致

---

## US-FM-010：设备类型过滤器按"实际房间"5 类重组

**As** 物业管理员，
**I want** 设备类型过滤器的选项直接对应人类可理解的房间名称（主卧、次卧、儿童房、书房、客厅），而不是 PLC 寄存器前缀（如"三房主卧四房次卧"），
**So that** 我在查询"3 号楼主卧温控面板故障"时，能用"主卧温控面板"直接过滤，无需了解 PLC 硬件地址分配逻辑。

### Given / When / Then

**GWT-010-01（4 房户型儿童房过滤）**
- Given: 用户选择特定 4 房户型（如 3-1-602）的房号，AND 在设备类型中选择"儿童房温控面板"
- When: 提交查询
- Then: 返回该户儿童房温控面板的故障（device_room.ori_room_name = "儿童房"）；预期 1 条（如有活跃故障）

**GWT-010-02（4 房户型次卧过滤）**
- Given: 4 房户型（3-1-602）+ 设备类型"次卧温控面板"
- When: 提交查询
- Then: 返回次卧（ori_room_name = "次卧"）的故障；对应 PLC 的 `bedroom_*` 寄存器组（4 房视角）

**GWT-010-03（4 房户型主卧过滤）**
- Given: 4 房户型（3-1-602）+ 设备类型"主卧温控面板"
- When: 提交查询
- Then: 返回主卧（ori_room_name = "主卧"）的故障；对应 PLC 的 `children_room_*` 寄存器组（4 房视角）

**GWT-010-04（3 房户型书房过滤）**
- Given: 任意 3 房户型 + 设备类型"书房温控面板"
- When: 提交查询
- Then: 返回 0 条（3 房无书房设备）

**GWT-010-05（过滤器标签已更新）**
- Given: 用户打开故障管理页设备类型下拉
- When: 浏览所有选项
- Then: 可见"客厅主温控"、"主卧温控面板"、"次卧温控面板"、"儿童房温控面板"、"书房温控面板"；
  不可见"卧室温控面板"、"儿童房温控面板（旧）"、"第四儿童房温控面板"等旧标签

**GWT-010-06（非温控类 sub_type 不受影响）**
- Given: 用户选择"新风机"设备类型过滤
- When: 提交查询
- Then: 过滤逻辑与 v0.6.3 一致（product_code=130004，无房间约束）

**GWT-010-07（seed_device_config 重建后 categories 接口更新）**
- Given: `seed_device_config --reset` 已执行，DeviceConfig 表已用新 sub_type 重建
- When: 前端调用 `/api/devices/fault-event-categories/`
- Then: 响应中的 `sub_types` 数组包含 5 个新 sub_type，不含旧 4 个 sub_type

---

## US-FM-011：fault_event 增加 room_name + room_id（方案 B+）

**As** 系统（FreeArk 后端故障消费服务），
**I want** 在每次写入新故障事件时自动填充 `room_name` 和 `room_id` 字段，并对历史数据执行一次性回填，
**So that** fault_event 表具备直接的房间信息，支持 FR-FM-009 的展示需求，且不依赖运行时 JOIN。

### Given / When / Then

**GWT-011-01（新故障 T1 INSERT 自动填充）**
- Given: MQTT 上报一条新故障，device_sn 在 `device_node` 表中有记录，且 DeviceNode 关联到 DeviceRoom（ori_room_name = "主卧"）
- When: fault_consumer 触发 T1 INSERT
- Then: 新写入的 `fault_event` 行的 `room_name` = "主卧"，`room_id` = 对应 DeviceRoom 的 id

**GWT-011-02（device_sn 无关联时容错）**
- Given: MQTT 上报故障，device_sn 在 `device_node` 中无记录（如早期测试脏数据 sn=1）
- When: fault_consumer 触发 T1 INSERT
- Then: `fault_event` 写入成功，`room_name` = NULL，`room_id` = NULL；无异常抛出，服务不崩溃

**GWT-011-03（历史数据回填）**
- Given: migration 0028 执行前，fault_event 中有约 3094 行 `room_name IS NULL`
- When: 运行 migration 0028
- Then: 所有 device_sn 可在 device_node 中找到对应记录的行，其 `room_name` 和 `room_id` 被正确回填；无法关联的行保持 NULL

**GWT-011-04（device_room 删除不阻塞）**
- Given: 某 DeviceRoom 记录被删除（如住户设备树重同步）
- When: 相关 fault_event 的 room_id 外键受影响
- Then: fault_event 的 `room_id` 被置为 NULL（ON DELETE SET NULL），fault_event 行不删除，故障历史不丢失

**GWT-011-05（fault_consumer 停启顺序）**
- Given: 部署 v0.6.4，需执行 migration 0027（DDL）和 migration 0028（数据回填）
- When: 按规定顺序：先停 `freeark-fault-consumer` → 执行 migration → 重启 `freeark-backend` + `freeark-mqtt-consumer` + `freeark-fault-consumer`
- Then: migration 期间无并发写入冲突；重启后新故障按新逻辑写入 room_name/room_id

---

## 验收标准汇总（AC 快速检索）

| 故事 | AC 编号 | 关键验收点 | 参考 GWT |
|------|---------|---------|---------|
| US-FM-009 | AC-009-01 | room_name 非空时正确展示 | GWT-009-01 |
| US-FM-009 | AC-009-02 | room_name=NULL 时展示 "-" | GWT-009-02 |
| US-FM-009 | AC-009-03 | 房间过滤器正确过滤 | GWT-009-03 |
| US-FM-009 | AC-009-04 | 列风格与现有列一致 | GWT-009-04 |
| US-FM-010 | AC-010-01 | 4 房户型"儿童房"过滤有效 | GWT-010-01 |
| US-FM-010 | AC-010-02 | 4 房户型"次卧"过滤有效 | GWT-010-02 |
| US-FM-010 | AC-010-03 | 4 房户型"主卧"过滤有效 | GWT-010-03 |
| US-FM-010 | AC-010-04 | 3 房户型"书房"过滤返回 0 条 | GWT-010-04 |
| US-FM-010 | AC-010-05 | 过滤器标签显示新名称 | GWT-010-05 |
| US-FM-010 | AC-010-06 | 非温控类 sub_type 行为不变 | GWT-010-06 |
| US-FM-011 | AC-011-01 | 新故障自动填充 room_name/room_id | GWT-011-01 |
| US-FM-011 | AC-011-02 | device_sn 无关联时 room=NULL 不崩溃 | GWT-011-02 |
| US-FM-011 | AC-011-03 | 历史数据回填正确 | GWT-011-03 |
| US-FM-011 | AC-011-04 | device_room 删除不阻塞 fault_event | GWT-011-04 |
| US-FM-011 | AC-011-05 | 部署停启顺序正确 | GWT-011-05 |
