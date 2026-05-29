# 测试计划文档

```
file_header:
  document_id: TEST-PLAN-v0.6.4-FM-ROOM
  title: 故障管理 — 房间列 + 设备类型过滤重组 — 测试计划
  author_agent: sub_agent_test_engineer (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.6.4-FM-ROOM
  created_at: 2026-05-29
  status: DRAFT
  references:
    - docs/requirements/v0.6.4_fault_mgmt_room_column/user_stories.md
    - docs/requirements/v0.6.4_fault_mgmt_room_column/requirements_spec.md
    - docs/architecture/architecture_design_v0.6.4_fault_mgmt_room_column.md (附录 F oracle)
    - docs/implementation/v0.6.4_fault_mgmt_room_column/implementation_plan.md
```

---

## 1. 测试范围

本测试计划覆盖 v0.6.4-FM-ROOM 的所有变更模块。测试运行顺序：**单元测试 → 集成测试（串行门控）**。

**明确排除**：
- 生产部署（devops-engineer 范围）
- E2E 浏览器自动化（Vue 组件测试在集成测试中以 API 级别替代）
- seed_device_config.py 相关（非 v0.6.4 范围）

**测试 DB**：SQLite :memory:（由 `freearkweb.test_settings` 配置），禁止连接生产 MySQL。

---

## 2. 测试文件

| 测试文件 | 测试类型 | 模块 |
|---------|---------|------|
| `api/tests/test_fault_mgmt_v064_unit.py` | 单元测试 | constants / room_lookup / state_machine / serializer |
| `api/tests/test_fault_mgmt_v064_integration.py` | 集成测试 | views_fault / migration 0028 / fault_consumer 写入路径 |

---

## 3. 单元测试用例

### 3.1 constants.py 结构验证（UT-C-001 ~ 005）

| ID | 用例描述 | 期望结果 |
|----|---------|---------|
| UT-C-001 | SUB_TYPE_ROOM_FILTER 包含所有 9 个新 key | 断言 5 个温控类 + 4 个非温控类 key 存在 |
| UT-C-002 | 旧 thermostat key 不在 SUB_TYPE_ROOM_FILTER 中 | `living_room_thermostat` 等不存在 |
| UT-C-003 | SUB_TYPE_LABELS keys 与 SUB_TYPE_ROOM_FILTER keys 相等 | 两个字典 key 集合完全一致 |
| UT-C-004 | VALID_ROOM_NAMES 包含且仅包含 5 个房间名 | frozenset == {'客厅','主卧','次卧','儿童房','书房'} |
| UT-C-005 | study_room_panel 的 room_keywords 仅含 '书房' | SUB_TYPE_ROOM_FILTER['study_room_panel'][1] == ['书房'] |

### 3.2 room_lookup.py 单元测试（UT-RL-001 ~ 004）

| ID | 用例描述 | 期望结果 |
|----|---------|---------|
| UT-RL-001 | 正常 device_sn，DeviceNode 存在且有 room | 返回 (ori_room_name, room_id) |
| UT-RL-002 | device_sn 在 DeviceNode 不存在 | 返回 (None, None)，不抛异常 |
| UT-RL-003 | device_sn 为非整数字符串（如 'abc'） | 返回 (None, None)，不抛异常 |
| UT-RL-004 | DB 查询抛出异常（mock） | 返回 (None, None)，记录 ERROR 日志，不上抛 |

### 3.3 state_machine._t1_insert 单元测试（UT-SM-001 ~ 002）

| ID | 用例描述 | 期望结果 |
|----|---------|---------|
| UT-SM-001 | T1 INSERT：mock DeviceNode 返回有效 room，验证 FaultEvent 写入 room_name 正确 | FaultEvent.room_name == ori_room_name，room_id_id == room.id |
| UT-SM-002 | T1 INSERT：mock DeviceNode 返回无结果（room_lookup 返回 (None, None)），FaultEvent 仍正常写入 | FaultEvent.room_name is None，不崩溃 |

### 3.4 oracle 反推表验证（UT-OR-001，主线要求）

| ID | 用例描述 | 期望结果 |
|----|---------|---------|
| UT-OR-001 | 3-1-602（4 房）error_code 反推表：5 个 error_code 与 device_sn / ori_room_name 的对应关系 | error_679↔客厅，error_709↔书房，error_739↔次卧，error_769↔主卧，error_799↔儿童房（oracle 来自架构文档附录 F） |

---

## 4. 集成测试用例

### 4.1 migration 0028 回填测试（IT-MIG-001 ~ 002）

