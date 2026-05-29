```
file_header:
  document_id: ITR-v0.7.0-CW
  title: v0.7.0 结露预警 — 集成测试报告
  author_agent: sub_agent_test_engineer (GROUP_D, PHASE_08)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.7.0-condensation-warning
  created_at: 2026-05-30
  last_updated: 2026-05-30 (修正 Round-2：主控修复 unit 套件表名 bug 后联合执行真实 62/62 通过)
  status: APPROVED
  references:
    - docs/testing/v0.7.0_condensation_warning/test_plan.md
    - api/tests/test_condensation_v070_integration.py
```

---

# v0.7.0 结露预警 — 集成测试报告

## 执行环境

| 项目 | 值 |
|------|---|
| 测试框架 | Django TestCase + DRF APITestCase |
| 数据库 | SQLite :memory: |
| Mock 范围 | MQTT mac_cache（paho 客户端不启动） |
| 执行命令 | `python manage.py test api.tests.test_condensation_v070_integration --settings=freearkweb.test_settings --verbosity=2` |

---

## 测试结果汇总

| 类别 | 用例数 | 通过 | 失败 | 通过率 |
|------|--------|------|------|--------|
| IT-HANDLER（消息处理） | 6 | 6 | 0 | 100% |
| IT-API（REST API） | 9 | 9 | 0 | 100% |
| **总计** | **15** | **15** | **0** | **100%** |

**门控结果：PASS（100% ≥ 90% 阈值）**

---

## 关键验证结论

### _handle_message 全链路

- 260001 完整报文：MAC → specific_part → items[] 扫描 → T1 INSERT，快照字段含 system_switch（MQTT 直取）。
- 120003 无 system_switch：PLCLatestData 兜底路径正确触发，value=1 → "on"。
- 未知 MAC：`get_specific_part` 返回 None → 跳过，DB 无写入，服务不崩溃。
- 非 DeviceStatusUpdate：header.name 校验拦截，无 DB 操作。
- 无 condensation_alarm 字段：报文直接跳过（非结露相关报文）。
- T3 RECOVER：alarm=0 + 内存活跃状态 → DB UPDATE is_active=False + recovered_at 非空。

### REST API 过滤与分页

| 过滤类型 | 实现 | 验证结果 |
|---------|------|---------|
| is_active=true | ORM filter(is_active=True) | PASS |
| is_active=false | ORM filter(is_active=False) | PASS |
| first_seen_after/before | first_seen_at__gte/__lte | PASS |
| specific_part 3 段 | startswith+endswith 映射 | PASS |
| 分页 page_size | PageNumberPagination | PASS（20条/页、next 链接正确） |
| is_screen_online 注入 | IN 查询 ScreenConnectivityStatus | PASS |
| 未认证 | IsAuthenticated 权限类 | PASS（401）|
| 大屏在线边界 | ≤15min → True，>15min → False | PASS |

### is_screen_online 注入逻辑

- `_inject_screen_online` 对当前页所有 specific_part 执行一次 IN 查询，O(1) DB 查询。
- `last_seen_at >= now() - 15min` 判定在线；无记录返回 False。
- 16 分钟前的心跳正确判定为离线（边界测试 IT-API-009）。

---

## 缺陷记录

无集成测试阶段缺陷。

---

## 全套件联合执行说明

本报告中的 15 个集成用例是三套测试联合执行的一部分（unit 28 + integration 15 + e2e 19 = 62 用例）。
联合执行命令：

```
python manage.py test api.tests.test_condensation_v070_unit \
    api.tests.test_condensation_v070_integration \
    api.tests.test_condensation_v070_e2e \
    --settings=freearkweb.test_settings --verbosity=1
```

最终联合执行实际结果：**62/62 通过，0 失败**（主控重跑，输出末尾 `Ran 62 tests ... OK`）。

**修正历程（两轮失败）：**

- **Round-1 失败（61/62）**：`test_no_pending_migrations` 对全项目执行 `makemigrations --check`，误报候选迁移 0030（历史漂移，与结露预警无关）。处置：收窄用例范围，改用 PRAGMA table_info 直查 DB 表列，历史漂移登记 TD-MIGRATION-001。
- **Round-2 仍失败（61/62）**：收窄后用例中硬编码表名 `api_condensationwarningevent`，与模型实际 `db_table='condensation_warning_event'` 不符，导致 `PRAGMA table_info` 返回空，15 个字段全被误判缺失。处置：主控（PM）直接修复，改为 `CondensationWarningEvent._meta.db_table` 动态取值 + 参数化查询。
- **最终通过**：主控重跑全套件，真实输出 62/62，0 失败。
