# 集成测试报告

```
file_header:
  document_id: IT-RPT-v0.6.4-FM-ROOM
  title: 故障管理 — 房间列 + 设备类型过滤重组 — 集成测试报告
  author_agent: sub_agent_test_engineer (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.6.4-FM-ROOM
  created_at: 2026-05-29
  status: DRAFT
  test_file: FreeArkWeb/backend/freearkweb/api/tests/test_fault_mgmt_v064_integration.py
  settings: freearkweb.test_settings (SQLite :memory:)
  gate_prerequisite: 单元测试已通过（UT-RPT-v0.6.4-FM-ROOM，通过率 100%）
```

---

## 执行命令

```bash
cd FreeArkWeb/backend/freearkweb
python manage.py test api.tests.test_fault_mgmt_v064_integration \
    --settings=freearkweb.test_settings --verbosity=2
```

---

## 测试结果汇总

| 测试类 | 用例数 | 通过 | 失败 | 跳过 |
|--------|--------|------|------|------|
| TestMigration0028Backfill | 4 | 4 | 0 | 0 |
| TestFaultConsumerWritePath | 3 | 3 | 0 | 0 |
| TestFaultEventRoomNameFilter | 6 | 6 | 0 | 0 |
| TestKeyRegressionScenarios | 5 | 5 | 0 | 0 |
| **总计** | **18** | **18** | **0** | **0** |

**通过率：100%（>= 90% 阈值）**

---

## 各用例详细结果

### IT-MIG: migration 0028 数据回填

| 用例 ID | 用例名称 | 结果 | 关键验证点 |
|---------|---------|------|-----------|
| IT-MIG-001a | 回填后所有可关联行 room_name 非 NULL | PASS | 10 条 FaultEvent，device_sn 均可关联，回填后 NULL 行 = 0 |
| IT-MIG-001b | 回填后各 device_sn 对应 room_name 正确 | PASS | 22158→客厅，22552→书房，22553→次卧，22554→主卧，22555→儿童房 |
| IT-MIG-001c | 回填后 room_id FK 有效 | PASS | 所有 room_id_id 指向真实 DeviceRoom.id |
| IT-MIG-002 | 孤立 device_sn（无 DeviceNode）回填后仍 NULL | PASS | device_sn='99999' → room_name 仍 NULL，不崩溃 |

**IT-MIG oracle 验证**：migration 0028 的 `str(dn.device_sn)` 字典 key 方案正确处理了 fault_event.device_sn (VARCHAR) 与 device_node.device_sn (INT) 的类型差异，回填路径可靠。

### IT-FC: fault_consumer 写入路径

| 用例 ID | 用例名称 | 结果 | 关键验证点 |
|---------|---------|------|-----------|
| IT-FC-001a | _t1_insert 调用 get_room_for_device 1 次 | PASS | mock 验证调用次数，patch 路径正确 |
| IT-FC-001b | T1 INSERT 写入正确 room_name 和 room_id | PASS | FaultEvent.room_name='主卧'，room_id_id 匹配 |
| IT-FC-002 | get_room_for_device 返回 (None,None) 时 FaultEvent 仍写入 | PASS | FaultEvent 存在，room_name=None |

### IT-VF: views_fault.py room_name 过滤

| 用例 ID | 用例名称 | 结果 | 关键验证点 |
|---------|---------|------|-----------|
| IT-VF-001 | room_name=主卧 仅返回 2 条主卧 FaultEvent | PASS | 过滤后 count=2，所有结果 room_name='主卧' |
| IT-VF-002 | room_name=主卧&room_name=次卧 返回 4 条 | PASS | 多值 OR 过滤，room_names in {'主卧','次卧'} |
| IT-VF-003 | 无效 room_name=卫生间，白名单过滤后返回全量 10 条 | PASS | valid_room_names=[] → 不添加 filter，全量返回 |
| IT-VF-004 | 不传 room_name 返回全量 10 条 | PASS | 无 room_name 参数时不过滤 |
| IT-SER-001 | 响应含 room_name 和 room_id 字段 | PASS | 两字段均在 API 响应中 |
| IT-SER-002 | room_name=NULL 序列化为 null | PASS | JSON null 值，字段存在 |

### IT-REG: 关键回归场景（主线 PM 要求）

| 场景 | 输入 | 期望 | 实际 | 结果 |
|------|------|------|------|------|
| 3-1-602 书房温控面板 | specific_part=3-1-602, sub_type=study_room_panel | 1 条（device_sn=22552） | 1 条，device_sn='22552' | PASS |
| 3-1-602 儿童房温控面板 | specific_part=3-1-602, sub_type=children_room_panel | 1 条（device_sn=22555） | 1 条，device_sn='22555' | PASS |
| 3-1-602 主卧温控面板 | specific_part=3-1-602, sub_type=master_bedroom_panel | 1 条（device_sn=22554） | 1 条，device_sn='22554' | PASS |
| 3-1-602 次卧温控面板 | specific_part=3-1-602, sub_type=secondary_bedroom_panel | 1 条（device_sn=22553） | 1 条，device_sn='22553' | PASS |
| 1-1-16-1601（3 房）书房温控面板 | specific_part=1-1-16-1601, sub_type=study_room_panel | 0 条 | 0 条 | PASS |

**关键回归场景 oracle 验证说明**：
- 上述场景基于 `device_sn → device_node → device_room.ori_room_name` 过滤路径（主路径）。
- fixture 中的 device_sn 对应关系与架构文档附录 F oracle 表完全一致。
- `specific_part=3-1-602` 的 3 段格式匹配通过 `startswith('3-1-') + endswith('-602')` 路径实现（BUG-FM-004 修复，views_fault.py L89-98）。

---

## 发现的问题

无新问题发现。

**code review M-001（serializers_fault.py room_name 注释）**在集成测试中验证为无功能影响——`room_name` 字段在 API 响应中正确出现且值正确，DRF 自动推断路径工作正常。

---

## 门控结论

集成测试通过率 = 100%，>= 90% 阈值。

**集成测试门控：PASS — GROUP_C + GROUP_D（测试阶段）完成**

---

## 附：测试环境说明

| 项目 | 值 |
|------|---|
| 测试 DB | SQLite :memory: |
| Django 版本 | 5.2.x（生产 5.2.7） |
| Python 版本 | 3.12 |
| 测试框架 | Django TestCase + DRF APIClient |
| 时区 | USE_TZ=False（test_settings 继承自 settings.py） |
| 认证 | Token 认证（rest_framework.authtoken） |

**特别说明**：
1. SQLite 不强制外键约束（PRAGMA foreign_keys 默认 OFF），集成测试中 room_id FK 有效性通过显式 `DeviceRoom.objects.filter(id=room_id_id).exists()` 验证（IT-MIG-001c）。
2. 关键回归场景（IT-REG）通过构造 fixture 模拟生产 device_sn ↔ ori_room_name 对应关系，不依赖生产 MySQL 数据。