| ID | 用例描述 | 期望结果 |
|----|---------|---------|
| IT-MIG-001 | 构造 10 行 FaultEvent（含可关联 DeviceNode 的 device_sn），执行 migration 0028，验证 room_name 填充率 = 100% | 所有可关联行 room_name 非 NULL，room_id 外键有效 |
| IT-MIG-002 | 无关联 DeviceNode 的行（孤立 device_sn），迁移后 room_name 仍为 NULL | 不崩溃，孤立行 room_name = NULL |

### 4.2 fault_consumer 写入路径集成测试（IT-FC-001 ~ 002）

| ID | 用例描述 | 期望结果 |
|----|---------|---------|
| IT-FC-001 | mock DeviceNode 查询，验证 _t1_insert 调用 get_room_for_device 一次并将结果存入 FaultEvent | get_room_for_device 被调用 1 次，FaultEvent.room_name 正确 |
| IT-FC-002 | DeviceNode 查询失败（mock Exception），FaultEvent 仍写入，room_name=None | FaultEvent.id 存在，room_name is None |

### 4.3 views_fault.py room_name 过滤集成测试（IT-VF-001 ~ 006）

| ID | 用例描述 | 期望结果 |
|----|---------|---------|
| IT-VF-001 | GET /api/devices/fault-events/?room_name=主卧，有 2 条主卧、1 条次卧 | 返回 2 条（仅主卧） |
| IT-VF-002 | GET /api/devices/fault-events/?room_name=主卧&room_name=次卧（多值） | 返回 3 条（主卧+次卧合集） |
| IT-VF-003 | 无效 room_name 值（如 room_name=卫生间）白名单拒绝 | 返回 0 条（过滤后无合法值，不添加 filter 条件，返回全量） |
| IT-VF-004 | room_name 参数不传，不过滤 | 返回全部记录 |
| IT-VF-005 | 关键场景：3-1-602 + sub_type=study_room_panel → 期望 1 条（书房） | 1 条来自 device_sn=22552（ori_room_name='书房'） |
| IT-VF-006 | 关键场景：1-1-16-1601（3 房）+ sub_type=study_room_panel → 期望 0 条 | 3 房无书房设备，返回 0 条（oracle：arch 附录 F） |

### 4.4 序列化器 room_name/room_id 字段测试（IT-SER-001 ~ 002）

| ID | 用例描述 | 期望结果 |
|----|---------|---------|
| IT-SER-001 | FaultEvent 有 room_name='主卧'，序列化后响应含 room_name='主卧' | 字段存在且值正确 |
| IT-SER-002 | FaultEvent room_name=NULL，序列化后 room_name=null（JSON） | 字段存在，值为 null |

---

## 5. 主线要求的关键回归场景（来自主线 PM 指令）

| 场景 | 输入 | 期望输出 |
|------|------|---------|
| 3-1-602（4 房）点"书房温控面板" | specific_part=3-1-602, sub_type=study_room_panel | 1 条（device_sn=22552，ori_room_name='书房'） |
| 3-1-602 点"儿童房温控面板" | specific_part=3-1-602, sub_type=children_room_panel | 1 条（device_sn=22555，ori_room_name='儿童房'，来自 fourth_children_room_*） |
| 3-1-602 点"主卧温控面板" | specific_part=3-1-602, sub_type=master_bedroom_panel | 1 条（device_sn=22554，ori_room_name='主卧'，来自 children_room_*） |
| 3-1-602 点"次卧温控面板" | specific_part=3-1-602, sub_type=secondary_bedroom_panel | 1 条（device_sn=22553，ori_room_name='次卧'，来自 bedroom_*） |
| 1-1-16-1601（3 房）点"书房温控面板" | specific_part=1-1-16-1601, sub_type=study_room_panel | 0 条（3 房无书房设备） |

**注意**：上述场景为 oracle 驱动的集成测试（基于架构文档附录 F），在 SQLite 测试 DB 中通过构造 fixture 模拟（不连接生产 DB）。

---

## 6. 串行门控策略

1. 单元测试全部通过（pass rate = 100%，覆盖率 >= 80%）后，执行集成测试。
2. 集成测试通过率 >= 90%（允许最多 1 个低优先级集成场景暂时跳过，需说明原因）。
3. 任何测试失败立即停止，回报 PM，不尝试自修复绕过。

---

## 7. 测试执行命令

```bash
# 工作目录：FreeArkWeb/backend/freearkweb/
# 单元测试
python manage.py test api.tests.test_fault_mgmt_v064_unit \
    --settings=freearkweb.test_settings --verbosity=2

# 集成测试（单元通过后执行）
python manage.py test api.tests.test_fault_mgmt_v064_integration \
    --settings=freearkweb.test_settings --verbosity=2

# 全量（含回归）
python manage.py test api.tests.test_fault_mgmt_v064_unit \
    api.tests.test_fault_mgmt_v064_integration \
    --settings=freearkweb.test_settings --verbosity=2
```
