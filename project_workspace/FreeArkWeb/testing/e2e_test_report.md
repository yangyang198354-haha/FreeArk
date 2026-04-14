# E2E Test Report — FreeArkWeb

## Summary

| Item | Value |
|------|-------|
| Report date | 2026-04-14 |
| Test framework | Django TestCase + DRF APIClient (no browser automation needed; physical-machine deployment) |
| Test database | SQLite (in-memory / file, auto-selected by settings.py when `test` is in sys.argv) |
| Scope | E2E HTTP scenario tests + Management Command integration tests |

---

## E2E Test Classes

### E2ETestAuthProtection

**Purpose**: Every endpoint with `permission_classes=[permissions.IsAuthenticated]` (or IsAdminUser) must return 401 when accessed without a Token.

| Test | Endpoint | Expected |
|------|----------|----------|
| `test_logout_requires_auth` | POST /api/auth/logout/ | 401 |
| `test_get_current_user_requires_auth` | GET /api/auth/me/ | 401 |
| `test_change_password_requires_auth` | POST /api/change-password/ | 401 |
| `test_user_list_requires_auth` | GET /api/users/ | 401 |
| `test_admin_user_create_requires_auth` | POST /api/users/create/ | 401 |
| `test_user_detail_requires_auth` | GET /api/users/<pk>/ | 401 |

**Coverage**: All authenticated endpoints verified. Public endpoints (health-check, get-csrf-token, usage queries, billing) intentionally excluded from this class (they use AllowAny).

---

### E2ETestBillingFlow

**Purpose**: Full billing query flow from login → CSRF acquisition → billing POST → verify amounts.

| Test | Description |
|------|-------------|
| `test_login_then_query_billing` | Login → confirm token works (GET /api/auth/me/ = 200) → POST billing → 2 records, amounts correct |
| `test_csrf_then_billing` | GET /api/get-csrf-token/ → POST billing (csrf_exempt) → 2 records returned |
| `test_billing_flow_with_energy_type_filter` | energyType=制冷 filter returns exactly 1 cooling record with correct billAmount |

**Amount formula verified**: `billAmount = round(usage_quantity × 0.28, 2)`

---

### E2ETestPaginationConsistency

**Purpose**: Verify that paginated queries are internally consistent across pages.

| Test | Description |
|------|-------------|
| `test_daily_pagination_total_consistent` | Page 1 and Page 2 of daily usage return identical `total` |
| `test_daily_pagination_no_overlap` | IDs on Page 1 and Page 2 are disjoint |
| `test_daily_pagination_all_pages_cover_total` | Union of all page IDs equals `total` (7 records across 3 pages of size 3) |
| `test_monthly_pagination_total_consistent` | Monthly usage pagination total is consistent across pages |

---

### E2ETestFilterCombinations

**Purpose**: Multi-condition filter combinations return results that strictly satisfy all specified conditions.

| Test | Filters Applied | Verified |
|------|----------------|---------|
| `test_filter_building_only` | building=3 | All returned items have building=3 |
| `test_filter_energy_mode_and_date_range` | energy_mode=制冷 + date range | All items match mode and date bounds |
| `test_filter_specific_part_and_energy_mode` | specific_part + energy_mode | Exactly 1 result, correct fields |
| `test_specific_time_period_filter_combinations` | specific_part + energy_mode + date range | 1 aggregated result, usage_quantity = max(final) - min(initial) |
| `test_monthly_building_unit_room_energy_combination` | building + unit + room_number + energy_mode + usage_month | Exactly 1 result with all fields matching |

---

### E2ETestPLCStatisticsConsistency

**Purpose**: Verify that statistics fields in /api/plc/connection-status/ are internally consistent and stable.

| Test | Description |
|------|-------------|
| `test_online_plus_offline_equals_total` | online_count + offline_count = total_devices (3 online, 2 offline) |
| `test_online_rate_calculation` | online_rate = round(2/5 × 100, 2) = 40.0 |
| `test_all_online_rate_is_100` | 4 online, 0 offline → online_rate = 100.0 |
| `test_all_offline_rate_is_0` | 0 online, 3 offline → online_rate = 0 |
| `test_empty_devices_rate_is_0` | No devices → total=0, rate=0 (no ZeroDivisionError) |
| `test_statistics_stable_across_pages` | Statistics fields identical on page 1 and page 2 |

---

## Management Command Integration Tests (IntegrationTestManagementCommands)

**Strategy**: Use `call_command()` for `--run-once` / `--once` paths only. The `while True` scheduler loop is not tested. Direct method calls (`Command.calculate_daily_usage()`, `Command.run_cleanup_task()`) are also tested to verify delegation.

### daily_usage_service

| Test | Description |
|------|-------------|
| `test_daily_usage_service_run_once_processes_data` | `--run-once` with PLCData for yesterday → UsageQuantityDaily record created |
| `test_daily_usage_service_run_once_with_explicit_date` | `--run-once --date=2025-03-15` → record created for that exact date |
| `test_daily_usage_service_no_plc_data_does_not_crash` | No PLCData → command exits cleanly (no exception) |
| `test_daily_usage_service_invalid_date_returns_gracefully` | Bad date format → no non-SystemExit exception propagates |
| `test_daily_usage_service_calculate_method_called` | Direct `Command.calculate_daily_usage()` → DB record created |

### monthly_usage_service

| Test | Description |
|------|-------------|
| `test_monthly_usage_service_run_once_processes_data` | `--run-once` with last-month daily data → UsageQuantityMonthly created |
| `test_monthly_usage_service_run_once_with_explicit_month` | `--run-once --month=2025-03` → monthly record for 2025-03 |
| `test_monthly_usage_service_no_data_does_not_crash` | No daily data → `skipped=True` returned, no exception |
| `test_monthly_usage_service_calculate_method_called` | Direct `Command.calculate_monthly_usage()` → DB record created |

### plc_data_clean_up_service

| Test | Description |
|------|-------------|
| `test_plc_cleanup_service_once_deletes_old_data` | `--once --days=0` with mocked time → PLCData deleted |
| `test_plc_cleanup_service_once_no_data_does_not_crash` | No data → exits cleanly |
| `test_plc_cleanup_service_days_parameter_respected` | `--days=3650` → today's data not deleted |
| `test_plc_cleanup_command_run_cleanup_task_method` | Direct `Command.run_cleanup_task(days=3650)` → data preserved |

---

## Total New Tests Added

| Class | Tests |
|-------|-------|
| IntegrationTestPLCToUsagePipeline | 6 |
| IntegrationTestUserLifecycle | 3 |
| IntegrationTestPLCStatusFlow | 6 |
| IntegrationTestBillingCalculation | 5 |
| E2ETestAuthProtection | 6 |
| E2ETestBillingFlow | 3 |
| E2ETestPaginationConsistency | 4 |
| E2ETestFilterCombinations | 5 |
| E2ETestPLCStatisticsConsistency | 6 |
| IntegrationTestManagementCommands | 13 |
| **Total new** | **57** |

Previous test count: 116
Expected total: 173

---

## Quality Gate Compliance

| Metric | Target | Status |
|--------|--------|--------|
| Integration tests cover all 4 gap scenarios | 4/4 | PASS |
| E2E tests cover all 5 HTTP scenarios | 5/5 | PASS |
| Management command tests cover all 3 commands | 3/3 | PASS |
| SQLite only (no MySQL connection) | Required | PASS |
| Existing 116 tests unmodified | Required | PASS |
| Source code unmodified | Required | PASS |
| while-loop scheduling not tested | Required | PASS |
