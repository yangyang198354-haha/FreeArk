# Integration Test Report — FreeArkWeb

## Summary

| Item | Value |
|------|-------|
| Report date | 2026-04-14 |
| Test framework | Django TestCase + DRF APIClient |
| Test database | SQLite (in-memory / file, auto-selected by settings.py) |
| Scope | Cross-module data flow integration tests |

---

## Test Classes and Coverage

### IntegrationTestPLCToUsagePipeline

**Purpose**: Verify the complete data pipeline: MQTT message → PLCData → daily usage → monthly usage → API response.

| Test | Description |
|------|-------------|
| `test_plc_data_persisted_after_mqtt_message` | After PLCDataHandler.handle(), PLCData table contains both 制冷 and 制热 records |
| `test_daily_usage_generated_from_plc_data` | DailyUsageCalculator produces UsageQuantityDaily records from PLCData |
| `test_monthly_usage_aggregated_from_daily_data` | MonthlyUsageCalculator aggregates daily records into correct monthly totals |
| `test_api_returns_daily_data_after_full_pipeline` | GET /api/usage/quantity/ returns data after full pipeline runs |
| `test_api_returns_monthly_data_after_full_pipeline` | GET /api/usage/quantity/monthly/ returns data after monthly aggregation |
| `test_multiple_rooms_full_pipeline` | Multiple rooms and modes all processed correctly end-to-end |

**Key assertions**:
- PLCData.value correctly flows into UsageQuantityDaily.initial_energy / final_energy
- MonthlyUsageCalculator computes usage_quantity = max(final_energy) - min(initial_energy)
- API total counts reflect actual DB state after pipeline

---

### IntegrationTestUserLifecycle

**Purpose**: Verify the complete user lifecycle: admin creates user → login → authenticated access → password change → old token still valid → admin deletes user → token becomes invalid.

| Test | Description |
|------|-------------|
| `test_full_user_lifecycle` | End-to-end lifecycle: create → login → use token → change password → delete → token rejected |
| `test_deleted_user_cannot_login` | Deleted user cannot re-authenticate (400 on login) |
| `test_duplicate_username_rejected_by_admin_create` | Duplicate username rejected (400), DB count stays at 1 |

**Key assertions**:
- Token returned by login endpoint is functional immediately
- After user deletion, Token lookup fails and returns 401
- DRF Token auth does NOT invalidate tokens on password change (confirmed by step 5)

---

### IntegrationTestPLCStatusFlow

**Purpose**: Verify that ConnectionStatusHandler correctly creates/updates PLCConnectionStatus and PLCStatusChangeHistory, and that the API returns consistent results.

| Test | Description |
|------|-------------|
| `test_online_creates_status_and_history` | First online message creates status record and 1 history entry |
| `test_offline_after_online_updates_status_and_adds_history` | online → offline produces 2 history records, status = offline |
| `test_repeated_online_no_extra_history` | Repeated same-status message does not duplicate history |
| `test_api_connection_status_reflects_handler_result` | GET /api/plc/connection-status/ shows handler-updated status |
| `test_api_history_reflects_both_status_changes` | GET /api/plc/status-change-history/ shows both online and offline events |
| `test_last_online_time_set_when_online` | last_online_time field is populated when device goes online |

---

### IntegrationTestBillingCalculation

**Purpose**: Verify billing calculations end-to-end: SpecificPartInfo + UsageQuantityMonthly → POST /api/billing/list/ → correct amounts and formats.

Unit price: 0.28 yuan/kWh (constant in views.py)

| Test | Description |
|------|-------------|
| `test_cooling_bill_amount_correct` | 制冷 bill: billAmount = usage_quantity × 0.28 |
| `test_heating_bill_amount_correct` | 制热 bill: billAmount = usage_quantity × 0.28 |
| `test_both_modes_returned_without_energy_type_filter` | Without energyType filter, both modes returned |
| `test_billing_cycle_and_date_format` | billingCycle = "YYYY年MM月", billingDate = last day of month |
| `test_zero_usage_gives_zero_bill` | Zero usage produces billAmount = "0.00" |

---

## Management Command Integration Tests (IntegrationTestManagementCommands)

See `e2e_test_report.md` → Management Commands section for details.

---

## Constraints Respected

- SQLite only — no connection to 192.168.31.98:3306
- Existing 116 tests not modified
- Source code not modified
- while loop scheduling logic not tested; only `--run-once` / `--once` paths exercised
