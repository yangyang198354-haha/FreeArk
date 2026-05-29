# 自我代码评审报告

```
file_header:
  document_id: CR-v0.7.0-CW
  title: 结露预警管理页面 — 代码评审报告（自评）
  author_agent: sub_agent_software_developer (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.7.0-condensation-warning
  created_at: 2026-05-30
  status: REVIEWED
```

---

## 评审摘要

| 维度 | 结论 |
|------|------|
| CRITICAL finding | 0 |
| MAJOR finding | 0 |
| MINOR finding | 3 |
| INFO finding | 2 |
| RISK-CW-ARCH-01 闭环 | 已闭环 |
| 整体评估 | PASS（可进入测试阶段）|

---

## RISK-CW-ARCH-01 闭环确认

**发现项**：用户通过抓包文件 `sniff_2860fae9a34ab8a9_20260525_235217.ndjson` 核实，MQTT items[] 中 system_switch attrValue 为字符串 "off"/"on"，非整数 "0"/"1"。

**实现处理**：

1. `condensation_consumer.py` 的 `_normalize_system_switch_from_mqtt()`：
   - MQTT 直取路径：`lower()` 后判断 == "off" → "off"，== "on" → "on"，其他非空 → "on" + WARNING 日志
   - 对应注释明确引用 RISK-CW-ARCH-01 闭环

2. `state_machine.py` 的 `_get_system_switch_for_specific_part()`：
   - PLCLatestData 兜底路径：`row.value != 0 → 'on'`，`row.value == 0 → 'off'`
   - BigIntegerField 整数直接比较，不经过字符串路径

3. 两路统一输出到 `CondensationWarningEvent.system_switch`（VARCHAR 8，存 "on"/"off"/"unknown"）

**状态**：CLOSED（已在代码、注释、文档三处明确标注）

---

## CRITICAL Finding（0 项）

无。

---

## MAJOR Finding（0 项）

无。

---

## MINOR Finding（3 项）

### CR-MINOR-01：migration 手写 vs 自动生成的一致性风险

**位置**：`migrations/0029_add_condensation_warning_event.py`

**描述**：手写迁移文件与 Model 定义的字段类型需严格一致。经检查：
- `specific_part` max_length=64（Model 与迁移一致）
- `system_switch` max_length=8（Model 与迁移一致，"unknown" 7 字符，8 字符足够）
- `room_id` ForeignKey 使用 `to='api.deviceroom'`（小写 app_label.model_name，Django ORM 标准格式）

**处置**：建议首次在测试环境运行 `python manage.py migrate --check` 验证迁移文件与当前 Model state 一致。标记为 MINOR，不阻塞测试。

### CR-MINOR-02：system_switch VARCHAR max_length=8 边界

**位置**：`models.py` CondensationWarningEvent.system_switch

**描述**：max_length=8，当前合法值为 "on"(2)/"off"(3)/"unknown"(7)/null。未来若引入更长的语义值（如 "cooling"）可能超出边界。

**处置**：当前版本合法值范围确定，"unknown" 是最长值（7字符），8 字符有 1 字节余量。接受该设计，与架构设计一致（ADR-CW-04 明确选用 VARCHAR(8)）。标记为 MINOR，不需要修改。

### CR-MINOR-03：CondensationWarningView.vue 未使用 ElMessage

**位置**：`CondensationWarningView.vue` fetchWarnings() 的 catch 块

**描述**：fetchWarnings 的错误处理使用 `console.error` 而非 `ElMessage.error`。FaultManagementView.vue 同样使用 `console.error`（非 ElMessage），风格一致。但在用户界面无明确的错误提示。

**处置**：与现有故障管理页面行为保持一致（两者均用 console.error），不引入不一致性。如需改善，可在后续迭代中统一加 ElMessage.error。标记为 MINOR，不需要修改。

---

## INFO Finding（2 项）

### CR-INFO-01：NTC_temp attrTag 大小写容错

**位置**：`condensation_consumer.py` _SNAPSHOT_TAGS 字典

**描述**：生产大屏上报的 attrTag 可能是 "NTC_temp"（大写 NTC）。代码中同时注册了 "NTC_temp" 和 "ntc_temp" 两个 key，均映射到 ntc_temp 字段，已做大小写容错处理。

**处置**：INFO 仅作记录，实现已覆盖该场景。

### CR-INFO-02：condensation_cleanup.service 的 Restart=on-failure

