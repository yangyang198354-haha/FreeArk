# 实现计划

```
file_header:
  document_id: IMPL-v0.7.0-CW
  title: 结露预警管理页面 — 实现计划
  author_agent: sub_agent_software_developer (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.7.0-condensation-warning
  created_at: 2026-05-30
  status: APPROVED
  references:
    - docs/architecture/module_design_v0.7.0_condensation_warning.md
    - docs/architecture/architecture_design_v0.7.0_condensation_warning.md
```

---

## 实现文件清单

| # | 文件路径 | 模块 ID | 类型 | 状态 |
|---|---------|---------|------|------|
| 1 | `FreeArkWeb/backend/freearkweb/api/condensation_consumer/__init__.py` | MOD-BE-CW-01 | 新建 | DONE |
| 2 | `FreeArkWeb/backend/freearkweb/api/condensation_consumer/state_machine.py` | MOD-BE-CW-02 | 新建 | DONE |
| 3 | `FreeArkWeb/backend/freearkweb/api/management/commands/condensation_consumer.py` | MOD-BE-CW-03 | 新建 | DONE |
| 4 | `FreeArkWeb/backend/freearkweb/api/management/commands/condensation_cleanup.py` | MOD-BE-CW-04 | 新建 | DONE |
| 5 | `FreeArkWeb/backend/freearkweb/api/models.py` | MOD-BE-CW-05 | 追加 | DONE |
| 6 | `FreeArkWeb/backend/freearkweb/api/views_condensation.py` | MOD-BE-CW-06 | 新建 | DONE |
| 7 | `FreeArkWeb/backend/freearkweb/api/serializers_condensation.py` | MOD-BE-CW-07 | 新建 | DONE |
| 8 | `FreeArkWeb/backend/freearkweb/api/migrations/0029_add_condensation_warning_event.py` | DB-CW-01 | 新建 | DONE |
| 9 | `FreeArkWeb/backend/freearkweb/api/urls.py` | 追加路由 | 修改 | DONE |
| 10 | `FreeArkWeb/frontend/src/views/CondensationWarningView.vue` | MOD-FE-CW-01 | 新建 | DONE |
| 11 | `FreeArkWeb/frontend/src/router/index.js` | MOD-FE-CW-02 | 修改 | DONE |
| 12 | `FreeArkWeb/frontend/src/components/Layout.vue` | MOD-FE-CW-03 | 修改 | DONE |
| 13 | `deployment/systemd/freeark-condensation-consumer.service` | MOD-INFRA-CW-01 | 新建 | DONE |
| 14 | `deployment/systemd/freeark-condensation-cleanup.service` | MOD-INFRA-CW-02 | 新建 | DONE |
| 15 | `deployment/systemd/freeark-condensation-cleanup.timer` | MOD-INFRA-CW-03 | 新建 | DONE |

---

## RISK-CW-ARCH-01 闭环说明

**OD-CW-ARCH-01 已确认（来自用户抓包核实）**：

MQTT items[] 中 system_switch 的 attrValue 实测为字符串 **"on"/"off"**（非 "0"/"1"）。
例：`{"attrTag":"system_switch","attrValue":"off"}`。

**两源格式差异及分别处理路径**：

| 来源 | 格式 | 处理方式 | 实现位置 |
|------|------|---------|---------|
| MQTT 直取（260001 等水力模块同报文含 system_switch） | 字符串 "on"/"off" | `_normalize_system_switch_from_mqtt()` 做 lower() 容错 | `condensation_consumer.py` |
| PLCLatestData 兜底（120003 温控面板等无 system_switch 的设备） | BigIntegerField 整数（0=关/非0=开） | `return 'on' if row.value != 0 else 'off'` | `state_machine._get_system_switch_for_specific_part()` |
| 均无 | — | 传 None → state_machine 内部返回 'unknown' | 两处均处理 |

---

## 关键实现决策

1. **state_machine.py key 设计**：二元组 `(specific_part, device_sn)`，无 fault_code 维度（ADR-CW-03）。
2. **T1 system_switch 优先级**：`_t1_insert` 接收 caller 已规范化的 system_switch（可 None），None 时内部调 `_get_system_switch_for_specific_part` — 确保两源处理逻辑各自封装。
3. **is_screen_online 注入**：`_inject_screen_online` 在分页后对当前页所有 specific_part 执行一次 IN 查询，结果注入 dict（非存储到 DB），符合 ADR-CW-05。
4. **migration 0029**：手写迁移文件（不依赖 `makemigrations`），依赖 0028，包含 UniqueConstraint + 2 个 Index，与 Model 定义一致。
5. **cleanup.service Restart=on-failure**：oneshot 类型服务加 Restart=on-failure，符合部署要求。
