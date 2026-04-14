# FreeArkWeb 测试计划

<!-- file_header
author_agent: sub_agent_test_engineer
phase: PHASE_07
project: FreeArkWeb
created_at: 2026-04-14
status: DRAFT
-->

---

## 1. 测试目标

- 单元测试覆盖率 >= 80%（api 模块）
- 集成测试（API 端到端）覆盖率 >= 90%（所有 API 端点）
- 每个 US-* 的每条 AC-NNN-NN 均有对应测试用例
- 所有测试使用 Django TestCase（SQLite 内存数据库，不连接生产）

---

## 2. 测试范围

### 2.1 单元测试

| 测试类 | 覆盖模块 | 关联 AC |
|-------|---------|---------|
| CustomUserModelTest | models.CustomUser | - |
| PLCDataModelTest | models.PLCData | - |
| UsageQuantityDailyModelTest | models.UsageQuantityDaily | - |
| UsageQuantityMonthlyModelTest | models.UsageQuantityMonthly | - |
| PLCConnectionStatusModelTest | models.PLCConnectionStatus | - |
| PLCStatusChangeHistoryModelTest | models.PLCStatusChangeHistory | - |
| SpecificPartInfoModelTest | models.SpecificPartInfo | - |
| ParseSpecificPartTest | DailyUsageCalculator.parse_specific_part | - |
| DailyUsageCalculatorTest | DailyUsageCalculator.calculate_daily_usage | - |
| MonthlyUsageCalculatorTest | MonthlyUsageCalculator.calculate_monthly_usage | - |
| PLCDataCleanerTest | plc_data_cleaner.clean_old_plc_data | - |
| PLCDataHandlerTest | mqtt_handlers.PLCDataHandler | - |
| ConnectionStatusHandlerTest | mqtt_handlers.ConnectionStatusHandler | - |

### 2.2 集成测试（API）

| 测试类 | 覆盖端点 | 关联 AC |
|-------|---------|---------|
| HealthCheckAPITest | GET /api/health/ | AC-008-01 |
| AuthAPITest | POST /api/auth/login/, /logout/, GET /api/auth/me/ | AC-001-*, AC-002-*, AC-003-* |
| UserRegisterAPITest | POST /api/auth/register/ | AC-004-* |
| ChangePasswordAPITest | POST /api/change-password/ | AC-005-* |
| UserManagementAPITest | GET/POST /api/users/, /api/users/create/ | AC-006-*, AC-007-* |
| UsageQuantityAPITest | GET /api/usage/quantity/ | AC-009-* |
| UsageQuantitySpecificTimePeriodAPITest | GET /api/usage/quantity/specifictimeperiod/ | AC-010-* |
| UsageQuantityMonthlyAPITest | GET /api/usage/quantity/monthly/ | AC-011-* |
| PLCConnectionStatusAPITest | GET /api/plc/connection-status/, /detail/, /history/ | AC-012-*, AC-013-*, AC-014-* |
| BillingAPITest | POST /api/billing/list/ | AC-015-* |
| CSRFTokenAPITest | GET /api/get-csrf-token/ | - |

---

## 3. 测试环境

- 数据库：SQLite（Django TestCase 自动创建/销毁）
- 认证：DRF APIClient with Token credentials
- 运行命令：`python manage.py test api`

---

## 4. 质量门控标准

| 指标 | 目标 |
|------|-----|
| 单元测试通过率 | 100% |
| 集成测试通过率 | 100% |
| 所有 AC-NNN-NN 有对应测试 | 是 |
| 不连接生产数据库 | 强制要求 |