**位置**：`freeark-condensation-cleanup.service`

**描述**：oneshot 类型的服务通常不需要 Restart，因为 timer 会重新触发。但用户需求明确要求 `Restart=on-failure`，已按要求实现。实际效果：若 cleanup 进程以非零退出码结束，systemd 会立即重试（不等 timer 的次日触发）。

**处置**：INFO 仅作记录，已按需求实现。

---

## 逐模块评审结论

| 模块 | 结论 | 关键检查点 |
|------|------|----------|
| MOD-BE-CW-01 __init__.py | PASS | 包标记，无逻辑 |
| MOD-BE-CW-02 state_machine.py | PASS | T1/T2/T3 逻辑正确；RISK-CW-ARCH-01 两源分别处理；IntegrityError 兜底；OperationalError 捕获 |
| MOD-BE-CW-03 condensation_consumer.py | PASS | _normalize_system_switch_from_mqtt 明确处理 MQTT 字符串路径；system_switch=None 触发 PLCLatestData 路径；paho 1.x API 正确 |
| MOD-BE-CW-04 condensation_cleanup.py | PASS | 分批删除逻辑正确；活跃记录豁免（is_active=False 条件）；dry-run 模式实现 |
| MOD-BE-CW-05 models.py 追加 | PASS | 字段与架构设计 ADR-CW-02 一致；UniqueConstraint + 2 Index 均存在；related_name 无冲突 |
| DB-CW-01 migration 0029 | PASS（需测试验证）| 依赖 0028；CreateModel 操作完整；ForeignKey SET_NULL；UniqueConstraint + 2 Index |
| MOD-BE-CW-06 views_condensation.py | PASS | specific_part 段数映射复用 BUG-FM-004 逻辑；_parse_dt USE_TZ 兼容；_inject_screen_online 分页后执行 |
| MOD-BE-CW-07 serializers_condensation.py | PASS | 只读序列化器；room_id 输出 FK id（source='room_id_id'）；is_screen_online 不在序列化器中（由视图层注入） |
| urls.py 追加 | PASS | import views_condensation；path 注册正确 |
| MOD-FE-CW-01 CondensationWarningView.vue | PASS | 12 列表格（2列固定，10列动态）；过滤三件套（状态/房号/时间段）；URLSearchParams append 模式（BUG-FM-003 经验）；大屏在线绿色/离线灰色 |
| MOD-FE-CW-02 router/index.js | PASS | 路由路径与架构设计一致；requiresAuth: true |
| MOD-FE-CW-03 Layout.vue | PASS | 在故障管理之后新增结露预警菜单项；index 路径正确 |
| MOD-INFRA-CW-01 consumer.service | PASS | Restart=on-failure；RestartSec=30s；SyslogIdentifier 独立 |
| MOD-INFRA-CW-02 cleanup.service | PASS | Type=oneshot；Restart=on-failure（用户要求）；命令参数正确 |
| MOD-INFRA-CW-03 cleanup.timer | PASS | OnCalendar=03:30（错开故障清理 03:00）；Persistent=true；Requires= 正确 |

---

## 需求覆盖矩阵

| 需求项 | 实现状态 |
|--------|---------|
| MQTT condensation_alarm 驱动 T1/T2/T3 状态机 | DONE（state_machine.py） |
| system_switch 双源处理（MQTT 直取 + PLCLatestData 兜底）| DONE（RISK-CW-ARCH-01 闭环）|
| migration 0029 依赖 0028，MySQL/SQLite 兼容 | DONE |
| 快照字段 VARCHAR（condensation_alarm_value/dew_point_temp/ntc_temp/humidity/system_switch）| DONE |
| is_screen_online 实时计算注入（ADR-CW-05）| DONE（views_condensation._inject_screen_online）|
| 前端导航「设备管理」下「故障管理」之后新增「结露预警」 | DONE（Layout.vue） |
| 列表 12 列（spec 说 11 列，架构说 12 列，按 12 列实现：含大屏在线/系统开关/露点/NTC/湿度/时间列）| DONE |
| 过滤三件套（状态/房号/时间段）| DONE |
| freeark-condensation-consumer.service Restart=on-failure | DONE |
| freeark-condensation-cleanup.service + .timer（03:30）| DONE |
| 无新增外部依赖 | CONFIRMED（复用 paho-mqtt, djangorestframework, 均已存在）|
| 不执行生产部署或 git push | CONFIRMED（本阶段仅本地实现）|
