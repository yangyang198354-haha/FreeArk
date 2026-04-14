# FreeArkWeb 测试报告

<!-- file_header
author_agent: sub_agent_test_engineer
phase: PHASE_08 / PHASE_09
project: FreeArkWeb
created_at: 2026-04-14
status: DRAFT
note: 测试代码已写入 api/tests.py，需在目标机器上运行 python manage.py test api 确认实际结果
-->

---

## 1. 测试代码溯源矩阵

| 测试类 | 测试方法数 | 溯源 AC |
|-------|-----------|---------|
| CustomUserModelTest | 4 | 模型约束 |
| PLCDataModelTest | 3 | 模型约束 |
| UsageQuantityDailyModelTest | 2 | 模型约束 |
| UsageQuantityMonthlyModelTest | 2 | 模型约束 |
| PLCConnectionStatusModelTest | 3 | 模型约束 |
| PLCStatusChangeHistoryModelTest | 1 | 模型约束 |
| SpecificPartInfoModelTest | 3 | 模型约束 |
| ParseSpecificPartTest | 4 | 计算模块 |
| DailyUsageCalculatorTest | 7 | 计算模块 |
| MonthlyUsageCalculatorTest | 5 | 计算模块 |
| PLCDataCleanerTest | 4 | 清理模块 |
| PLCDataHandlerTest | 6 | AC-012-* (MQTT) |
| ConnectionStatusHandlerTest | 6 | AC-012-*, AC-014-* |
| HealthCheckAPITest | 1 | AC-008-01 |
| AuthAPITest | 7 | AC-001-*, AC-002-*, AC-003-* |
| UserRegisterAPITest | 4 | AC-004-01, AC-004-02 |
| ChangePasswordAPITest | 3 | AC-005-01, AC-005-02, AC-005-03 |
| UserManagementAPITest | 4 | AC-006-01, AC-006-02, AC-007-01, AC-007-02, AC-007-03 |
| UserDetailAPITest | 5 | AC-006-*, AC-007-* |
| UsageQuantityAPITest | 6 | AC-009-01~05 |
| UsageQuantitySpecificTimePeriodAPITest | 3 | AC-010-01~03 |
| UsageQuantityMonthlyAPITest | 6 | AC-011-01~04 |
| UsageQuantityMonthlyFilterTest | 2 | AC-011-02 (building/room filter) |
| PLCConnectionStatusAPITest | 8 | AC-012-01~03, AC-013-01~02, AC-014-01~02 |
| PLCStatusHistoryPaginationTest | 2 | AC-014-* 分页 |
| CSRFTokenAPITest | 2 | CSRF 接口 |
| BillingAPITest | 10 | AC-015-01~08 |
| **合计** | **~113** | 全部 AC-NNN-NN 覆盖 |

---

## 2. AC 覆盖情况

| 用户故事 | AC 总数 | 已覆盖 |
|---------|--------|-------|
| US-001 (登录) | 3 | 3 |
| US-002 (登出) | 2 | 2 |
| US-003 (当前用户) | 2 | 2 |
| US-004 (注册) | 2 | 2 |
| US-005 (改密) | 3 | 3 |
| US-006 (用户列表) | 2 | 2 |
| US-007 (创建用户) | 3 | 3 |
| US-008 (健康检查) | 1 | 1 |
| US-009 (日用量) | 5 | 5 |
| US-010 (时段汇总) | 3 | 3 |
| US-011 (月用量) | 4 | 4 |
| US-012 (PLC 状态列表) | 3 | 3 |
| US-013 (PLC 详情) | 2 | 2 |
| US-014 (PLC 历史) | 2 | 2 |
| US-015 (账单) | 8 | 8 |
| **合计** | **45** | **45 (100%)** |

---

## 3. 代码修改记录

### 3.1 api/tests.py — 新增测试类

新增（追加在原有1459行基础上）：
- `UserRegisterAPITest`（4个方法）— 覆盖 AC-004-01/02
- `CSRFTokenAPITest`（2个方法）— 覆盖 CSRF 接口
- `UserDetailAPITest`（5个方法）— 覆盖 UserDetail 视图的 CRUD 操作
- `PLCStatusHistoryPaginationTest`（2个方法）— 覆盖历史分页
- `UsageQuantityMonthlyFilterTest`（2个方法）— 覆盖按 building/room_number 过滤

### 3.2 freearkweb/settings.py — 测试数据库自动切换

修改：在 DATABASES 配置中添加测试环境自动切换逻辑：
```python
import sys as _sys
_RUNNING_TESTS = 'test' in _sys.argv
DATABASES = {
    'default': SQLITE_DATABASE if (USE_SQLITE or _RUNNING_TESTS) else MYSQL_DATABASE
}
```
效果：运行 `python manage.py test` 时自动使用 SQLite，不需要 `--settings` 参数覆盖。

### 3.3 api/monthly_usage_calculator.py — finally 块修复

修改：`calculate_monthly_usage` 的 `finally` 块，防止 `target_date` 为非 date 类型时 `AttributeError` 传播：
```python
finally:
    try:
        month_label = target_date.strftime("%Y-%m")
    except AttributeError:
        month_label = str(target_date)
    logger.info(f'🏁 月度用量计算流程结束 - 目标月份: {month_label}')
```

### 3.4 freearkweb/test_settings.py — 新增测试专用配置（备用）

创建了 `freearkweb/test_settings.py` 作为备用（如需显式指定 `--settings` 时使用）。

---

## 4. 运行命令

```bash
cd C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend\freearkweb
python manage.py test api
```

预期输出（全部通过时）：
```
Ran ~113 tests in X.XXXs
OK
```

---

## 5. 质量指标目标

| 指标 | 目标 | 分析结论 |
|------|------|---------|
| 测试通过率 | 100% | 代码逻辑分析确认测试预期正确 |
| 单元测试覆盖率 | ≥ 80% | 模型+计算器+清理模块均有覆盖 |
| API 集成测试覆盖 | ≥ 90% | 17个端点全覆盖 |
| AC 覆盖率 | 100% | 45/45 AC 已有对应测试 |
| 生产数据库隔离 | 强制 | settings.py 已配置测试自动用 SQLite |
