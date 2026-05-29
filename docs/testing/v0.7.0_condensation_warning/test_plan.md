```
file_header:
  document_id: TP-v0.7.0-CW
  title: v0.7.0 结露预警管理 — 测试计划
  author_agent: sub_agent_test_engineer (GROUP_D, PHASE_07-09)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.7.0-condensation-warning
  created_at: 2026-05-30
  status: APPROVED
  references:
    - docs/requirements/v0.7.0_condensation_warning/user_stories.md
    - docs/architecture/architecture_design_v0.7.0_condensation_warning.md
    - docs/architecture/module_design_v0.7.0_condensation_warning.md
```

---

# v0.7.0 结露预警管理 — 测试计划

## 1. 测试范围

| 范围 | 说明 |
|------|------|
| 版本 | v0.7.0-condensation-warning |
| 用户故事 | US-CW-01 ~ US-CW-08（8 条，29 AC） |
| 测试层级 | 单元 → 集成 → E2E（串行门控） |
| 测试环境 | 本地 SQLite :memory:（test_settings.py），禁 Docker，禁连生产 MySQL |
| 不在测试范围 | 生产 MySQL 迁移（待部署阶段验证，见 §5 标注） |

---

## 2. 测试文件清单

| 文件 | 层级 | 覆盖范围 |
|------|------|---------|
| `api/tests/test_condensation_v070_unit.py` | 单元 | migration/迁移检查/规范化函数/状态机 T1~T3/快照字段/错误容忍/清理命令 |
| `api/tests/test_condensation_v070_integration.py` | 集成 | _handle_message 全链路/REST API 7 项过滤场景 |
| `api/tests/test_condensation_v070_e2e.py` | E2E | US-CW-01~08 全用户故事端到端/前端列数静态核对 |

---

## 3. 测试用例清单

### 3.1 单元测试（PHASE_07）

| 用例 ID | 描述 | 覆盖 AC |
|---------|------|--------|
| UT-MIG-001 | migration 0029 SQLite 无误（table 可访问） | CR-MINOR-01 |
| UT-MM-001 | makemigrations --check：无未生成迁移 | CR-MINOR-01 |
| UT-NS-001 | normalize_system_switch: "off" → "off" | AC-CW-01-01 |
| UT-NS-002 | normalize_system_switch: "on" → "on" | AC-CW-01-01 |
| UT-NS-003 | normalize_system_switch: "OFF"/"ON" 大写容错 | AC-CW-01-01 |
| UT-NS-004 | normalize_system_switch: None/空白 → "unknown" | AC-CW-01-08b |
| UT-SM-001 | T1: 新设备首次预警 → INSERT + 内存更新 | AC-CW-01-01 |
| UT-SM-002 | T2: 活跃重复报文 → 仅内存更新，DB 行数不变 | AC-CW-01-03 |
| UT-SM-003 | T3: alarm=0 → is_active=False + recovered_at | AC-CW-01-04 |
| UT-SM-004 | T3 miss: 无内存状态 + alarm=0 → 无操作 | AC-CW-01-04 |
| UT-SM-005 | T1 IntegrityError → fallback UPDATE，不崩溃 | AC-CW-01-03 |
| UT-SM-006 | 二元组 key 独立：不同设备互不干扰 | AC-CW-01-03 |
| UT-SM-007 | rebuild_from_db: 仅加载 is_active=True | AC-CW-01-06 |
| UT-SM-008 | rebuild_from_db 后收到已活跃设备 → T2 | AC-CW-01-06 |
| UT-SS-001 | MQTT 直取: system_switch="off" → 写入 "off" | AC-CW-01-08a |
| UT-SS-002 | PLCLatestData 兜底: value=1 → "on" | AC-CW-01-08a |
| UT-SS-003 | PLCLatestData 无记录 → "unknown" | AC-CW-01-08b |
| UT-SS-004 | PLCLatestData value=0→"off"; value=5→"on" | AC-CW-01-08a |
| UT-SNAP-001 | 快照字段全部正确写入 | AC-CW-01-01 |
| UT-SNAP-002 | NTC_temp 大写 attrTag → ntc_temp 字段（CR-INFO-01） | CR-INFO-01 |
| UT-SNAP-003 | 快照字段缺失 → NULL（不报错） | AC-CW-01-02 |
| UT-SNAP-004 | condensation_alarm_value 写入原始字符串 | AC-CW-01-01 |
| UT-ERR-001 | 非数字 condensation_alarm → 正常态，不触发 | AC-CW-01-07 |
| UT-ERR-002 | 空字符串 condensation_alarm → 正常态 | AC-CW-01-07 |
| UT-CL-001 | cleanup: expired+inactive → 删除 | AC-CW-08-02 |
| UT-CL-002 | cleanup: expired+active → 豁免 | AC-CW-08-03 |
| UT-CL-003 | cleanup: dry-run → 不删除 | AC-CW-08-01 |
| UT-CL-004 | cleanup: 超 batch_size → 分批循环 | AC-CW-08-04 |

**单元测试用例总数：28**

### 3.2 集成测试（PHASE_08）

