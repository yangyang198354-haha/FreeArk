# 代码评审报告

```
file_header:
  document_id: DEV-CR-v0.6.0-FM
  title: MQTT 故障事件持久化 + 故障管理页面 — 代码评审报告
  author_agent: sub_agent_software_developer (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.6.0-fault-management
  created_at: 2026-05-27
  status: DRAFT
  references:
    - docs/architecture/architecture_design_v0.6.0_fault_management.md
    - docs/architecture/module_design_v0.6.0_fault_management.md
    - docs/development/v0.6.0_fault_management/implementation_plan.md
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-27 | 初始代码评审，16 个模块全覆盖 |

---

## 1. 评审摘要

| 维度 | 评审结论 | CRITICAL | MAJOR | MINOR |
|------|---------|---------|-------|-------|
| 安全（SQL 注入/XSS） | PASS | 0 | 0 | 1 |
| 性能（N+1/索引使用） | PASS | 0 | 0 | 2 |
| 可观测性（日志） | PASS | 0 | 0 | 1 |
| 架构一致性 | PASS | 0 | 0 | 1 |
| **总计** | **PASS** | **0** | **0** | **5** |

无 CRITICAL finding，无 MAJOR finding。门控结论：**PASS_WITH_CONDITIONS**（5 个 MINOR 条件项，均为非阻塞改进建议）。

---

## 2. 安全评审

### 2.1 SQL 注入防护

| 检查项 | 文件 | 结论 | 说明 |
|-------|------|------|------|
| `fault_event_list` 查询参数 | `views_fault.py` | PASS | 所有过滤均使用 Django ORM（icontains、`__in`、`__gte`、`__lte`），无原生 SQL 拼接 |
| `specific_part` icontains | `views_fault.py:L58` | PASS | Django ORM 自动对特殊字符（%, _）转义，不产生注入点 |
| `fault_type__in` 白名单校验 | `views_fault.py:L65-68` | PASS | 过滤前与 `FAULT_TYPE_LABELS` 做白名单比对，过滤非法值 |
| `sub_type` 白名单校验 | `views_fault.py:L72-87` | PASS | 过滤前与 `SUB_TYPE_LABELS` 做白名单比对，忽略非法值 |
| `is_active` 参数处理 | `views_fault.py:L90-96` | PASS | 仅接受 "true"/"false" 字符串，其他值静默忽略 |
| `first_seen_after/before` | `views_fault.py:L99-112` | MINOR-1 | 时间格式未做严格校验；Django ORM 会抛出 ValueError，已有 try/except 兜底，但错误提示不够明确（见 MINOR-1）|
| state_machine DB 操作 | `state_machine.py` | PASS | 所有 DB 写入使用 ORM（`create`、`filter().update()`），无原生 SQL |

**MINOR-1（安全/输入校验）**：`views_fault.py` 中 `first_seen_after`/`first_seen_before` 参数的时间字符串未做格式预校验，仅依赖 Django ORM 解析失败时的 try/except。建议增加 `datetime.fromisoformat()` 预校验，并在格式错误时返回 HTTP 400（而非静默使用默认值），提升 API 健壮性。

### 2.2 XSS 防护

| 检查项 | 文件 | 结论 | 说明 |
|-------|------|------|------|
| API 响应内容 | `serializers_fault.py` | PASS | DRF 序列化器输出 JSON，无 HTML 渲染，无 XSS 风险 |
| fault_message 字段 | `fault_classifier.py:get_fault_message()` | PASS | 仅做字符串格式化（replace + capitalize），无 HTML 写入 |
| 前端 FaultManagementView.vue | `FaultManagementView.vue` | PASS | 所有数据通过 `:prop` 绑定或插值，不使用 `v-html`，无 XSS 风险 |
| `specific_part` LIKE 模糊搜索 | `FaultManagementView.vue` | PASS | 传值仅为查询参数，服务端已转义，前端无自渲染 |

### 2.3 密码/凭证安全

| 检查项 | 文件 | 结论 | 说明 |
|-------|------|------|------|
| broker 密码日志 | `fault_consumer.py:L104-108` | PASS | 日志仅记录 protocol/host/port，不输出 password 字段 |
| 配置文件路径 | `fault_consumer.py:_HBC_CONFIG_PATH` | PASS | 与心跳服务使用相同路径策略，配置文件不进 git（.gitignore 覆盖） |

---

## 3. 性能评审

### 3.1 N+1 查询

| 检查项 | 文件 | 结论 | 说明 |
|-------|------|------|------|
| `fault_event_list` 分页查询 | `views_fault.py` | PASS | 单条 SQL 查询（count + page），无循环 DB 调用，无 N+1 |
| `fault_event_categories` | `views_fault.py` | PASS | 无 DB 查询，纯常量返回，O(1) |
| `fault_consumer` on_message | `fault_consumer.py` + `state_machine.py` | PASS | T2 路径（故障持续）无 DB 操作；T1/T3 各执行 1 条 SQL，符合 ADR-FM-03 设计 |
| `rebuild_from_db` | `state_machine.py:L51-64` | PASS | 单条 SELECT（LIMIT 10000），仅启动时执行一次 |
| `_MacCache._refresh` | `fault_consumer.py:L108-123` | PASS | 全量加载一次，300s 内不再查 DB；与心跳服务一致 |

### 3.2 索引使用

| 查询场景 | 预期使用索引 | 说明 |
|---------|------------|------|
| API 默认查询（最近 7 天） | `idx_fault_time_active (first_seen_at, is_active)` | 覆盖 `first_seen_at__gte + order_by(-first_seen_at)` |
| 按房号 + 活跃状态过滤 | `idx_fault_sp_active (specific_part, is_active)` | `icontains` 降级为全表扫，见 MINOR-2 |
| `rebuild_from_db` WHERE is_active=True | 无专用索引；MySQL 通常不用低 cardinality bool 单列索引 | 可由 `idx_fault_sp_active` 最左前缀辅助 |
| `fault_cleanup` WHERE first_seen_at < cutoff AND is_active=False | `idx_fault_time_active` | 符合最左前缀 |

**MINOR-2（性能）**：`specific_part` 参数使用 `icontains`（等价 `LIKE '%value%'`），属于前缀不固定的模糊查询，MySQL 无法使用索引扫描，将退化为全表扫。当 fault_event 表增长到百万级别时可能产生性能问题。建议后续版本（AB-009）考虑改为前缀匹配（`istartswith`）或增加全文检索，本期 fault_event 表规模可控（月增 < 1 万行），可接受。

**MINOR-3（性能）**：`fault_event_list` 视图在多个过滤条件组合时，QuerySet 链式 filter 会生成包含多个 AND/OR 子句的 SQL。对于 `sub_type=fresh_air_unit` 场景，同时生成 `fault_code IN (...)` 和 `fault_code__startswith='fresh_air_fault_bit_'` 两个条件，EXPLAIN 需验证索引命中。实现正确但建议在生产上线后执行一次 EXPLAIN 确认。

### 3.3 内存占用

| 场景 | 估算 | 结论 |
|------|------|------|
| 典型 45,000 条活跃故障 | ~10 MB | PASS（ADR-FM-08）|
| 突发 10x 450,000 条 | ~100 MB | PASS（低于 256 MB 触发阈值）|
| MacCache | ~15 KB（100 户 × 50 字节/条）| PASS |

---

## 4. 可观测性评审

| 检查项 | 文件 | 结论 | 说明 |
|-------|------|------|------|
| 状态机 T1 INSERT | `state_machine.py:L117` | PASS | `DEBUG` 级别记录 event_id + key |
| 状态机 T2（仅内存） | `state_machine.py` | PASS | 无日志（设计决策，T2 为高频操作，日志会淹没 journal）|
| 状态机 T3 RECOVER | `state_machine.py:L163` | PASS | `DEBUG` 级别记录 event_id + key |
| T1 IntegrityError 兜底 | `state_machine.py:L106` | PASS | `WARNING` 级别记录 |
| OperationalError | `state_machine.py:L109,L167` | PASS | `ERROR` 级别记录 |
| fault_consumer 启动日志 | `fault_consumer.py:L104-111,L120` | PASS | 记录 protocol/host/port/topic + 状态机加载条数 |
| on_message 异常兜底 | `fault_consumer.py:L156` | PASS | `exception` 级别（含 traceback）|
| MacCache 刷新 | `fault_consumer.py:L120` | PASS | `INFO` 级别记录映射数量 |
| fault_cleanup 执行日志 | `fault_cleanup.py:L95-99` | PASS | 每批记录批次号、删除行数、累计行数 |
| fault_cleanup 完成日志 | `fault_cleanup.py:L103` | PASS | 记录总删除行数和批次数 |
| API 请求日志 | `views_fault.py` | MINOR-4 | 无请求级别日志（如 specific_part 参数值）；Django access log 可覆盖，但无法精确定位 ORM 查询；建议增加 DEBUG 级别的查询参数日志 |

**MINOR-4（可观测性）**：`views_fault.py` 未记录请求参数的 DEBUG 日志。当生产出现慢查询时，无法从 journalctl 还原请求上下文（需结合 Nginx access log + Django ORM SQL log）。建议增加 `logger.debug('fault_event_list params: %s', dict(request.query_params))`，便于故障排查。

---

## 5. 架构一致性评审

| 检查项 | 结论 | 说明 |
|-------|------|------|
| 不修改 fault_utils.py | PASS | fault_classifier.py 仅通过 import 读取 FAULT_PARAM_NAMES，未修改 fault_utils |
| 不修改 screen_heartbeat_consumer.py | PASS | fault_consumer 使用独立 MacCache 实例，不共享代码，不修改心跳服务 |
| 不修改 mqtt_handlers.py | PASS | AB-002 钩子（invalidate_fault_count_cache）本期未调用 |
| 不修改现有 API 视图 | PASS | 新接口在 views_fault.py，urls.py 仅追加路由 |
| 最小侵入前端 | PASS | DeviceManagementDeviceListView.vue 仅追加 1 个导航按钮，不改动现有逻辑 |
| SQLite 兼容性 | PASS | migration 0026 使用 UniqueConstraint + Index，SQLite 和 MySQL 均支持 |
| paho-mqtt 1.x API | PASS | 使用 `mqtt.Client(client_id=..., transport=...)` + 1.x 回调签名（无 CallbackAPIVersion）|
| systemd 服务路径 | MINOR-5 | 仓库中 systemd 文件的 ExecStart venv 路径（`/home/yangyang/Freeark/venv/bin/python`）为推断值，需部署前确认生产服务器实际 venv 路径 |

**MINOR-5（运维）**：`deployment/systemd/` 中 `ExecStart` 使用的 venv 路径为 `/home/yangyang/Freeark/venv/bin/python`，基于现有部署文档推断。生产部署前须在服务器上执行 `which python` 或 `ls /home/yangyang/Freeark/venv/bin/python` 确认实际路径，必要时调整 service 文件。

---

## 6. 技术债清单

| 编号 | 描述 | 严重级别 | 来源 |
|------|------|---------|------|
| TD-FM-01 | `first_seen_after`/`first_seen_before` 参数缺少 ISO8601 格式预校验，错误时静默使用默认值 | LOW | MINOR-1 |
| TD-FM-02 | `specific_part` icontains 在大表上退化为全表扫，百万级别后需优化 | LOW | MINOR-2 |
| TD-FM-03 | `fault_event_list` 缺少 DEBUG 级别请求参数日志 | INFO | MINOR-4 |
| TD-FM-04 | systemd ExecStart venv 路径需生产部署前人工确认 | DEPLOY | MINOR-5 |
| TD-FM-05 | `get_fault_message()` 使用简单格式化，AB-004 实现后替换为中文字典 | LOW | AB-004 |
| TD-FM-06 | T2 路径（故障持续）无 DB 操作无日志，高频场景下无法追踪具体报文 | INFO | 设计决策 |

---

## 7. 测试覆盖率估算

基于实现代码，按架构文档 §8 测试策略预估：

| 测试类型 | 目标 | 预估覆盖文件 |
|---------|------|------------|
| 单元测试 | `is_fault_candidate`、`is_fault_active`、`get_fault_type_and_severity` | `fault_classifier.py`（~85%）|
| 单元测试 | 状态机 T1/T2/T3 转移逻辑 | `state_machine.py`（~80%）|
| 集成测试 | fault_event INSERT/UPDATE + DB | `state_machine.py` + `models.py`（~75%）|
| 集成测试 | REST API 过滤/分页 | `views_fault.py` + `serializers_fault.py`（~85%）|
| 集成测试 | fault_cleanup --dry-run + 实际删除 | `fault_cleanup.py`（~80%）|
| 手工验收 | systemd 服务启动 + 前端页面 | 生产/staging 环境 |

测试文件将在测试阶段（GROUP_D）由 test_engineer 实现，本阶段代码评审确认实现具备可测试性（纯函数、依赖注入友好）。

---

## 8. 评审结论

**PASS_WITH_CONDITIONS**

- CRITICAL finding 数：0
- MAJOR finding 数：0
- MINOR finding 数：5（MINOR-1 ~ MINOR-5，均为非阻塞改进建议）

所有核心功能实现符合架构设计文档（ADR-FM-01 ~ ADR-FM-08），满足进入测试阶段的门控条件。
5 个 MINOR 条件项可在后续迭代中逐步修复，不阻塞当前版本交付。
