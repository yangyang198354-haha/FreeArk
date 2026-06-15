# 自治巡检 Agent（方案 B）— 测试计划与报告（GROUP_D）

```
document_id : TEST-v1.1.0-AIA
title       : 自治巡检 Agent（方案 B）测试计划与本地执行报告
project     : FreeArk v1.1.0
version     : 0.1.0
created_at  : 2026-06-16
status      : 本地通过 / Pi 权威回归待执行
references  :
  - docs/requirements/v1.1.0_autonomous_inspection_agent/requirements_spec.md
  - docs/requirements/v1.1.0_autonomous_inspection_agent/architecture_design.md
  - docs/requirements/v1.1.0_autonomous_inspection_agent/user_stories.md
```

> ⚠️ 本报告的本地执行用系统 Python 3.12 + Django 5.1.15 + SQLite（`--settings=freearkweb.test_settings`）。
> 生产为 Django 5.2 + MySQL 9.4，**权威回归须在 Pi 上经 git worktree 执行**（见 §6）。
> 本地与生产 Django 次版本差异是项目既有技术债 TD-MIGRATION-001 的根因，详见 §5。

---

## 1. 测试范围

| 增量 | 交付物 | 测试套件 | 用例数 |
|------|--------|----------|-------:|
| ① 地基 | migration 0033 + WorkOrder 模型 + 状态字段 + Admin | `api.tests.test_inspection_workorder_v110` | 9 |
| ② 包骨架 | `inspection_agent/` auth / event_poller / work_order / audit | `api.tests.test_inspection_agent_v110` | 21 |
| ③ 决策循环 | `inspection_agent/agent.py` + management command + systemd | `api.tests.test_inspection_agent_loop_v110` | 8 |
| **合计（新增）** | | | **38** |

外加 **回归**：对 migration 0033 改动的两张事件表（`fault_event` / `condensation_warning_event`）相关的现有套件做无回归验证（§4）。

不在本地范围（须 Pi 执行）：方案 A 的 `test_langgraph_phase_a` / `test_langgraph_phase_g`（依赖 langgraph/langchain，本地系统 Python 未装；属方案 A，本期不改其代码）。

---

## 2. 测试策略

- **纯逻辑离线可测**：增量②/③ 的模块对 LLM/orchestrator 的依赖全部**惰性 import + 可注入**（fake orchestrator 的 async `_expert`、fake `write_executor`），故无 langgraph 也能在本地与 CI 跑全量决策逻辑。
- **schema 校验用 PRAGMA table_info**（仿 v0.7.0 UT-MM-001），不用全项目 `makemigrations --check`——后者会被 TD-MIGRATION-001 既有漂移误报（§5）。
- **安全属性以测试钉死**：策略 B 下 `execute_write` 零调用、写提案唯一入口、凭证脱敏，均有对应断言（§3）。
- **子代理零依赖**：本报告所有数字由主控**亲自执行真实命令**得出，未经任何子代理转述（遵守"子代理测试结论必须亲自复核"）。

---

## 3. 用例清单与映射

### 3.1 增量①（`test_inspection_workorder_v110`，9）
| 用例 | 验证点 | 关联需求/AC |
|------|--------|------------|
| UT-SCHEMA-001/002 | fault_event / cw 新增 `inspection_status`+`inspection_started_at` 列 | OD-02 / OD-03 |
| UT-SCHEMA-003 | `inspection_work_order` 表与列完整 | REQ-FUNC-008 |
| UT-DEFAULT-001/002 | 新事件默认 `PENDING`、`started_at=None` | OD-03 |
| UT-WO-001 | WorkOrder 创建 + `__str__` | REQ-FUNC-008 |
| UT-WO-002 | 同源活跃工单第二条 → IntegrityError（条件唯一约束） | 防重复建单 §7.3 |
| UT-WO-003 | RESOLVED 后可再建活跃工单（非活跃不计入约束） | §7.3 |
| UT-WO-004 | 不同来源事件活跃工单互不冲突 | §7.3 |

### 3.2 增量②（`test_inspection_agent_v110`，21）
| 分组 | 用例 | 验证点 | 关联 |
|------|------|--------|------|
| auth（8） | UT-AUTH-001..008 | 默认/显式/非法策略均退策略 B 拦截；策略 A 白名单 default-deny（不在表/越界/非数值/无规则/非法 JSON 全拒，区间内放行） | OD-01 / REQ-FUNC-005 |
| event_poller（5） | UT-POLL-001..005 | 取 PENDING 升序、原子认领 IN_PROGRESS、已认领不重出、inactive/DONE 排除、batch 截断、`reset_in_progress` 重建 | OD-02 / REQ-NFUNC-002 |
| work_order（5） | UT-WO-101..105 | ticket_id 格式与日递增、按事件推导建单、CW 用 warning_type 作 severity、活跃去重、RESOLVED 后可再建 | §7 |
| audit（3） | UT-AUDIT-001..003 | JSON 结构与事件类型映射、凭证键名脱敏（明文不落盘） | §9 / REQ-NFUNC-003 |