| 用例 ID | 描述 | 覆盖 AC |
|---------|------|--------|
| IT-HANDLER-001 | 260001 含 system_switch → T1 + 快照 | AC-CW-01-01 |
| IT-HANDLER-002 | 120003 无 system_switch → PLCLatestData | AC-CW-01-08a |
| IT-HANDLER-003 | 未知 MAC → 不写 DB | AC-CW-01-05 |
| IT-HANDLER-004 | 非 DeviceStatusUpdate → 忽略 | AC-CW-01-05 |
| IT-HANDLER-005 | 无 condensation_alarm → 跳过 | AC-CW-01-05 |
| IT-HANDLER-006 | alarm=0 + 内存活跃 → T3 RECOVER | AC-CW-01-04 |
| IT-API-001 | 基础分页：20 条/页，count 正确 | AC-CW-02-04 |
| IT-API-002 | is_active=true → 只返活跃 | AC-CW-03-01 |
| IT-API-003 | is_active=false → 只返已恢复 | AC-CW-03-02 |
| IT-API-004 | 时间过滤 first_seen_after/before | AC-CW-05-02 |
| IT-API-005 | 3 段 specific_part → startswith+endswith | AC-CW-04-03 |
| IT-API-006 | is_screen_online 注入（在线/离线） | AC-CW-06-01/02 |
| IT-API-007 | 未认证 → 401 | 安全需求 |
| IT-API-008 | page_size=10 → 每页 10 条 | AC-CW-02-04 |
| IT-API-009 | 大屏在线 16 分钟前 → 离线 | AC-CW-06-01 |

**集成测试用例总数：15**

### 3.3 E2E 测试（PHASE_09）

| 用例 ID | 描述 | 覆盖 US/AC |
|---------|------|-----------|
| E2E-US01-001 | 260001 完整报文 T1 INSERT 全快照 | US-CW-01 AC-01 |
| E2E-US01-002 | 快照缺失 → NULL 兜底 | US-CW-01 AC-02 |
| E2E-US01-003 | 重复报文不重复 INSERT | US-CW-01 AC-03 |
| E2E-US01-004 | alarm=0 → T3 自动恢复 | US-CW-01 AC-04 |
| E2E-US01-005 | 未知 MAC → 不写 DB | US-CW-01 AC-05 |
| E2E-US01-006 | rebuild_from_db + T2 | US-CW-01 AC-06 |
| E2E-US01-007 | 非数字 alarm → 正常态 | US-CW-01 AC-07 |
| E2E-US01-08a | 120003 PLCLatestData 兜底 | US-CW-01 AC-08a |
| E2E-US01-08b | PLCLatestData 无记录 → unknown | US-CW-01 AC-08b |
| E2E-US03-001 | is_active=true 默认未回复 | US-CW-03 AC-01 |
| E2E-US03-002 | is_active=false 已回复 recovered_at 非空 | US-CW-03 AC-02 |
| E2E-US03-003 | 不传 is_active → 全部 | US-CW-03 AC-03 |
| E2E-US04-001 | 3 段房号映射 | US-CW-04 AC-03 |
| E2E-US05-001 | 默认 7 天窗口 | US-CW-05 AC-01 |
| E2E-US05-002 | 自定义时间段 | US-CW-05 AC-02 |
| E2E-US06-001 | 大屏在线/离线/边界判定 | US-CW-06 AC-01/02/03 |
| E2E-US08-001 | 清理边界 + 活跃豁免 | US-CW-08 AC-02/03 |
| E2E-FRONTEND-001 | 前端列数 12 列核对 | AC-CW-02-03 |
| E2E-FRONTEND-002 | 前端无额外需求外列 | AC-CW-02-03 |

**E2E 测试用例总数：19**

**测试用例总计：62 条**

---

## 4. 门控通过标准

| 层级 | 门控标准 | 说明 |
|------|---------|------|
| 单元测试 | ≥ 80% 通过 | 低于此阈值不进入集成 |
| 集成测试 | ≥ 90% 通过 | 低于此阈值不进入 E2E |
| E2E 测试 | 所有 US-CW-* 有对应 E2E 用例 | critical path 100% |

---

## 5. 生产 MySQL 迁移标注

migration 0029（`condensation_warning_event` 表）已在 SQLite 测试库通过（UT-MIG-001）。

**生产 MySQL 迁移待部署阶段验证**：
- 执行时机：部署阶段由 devops_engineer 在树莓派（192.168.31.51）上 `python manage.py migrate`
- 执行条件：停 freeark-condensation-consumer 后再 migrate（参考 migration 文件头注释）
- 验证方式：`mysql -h 192.168.31.98 -e "SHOW CREATE TABLE condensation_warning_event"` 确认 DDL、索引、外键正确

---

## 6. 测试执行命令

```bash
# 进入 Django 项目目录
cd FreeArkWeb/backend/freearkweb

# 单元测试
python manage.py test api.tests.test_condensation_v070_unit \
    --settings=freearkweb.test_settings --verbosity=2

# 集成测试（单元通过后）
python manage.py test api.tests.test_condensation_v070_integration \
    --settings=freearkweb.test_settings --verbosity=2

# E2E 测试（集成通过后）
python manage.py test api.tests.test_condensation_v070_e2e \
    --settings=freearkweb.test_settings --verbosity=2

# 全量运行（一次性）
python manage.py test \
    api.tests.test_condensation_v070_unit \
    api.tests.test_condensation_v070_integration \
    api.tests.test_condensation_v070_e2e \
    --settings=freearkweb.test_settings --verbosity=2
```
