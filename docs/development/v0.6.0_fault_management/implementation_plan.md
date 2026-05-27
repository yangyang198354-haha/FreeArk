# 实现计划

```
file_header:
  document_id: DEV-PLAN-v0.6.0-FM
  title: MQTT 故障事件持久化 + 故障管理页面 — 实现计划
  author_agent: sub_agent_software_developer (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.6.0-fault-management
  created_at: 2026-05-27
  status: DRAFT
  references:
    - docs/architecture/architecture_design_v0.6.0_fault_management.md
    - docs/architecture/module_design_v0.6.0_fault_management.md
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-27 | 初始实现计划，覆盖全部 16 个模块 |

---

## 1. 实现顺序

按依赖顺序，从底层向上实现：

1. **MOD-BE-FM-01** `fault_consumer/constants.py` — 无依赖，全常量
2. **MOD-BE-FM-02** `fault_consumer/fault_classifier.py` — 依赖 constants + fault_utils
3. **MOD-BE-FM-03** `fault_consumer/state_machine.py` — 依赖 FaultEvent model（先写 model）
4. **MOD-BE-FM-06** `models.py` 追加 FaultEvent — 依赖无
5. **MOD-BE-FM-07** `migrations/0026_add_fault_event.py` — 依赖 models
6. **MOD-BE-FM-04** `management/commands/fault_consumer.py` — 依赖 classifier + state_machine
7. **MOD-BE-FM-05** `management/commands/fault_cleanup.py` — 依赖 FaultEvent model
8. **MOD-BE-FM-09** `serializers_fault.py` — 依赖 FaultEvent model
9. **MOD-BE-FM-08** `views_fault.py` — 依赖 serializers + constants
10. **MOD-BE-FM-10** `urls.py` 追加路由 — 依赖 views_fault
11. **MOD-FE-FM-01** `FaultManagementView.vue` — 独立前端组件
12. **MOD-FE-FM-02** `router/index.js` 追加路由 — 依赖 FaultManagementView
13. **MOD-FE-FM-03** `DeviceManagementDeviceListView.vue` 追加导航按钮
14. **MOD-SYS-FM-01** `deployment/systemd/freeark-fault-consumer.service`
15. **MOD-SYS-FM-02** `deployment/systemd/freeark-fault-cleanup.service`
16. **MOD-SYS-FM-03** `deployment/systemd/freeark-fault-cleanup.timer`

---

## 2. 关键实现决策

### 2.1 fault_consumer 包结构

```
FreeArkWeb/backend/freearkweb/api/fault_consumer/
    __init__.py          (空，标记包)
    constants.py         MOD-BE-FM-01
    fault_classifier.py  MOD-BE-FM-02
    state_machine.py     MOD-BE-FM-03
```

Management Command 路径（ADR-FM-01 决策 B）：
```
FreeArkWeb/backend/freearkweb/api/management/commands/fault_consumer.py  MOD-BE-FM-04
FreeArkWeb/backend/freearkweb/api/management/commands/fault_cleanup.py   MOD-BE-FM-05
```

### 2.2 Migration 编号

最新 migration 为 0025，因此新文件为 `0026_add_fault_event.py`。

### 2.3 systemd 文件路径

存入仓库目录 `deployment/systemd/`，生产部署时由运维人员手动 cp 至 `/etc/systemd/system/`。

### 2.4 fresh_air_fault_bit_* 在 sub_type API 过滤中的处理

`views_fault.py` 的 `sub_type=fresh_air_unit` 过滤中，除 `fault_code__in` 精确匹配外，
还需 `Q(fault_code__startswith='fresh_air_fault_bit_')` 联合 OR 处理，
确保所有新风机相关故障码都能被过滤到。

### 2.5 fault_message 生成策略

`fault_message` 字段记录可读描述，由 `fault_classifier.get_fault_message(param_name)` 生成。
实现时基于 `param_name` 做简单格式化（如将下划线替换为空格，首字母大写），
不依赖外部字典（AB-004 待决）。

---

## 3. 文件清单（预计）

| 文件路径 | 操作 | 模块 ID |
|---------|------|---------|
| `api/fault_consumer/__init__.py` | 新增 | — |
| `api/fault_consumer/constants.py` | 新增 | MOD-BE-FM-01 |
| `api/fault_consumer/fault_classifier.py` | 新增 | MOD-BE-FM-02 |
| `api/fault_consumer/state_machine.py` | 新增 | MOD-BE-FM-03 |
| `api/management/commands/fault_consumer.py` | 新增 | MOD-BE-FM-04 |
| `api/management/commands/fault_cleanup.py` | 新增 | MOD-BE-FM-05 |
| `api/models.py` | 修改（追加末尾） | MOD-BE-FM-06 |
| `api/migrations/0026_add_fault_event.py` | 新增 | MOD-BE-FM-07 |
| `api/serializers_fault.py` | 新增 | MOD-BE-FM-09 |
| `api/views_fault.py` | 新增 | MOD-BE-FM-08 |
| `api/urls.py` | 修改（追加 2 条路由） | MOD-BE-FM-10 |
| `frontend/src/views/FaultManagementView.vue` | 新增 | MOD-FE-FM-01 |
| `frontend/src/router/index.js` | 修改（追加 1 条路由） | MOD-FE-FM-02 |
| `frontend/src/views/DeviceManagementDeviceListView.vue` | 修改（追加按钮） | MOD-FE-FM-03 |
| `deployment/systemd/freeark-fault-consumer.service` | 新增 | MOD-SYS-FM-01 |
| `deployment/systemd/freeark-fault-cleanup.service` | 新增 | MOD-SYS-FM-02 |
| `deployment/systemd/freeark-fault-cleanup.timer` | 新增 | MOD-SYS-FM-03 |