### 3.3 增量③（`test_inspection_agent_loop_v110`，8）
| 用例 | 验证点 | 关联 |
|------|--------|------|
| UT-AGENT-001 | 结论路径建工单（recommended_action=结论、diagnosis=委托摘要）、置 DONE | REQ-FUNC-006/008 |
| UT-AGENT-002 | 写提案 + 策略 B → 拦截建单、**`execute_write` 零调用**、审计 `WRITE_BLOCKED_POLICY_B` | OD-01 / REQ-FUNC-005 |
| UT-AGENT-003 | 写提案 + 策略 A 区间内 → 调 `execute_write`(operator=`inspection-agent`)、不建单、置 DONE、审计 `WRITE_EXECUTED` | 策略 A 接缝 |
| UT-AGENT-004 | 事件已恢复(inactive) → SKIPPED、不建单、不走决策 | §4.3 |
| UT-AGENT-005 | 决策超时/异常 → 兜底建单、置 DONE（不丢单/不崩溃） | REQ-NFUNC-002 / §5.2 |
| UT-AGENT-006 | `run_once` 串行处置轮询取到的多条事件 | §10.1 |
| UT-AGENT-007 | 工单/状态持久化失败 → 事件重置 PENDING 待重试（不置 DONE） | §5.2 |
| UT-AGENT-008 | 同源事件重复处置 → 命中活跃工单去重，不重复建单 | §7.3 |

---

## 4. 本地执行结果

### 4.1 增量套件（38）+ 全链 migration
```
python manage.py test \
  api.tests.test_inspection_agent_loop_v110 \
  api.tests.test_inspection_agent_v110 \
  api.tests.test_inspection_workorder_v110 \
  --settings=freearkweb.test_settings
→ Ran 38 tests ... OK
  （migration 0001→0033 全链在 SQLite apply 成功；System check 0 issue）
```

### 4.2 回归（migration 0033 改动的事件表相关现有套件）
```
python manage.py test \
  <上述 3 个 inspection 套件> \
  api.tests.test_fault_mgmt_v064_unit \
  api.tests.test_fault_mgmt_v064_integration \
  api.tests.test_device_list_fault_filter \
  api.tests.test_condensation_v070_unit \
  api.tests.test_condensation_v070_integration \
  api.tests.test_condensation_v070_e2e \
  --settings=freearkweb.test_settings
→ Ran 163 tests ... OK
```
结论：向 `fault_event` / `condensation_warning_event` 追加的两个字段（migration 0033，非破坏）**对读取这两张表的现有故障/结露功能零回归**。

### 4.3 已知既有失败（非本期引入，不计入门控）
- `api.tests.test_fault_event_serializer_v061`：3 个 `'新风机' != '新风'` 断言失败，**main 上既有**（前序已用 `git stash` 复核确认与本期改动正交）。本期未触碰该序列化逻辑，故不纳入回归集；待项目单独处理。

---

## 5. TD-MIGRATION-001 说明（为何不用全项目 --check）

本地 Django 5.1.15 ≠ 生产 5.2，全项目 `makemigrations --check` 会对若干**与本期无关**的既有模型报漂移（索引重命名 + id `AutoField→BigAutoField`）。这是项目已立项的技术债 TD-MIGRATION-001，非本增量引入。故：
- 本期 schema 校验改用 `PRAGMA table_info` 精确核验本增量涉及的表/列与 migration 0033 一致；
- 权威的 `makemigrations api --check` 留到 Pi（Django 5.2）执行（§6）。

---

## 6. Pi 权威回归待办（部署前必做，门控）

在 Pi 上用 git worktree 隔离（不碰生产工作树）：
```bash
git worktree add /tmp/fa-wt feat/aia-b-increment1
cd /tmp/fa-wt/FreeArkWeb/backend/freearkweb
# 1) 权威迁移一致性（Django 5.2）
/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py makemigrations api --check --dry-run
# 2) 增量 + 回归套件（SQLite test_settings）
/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py test \
  api.tests.test_inspection_agent_loop_v110 api.tests.test_inspection_agent_v110 \
  api.tests.test_inspection_workorder_v110 \
  api.tests.test_fault_mgmt_v064_unit api.tests.test_fault_mgmt_v064_integration \
  api.tests.test_condensation_v070_unit api.tests.test_condensation_v070_integration \
  api.tests.test_condensation_v070_e2e \
  --settings=freearkweb.test_settings
# 3) 方案 A 未回归（langgraph 已装于 Pi）
/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py test \
  api.tests.test_langgraph_phase_a api.tests.test_langgraph_phase_g \
  --settings=freearkweb.test_settings
cd - && git worktree remove --force /tmp/fa-wt
```

通过判据：①`makemigrations api --check` 对 api app **无新增待生成迁移**（若仅报 TD-MIGRATION-001 既有漂移则记录、不阻断；若报 0033 相关新差异则阻断）；②增量+回归套件全绿；③方案 A 套件全绿。

---

## 7. 门控结论

- 本地：**38/38 增量 + 163/163 回归集 通过**，零本期引入的失败。
- 待办：§6 的 Pi 权威回归（迁移一致性 + MySQL 行为 + 方案 A 无回归）须在部署前执行并记录。
- 风险：策略 A（PolicyA）为未启用接缝，其与真实写工具 schema 的映射在启用前须按 OQ-05 复核（本期不部署策略 A，风险已隔离）。
