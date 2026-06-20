# FreeArk 后端测试清单（test_inventory.md）

> 自动生成：`python scripts/gen_test_inventory.py`（请勿手改，改 @tag 后重新生成）
> 生成日期：2026-06-20

**分层方式**：Django 原生 `@tag('unit'|'integration'|'e2e')`（类级）。文件位置保持不动（扁平），仅靠 tag 分层。

**运行命令**（主测试体，Django test runner）：
```bash
cd FreeArkWeb/backend/freearkweb
FREEARK_POC_MOCK=1 python manage.py test api --settings=freearkweb.test_settings [--tag=unit|integration|e2e]
```

## 汇总

| 层级 | 用例数 |
|------|-------:|
| unit | 824 |
| integration | 871 |
| e2e | 84 |
| **合计（已分层）** | **1779** |

> 全量 `manage.py test api` 共发现 **1702** 个测试；上表三层之和应等于 1702（每个用例恰属一层，无重复、无遗漏）。

### 各文件分层用例数

| 脚本 | unit | integration | e2e | 合计 |
|------|-----:|------------:|----:|-----:|
| `api/tests/test_chat_memory_session.py` | 30 | 0 | 0 | 30 |
| `api/tests/test_chat_session_e2e.py` | 0 | 0 | 1 | 1 |
| `api/tests/test_chat_session_feature.py` | 17 | 12 | 0 | 29 |
| `api/tests/test_condensation_v070_e2e.py` | 0 | 0 | 19 | 19 |
| `api/tests/test_condensation_v070_integration.py` | 0 | 15 | 0 | 15 |
| `api/tests/test_condensation_v070_unit.py` | 33 | 0 | 0 | 33 |
| `api/tests/test_connection_status_cache_coherence_v058.py` | 6 | 0 | 0 | 6 |
| `api/tests/test_connection_status_lock_opt_v055.py` | 8 | 2 | 0 | 10 |
| `api/tests/test_csrf_relogin.py` | 0 | 17 | 0 | 17 |
| `api/tests/test_daily_usage_calculator.py` | 8 | 0 | 0 | 8 |
| `api/tests/test_dashboard_perf.py` | 0 | 0 | 0 | 0 |
| `api/tests/test_dashboard_power_status_v053.py` | 0 | 37 | 0 | 37 |
| `api/tests/test_device_cards.py` | 11 | 30 | 0 | 41 |
| `api/tests/test_device_list_fault_filter.py` | 8 | 8 | 4 | 20 |
| `api/tests/test_device_management.py` | 27 | 62 | 21 | 110 |
| `api/tests/test_device_name_cache_v061.py` | 14 | 0 | 0 | 14 |
| `api/tests/test_device_settings.py` | 27 | 0 | 0 | 27 |
| `api/tests/test_device_settings_e2e.py` | 0 | 0 | 4 | 4 |
| `api/tests/test_device_settings_integration.py` | 0 | 22 | 0 | 22 |
| `api/tests/test_device_settings_v050.py` | 32 | 66 | 0 | 98 |
| `api/tests/test_device_tree_sync_lock_fix.py` | 0 | 8 | 0 | 8 |
| `api/tests/test_dph_cleanup_service.py` | 26 | 0 | 0 | 26 |
| `api/tests/test_fault_event_serializer_v061.py` | 0 | 13 | 0 | 13 |
| `api/tests/test_fault_mgmt_v064_integration.py` | 0 | 18 | 0 | 18 |
| `api/tests/test_fault_mgmt_v064_unit.py` | 20 | 0 | 0 | 20 |
| `api/tests/test_heartbeat_broker_config.py` | 25 | 18 | 0 | 43 |
| `api/tests/test_inspection_agent_loop_v110.py` | 8 | 0 | 0 | 8 |
| `api/tests/test_inspection_agent_v110.py` | 21 | 0 | 0 | 21 |
| `api/tests/test_inspection_ondemand_v130.py` | 0 | 24 | 0 | 24 |
| `api/tests/test_inspection_workorder_v110.py` | 9 | 0 | 0 | 9 |
| `api/tests/test_langgraph_phase_a.py` | 49 | 0 | 0 | 49 |
| `api/tests/test_langgraph_phase_g.py` | 7 | 0 | 0 | 7 |
| `api/tests/test_main.py` | 68 | 140 | 24 | 232 |
| `api/tests/test_memory_chat_memory.py` | 29 | 0 | 0 | 29 |
| `api/tests/test_memory_consumer_v13.py` | 0 | 14 | 0 | 14 |
| `api/tests/test_memory_models.py` | 18 | 0 | 0 | 18 |
| `api/tests/test_memory_skeleton_guard_sh.py` | 12 | 0 | 0 | 12 |
| `api/tests/test_memory_views.py` | 0 | 23 | 0 | 23 |
| `api/tests/test_mqtt_worker_conn_poison_heal.py` | 6 | 0 | 0 | 6 |
| `api/tests/test_openclaw_integration.py` | 0 | 9 | 0 | 9 |
| `api/tests/test_openclaw_unit.py` | 25 | 0 | 0 | 25 |
| `api/tests/test_owner.py` | 8 | 20 | 0 | 28 |
| `api/tests/test_owner_sprint2.py` | 0 | 28 | 0 | 28 |
| `api/tests/test_plc_latest.py` | 13 | 7 | 0 | 20 |
| `api/tests/test_reasoning_stream.py` | 0 | 35 | 0 | 35 |
| `api/tests/test_redis_cache_pretest.py` | 4 | 0 | 0 | 4 |
| `api/tests/test_room_filter_v057.py` | 31 | 13 | 0 | 44 |
| `api/tests/test_screen_heartbeat.py` | 14 | 4 | 0 | 18 |
| `api/tests/test_service_management.py` | 18 | 28 | 11 | 57 |
| `api/tests/test_service_registry_v120.py` | 12 | 3 | 0 | 15 |
| `api/tests/test_session_delete_view.py` | 0 | 13 | 0 | 13 |
| `api/tests/test_v100_dashboard_redesign.py` | 0 | 16 | 0 | 16 |
| `api/tests/test_waitress_config_v052.py` | 12 | 0 | 0 | 12 |
| `api/tests/test_workorder_v131.py` | 0 | 14 | 0 | 14 |
| `api/tests/test_ws_session_resolve.py` | 0 | 4 | 0 | 4 |
| `api/tests_fault_count.py` | 50 | 19 | 0 | 69 |
| `api/tests_fault_event.py` | 79 | 96 | 0 | 175 |
| `api/tests_rag.py` | 27 | 18 | 0 | 45 |
| `api/tests_session_timeout.py` | 12 | 15 | 0 | 27 |

---

## 明细：脚本 → 测试类［层级］→ 用例方法

### `api/tests/test_chat_memory_session.py`

- **LoadHistoryBySessionEmptyTest** ［unit］ — 1 用例
  - `test_empty_session_returns_empty_list`
- **LoadHistoryBySessionBasicTest** ［unit］ — 2 用例
  - `test_returns_messages_in_order`
  - `test_returns_list_of_dicts`
- **LoadHistoryBySessionIsolationTest** ［unit］ — 3 用例
  - `test_session_a_does_not_contain_session_b_messages`
  - `test_session_b_does_not_contain_session_a_messages`
  - `test_isolation_with_multiple_users`
- **LoadHistoryBySessionLimitTest** ［unit］ — 5 用例
  - `test_limit_20_returns_at_most_40_messages`
  - `test_limit_20_returns_most_recent_messages`
  - `test_exactly_20_turns_returned`
  - `test_limit_default_reads_from_settings`
  - `test_limit_exact_match`
- **SoftDeleteSessionTest** ［unit］ — 6 用例
  - `test_get_sessions_excludes_deleted`
  - `test_soft_delete_sets_is_deleted_flag`
  - `test_soft_delete_returns_true`
  - `test_soft_delete_idempotent_raises_value_error`
  - `test_soft_delete_wrong_user_raises_value_error`
  - `test_soft_delete_nonexistent_key_raises_value_error`
- **GetSessionsExtendedTest** ［unit］ — 6 用例
  - `test_session_key_full_field_present`
  - `test_session_key_is_truncated_for_display`
  - `test_is_deleted_filter_only_returns_active_sessions`
  - `test_empty_user_returns_empty`
  - `test_pagination_page2`
  - `test_returns_message_count`
- **LoadHistoryLimitZeroTest** ［unit］ — 1 用例
  - `test_limit_zero_returns_empty`
- **ResolveSessionTest** ［unit］ — 4 用例
  - `test_none_param_creates_new_session`
  - `test_valid_key_returns_existing_session`
  - `test_deleted_key_creates_new_session`
  - `test_wrong_user_key_creates_new_session`
- **GetSessionsOrderTest** ［unit］ — 1 用例
  - `test_sessions_ordered_by_started_at_desc`
- **LoadHistoryBySessionOrderTest** ［unit］ — 1 用例
  - `test_messages_returned_in_ascending_order`

### `api/tests/test_chat_session_e2e.py`

- **FullSessionLifecycleE2ETest** ［e2e］ — 1 用例
  - `test_tc_e2e_001_full_session_lifecycle`

### `api/tests/test_chat_session_feature.py`

- **GenerateTitleTruncateTest** ［unit］ — 5 用例
  - `test_tc_unit_001_truncates_long_content`
  - `test_tc_unit_002_no_truncation_for_short_content`
  - `test_tc_unit_003_empty_string_returns_empty`
  - `test_tc_unit_004_exactly_max_len_not_truncated`
  - `test_truncate_default_max_len_is_30`
- **GenerateTitleLlmAsyncTest** ［unit］ — 4 用例
  - `test_tc_unit_005_llm_success_updates_title`
  - `test_tc_unit_006_llm_exception_preserves_truncated_title`
  - `test_tc_unit_007_llm_empty_string_preserves_truncated_title`
  - `test_tc_unit_no_api_key_no_update`
- **GetSessionHistoryTest** ［unit］ — 6 用例
  - `test_tc_unit_008_normal_returns_ordered_messages`
  - `test_tc_unit_009_nonexistent_session_raises_valueerror`
  - `test_tc_unit_010_other_user_session_raises_valueerror`
  - `test_history_limit_respected`
  - `test_empty_session_returns_empty_list`
  - `test_soft_deleted_session_raises_valueerror`
- **EnsureSessionCreatedTest** ［integration］ — 2 用例
  - `test_tc_unit_011_first_call_creates_session`
  - `test_tc_unit_012_idempotent_second_call`
- **GetSessionsTitleFieldTest** ［unit］ — 2 用例
  - `test_tc_unit_013_title_field_present_and_correct`
  - `test_tc_unit_014_old_session_title_is_null`
- **SessionHistoryViewTest** ［integration］ — 6 用例
  - `test_tc_int_001_normal_returns_200_with_ordered_messages`
  - `test_tc_int_001_limit_40_for_large_session`
  - `test_tc_int_002_empty_session_returns_empty_list`
  - `test_tc_int_003_other_user_session_returns_404`
  - `test_tc_int_004_unauthenticated_returns_401_or_403`
  - `test_nonexistent_session_returns_404`
- **GetSessionsTitleIntegrationTest** ［integration］ — 2 用例
  - `test_tc_int_005_sessions_contain_title_field`
  - `test_tc_int_006_old_session_title_null`
- **WsNoDbOnConnectTest** ［integration］ — 1 用例
  - `test_tc_int_007_connect_no_db_record`
- **WsFirstMessageCreatesSessionTest** ［integration］ — 1 用例
  - `test_tc_int_008_first_message_creates_session_with_title`

### `api/tests/test_condensation_v070_e2e.py`

- **US01PersistenceE2ETest** ［e2e］ — 9 用例
  - `test_e2e_us01_001_full_260001_t1_insert`
  - `test_e2e_us01_002_missing_snapshot_null`
  - `test_e2e_us01_003_duplicate_no_insert`
  - `test_e2e_us01_004_recover_alarm_zero`
  - `test_e2e_us01_005_unknown_mac_no_db`
  - `test_e2e_us01_006_rebuild_then_t2`
  - `test_e2e_us01_007_non_numeric_alarm_normal`
  - `test_e2e_us01_08a_120003_plc_fallback`
  - `test_e2e_us01_08b_no_plc_record_unknown`
- **APIFilterE2ETest** ［e2e］ — 7 用例
  - `test_e2e_us03_001_default_is_active_true`
  - `test_e2e_us03_002_is_active_false_recovered_at_not_null`
  - `test_e2e_us03_003_all_no_filter`
  - `test_e2e_us04_001_specific_part_3_segment`
  - `test_e2e_us05_001_default_7_days`
  - `test_e2e_us05_002_custom_time_range`
  - `test_e2e_us06_001_screen_online_15min`
- **CleanupE2ETest** ［e2e］ — 1 用例
  - `test_e2e_us08_001_cleanup_boundary_and_exempt`
- **FrontendColumnCheckE2ETest** ［e2e］ — 2 用例
  - `test_frontend_001_column_count_and_labels`
  - `test_frontend_002_extra_columns_explained`

### `api/tests/test_condensation_v070_integration.py`

- **HandleMessageIntegrationTest** ［integration］ — 6 用例
  - `test_handler_001_260001_with_system_switch_mqtt_direct`
  - `test_handler_002_120003_no_system_switch_plc_fallback`
  - `test_handler_003_unknown_mac_no_db_write`
  - `test_handler_004_non_device_status_update_ignored`
  - `test_handler_005_no_condensation_alarm_tag_skipped`
  - `test_handler_006_alarm_zero_triggers_t3_recover`
- **CondensationAPITest** ［integration］ — 9 用例
  - `test_api_001_basic_pagination_default`
  - `test_api_002_filter_is_active_true`
  - `test_api_003_filter_is_active_false`
  - `test_api_004_time_filter`
  - `test_api_005_specific_part_3_segment_mapping`
  - `test_api_006_is_screen_online_injection`
  - `test_api_007_unauthenticated_401`
  - `test_api_008_page_size_override`
  - `test_api_009_screen_online_15min_boundary`

### `api/tests/test_condensation_v070_unit.py`

- **MigrationApplyTest** ［unit］ — 1 用例
  - `test_migration_0029_table_exists`
- **MakeMigrationsCheckTest** ［unit］ — 1 用例
  - `test_no_pending_migrations`
- **NormalizeSystemSwitchTest** ［unit］ — 4 用例
  - `test_ns_001_off_lowercase`
  - `test_ns_002_on_lowercase`
  - `test_ns_003_case_insensitive`
  - `test_ns_004_none_empty_blank`
- **StateMachineT1T2T3Test** ［unit］ — 8 用例
  - `test_sm_001_t1_insert_new_alarm`
  - `test_sm_002_t2_active_repeat`
  - `test_sm_003_t3_recover`
  - `test_sm_004_t3_no_state_no_op`
  - `test_sm_005_t1_integrity_error_fallback`
  - `test_sm_006_key_independence`
  - `test_sm_007_rebuild_from_db`
  - `test_sm_008_rebuild_then_t2_no_duplicate_insert`
- **StateMachineT2ThrottledPersistTest** ［unit］ — 5 用例
  - `test_t2_within_window_does_not_persist`
  - `test_t2_beyond_window_persists`
  - `test_t2_persist_adds_no_new_rows`
  - `test_persist_resets_throttle_window`
  - `test_threshold_zero_persists_every_t2`
- **SystemSwitchDualSourceTest** ［unit］ — 4 用例
  - `test_ss_001_mqtt_direct_off`
  - `test_ss_002_plc_fallback_on`
  - `test_ss_003_plc_no_record_unknown`
  - `test_ss_004_plc_value_zero_is_off`
- **SnapshotFieldTest** ［unit］ — 4 用例
  - `test_snap_001_all_snapshot_fields`
  - `test_snap_002_ntc_uppercase_tag`
  - `test_snap_003_missing_fields_null`
  - `test_snap_004_condensation_alarm_value_raw`
- **ErrorToleranceTest** ［unit］ — 2 用例
  - `test_err_001_non_numeric_condensation_alarm`
  - `test_err_002_empty_condensation_alarm`
- **CleanupCommandTest** ［unit］ — 4 用例
  - `test_cl_001_expired_inactive_deleted`
  - `test_cl_002_active_exempt`
  - `test_cl_003_dry_run_no_delete`
  - `test_cl_004_batch_loop`

### `api/tests/test_connection_status_cache_coherence_v058.py`

- **TestCacheCoherenceFixV058** ［unit］ — 4 用例
  - `test_f2_01_cache_online_db_online_fast_path_no_regression`
  - `test_f2_02_cache_online_db_offline_by_monitor_triggers_fallback`
  - `test_f2_03_cache_miss_status_online_slow_path_unchanged`
  - `test_f2_04_cache_offline_status_online_slow_path_unchanged`
- **TestCacheCoherenceLoggingV058** ［unit］ — 2 用例
  - `test_warning_log_format_on_cache_db_mismatch`
  - `test_no_warning_on_normal_fast_path`

### `api/tests/test_connection_status_lock_opt_v055.py`

- **TestConnectionStatusLockOpt** ［unit］ — 8 用例
  - `test_p2_01_new_device_first_call`
  - `test_p2_02_no_change_online_fast_path`
  - `test_p2_03_no_change_offline_fast_path`
  - `test_p2_04_change_online_to_offline_slow_path`
  - `test_p2_05_change_offline_to_online_slow_path`
  - `test_p2_06_restart_cache_cleared_slow_path_no_dup_history`
  - `test_p2_07_sqlite_select_for_update_no_error`
  - `test_p2_08_db_failure_does_not_update_cache`
- **TestConnectionStatusHandleIntegration** ［integration］ — 2 用例
  - `test_handle_marks_device_online`
  - `test_handle_marks_device_offline`

### `api/tests/test_csrf_relogin.py`

- **GetCSRFTokenEndpointTest** ［integration］ — 4 用例
  - `test_csrf_token_endpoint_returns_200`
  - `test_csrf_token_endpoint_returns_token_in_body`
  - `test_csrf_token_endpoint_sets_cookie`
  - `test_csrf_token_is_consistent_between_body_and_cookie`
- **LoginLogoutLoginFlowTest** ［integration］ — 6 用例
  - `test_first_login_succeeds`
  - `test_logout_succeeds_after_first_login`
  - `test_old_token_invalid_after_logout`
  - `test_second_login_succeeds_after_logout`
  - `test_new_token_works_after_re_login`
  - `test_repeated_login_logout_cycle_stable`
- **CSRFEnforcedLoginLogoutTest** ［integration］ — 2 用例
  - `test_login_is_csrf_exempt`
  - `test_logout_returns_401_without_token`
- **TokenRotationAfterLoginTest** ［integration］ — 2 用例
  - `test_second_login_produces_valid_token`
  - `test_token_deleted_on_logout_then_recreated_on_login`
- **SessionAuthCSRFRegressionTest** ［integration］ — 3 用例
  - `test_reproduce_session_auth_enforces_csrf_without_cookie`
  - `test_settings_no_longer_register_session_authentication`
  - `test_fix_no_csrf_failure_on_real_endpoint`

### `api/tests/test_daily_usage_calculator.py`

- **TC01_NextDayInitialEnergyWritten** ［unit］ — 1 用例
  - `test_next_day_initial_energy_set`
- **TC02_TodayRunDoesNotCreateTomorrowRecord** ［unit］ — 2 用例
  - `test_tomorrow_record_not_created`
  - `test_tomorrow_existing_record_not_modified`
- **TC03_UsageQuantityCalculation** ［unit］ — 1 用例
  - `test_usage_quantity_equals_value_minus_initial`
- **TC04_TodayRecordCreatedWithZeroUsage** ［unit］ — 1 用例
  - `test_record_created_with_zero_usage`
- **TC05_IdempotencyForToday** ［unit］ — 1 用例
  - `test_idempotent_two_runs`
- **TC06_ExistingNextDayInitialEnergyNotOverwritten** ［unit］ — 1 用例
  - `test_existing_initial_energy_preserved`
- **TC07_HourlyScheduleRegistered** ［unit］ — 1 用例
  - `test_hourly_job_registered_in_schedule`

### `api/tests/test_dashboard_perf.py`


### `api/tests/test_dashboard_power_status_v053.py`

- **TestPowerStatusBasic** ［integration］ — 7 用例
  - `test_empty_db_returns_zero_no_division_error`
  - `test_offline_device_excluded_from_powered_on`
  - `test_online_but_switch_off_excluded`
  - `test_online_switch_on_counted`
  - `test_mixed_online_offline_correct_counts`
  - `test_all_devices_on`
  - `test_all_devices_off`
- **TestPowerStatusModeDistribution** ［integration］ — 8 用例
  - `test_mode_1_cooling`
  - `test_mode_2_heating`
  - `test_mode_3_ventilation`
  - `test_mode_4_dehumidification`
  - `test_all_four_modes`
  - `test_only_cooling_mode`
  - `test_offline_device_mode_not_counted`
  - `test_mode_sum_leq_powered_on`
- **TestPowerStatusUnknownMode** ［integration］ — 5 用例
  - `test_powered_on_no_mode_record`
  - `test_mode_zero_counts_as_unknown`
  - `test_mode_distribution_sum_equals_powered_on`
  - `test_out_of_range_mode_counts_as_unknown`
  - `test_null_mode_value_counts_as_unknown`
- **TestPowerStatusBoundaries** ［integration］ — 5 用例
  - `test_online_no_switch_record_excluded`
  - `test_plclatestdata_only_no_connection_record_excluded`
  - `test_power_on_rate_two_decimal_places`
  - `test_unauthenticated_returns_401`
  - `test_post_not_allowed`
- **TestPowerStatusResponseStructure** ［integration］ — 2 用例
  - `test_response_structure_complete`
  - `test_response_types`
- **TestPowerStatusQueryCount** ［integration］ — 1 用例
  - `test_query_count_no_n_plus_one`
- **TestPowerStatusURL** ［integration］ — 2 用例
  - `test_url_registered_and_accessible`
  - `test_url_reverse`
- **TestFrontendCodeReview** ［integration］ — 7 用例
  - `test_ac201_power_status_card_exists_in_homeview`
  - `test_ac201_top_cards_row_layout`
  - `test_ac202_data_bindings_present`
  - `test_ac203_mode_distribution_bindings`
  - `test_ac204_v_loading_present`
  - `test_ac205_el_card_used`
  - `test_no_refresh_button_oq003`

### `api/tests/test_device_cards.py`

- **TestDeviceConfigModel** ［unit］ — 6 用例
  - `test_create_device_config`
  - `test_param_name_sub_type_unique_constraint`
  - `test_same_param_in_different_subtypes`
  - `test_is_active_default_true`
  - `test_str_representation`
  - `test_multiple_params_in_same_sub_type`
- **TestDeviceParamHistoryModel** ［unit］ — 5 用例
  - `test_create_history_record`
  - `test_multiple_records_same_specific_part_param`
  - `test_value_can_be_null`
  - `test_str_representation`
  - `test_multiple_specific_parts_isolated`
- **TestDeviceRealtimeParamsAPI** ［integration］ — 13 用例
  - `test_missing_specific_part_returns_400`
  - `test_response_structure`
  - `test_nested_structure`
  - `test_params_listed_correctly`
  - `test_group_filter`
  - `test_group_filter_no_match`
  - `test_inactive_config_excluded`
  - `test_stale_params_flagged`
  - `test_fresh_params_not_stale`
  - `test_specific_part_isolation`
  - `test_param_without_plc_data_excluded`
  - `test_energy_meter_params_in_device_panel`
  - `test_unauthenticated_access_allowed`
- **TestDeviceParamHistoryAPI** ［integration］ — 17 用例
  - `test_missing_specific_part_returns_400`
  - `test_basic_paginated_response`
  - `test_results_ordered_by_collected_at_desc`
  - `test_param_name_filter`
  - `test_sub_type_filter`
  - `test_sub_type_filter_no_match`
  - `test_start_time_filter`
  - `test_end_time_filter`
  - `test_pagination`
  - `test_pagination_page_2`
  - `test_nonexistent_specific_part_returns_empty_list`
  - `test_specific_part_data_isolation`
  - `test_response_field_format`
  - `test_collected_at_format`
  - `test_unauthenticated_access_allowed`
  - `test_default_page_size_is_50`
  - `test_specific_part_in_response`

### `api/tests/test_device_list_fault_filter.py`

- **TestFaultStatusFilterLogicUnit** ［unit］ — 8 用例
  - `test_has_fault_returns_only_positive_fault_count`
  - `test_no_fault_returns_only_zero_fault_count`
  - `test_none_device_excluded_from_has_fault`
  - `test_none_device_excluded_from_no_fault`
  - `test_no_fault_status_param_returns_all_owners_with_null_fault_count`
  - `test_invalid_fault_status_value_is_ignored`
  - `test_count_reflects_filtered_total_has_fault`
  - `test_count_reflects_filtered_total_no_fault`
- **TestFaultStatusFilterIntegration** ［integration］ — 8 用例
  - `test_pagination_total_correct_has_fault`
  - `test_pagination_total_correct_no_fault`
  - `test_screen_status_and_fault_status_combination`
  - `test_no_extra_db_query_when_fault_status_present`
  - `test_no_extra_db_query_no_fault`
  - `test_no_fault_status_still_queries_page_rows`
  - `test_page1_count_correct_simulates_45_devices`
  - `test_out_of_range_page_returns_empty_results`
- **TestFaultStatusFilterE2E** ［e2e］ — 4 用例
  - `test_e2e_has_fault_with_real_data`
  - `test_e2e_no_fault_with_real_data`
  - `test_e2e_nodata_device_appears_without_filter`
  - `test_e2e_nodata_excluded_from_both_sides`

### `api/tests/test_device_management.py`

- **TC_U_001_ScreenConnectivityStatusModel** ［unit］ — 5 用例
  - `test_create_status_record`
  - `test_unique_specific_part_constraint`
  - `test_str_representation`
  - `test_upsert_via_update_or_create`
  - `test_model_has_last_seen_at_not_status`
- **TC_U_002_ScreenConnectivityHandler** ［unit］ — 6 用例
  - `test_handle_online_payload_writes_last_seen_at`
  - `test_handle_offline_payload_noop`
  - `test_handle_online_updates_existing_record`
  - `test_handle_non_dict_payload_is_ignored`
  - `test_handle_missing_specific_part_is_ignored`
  - `test_handle_invalid_status_is_ignored`
- **TC_U_003_ScreenConnectivityChecker** ［unit］ — 10 用例
  - `test_probe_single_returns_true_on_success`
  - `test_probe_single_returns_false_on_nonzero_returncode`
  - `test_probe_single_returns_false_on_timeout`
  - `test_probe_single_returns_false_on_oserror`
  - `test_check_all_skips_empty_ip`
  - `test_check_all_returns_empty_list_for_empty_input`
  - `test_check_all_online_result`
  - `test_check_all_offline_result`
  - `test_check_all_multiple_ips`
  - `test_check_all_exception_in_probe_treated_as_offline`
- **TC_U_004_DeviceListViewFiltering** ［unit］ — 6 用例
  - `test_room_no_filter_building_only`
  - `test_room_no_filter_building_and_unit`
  - `test_room_no_filter_three_segments`
  - `test_room_no_invalid_format_returns_400`
  - `test_room_no_empty_segment_returns_400`
  - `test_no_filter_returns_all`
- **TC_I_001_DeviceListAPIAuth** ［integration］ — 3 用例
  - `test_unauthenticated_request_returns_401`
  - `test_authenticated_user_gets_200`
  - `test_post_method_not_allowed`
- **TC_I_002_DeviceListAPIResponseSchema** ［integration］ — 4 用例
  - `test_response_top_level_keys`
  - `test_result_item_fields`
  - `test_screen_status_is_online`
  - `test_system_switch_display_on`
- **TC_I_003_DeviceListAPIScreenStatusValues** ［integration］ — 6 用例
  - `test_screen_status_online`
  - `test_screen_status_offline`
  - `test_screen_status_unknown_when_no_record`
  - `test_filter_by_screen_status_online`
  - `test_filter_by_screen_status_offline`
  - `test_filter_by_screen_status_unknown`
- **TC_I_004_DeviceListAPISystemSwitch** ［integration］ — 5 用例
  - `test_system_switch_on_display`
  - `test_system_switch_off_display`
  - `test_system_switch_unknown_display`
  - `test_filter_system_switch_on`
  - `test_filter_system_switch_off`
- **TC_I_005_DeviceListAPIPagination** ［integration］ — 9 用例
  - `test_default_page_size_is_20`
  - `test_page_2_returns_remaining`
  - `test_page_size_10`
  - `test_page_size_large_value_capped_at_2000`
  - `test_page_size_2000_returns_all_records_in_one_page`
  - `test_invalid_page_defaults_to_1`
  - `test_invalid_page_size_defaults_to_20`
  - `test_results_sorted_by_building_unit_room`
  - `test_count_field_reflects_total_not_page_results`
- **TC_I_006_MQTTHandlerIntegration** ［integration］ — 3 用例
  - `test_multiple_online_messages_upsert_single_record`
  - `test_different_specific_parts_create_separate_records`
  - `test_api_reflects_online_status`
- **TC_E2E_US001_NavigationStructure** ［e2e］ — 2 用例
  - `test_device_list_url_is_accessible`
  - `test_url_not_found_for_wrong_path`
- **TC_E2E_US002_DisplayAllDevices** ［e2e］ — 2 用例
  - `test_all_owners_returned`
  - `test_results_contain_specific_part`
- **TC_E2E_US003_RoomNumberFilter** ［e2e］ — 3 用例
  - `test_filter_by_building_segment`
  - `test_filter_by_building_unit`
  - `test_filter_exact_room`
- **TC_E2E_US004_ScreenStatusFilter** ［e2e］ — 3 用例
  - `test_filter_online`
  - `test_filter_offline`
  - `test_filter_unknown`
- **TC_E2E_US005_SystemSwitchFilter** ［e2e］ — 2 用例
  - `test_filter_on`
  - `test_filter_off_includes_zero_and_null`
- **TC_E2E_US006_ScreenStatusPipelineIntegration** ［e2e］ — 2 用例
  - `test_handler_pipeline_online_status_visible_in_api`
  - `test_old_heartbeat_becomes_offline`
- **TC_E2E_US007_DevicePanelEntry** ［e2e］ — 2 用例
  - `test_specific_part_in_each_result`
  - `test_specific_part_format_four_segments`
- **TC_E2E_NFR_Performance** ［e2e］ — 2 用例
  - `test_50_records_returned_with_page_size_50`
  - `test_combined_filters_work_together`
- **TC_I_007_DeviceListAPIPlcStatusFields** ［integration］ — 5 用例
  - `test_plc_status_online`
  - `test_plc_status_offline`
  - `test_plc_status_unknown_when_no_record`
  - `test_screen_last_checked_at_not_in_response`
  - `test_plc_fields_present_in_all_results`
- **TC_I_008_DeviceListAPIPlcStatusFilter** ［integration］ — 5 用例
  - `test_filter_plc_status_online`
  - `test_filter_plc_status_offline`
  - `test_filter_plc_status_does_not_include_unknown`
  - `test_no_plc_filter_returns_all`
  - `test_combined_plc_status_and_room_no_filter`
- **TC_I_009_PlcStatusUnknownDegradation** ［integration］ — 2 用例
  - `test_owner_with_no_plc_record_returns_unknown_status`
  - `test_multiple_owners_mixed_plc_records`
- **TC_I_010_OperationModeField** ［integration］ — 8 用例
  - `test_operation_mode_1_cooling`
  - `test_operation_mode_2_heating`
  - `test_operation_mode_3_ventilation`
  - `test_operation_mode_4_dehumidification`
  - `test_operation_mode_null_when_no_record`
  - `test_operation_mode_fields_present_in_all_results`
  - `test_existing_fields_not_removed`
  - `test_operation_mode_unknown_integer_displays_unknown`
- **TC_E2E_US103_OperationModeColumn** ［e2e］ — 3 用例
  - `test_us103_mode_display_when_data_exists`
  - `test_us104_mode_display_when_no_data`
  - `test_no_model_changes`
- **TC_I_011_RoomNoFilterBuildingUnit** ［integration］ — 4 用例
  - `test_room_no_building_only_returns_all_in_building`
  - `test_room_no_building_unit_returns_correct_unit`
  - `test_room_no_building_unit_excludes_other_units`
  - `test_room_no_building_excludes_other_buildings`
- **TC_I_012_OperationModeFilter** ［integration］ — 8 用例
  - `test_filter_operation_mode_1_cooling`
  - `test_filter_operation_mode_2_heating`
  - `test_filter_operation_mode_3_ventilation`
  - `test_filter_operation_mode_4_dehumidification`
  - `test_filter_operation_mode_excludes_null_records`
  - `test_no_operation_mode_filter_returns_all`
  - `test_invalid_operation_mode_returns_all`
  - `test_combined_operation_mode_and_room_no_filter`

### `api/tests/test_device_name_cache_v061.py`

- **TestGetDeviceNameBySnHit** ［unit］ — 3 用例
  - `test_hit_returns_device_name`
  - `test_hit_with_real_db_fixture`
  - `test_multiple_calls_hit_cache_only_loads_once`
- **TestGetDeviceNameBySnMiss** ［unit］ — 2 用例
  - `test_miss_returns_none`
  - `test_empty_cache_after_load_returns_none`
- **TestTtlExpiry** ［unit］ — 4 用例
  - `test_ttl_expired_triggers_reload`
  - `test_ttl_not_expired_skips_reload`
  - `test_exactly_at_ttl_boundary_triggers_reload`
  - `test_just_over_ttl_triggers_reload`
- **TestInvalidateCache** ［unit］ — 3 用例
  - `test_invalidate_sets_loaded_at_to_zero`
  - `test_invalidate_then_get_triggers_load`
  - `test_invalidate_idempotent`
- **TestLoadCacheExceptionSafety** ［unit］ — 2 用例
  - `test_exception_does_not_raise_to_caller`
  - `test_exception_preserves_old_cache`

### `api/tests/test_device_settings.py`

- **PLCWriteRecordModelTests** ［unit］ — 5 用例
  - `test_ut_m_01_default_status_pending`
  - `test_ut_m_02_request_id_unique`
  - `test_ut_m_03_str_method`
  - `test_ut_m_04_status_choices`
  - `test_ut_m_05_acked_at_nullable_and_updatable`
- **PLCWriteRecordSerializerTests** ［unit］ — 5 用例
  - `test_ut_s_01_serializes_all_fields`
  - `test_ut_s_02_batch_write_serializer_valid`
  - `test_ut_s_03_rejects_empty_specific_part`
  - `test_ut_s_04_rejects_empty_items`
  - `test_ut_s_05_rejects_too_long_new_value`
- **NormalizeSelectValuesTests** ［unit］ — 4 用例
  - `test_ut_norm_01_array_passthrough`
  - `test_ut_norm_02_object_converted_to_array`
  - `test_ut_norm_03_empty_string_returns_empty_array`
  - `test_ut_norm_04_invalid_json_returns_empty_array`
- **IsWritableTests** ［unit］ — 8 用例
  - `test_ut_w_01_temp_setting_writable`
  - `test_ut_w_02_switch_writable`
  - `test_ut_w_03_temperature_readonly`
  - `test_ut_w_04_humidity_readonly`
  - `test_ut_w_05_dew_point_setting_readonly`
  - `test_ut_w_06_error_readonly`
  - `test_ut_w_07_alert_readonly`
  - `test_ut_w_08_unknown_suffix_readonly`
- **HandleWriteAckTests** ［unit］ — 5 用例
  - `test_ut_ack_01_batch_items_success_updates_status`
  - `test_ut_ack_02_batch_partial_failure_updates_correctly`
  - `test_ut_ack_03_missing_request_id_silently_skipped`
  - `test_ut_ack_04_idempotent_non_pending_not_updated`
  - `test_ut_ack_05_bytes_payload_decoded`

### `api/tests/test_device_settings_e2e.py`

- **E2EHappyPathTest** ［e2e］ — 1 用例
  - `test_e2e_01_batch_write_then_ack_success`
- **E2EPLCWriteFailTest** ［e2e］ — 1 用例
  - `test_e2e_02_ack_failure_marks_record_failed`
- **E2EMQTTUnreachableTest** ［e2e］ — 1 用例
  - `test_e2e_03_mqtt_publish_exception_returns_503`
- **E2EIdempotentAckTest** ［e2e］ — 1 用例
  - `test_e2e_04_duplicate_ack_idempotent`

### `api/tests/test_device_settings_integration.py`

- **GetParamsTests** ［integration］ — 8 用例
  - `test_it_params_01_returns_grouped_params`
  - `test_it_params_02_current_value_null_when_no_latest`
  - `test_it_params_03_readonly_excluded_p5`
  - `test_it_params_04_unauthenticated_returns_401`
  - `test_it_params_05_inactive_configs_excluded`
  - `test_it_params_06_attr_def_fields_present`
  - `test_it_params_07_switch_value_options_returned`
  - `test_it_params_08_select_values_object_normalized_to_array`
- **PostWriteTests** ［integration］ — 7 用例
  - `test_it_write_01_valid_batch_returns_202_and_creates_records`
  - `test_it_write_02_readonly_param_returns_400`
  - `test_it_write_03_unknown_specific_part_returns_404`
  - `test_it_write_04_missing_items_returns_400`
  - `test_it_write_04b_empty_items_returns_400`
  - `test_it_write_05_mqtt_failure_returns_503_and_records_failed`
  - `test_it_write_06_unauthenticated_returns_401`
- **GetRecordsTests** ［integration］ — 7 用例
  - `test_it_records_01_returns_all_records_paginated`
  - `test_it_records_02_filter_by_specific_part`
  - `test_it_records_03_filter_by_status`
  - `test_it_records_04_filter_by_operator`
  - `test_it_records_05_filter_by_time_range`
  - `test_it_records_06_page_size_param`
  - `test_it_records_07_unauthenticated_returns_401`

### `api/tests/test_device_settings_v050.py`

- **IsWritableV050Tests** ［unit］ — 15 用例
  - `test_UT_W_01_operation_mode_writable_via_mode_suffix`
  - `test_UT_W_02_any_mode_suffix_writable`
  - `test_UT_W_03_mode_suffix_not_confused_with_readonly`
  - `test_UT_W_04_away_energy_saving_writable_via_exact_name`
  - `test_UT_W_05_exact_name_does_not_match_partial_name`
  - `test_UT_W_06_readonly_suffix_beats_writable_suffix`
  - `test_UT_W_07_temperature_always_readonly`
  - `test_UT_W_08_fault_suffix_readonly`
  - `test_UT_W_09_alert_suffix_readonly`
  - `test_UT_W_10_error_suffix_readonly`
  - `test_UT_W_11_temp_setting_still_writable`
  - `test_UT_W_12_switch_still_writable`
  - `test_UT_W_13_central_energy_supply_writable`
  - `test_UT_W_14_humidity_readonly`
  - `test_UT_W_15_dew_point_setting_readonly`
- **ParamValueLabelTests** ［unit］ — 13 用例
  - `test_UT_VL_01_operation_mode_returns_four_options`
  - `test_UT_VL_02_away_energy_saving_exact_name_priority`
  - `test_UT_VL_03_switch_suffix_returns_options`
  - `test_UT_VL_04_unknown_param_returns_empty_list`
  - `test_UT_VL_05_exact_name_takes_priority_over_suffix`
  - `test_UT_VL_06_operation_mode_display_value_legacy_zero`
  - `test_UT_VL_07_operation_mode_display_value_cooling`
  - `test_UT_VL_08_operation_mode_display_value_unknown`
  - `test_UT_VL_09_away_energy_saving_display_enabled`
  - `test_UT_VL_10_away_energy_saving_display_disabled`
  - `test_UT_VL_11_none_value_returns_dash`
  - `test_UT_VL_12_switch_display_value`
  - `test_UT_VL_13_temp_setting_display_with_unit`
- **SeedDeviceConfigIdempotencyTests** ［unit］ — 4 用例
  - `test_UT_SD_01_update_or_create_idempotent_for_inactive`
  - `test_UT_SD_02_get_or_create_idempotent_for_active`
  - `test_UT_SD_03_inactive_record_not_reactivated_by_get_or_create`
  - `test_UT_SD_04_no_duplicate_on_reset_mode_simulation`
- **ReqFunc001SystemSwitchTests** ［integration］ — 4 用例
  - `test_IT_REQ001_01_main_thermostat_excludes_system_switch`
  - `test_IT_REQ001_02_hydraulic_module_retains_system_switch`
  - `test_IT_REQ001_03_main_thermostat_other_params_unaffected`
  - `test_IT_REQ001_04_write_to_inactive_system_switch_rejected`
- **ReqFunc002OperationModeTests** ［integration］ — 6 用例
  - `test_IT_REQ002_01_operation_mode_appears_in_params`
  - `test_IT_REQ002_02_operation_mode_has_four_value_options`
  - `test_IT_REQ002_03_operation_mode_display_value_from_plc`
  - `test_IT_REQ002_04_write_operation_mode_heating_succeeds`
  - `test_IT_REQ002_05_write_all_four_mode_values`
  - `test_IT_REQ002_06_write_illegal_value_99_not_rejected_by_backend`
- **ReqFunc003AwayEnergySavingTests** ［integration］ — 6 用例
  - `test_IT_REQ003_01_away_energy_saving_appears_in_params`
  - `test_IT_REQ003_02_away_energy_saving_has_two_value_options`
  - `test_IT_REQ003_03_away_energy_saving_current_display_value`
  - `test_IT_REQ003_04_write_away_energy_saving_enabled`
  - `test_IT_REQ003_05_write_away_energy_saving_disabled`
  - `test_IT_REQ003_06_away_energy_saving_whitelist_verified`
- **ReqFunc004DirtyFieldsTests** ［integration］ — 5 用例
  - `test_IT_REQ004_01_single_dirty_item_only_one_record_created`
  - `test_IT_REQ004_02_multiple_dirty_items_all_recorded`
  - `test_IT_REQ004_03_final_value_recorded_not_intermediate`
  - `test_IT_REQ004_04_empty_items_rejected_by_serializer`
  - `test_IT_REQ004_05_unchanged_params_not_in_write_payload`
- **RegressionProtectionTests** ［integration］ — 8 用例
  - `test_IT_REG_01_main_thermostat_switch_writable_via_switch_suffix`
  - `test_IT_REG_02_main_thermostat_temp_setting_writable`
  - `test_IT_REG_03_main_thermostat_readonly_fields_still_readonly`
  - `test_IT_REG_04_write_living_room_switch_still_works`
  - `test_IT_REG_05_write_hydraulic_system_switch_still_works`
  - `test_IT_REG_06_central_energy_supply_writable`
  - `test_IT_REG_07_write_readonly_param_still_rejected`
  - `test_IT_REG_08_inactive_config_excluded_from_api_response`
- **FR001InputNumberUndefinedTests** ［integration］ — 4 用例
  - `test_IT_FR1_01_serializer_accepts_undefined_string`
  - `test_IT_FR1_02_undefined_string_reaches_plc_write_record`
  - `test_IT_FR1_03_serializer_rejects_empty_string_as_new_value`
  - `test_IT_FR1_04_none_value_serializer_behavior`
- **V051ModeEnumAlignmentTests** ［integration］ — 13 用例
  - `test_UT_V051_01_mode_enum_key1_is_cooling`
  - `test_UT_V051_02_mode_enum_key2_is_heating`
  - `test_UT_V051_03_mode_enum_key3_is_ventilation`
  - `test_UT_V051_04_mode_enum_key4_is_dehumidification`
  - `test_UT_V051_05_mode_enum_key0_not_in_options`
  - `test_UT_V051_06_mode_legacy_zero_compat_display`
  - `test_UT_V051_07_central_energy_supply_writable`
  - `test_UT_V051_08_central_energy_supply_options`
  - `test_UT_V051_09_central_energy_supply_display_cooling`
  - `test_UT_V051_10_central_energy_supply_display_heating`
  - `test_UT_V051_11_central_energy_supply_display_none`
  - `test_UT_V051_12_central_energy_supply_legacy_zero_display`
  - `test_UT_V051_13_mode_key4_not_equal_to_1_in_options`
- **V051CentralEnergySupplyWriteTests** ［integration］ — 10 用例
  - `test_IT_V051_01_write_central_energy_supply_cooling`
  - `test_IT_V051_02_write_central_energy_supply_heating`
  - `test_IT_V051_03_write_central_energy_supply_none_value3`
  - `test_IT_V051_04_is_writable_central_energy_supply_true`
  - `test_IT_V051_05_operation_mode_still_writable`
  - `test_IT_V051_06_write_central_energy_supply_value0_rejected`
  - `test_IT_V051_07_write_central_energy_supply_value4_rejected`
  - `test_IT_FR1_05_recommended_frontend_fix_string_coercion`
  - `test_IT_FR1_06_operation_mode_none_display_value`
  - `test_IT_FR1_07_serializer_max_length_rejects_undefined_repeated`
- **SerializerV050CompatibilityTests** ［integration］ — 3 用例
  - `test_UT_SER_01_operation_mode_accepted_in_serializer`
  - `test_UT_SER_02_away_energy_saving_accepted_in_serializer`
  - `test_UT_SER_03_mixed_v050_params_accepted`
- **FR001HotfixVerificationTests** ［integration］ — 7 用例
  - `test_IT_FR1FIX_01_cleared_input_number_excluded_from_payload`
  - `test_IT_FR1FIX_02_cleared_then_reinput_submits_correctly`
  - `test_IT_FR1FIX_03_mixed_fields_only_valid_dirty_submitted`
  - `test_IT_FR1FIX_04_defensive_filter_blocks_undefined_if_dirty_not_cleaned`
  - `test_IT_FR1FIX_05_valid_number_zero_not_blocked_by_filter`
  - `test_IT_FR1FIX_06_no_undefined_string_in_write_record_after_fix`
  - `test_IT_FR1FIX_07_regression_existing_72_tests_baseline_maintained`

### `api/tests/test_device_tree_sync_lock_fix.py`

- **SingleOwnerSyncTest** ［integration］ — 4 用例
  - `test_tc_lock_01_001_attr_def_created_by_pre_pass`
  - `test_tc_lock_01_002_upsert_tree_full_path`
  - `test_tc_lock_01_003_pre_pass_idempotent`
  - `test_tc_lock_01_004_stats_attr_defs_new_zero_on_second_sync`
- **ConcurrentSyncLockTest** ［integration］ — 2 用例
  - `test_tc_lock_02_001_concurrent_4_workers_same_product_code`
  - `test_tc_lock_02_002_concurrent_data_integrity`
- **AttrDefFallbackTest** ［integration］ — 2 用例
  - `test_tc_lock_03_001_fallback_get_or_create_on_does_not_exist`
  - `test_tc_lock_03_002_no_fallback_needed_when_pre_pass_succeeds`

### `api/tests/test_dph_cleanup_service.py`

- **TC_U_DPH_001_OperationalError_Graceful** ［unit］ — 3 用例
  - `test_operational_error_does_not_propagate`
  - `test_operational_error_writes_stderr`
  - `test_operational_error_calls_connection_close`
- **TC_U_DPH_002_GenericException_Graceful** ［unit］ — 3 用例
  - `test_generic_exception_does_not_propagate`
  - `test_generic_exception_writes_stderr`
  - `test_generic_exception_calls_connection_close`
- **TC_U_DPH_003_CronLoop_RunCleanup_Error** ［unit］ — 2 用例
  - `test_run_cleanup_operational_error_does_not_escape_job`
  - `test_cron_loop_continues_after_run_cleanup_error`
- **TC_U_DPH_004_CronLoop_ScheduleError** ［unit］ — 1 用例
  - `test_main_loop_catches_schedule_exception`
- **TC_U_DPH_005_OnceModeOperationalError** ［unit］ — 1 用例
  - `test_once_mode_exits_cleanly_on_operational_error`
- **TC_U_DPH_006_OnceModeGenericException** ［unit］ — 1 用例
  - `test_once_mode_exits_cleanly_on_generic_exception`
- **TC_U_DPH_007_DryRun** ［unit］ — 2 用例
  - `test_dry_run_no_delete_called`
  - `test_dry_run_outputs_estimated_rows`
- **TC_U_DPH_008_NoExpiredData** ［unit］ — 1 用例
  - `test_no_expired_data_returns_cleanly`
- **TC_U_DPH_009_NormalDeletion** ［unit］ — 2 用例
  - `test_normal_deletion_executes_delete`
  - `test_sleep_called_between_batches`
- **TC_U_DPH_012_SetupScheduleValid** ［unit］ — 2 用例
  - `test_daily_cron_registers_job`
  - `test_custom_cron_time_registered`
- **TC_U_DPH_013_SetupScheduleInvalid** ［unit］ — 2 用例
  - `test_invalid_cron_falls_back_to_default`
  - `test_too_few_cron_fields_falls_back`
- **TC_U_DPH_014_ApplyDbTimeout** ［unit］ — 1 用例
  - `test_raises_read_and_write_timeout`
- **TC_U_DPH_015_ApplyDbTimeout_NoOp** ［unit］ — 1 用例
  - `test_no_timeout_keys_is_noop`
- **TC_U_DPH_016_ApplyDbTimeout_ClosesConnection** ［unit］ — 1 用例
  - `test_closes_connection_when_changed`
- **TC_U_DPH_017_MaxBatchesCap** ［unit］ — 1 用例
  - `test_run_cleanup_stops_at_max_batches`
- **TC_U_DPH_018_MaxBatchesUnlimited** ［unit］ — 1 用例
  - `test_max_batches_zero_runs_to_completion`
- **TC_U_DPH_019_HandlePassesMaxBatches** ［unit］ — 1 用例
  - `test_handle_passes_max_batches_to_run_cleanup`

### `api/tests/test_fault_event_serializer_v061.py`

- **TestSerializerNewFieldsPresent** ［integration］ — 3 用例
  - `test_device_name_field_present`
  - `test_device_type_label_field_present`
  - `test_both_new_fields_exist_simultaneously`
- **TestSerializerMainPath** ［integration］ — 3 用例
  - `test_device_sn_hit_returns_device_name`
  - `test_device_sn_hit_supersedes_product_code`
  - `test_cache_already_warm_no_reload`
- **TestSerializerFallbackOne** ［integration］ — 2 用例
  - `test_cache_miss_product_code_hit_returns_type_label`
  - `test_various_known_product_codes`
- **TestSerializerFallbackTwo** ［integration］ — 2 用例
  - `test_both_miss_returns_null_null`
  - `test_null_null_preserves_device_sn_field`
- **TestSerializerEdgeCases** ［integration］ — 3 用例
  - `test_non_numeric_device_sn_returns_none_gracefully`
  - `test_empty_device_sn_returns_none_gracefully`
  - `test_all_v061_fields_in_serializer_output`

### `api/tests/test_fault_mgmt_v064_integration.py`

- **TestMigration0028Backfill** ［integration］ — 4 用例
  - `test_backfill_fills_room_name_for_all_connectable_rows`
  - `test_backfill_correct_room_name_per_device_sn`
  - `test_backfill_room_id_valid_fk`
  - `test_backfill_orphan_device_sn_remains_null`
- **TestFaultConsumerWritePath** ［integration］ — 3 用例
  - `test_t1_insert_calls_room_lookup_once`
  - `test_t1_insert_stores_room_in_fault_event`
  - `test_t1_insert_room_lookup_db_exception_fault_event_still_created`
- **TestFaultEventRoomNameFilter** ［integration］ — 6 用例
  - `test_room_name_filter_single_room`
  - `test_room_name_filter_multiple_rooms`
  - `test_invalid_room_name_not_in_whitelist`
  - `test_no_room_name_param_returns_all`
  - `test_room_name_field_in_response`
  - `test_room_name_null_serialized_as_null`
- **TestKeyRegressionScenarios** ［integration］ — 5 用例
  - `test_4room_study_room_panel_returns_1`
  - `test_4room_children_room_panel_returns_1`
  - `test_4room_master_bedroom_panel_returns_1`
  - `test_4room_secondary_bedroom_panel_returns_1`
  - `test_3room_study_room_panel_returns_0`

### `api/tests/test_fault_mgmt_v064_unit.py`

- **TestConstantsStructure** ［unit］ — 8 用例
  - `test_sub_type_room_filter_new_keys_present`
  - `test_old_thermostat_keys_absent`
  - `test_sub_type_labels_keys_match_room_filter`
  - `test_valid_room_names_correct`
  - `test_study_room_panel_room_keywords`
  - `test_sub_type_to_fault_codes_new_keys`
  - `test_sub_type_labels_study_room_panel_label`
  - `test_sub_type_labels_no_fourth_children_thermostat`
- **TestRoomLookup** ［unit］ — 6 用例
  - `test_normal_device_sn_returns_room_info`
  - `test_nonexistent_device_sn_returns_none_none`
  - `test_non_integer_device_sn_returns_none_none`
  - `test_db_exception_returns_none_none`
  - `test_empty_string_device_sn_returns_none_none`
  - `test_multiple_nodes_same_sn_returns_first`
- **TestStateMachineT1RoomLookup** ［unit］ — 3 用例
  - `test_t1_insert_writes_room_name`
  - `test_t1_insert_room_lookup_failure_still_creates_fault_event`
  - `test_t1_insert_calls_room_lookup_once`
- **TestOracleReverseTable** ［unit］ — 3 用例
  - `test_oracle_device_sn_to_ori_room_name`
  - `test_oracle_sub_type_room_keywords_match`
  - `test_three_room_1601_no_study_room`

### `api/tests/test_heartbeat_broker_config.py`

- **TestReadHbcConfig** ［unit］ — 3 用例
  - `test_reads_existing_file`
  - `test_returns_default_when_file_missing`
  - `test_returns_default_on_json_decode_error`
- **TestWriteHbcConfig** ［unit］ — 3 用例
  - `test_writes_and_reads_back`
  - `test_atomic_write_no_tmp_left_on_success`
  - `test_utf8_encoding`
- **TestHostPatternValidation** ［unit］ — 11 用例
  - `test_valid_ipv4`
  - `test_valid_ipv4_localhost_style`
  - `test_valid_domain`
  - `test_valid_subdomain`
  - `test_valid_single_label_tld`
  - `test_invalid_shell_injection`
  - `test_invalid_ampersand`
  - `test_invalid_backtick`
  - `test_invalid_spaces`
  - `test_invalid_empty`
  - `test_invalid_path_traversal`
- **TestPasswordPreservation** ［unit］ — 2 用例
  - `test_empty_password_preserves_original`
  - `test_nonempty_password_overwrites`
- **TestRestartService** ［unit］ — 3 用例
  - `test_success_returns_true`
  - `test_nonzero_returncode_returns_false`
  - `test_timeout_returns_false`
- **TestLoadHeartbeatConfig** ［unit］ — 3 用例
  - `test_loads_valid_config_file`
  - `test_fallback_on_missing_file`
  - `test_fallback_on_bad_json`
- **TestHeartbeatBrokerConfigGetAPI** ［integration］ — 3 用例
  - `test_get_returns_config_with_empty_password`
  - `test_get_returns_all_fields`
  - `test_get_requires_authentication`
- **TestHeartbeatBrokerConfigPutMqttAPI** ［integration］ — 9 用例
  - `test_admin_put_mqtt_success`
  - `test_put_writes_correct_config_fields`
  - `test_non_admin_put_returns_403`
  - `test_unauthenticated_put_returns_401`
  - `test_invalid_host_returns_400`
  - `test_invalid_port_returns_400`
  - `test_invalid_protocol_returns_400`
  - `test_empty_password_preserves_original`
  - `test_nonempty_password_overwrites`
- **TestHeartbeatBrokerConfigPutWssAPI** ［integration］ — 2 用例
  - `test_wss_config_accepted`
  - `test_wss_triggers_service_restart`
- **TestHeartbeatBrokerConfigRestartIntegration** ［integration］ — 3 用例
  - `test_subprocess_called_with_correct_args`
  - `test_restart_failure_returns_500_with_config_saved`
  - `test_restart_timeout_returns_500`
- **TestLegacyMqttCompatibility** ［integration］ — 1 用例
  - `test_legacy_mqtt_address_accepted`

### `api/tests/test_inspection_agent_loop_v110.py`

- **DecisionLoopTest** ［unit］ — 8 用例
  - `test_conclusion_creates_workorder`
  - `test_write_proposal_blocked_policy_b`
  - `test_write_proposal_allowed_policy_a_executes`
  - `test_inactive_event_skipped`
  - `test_decision_exception_fallback_workorder`
  - `test_run_once_processes_polled_events`
  - `test_persistence_failure_resets_pending`
  - `test_duplicate_event_no_second_workorder`

### `api/tests/test_inspection_agent_v110.py`

- **WriteAuthPolicyTest** ［unit］ — 8 用例
  - `test_default_is_policy_b_block`
  - `test_explicit_policy_b_block`
  - `test_invalid_policy_falls_back_to_b`
  - `test_policy_a_tool_not_in_whitelist`
  - `test_policy_a_value_within_bounds`
  - `test_policy_a_value_out_of_bounds`
  - `test_policy_a_non_numeric_and_unknown_param_deny`
  - `test_invalid_whitelist_json_blocks_all`
- **EventPollerTest** ［unit］ — 5 用例
  - `test_poll_claims_and_orders`
  - `test_claimed_events_not_repolled`
  - `test_inactive_and_done_excluded`
  - `test_batch_size_limit`
  - `test_reset_in_progress`
- **WorkOrderCreateTest** ［unit］ — 5 用例
  - `test_generate_ticket_id_format_and_increment`
  - `test_create_from_fault_event`
  - `test_create_from_cw_event_uses_warning_type`
  - `test_duplicate_active_returns_existing`
  - `test_can_recreate_after_resolved`
- **AuditLogTest** ［unit］ — 3 用例
  - `test_workorder_created_record`
  - `test_write_blocked_event_type_mapping`
  - `test_sensitive_keys_redacted`

### `api/tests/test_inspection_ondemand_v130.py`

- **AuditDoubleWriteTest** ［integration］ — 5 用例
  - `test_workorder_created_persists_row`
  - `test_write_blocked_maps_step`
  - `test_lifecycle_steps_persist`
  - `test_step_detail_scrubbed`
  - `test_persist_failure_does_not_raise`
- **TriggerApiTest** ［integration］ — 9 用例
  - `test_unauth_401`
  - `test_bad_event_type_400`
  - `test_missing_event_404`
  - `test_trigger_202_sets_in_progress`
  - `test_trigger_409_when_in_progress`
  - `test_trigger_429_when_busy_elsewhere`
  - `test_stale_in_progress_reclaimed_then_trigger_succeeds`
  - `test_own_stale_in_progress_can_retrigger`
  - `test_retrigger_done_allowed`
- **StatusApiTest** ［integration］ — 2 用例
  - `test_status_fields`
  - `test_status_missing_404`
- **LogsApiTest** ［integration］ — 6 用例
  - `test_unauth_401`
  - `test_list_all`
  - `test_filter_event_type`
  - `test_filter_result`
  - `test_filter_specific_part`
  - `test_pagination`
- **RunThreadTest** ［integration］ — 2 用例
  - `test_thread_runs_process_event_and_logs`
  - `test_thread_resets_pending_on_exception`

### `api/tests/test_inspection_workorder_v110.py`

- **SchemaTest** ［unit］ — 3 用例
  - `test_fault_event_has_inspection_columns`
  - `test_cw_event_has_inspection_columns`
  - `test_work_order_table_columns`
- **InspectionStatusDefaultTest** ［unit］ — 2 用例
  - `test_fault_event_default_pending`
  - `test_cw_event_default_pending`
- **WorkOrderModelTest** ［unit］ — 4 用例
  - `test_create_and_str`
  - `test_duplicate_active_workorder_blocked`
  - `test_inactive_workorder_not_counted`
  - `test_different_events_independent`

### `api/tests/test_langgraph_phase_a.py`

- **PromptLoadingTests** ［unit］ — 5 用例
  - `test_strip_comments`
  - `test_prefers_langgraph_variant_and_strips_comment`
  - `test_falls_back_to_openclaw_md_when_no_variant`
  - `test_missing_files_raise`
  - `test_load_real_repo_prompts_are_langgraph_native`
- **RouterClassifierTests** ［unit］ — 24 用例
  - `test_parse_clean_json`
  - `test_parse_json_fenced`
  - `test_parse_prose_wrapped`
  - `test_parse_filters_invalid_names_and_dedupes`
  - `test_parse_skips_non_name_array_then_finds_valid`
  - `test_parse_empty_or_garbage_returns_none`
  - `test_classify_llm_hit_wins`
  - `test_classify_llm_composite`
  - `test_classify_garbage_falls_back_to_keyword`
  - `test_classify_exception_falls_back_to_keyword`
  - `test_classify_empty_llm_falls_back_then_default`
  - `test_classify_none_llm_uses_keyword`
  - `test_guard_overrides_sanheng_only_on_data_query`
  - `test_guard_keeps_sanheng_for_pure_knowledge`
  - `test_guard_ignores_data_keywords_in_history_prefix`
  - `test_guard_overrides_with_history_when_current_is_data`
  - `test_guard_no_fire_when_data_expert_already_present`
  - `test_guard_overrides_sanheng_only_on_control_request`
  - `test_control_keyword_falls_back_to_energy`
  - `test_guard_excludes_control_concept_from_pure_knowledge`
  - `test_guard_overrides_wrong_data_expert_on_energy_query`
  - `test_guard_keeps_llm_when_keyword_agrees`
  - `test_guard_keeps_llm_when_no_data_keyword`
  - `test_route_ignores_history_uses_current_query`
- **ChatBackendFactoryTests** ［unit］ — 2 用例
  - `test_default_selects_openclaw`
  - `test_switch_selects_langgraph`
- **OrchestratorRoutingTests** ［unit］ — 4 用例
  - `test_router_single_intent`
  - `test_router_composite_intent`
  - `test_run_single_expert`
  - `test_run_parallel_vs_serial_same_experts`
- **FaDirectRoutingTests** ［unit］ — 4 用例
  - `test_resolve_maps_tool_paths_to_views`
  - `test_directclient_unknown_path_returns_404_envelope`
  - `test_default_mode_resolves_http`
  - `test_settings_direct_resolves`
- **FaDirectConnectionHealthTests** ［unit］ — 3 用例
  - `test_get_calls_close_old_connections_before_healthy_view`
  - `test_get_retries_once_on_operational_error_then_succeeds`
  - `test_get_retry_exhausted_returns_error_envelope`
- **UsageDailyParamMappingTests** ［unit］ — 1 用例
  - `test_start_date_maps_to_start_time`
- **DateHintInjectionTests** ［unit］ — 1 用例
  - `test_date_hint_contains_today_and_guidance`
- **LangGraphAdapterTests** ［unit］ — 2 用例
  - `test_stream_chat_yields_content_tuples`
  - `test_failure_raises_openclaw_unavailable`
- **OrchestratorWriteGateTests** ［unit］ — 3 用例
  - `test_write_triggers_confirm_then_executes_on_approve`
  - `test_write_rejected_does_not_execute`
  - `test_approve_executes_with_operator_from_prefix`

### `api/tests/test_langgraph_phase_g.py`

- **ReadKnowledgeDelegationTests** ［unit］ — 4 用例
  - `test_inspection_delegates_knowledge_and_read`
  - `test_knowledge_only_delegation`
  - `test_non_delegating_expert_has_no_delegation_tools`
  - `test_subexpert_depth_limit_no_recursion`
- **WriteDelegationGateTests** ［unit］ — 3 用例
  - `test_delegate_write_triggers_confirm_then_executes`
  - `test_delegate_write_rejected_does_not_execute`
  - `test_delegate_write_approve_executes_with_operator`

### `api/tests/test_main.py`

- **CustomUserModelTest** ［unit］ — 4 用例
  - `test_create_user_default_role`
  - `test_create_admin_user`
  - `test_str_returns_username`
  - `test_department_and_position_optional`
- **PLCDataModelTest** ［unit］ — 3 用例
  - `test_create_plc_data`
  - `test_unique_together_constraint`
  - `test_str_representation`
- **UsageQuantityDailyModelTest** ［unit］ — 2 用例
  - `test_create_record`
  - `test_str_representation`
- **UsageQuantityMonthlyModelTest** ［unit］ — 2 用例
  - `test_create_record`
  - `test_str_representation`
- **PLCConnectionStatusModelTest** ［unit］ — 3 用例
  - `test_create_online_status`
  - `test_default_status_is_offline`
  - `test_specific_part_unique`
- **PLCStatusChangeHistoryModelTest** ［unit］ — 1 用例
  - `test_create_history_record`
- **OwnerInfoUniqueIdTest** ［unit］ — 3 用例
  - `test_lookup_by_unique_id`
  - `test_specific_part_unique`
  - `test_str_representation`
- **ParseSpecificPartTest** ［unit］ — 4 用例
  - `test_three_part_format`
  - `test_four_part_format`
  - `test_invalid_format_returns_defaults`
  - `test_empty_string`
- **DailyUsageCalculatorTest** ［unit］ — 7 用例
  - `test_creates_new_daily_record_when_none_exists`
  - `test_updates_existing_daily_record`
  - `test_creates_next_day_record`
  - `test_fills_previous_day_incomplete_records`
  - `test_no_plc_data_returns_zero_processed`
  - `test_multiple_rooms_and_modes`
  - `test_accepts_date_object`
- **MonthlyUsageCalculatorTest** ［unit］ — 5 用例
  - `test_basic_monthly_aggregation`
  - `test_updates_existing_monthly_record`
  - `test_skips_when_no_daily_data`
  - `test_clamps_negative_usage_to_zero`
  - `test_invalid_date_type_returns_error`
- **PLCDataCleanerTest** ［unit］ — 4 用例
  - `test_cleans_all_when_days_zero`
  - `test_no_records_to_delete_with_large_days`
  - `test_no_records_at_all`
  - `test_deletes_old_records_via_mock`
- **PLCDataHandlerTest** ［unit］ — 7 用例
  - `test_saves_valid_data_point`
  - `test_skips_failed_data_point`
  - `test_upsert_updates_value_for_same_key`
  - `test_missing_specific_part_is_skipped`
  - `test_parses_building_info_from_four_part_specific_part`
  - `test_handle_improved_format`
  - `test_non_energy_params_are_excluded_from_plc_data`
- **ConnectionStatusHandlerTest** ［unit］ — 6 用例
  - `test_marks_online_when_any_success`
  - `test_marks_offline_when_all_failed`
  - `test_creates_history_on_status_change`
  - `test_no_history_when_status_unchanged`
  - `test_parse_four_part_specific_part`
  - `test_parse_three_part_specific_part`
- **HealthCheckAPITest** ［integration］ — 1 用例
  - `test_health_check_returns_200`
- **AuthAPITest** ［integration］ — 7 用例
  - `test_login_success`
  - `test_login_wrong_password`
  - `test_login_missing_fields`
  - `test_logout_success`
  - `test_logout_requires_auth`
  - `test_get_current_user`
  - `test_get_current_user_unauthenticated`
- **ChangePasswordAPITest** ［integration］ — 3 用例
  - `test_change_password_success`
  - `test_change_password_wrong_current`
  - `test_change_password_missing_fields`
- **UserManagementAPITest** ［integration］ — 5 用例
  - `test_admin_can_list_users`
  - `test_regular_cannot_list_users`
  - `test_admin_create_user`
  - `test_admin_create_duplicate_username`
  - `test_regular_cannot_create_user`
- **UsageQuantityAPITest** ［integration］ — 6 用例
  - `test_get_all_records_no_filter`
  - `test_filter_by_specific_part`
  - `test_filter_by_energy_mode`
  - `test_filter_by_date_range`
  - `test_pagination`
  - `test_sorted_by_time_period`
- **UsageQuantitySpecificTimePeriodAPITest** ［integration］ — 3 用例
  - `test_aggregation_returns_min_initial_max_final`
  - `test_empty_result_when_no_data`
  - `test_energy_mode_filter_isolation`
- **UsageQuantityMonthlyAPITest** ［integration］ — 6 用例
  - `test_get_all_records`
  - `test_filter_by_specific_part`
  - `test_filter_by_energy_mode`
  - `test_filter_by_usage_month`
  - `test_filter_by_month_range`
  - `test_pagination`
- **PLCConnectionStatusAPITest** ［integration］ — 8 用例
  - `test_list_all_devices`
  - `test_statistics_included`
  - `test_filter_by_connection_status`
  - `test_filter_by_building`
  - `test_detail_returns_device`
  - `test_detail_not_found`
  - `test_status_history_empty`
  - `test_status_history_ordered_descending`
- **BillingAPITest** ［integration］ — 12 用例
  - `test_success_returns_200_with_data`
  - `test_missing_screenmac_returns_400`
  - `test_unknown_screenmac_returns_404`
  - `test_energy_type_filter_cooling`
  - `test_energy_type_filter_heating`
  - `test_bill_amount_calculation`
  - `test_billing_cycle_format`
  - `test_billing_date_is_last_day_of_month`
  - `test_date_format_yyyymm_conversion`
  - `test_family_name_format`
  - `test_charge_items_format`
  - `test_no_data_returns_empty_list`
- **UserRegisterAPITest** ［integration］ — 4 用例
  - `test_register_success_returns_201_with_token`
  - `test_register_password_mismatch_returns_400`
  - `test_register_missing_password_returns_400`
  - `test_register_duplicate_username_returns_400`
- **DashboardTotalEnergyAPITest** ［integration］ — 7 用例
  - `test_default_returns_current_year`
  - `test_custom_date_range`
  - `test_no_data_returns_zeros`
  - `test_unauthenticated_returns_401`
  - `test_invalid_start_date_returns_400`
  - `test_invalid_end_date_returns_400`
  - `test_response_contains_date_fields`
- **DashboardSummaryAPITest** ［integration］ — 5 用例
  - `test_today_kwh`
  - `test_month_kwh_includes_today`
  - `test_no_data_returns_zeros`
  - `test_unauthenticated_returns_401`
  - `test_response_contains_date_and_month`
- **DashboardPLCOnlineRateAPITest** ［integration］ — 4 用例
  - `test_all_online`
  - `test_mixed_status`
  - `test_no_devices_returns_zero_rate`
  - `test_unauthenticated_returns_401`
- **DashboardTrendAPITest** ［integration］ — 10 用例
  - `test_default_7_days_returns_7_items`
  - `test_custom_days`
  - `test_today_total_correct`
  - `test_yesterday_total_correct`
  - `test_missing_day_filled_with_zeros`
  - `test_invalid_days_returns_400`
  - `test_days_zero_returns_400`
  - `test_days_exceeds_365_returns_400`
  - `test_unauthenticated_returns_401`
  - `test_result_ordered_by_date_ascending`
- **DashboardServicesAPITest** ［integration］ — 6 用例
  - `test_all_services_active`
  - `test_service_inactive`
  - `test_subprocess_exception_returns_unknown`
  - `test_service_names_in_response`
  - `test_subprocess_called_for_each_service`
  - `test_unauthenticated_returns_401`
- **DashboardActivitiesAPITest** ［integration］ — 9 用例
  - `test_returns_activities`
  - `test_default_limit_20`
  - `test_custom_limit`
  - `test_activity_structure`
  - `test_no_data_returns_empty_list`
  - `test_invalid_limit_returns_400`
  - `test_limit_zero_returns_400`
  - `test_unauthenticated_returns_401`
  - `test_plc_status_change_appears_in_activities`
- **CSRFTokenAPITest** ［integration］ — 2 用例
  - `test_get_csrf_token_returns_200`
  - `test_get_csrf_token_sets_cookie`
- **UserDetailAPITest** ［integration］ — 5 用例
  - `test_admin_can_retrieve_user`
  - `test_admin_can_update_user`
  - `test_admin_can_delete_user`
  - `test_regular_user_cannot_access_detail`
  - `test_nonexistent_user_returns_404`
- **PLCStatusHistoryPaginationTest** ［integration］ — 2 用例
  - `test_pagination_page_size`
  - `test_second_page`
- **UsageQuantityMonthlyFilterTest** ［integration］ — 2 用例
  - `test_filter_by_building`
  - `test_filter_by_room_number`
- **IntegrationTestPLCToUsagePipeline** ［integration］ — 6 用例
  - `test_plc_data_persisted_after_mqtt_message`
  - `test_daily_usage_generated_from_plc_data`
  - `test_monthly_usage_aggregated_from_daily_data`
  - `test_api_returns_daily_data_after_full_pipeline`
  - `test_api_returns_monthly_data_after_full_pipeline`
  - `test_multiple_rooms_full_pipeline`
- **IntegrationTestUserLifecycle** ［integration］ — 3 用例
  - `test_full_user_lifecycle`
  - `test_deleted_user_cannot_login`
  - `test_duplicate_username_rejected_by_admin_create`
- **IntegrationTestPLCStatusFlow** ［integration］ — 6 用例
  - `test_online_creates_status_and_history`
  - `test_offline_after_online_updates_status_and_adds_history`
  - `test_repeated_online_no_extra_history`
  - `test_api_connection_status_reflects_handler_result`
  - `test_api_history_reflects_both_status_changes`
  - `test_last_online_time_set_when_online`
- **IntegrationTestBillingCalculation** ［integration］ — 5 用例
  - `test_cooling_bill_amount_correct`
  - `test_heating_bill_amount_correct`
  - `test_both_modes_returned_without_energy_type_filter`
  - `test_billing_cycle_and_date_format`
  - `test_zero_usage_gives_zero_bill`
- **E2ETestAuthProtection** ［e2e］ — 6 用例
  - `test_logout_requires_auth`
  - `test_get_current_user_requires_auth`
  - `test_change_password_requires_auth`
  - `test_user_list_requires_auth`
  - `test_admin_user_create_requires_auth`
  - `test_user_detail_requires_auth`
- **E2ETestBillingFlow** ［e2e］ — 3 用例
  - `test_login_then_query_billing`
  - `test_csrf_then_billing`
  - `test_billing_flow_with_energy_type_filter`
- **E2ETestPaginationConsistency** ［e2e］ — 4 用例
  - `test_daily_pagination_total_consistent`
  - `test_daily_pagination_no_overlap`
  - `test_daily_pagination_all_pages_cover_total`
  - `test_monthly_pagination_total_consistent`
- **E2ETestFilterCombinations** ［e2e］ — 5 用例
  - `test_filter_building_only`
  - `test_filter_energy_mode_and_date_range`
  - `test_filter_specific_part_and_energy_mode`
  - `test_specific_time_period_filter_combinations`
  - `test_monthly_building_unit_room_energy_combination`
- **E2ETestPLCStatisticsConsistency** ［e2e］ — 6 用例
  - `test_online_plus_offline_equals_total`
  - `test_online_rate_calculation`
  - `test_all_online_rate_is_100`
  - `test_all_offline_rate_is_0`
  - `test_empty_devices_rate_is_0`
  - `test_statistics_stable_across_pages`
- **IntegrationTestManagementCommands** ［integration］ — 13 用例
  - `test_daily_usage_service_run_once_processes_data`
  - `test_daily_usage_service_run_once_with_explicit_date`
  - `test_daily_usage_service_no_plc_data_does_not_crash`
  - `test_daily_usage_service_invalid_date_returns_gracefully`
  - `test_monthly_usage_service_run_once_processes_data`
  - `test_monthly_usage_service_run_once_with_explicit_month`
  - `test_monthly_usage_service_no_data_does_not_crash`
  - `test_monthly_usage_service_calculate_method_called`
  - `test_plc_cleanup_service_once_deletes_old_data`
  - `test_plc_cleanup_service_once_no_data_does_not_crash`
  - `test_plc_cleanup_service_days_parameter_respected`
  - `test_plc_cleanup_command_run_cleanup_task_method`
  - `test_daily_usage_service_calculate_method_called`
- **DphCleanupServiceWhitelistTest** ［unit］ — 17 用例
  - `test_dph_cleanup_in_monitored_services_list`
  - `test_dph_cleanup_in_monitored_services_set`
  - `test_monitored_services_count_is_twenty`
  - `test_service_list_contains_dph_cleanup`
  - `test_service_list_dph_cleanup_active_state`
  - `test_service_list_dph_cleanup_inactive`
  - `test_service_list_unauthenticated_returns_401`
  - `test_service_detail_dph_cleanup_accessible`
  - `test_service_detail_unknown_service_rejected`
  - `test_action_start_dph_cleanup_accepted`
  - `test_action_stop_dph_cleanup_accepted`
  - `test_action_restart_dph_cleanup_accepted`
  - `test_action_unknown_service_rejected`
  - `test_action_unauthenticated_returns_401`
  - `test_dashboard_services_contains_dph_cleanup`
  - `test_dashboard_services_dph_cleanup_is_active_true`
  - `test_dashboard_services_dph_cleanup_inactive_is_active_false`

### `api/tests/test_memory_chat_memory.py`

- **CreateSessionTest** ［unit］ — 1 用例
  - `test_creates_session_in_db`
- **CloseSessionTest** ［unit］ — 1 用例
  - `test_sets_ended_at`
- **AppendMessageTest** ［unit］ — 4 用例
  - `test_append_user_message`
  - `test_append_assistant_message`
  - `test_invalid_role_raises`
  - `test_messages_stored_in_db`
- **LoadHistoryTest** ［unit］ — 8 用例
  - `test_empty_history`
  - `test_basic_history_returned`
  - `test_limit_truncates_oldest`
  - `test_limit_zero_returns_empty`
  - `test_cross_user_isolation`
  - `test_cross_session_history`
  - `test_override_settings_inject_turns`
  - `test_result_is_list_of_dicts`
- **LoadHistoryDegradationTest** ［unit］ — 1 用例
  - `test_db_error_in_load_history_is_catchable`
- **BuildInjectPrefixTest** ［unit］ — 6 用例
  - `test_empty_history_returns_empty_string`
  - `test_normal_history_format`
  - `test_prefix_ends_with_newline`
  - `test_major001_odd_messages_no_crash`
  - `test_single_user_message`
  - `test_role_labels`
- **ClearMemoryTest** ［unit］ — 3 用例
  - `test_clears_all_sessions`
  - `test_clear_only_affects_target_user`
  - `test_clear_empty_memory_returns_zero`
- **GetSessionsTest** ［unit］ — 5 用例
  - `test_returns_correct_total`
  - `test_pagination_page1`
  - `test_pagination_page2`
  - `test_session_dict_fields`
  - `test_empty_user_returns_empty`

### `api/tests/test_memory_consumer_v13.py`

- **ConsumerSessionCreationTest** ［integration］ — 2 用例
  - `test_connect_creates_chat_session`
  - `test_disconnect_sets_ended_at`
- **ConsumerMessageWriteTest** ［integration］ — 2 用例
  - `test_stream_end_writes_assistant_message`
  - `test_user_message_written_before_stream`
- **ConsumerHistoryInjectionTest** ［integration］ — 2 用例
  - `test_history_prefix_passed_to_openclaw`
  - `test_empty_history_no_prefix`
- **ConsumerCrossUserIsolationTest** ［integration］ — 1 用例
  - `test_user_b_does_not_see_user_a_history`
- **ConsumerDegradationTest** ［integration］ — 3 用例
  - `test_create_session_failure_ws_still_connects`
  - `test_load_history_failure_chat_still_works`
  - `test_append_message_failure_chat_continues`
- **ConsumerInjectTurnsZeroTest** ［integration］ — 1 用例
  - `test_inject_turns_zero_no_prefix`
- **ConsumerReasoningStreamRegressionTest** ［integration］ — 3 用例
  - `test_reasoning_token_sequence_unchanged`
  - `test_no_reasoning_sequence_compat`
  - `test_reasoning_end_only_once`

### `api/tests/test_memory_models.py`

- **ChatSessionCRUDTest** ［unit］ — 5 用例
  - `test_create_session`
  - `test_read_session`
  - `test_update_ended_at`
  - `test_delete_session`
  - `test_str_representation`
- **ChatSessionCascadeTest** ［unit］ — 1 用例
  - `test_cascade_on_user_delete`
- **ChatSessionIsolationTest** ［unit］ — 1 用例
  - `test_user_isolation`
- **ChatSessionIndexTest** ［unit］ — 1 用例
  - `test_index_fields`
- **ChatMessageCRUDTest** ［unit］ — 5 用例
  - `test_create_user_message`
  - `test_create_assistant_message`
  - `test_message_ordering_by_created_at`
  - `test_delete_message`
  - `test_str_representation`
- **ChatMessageCascadeTest** ［unit］ — 2 用例
  - `test_cascade_on_session_delete`
  - `test_cascade_on_user_delete_removes_messages`
- **ChatMessageIndexTest** ［unit］ — 1 用例
  - `test_index_fields`
- **ChatMessageRelatedManagerTest** ［unit］ — 2 用例
  - `test_related_manager`
  - `test_user_sessions_related_manager`

### `api/tests/test_memory_skeleton_guard_sh.py`

- **SkeletonGuardInitTest** ［unit］ — 3 用例
  - `test_init_creates_hash_file`
  - `test_init_hash_file_contains_all_skeleton_files`
  - `test_init_output_mentions_ok`
- **SkeletonGuardVerifyTest** ［unit］ — 5 用例
  - `test_verify_pass_when_files_unchanged`
  - `test_verify_fail_when_file_modified`
  - `test_verify_fail_when_hash_file_missing`
  - `test_verify_output_per_file_pass_markers`
  - `test_verify_fail_shows_changed_file`
- **SkeletonGuardStatusTest** ［unit］ — 2 用例
  - `test_status_exits_zero`
  - `test_status_lists_skeleton_files`
- **SkeletonGuardInvalidCommandTest** ［unit］ — 2 用例
  - `test_invalid_command_shows_usage`
  - `test_no_args_shows_usage`

### `api/tests/test_memory_views.py`

- **MyMemoryViewGetTest** ［integration］ — 7 用例
  - `test_get_returns_200`
  - `test_get_returns_session_list`
  - `test_get_unauthenticated_returns_403`
  - `test_get_only_returns_own_sessions`
  - `test_get_pagination_page_size`
  - `test_get_page_size_capped_at_100`
  - `test_get_empty_returns_empty_list`
- **MyMemoryViewDeleteTest** ［integration］ — 5 用例
  - `test_delete_clears_own_memory`
  - `test_delete_unauthenticated_returns_403`
  - `test_delete_does_not_affect_other_users`
  - `test_delete_empty_memory_ok`
  - `test_delete_returns_message_field`
- **AdminMemoryViewGetTest** ［integration］ — 6 用例
  - `test_admin_get_target_user_sessions`
  - `test_normal_user_access_admin_returns_403`
  - `test_unauthenticated_access_admin_returns_403`
  - `test_admin_get_nonexistent_user_returns_404`
  - `test_admin_get_pagination`
  - `test_admin_get_page_size_capped`
- **AdminMemoryViewDeleteTest** ［integration］ — 5 用例
  - `test_admin_delete_target_user_sessions`
  - `test_normal_user_admin_delete_returns_403`
  - `test_admin_delete_nonexistent_user_returns_404`
  - `test_admin_delete_returns_target_user_field`
  - `test_admin_delete_does_not_affect_other_users`

### `api/tests/test_mqtt_worker_conn_poison_heal.py`

- **TestIsDbConnectionError** ［unit］ — 3 用例
  - `test_atomic_block_poison_is_connection_error`
  - `test_operational_errors_are_connection_errors`
  - `test_business_errors_are_not_connection_errors`
- **TestWorkerLoopHeal** ［unit］ — 3 用例
  - `test_worker_heals_on_atomic_poison`
  - `test_worker_heals_on_server_gone_away`
  - `test_worker_does_not_reconnect_on_business_error`

### `api/tests/test_openclaw_integration.py`

- **TestChatConsumerIntegration** ［integration］ — 9 用例
  - `test_valid_token_connects`
  - `test_no_token_rejected`
  - `test_invalid_token_rejected`
  - `test_chat_message_flow`
  - `test_openclaw_unavailable_error`
  - `test_openclaw_timeout_error`
  - `test_no_db_writes_during_chat`
  - `test_non_chat_message_ignored`
  - `test_session_key_consistency`

### `api/tests/test_openclaw_unit.py`

- **TestUrlNormalization** ［unit］ — 4 用例
  - `test_http_to_ws`
  - `test_https_to_wss`
  - `test_ws_passthrough`
  - `test_bare_host`
- **TestConnectFrameBuilder** ［unit］ — 1 用例
  - `test_connect_frame_shape`
- **TestChatSendFrameBuilder** ［unit］ — 1 用例
  - `test_chat_send_frame_shape`
- **TestStreamChat** ［unit］ — 15 用例
  - `test_token_not_configured_raises`
  - `test_normal_flow_yields_deltas`
  - `test_chinese_deltas`
  - `test_empty_delta_text_filtered`
  - `test_sends_connect_then_chat_send`
  - `test_ws_connect_url_normalized`
  - `test_aborted_event_raises`
  - `test_error_event_raises_with_kind_and_message`
  - `test_connect_rejected_raises`
  - `test_chat_send_rejected_scope_error`
  - `test_stream_ends_without_final_raises`
  - `test_ws_closed_mid_stream_raises`
  - `test_connect_failure_raises`
  - `test_events_for_other_runid_are_ignored`
  - `test_gateway_token_never_appears_in_yielded_chunks`
- **TestGetUserByToken** ［unit］ — 4 用例
  - `test_valid_token_returns_user`
  - `test_invalid_token_returns_none`
  - `test_empty_token_returns_none`
  - `test_none_token_returns_none`

### `api/tests/test_owner.py`

- **OwnerInfoModelTest** ［unit］ — 3 用例
  - `test_tc_m_001_create_owner`
  - `test_tc_m_002_unique_specific_part`
  - `test_tc_m_003_str_representation`
- **OwnerInfoSerializerTest** ［unit］ — 5 用例
  - `test_tc_s_001_valid_data`
  - `test_tc_s_002_missing_specific_part`
  - `test_tc_s_003_specific_part_too_long`
  - `test_tc_s_004_missing_room_number`
  - `test_tc_s_005_readonly_fields`
- **OwnerAPITest** ［integration］ — 17 用例
  - `test_tc_a_001_unauthenticated_list`
  - `test_tc_a_002_regular_user_list`
  - `test_tc_a_003_admin_list`
  - `test_tc_a_004_filter_by_building`
  - `test_tc_a_005_search_by_keyword`
  - `test_tc_a_006_filter_by_bind_status`
  - `test_tc_a_007_admin_create`
  - `test_tc_a_008_regular_user_create_forbidden`
  - `test_tc_a_009_duplicate_specific_part`
  - `test_tc_a_010_missing_required_field`
  - `test_tc_a_011_get_detail_exists`
  - `test_tc_a_012_get_detail_not_found`
  - `test_tc_a_013_admin_patch`
  - `test_tc_a_014_regular_user_patch_forbidden`
  - `test_tc_a_015_admin_delete`
  - `test_tc_a_016_regular_user_delete_forbidden`
  - `test_tc_a_017_pagination`
- **ImportAllOwnersCommandTest** ［integration］ — 3 用例
  - `test_tc_cmd_001_first_import`
  - `test_tc_cmd_002_idempotent_import`
  - `test_tc_cmd_003_file_not_found`

### `api/tests/test_owner_sprint2.py`

- **DeviceListPageSizeTest** ［integration］ — 5 用例
  - `test_tc_us01_001_page_size_capped_at_50`
  - `test_tc_us01_002_page_size_2000_capped_at_50`
  - `test_tc_us01_003_page_size_20_normal`
  - `test_tc_us01_004_page_size_50_boundary`
  - `test_tc_us01_005_page_size_51_capped`
- **OwnerRoomCountTest** ［integration］ — 6 用例
  - `test_tc_us02_001_room_count_zero_no_tree`
  - `test_tc_us02_002_room_count_correct_single_floor`
  - `test_tc_us02_003_room_count_correct_multi_floor`
  - `test_tc_us02_004_room_count_multiple_owners_independent`
  - `test_tc_us02_005_room_count_in_response_field`
  - `test_tc_us02_006_no_n_plus_1_query`
- **OwnerDeviceTreeAPITest** ［integration］ — 9 用例
  - `test_tc_us03_001_unauthenticated_returns_401`
  - `test_tc_us03_002_regular_user_can_access`
  - `test_tc_us03_003_admin_can_access`
  - `test_tc_us03_004_not_found_returns_404`
  - `test_tc_us03_005_empty_tree_no_floors`
  - `test_tc_us03_006_full_tree_structure`
  - `test_tc_us03_007_response_contains_location_name`
  - `test_tc_us03_008_no_n_plus_1_prefetch`
  - `test_tc_us03_009_device_system_flag_values`
- **OwnerBatchSyncTest** ［integration］ — 5 用例
  - `test_tc_us04_001_no_auth_returns_401`
  - `test_tc_us04_002_empty_body_triggers_full_sync`
  - `test_tc_us04_003_explicit_specific_parts_overrides_full`
  - `test_tc_us04_004_task_status_endpoint_reachable`
  - `test_tc_us04_005_exclude_empty_unique_id`
- **OwnerIntegrationTest** ［integration］ — 3 用例
  - `test_tc_int_001_room_count_consistent_with_device_tree`
  - `test_tc_int_002_room_count_zero_owner_has_empty_tree`
  - `test_tc_int_003_owner_list_still_works_after_annotate`

### `api/tests/test_plc_latest.py`

- **TestPLCLatestDataHandlerBasic** ［unit］ — 8 用例
  - `test_success_params_are_persisted`
  - `test_failed_params_are_discarded`
  - `test_energy_params_written_to_latest`
  - `test_upsert_updates_existing_record`
  - `test_building_info_parsed_from_specific_part`
  - `test_collected_at_is_parsed`
  - `test_unsupported_payload_format_ignored`
  - `test_all_failed_params_writes_nothing`
- **TestHistoryHourlyDedup** ［unit］ — 5 用例
  - `test_general_param_same_hour_deduped`
  - `test_general_param_new_hour_writes`
  - `test_energy_param_same_hour_deduped`
  - `test_energy_param_new_hour_writes`
  - `test_energy_and_general_dedup_independent`
- **TestPLCLatestDataAPI** ［integration］ — 7 用例
  - `test_list_all_params_for_device`
  - `test_filter_by_param_name`
  - `test_collected_at_format_in_response`
  - `test_unknown_device_returns_empty_params`
  - `test_missing_specific_part_returns_400`
  - `test_unauthenticated_request_returns_401`
  - `test_device_data_isolation`

### `api/tests/test_reasoning_stream.py`

- **ChatConsumerReasoningProtocolTest** ［integration］ — 2 用例
  - `test_reasoning_then_content_message_sequence`
  - `test_reasoning_end_sent_only_once`
- **ChatConsumerNoReasoningCompatTest** ［integration］ — 1 用例
  - `test_no_reasoning_sequence_is_compat`
- **AdapterDeltaParseLogicTest** ［integration］ — 9 用例
  - `test_TC_UNIT_001_reasoning_and_content_same_frame_order`
  - `test_TC_UNIT_002_content_only_no_reasoning`
  - `test_TC_UNIT_003_reasoning_only_no_deltaText`
  - `test_TC_UNIT_004_kind_reasoning_fallback_path`
  - `test_TC_UNIT_005_empty_texts_not_yielded`
  - `test_TC_UNIT_005b_empty_reasoning_field_with_empty_deltatext`
  - `test_TC_UNIT_006_yield_types_are_tuple_of_two_strings`
  - `test_TC_UNIT_004b_kind_content_uses_deltatext_normally`
  - `test_TC_UNIT_reasoning_field_takes_priority_over_kind`
- **AdapterBuildChatSendFrameTest** ［integration］ — 8 用例
  - `test_TC_UNIT_007_low_injects_thinking`
  - `test_TC_UNIT_008a_medium_injects_thinking`
  - `test_TC_UNIT_008b_high_injects_thinking`
  - `test_extended_thinking_values_injected`
  - `test_TC_UNIT_009_invalid_value_not_injected`
  - `test_TC_UNIT_010_empty_string_not_injected`
  - `test_frame_structure_invariants`
  - `test_reasoning_effort_none_not_injected`
- **AdapterReasoningEffortWarningTest** ［integration］ — 2 用例
  - `test_TC_UNIT_009_warning_on_invalid_effort_via_module_logic`
  - `test_valid_effort_no_warning`
- **AdapterGetConfigReasoningEffortTest** ［integration］ — 2 用例
  - `test_reads_reasoning_effort_from_settings`
  - `test_defaults_to_empty_string_when_not_set`
- **AdapterToWsUrlTest** ［integration］ — 6 用例
  - `test_TC_UNIT_015_http_to_ws`
  - `test_TC_UNIT_016_https_to_wss`
  - `test_TC_UNIT_017_ws_passthrough`
  - `test_TC_UNIT_018_no_protocol_prefix`
  - `test_TC_UNIT_019_trailing_slash_not_doubled`
  - `test_wss_passthrough`
- **AdapterStatLogTest** ［integration］ — 4 用例
  - `test_TC_UNIT_011_stream_complete_log_format_has_required_fields`
  - `test_TC_UNIT_012_stream_incomplete_aborted_log_format`
  - `test_TC_UNIT_013_stream_incomplete_error_log_format`
  - `test_TC_UNIT_014_log_does_not_contain_token_text`
- **ChatConsumerEdgeCasesTest** ［integration］ — 1 用例
  - `test_TC_INTG_001_reasoning_after_content_no_duplicate_reasoning_end`

### `api/tests/test_redis_cache_pretest.py`

- **DummyCacheBaselineTest** ［unit］ — 4 用例
  - `test_cache_backend_is_dummy_during_test_run`
  - `test_cache_get_returns_none_in_dummy`
  - `test_cache_dashboard_decorator_structure`
  - `test_cache_dashboard_vary_params`

### `api/tests/test_room_filter_v057.py`

- **TestMatchPanelSubTypes** ［unit］ — 10 用例
  - `test_three_room_no_children`
  - `test_three_room_with_children`
  - `test_four_room_with_fourth_children`
  - `test_four_room_inferred_by_study_room`
  - `test_three_room_with_children_but_no_study`
  - `test_four_room_with_study_and_children`
  - `test_no_children_no_fourth_children`
  - `test_panel_bedroom_panel_children_both_active`
  - `test_empty_room_name_skipped`
  - `test_four_rooms_but_no_children_keyword`
- **TestGetAvailableSubTypes** ［unit］ — 9 用例
  - `test_three_room_no_fourth_children`
  - `test_device_tree_not_synced_fallback_plan_b`
  - `test_four_room_with_fourth_children_room`
  - `test_production_1001_four_room_activates_fourth_children`
  - `test_production_1002_three_room_no_fourth_children`
  - `test_cache_hit_no_second_db_query`
  - `test_cache_invalidate_triggers_requery`
  - `test_global_cache_invalidate`
  - `test_db_error_returns_system_level_not_cached`
- **TestGetPanelParamBlocklist** ［unit］ — 2 用例
  - `test_blocklist_for_missing_room`
  - `test_blocklist_empty_when_all_rooms_exist`
- **TestPLCLatestDataHandlerRoomFilter** ［unit］ — 5 用例
  - `test_room_filter_blocks_invalid_params_plc_latest`
  - `test_room_filter_blocks_invalid_params_device_param_history`
  - `test_valid_room_params_still_written`
  - `test_system_level_params_not_filtered`
  - `test_empty_blocklist_no_filtering`
- **TestOndemandCollectSubscriberAllowedParams** ［unit］ — 5 用例
  - `test_execute_ondemand_with_allowed_params_filters_configs`
  - `test_execute_ondemand_without_allowed_params_full_collect`
  - `test_execute_ondemand_with_empty_set_yields_no_configs`
  - `test_on_request_parses_allowed_params_from_payload`
  - `test_on_request_without_allowed_params_passes_none`
- **TestGetDeviceRealtimeParamsWithRoomFilter** ［integration］ — 4 用例
  - `test_three_room_no_fourth_children_panel_excluded`
  - `test_system_level_panels_always_shown`
  - `test_no_device_tree_synced_plan_b_fallback`
  - `test_four_room_with_fourth_children_panel_included`
- **TestDeviceSettingsParamsWithRoomFilter** ［integration］ — 2 用例
  - `test_no_children_room_panel_excluded_from_settings`
  - `test_system_level_writable_params_not_filtered`
- **TestDeviceTreeSyncCacheInvalidation** ［integration］ — 1 用例
  - `test_sync_one_calls_cache_invalidation`
- **TestOndemandRefreshAllowedParamsInjection** ［integration］ — 2 用例
  - `test_synced_device_tree_payload_has_allowed_params`
  - `test_no_device_tree_payload_has_system_only_params`
- **TestEdgeCases** ［integration］ — 4 用例
  - `test_panel_bedroom_and_children_room_both_active_when_both_keywords_present`
  - `test_four_rooms_no_children_keyword_no_fourth_children`
  - `test_empty_ori_room_name_does_not_crash`
  - `test_cache_hit_performance`

### `api/tests/test_screen_heartbeat.py`

- **OnMessageTest** ［unit］ — 4 用例
  - `test_tc_hb_001_on_message_writes_last_seen_at`
  - `test_tc_hb_001b_on_message_upsert_idempotent`
  - `test_tc_hb_002_on_message_unknown_mac_no_write`
  - `test_tc_hb_003_on_message_empty_mac_no_write`
- **OnlineStatusTest** ［unit］ — 4 用例
  - `test_tc_hb_004_online_within_threshold`
  - `test_tc_hb_004b_online_exactly_at_boundary`
  - `test_tc_hb_005_offline_beyond_threshold`
  - `test_tc_hb_006_unknown_no_record`
- **MacCacheTest** ［unit］ — 2 用例
  - `test_tc_hb_007_cache_refresh_on_expiry`
  - `test_tc_hb_007b_cache_hit_without_db`
- **MigrationFieldTest** ［unit］ — 4 用例
  - `test_tc_hb_008_model_has_last_seen_at`
  - `test_tc_hb_008b_model_no_status_field`
  - `test_tc_hb_008c_model_no_last_checked_at_field`
  - `test_tc_hb_008d_can_create_record_with_last_seen_at`
- **DeviceListAPITest** ［integration］ — 4 用例
  - `test_tc_hb_009_filter_online`
  - `test_tc_hb_009b_filter_offline`
  - `test_tc_hb_010_filter_unknown`
  - `test_tc_hb_010b_no_filter_returns_all`

### `api/tests/test_service_management.py`

- **TC_U_SM_001_WhitelistConstants** ［unit］ — 4 用例
  - `test_monitored_services_is_list`
  - `test_monitored_services_set_matches_list`
  - `test_allowed_actions_contains_required`
  - `test_known_service_names_in_whitelist`
- **TC_U_SM_002_GetServiceStatus** ［unit］ — 6 用例
  - `test_returns_active_when_systemctl_outputs_active`
  - `test_returns_inactive_when_systemctl_outputs_inactive`
  - `test_returns_failed_when_systemctl_outputs_failed`
  - `test_returns_unknown_on_exception`
  - `test_returns_unknown_on_timeout`
  - `test_empty_stdout_returns_unknown`
- **TC_U_SM_003_GetServiceDetail** ［unit］ — 8 用例
  - `test_parses_active_state`
  - `test_parses_sub_state`
  - `test_parses_pid`
  - `test_parses_memory`
  - `test_raw_output_present`
  - `test_raw_output_limited_to_4096`
  - `test_timeout_returns_error_dict`
  - `test_exception_returns_error_dict`
- **TC_I_SM_001_ServiceListAPIAuth** ［integration］ — 3 用例
  - `test_unauthenticated_returns_401`
  - `test_authenticated_returns_200`
  - `test_post_not_allowed_on_list`
- **TC_I_SM_002_ServiceListAPIResponse** ［integration］ — 7 用例
  - `test_response_success_field`
  - `test_response_data_is_list`
  - `test_response_data_count_equals_monitored_services`
  - `test_each_item_has_required_fields`
  - `test_all_service_names_in_whitelist`
  - `test_is_active_true_when_active_state_active`
  - `test_is_active_false_when_active_state_inactive`
- **TC_I_SM_003_ServiceDetailAPI** ［integration］ — 4 用例
  - `test_unauthenticated_detail_returns_401`
  - `test_valid_service_detail_returns_200`
  - `test_invalid_service_name_returns_400`
  - `test_detail_contains_required_fields`
- **TC_I_SM_004_ServiceActionAPI** ［integration］ — 11 用例
  - `test_unauthenticated_action_returns_401`
  - `test_invalid_service_name_returns_400`
  - `test_invalid_action_returns_400`
  - `test_empty_action_returns_400`
  - `test_start_action_succeeds`
  - `test_stop_action_succeeds`
  - `test_restart_action_succeeds`
  - `test_systemctl_failure_returns_500`
  - `test_systemctl_timeout_returns_504`
  - `test_sudo_is_called_with_correct_args`
  - `test_status_action_is_rejected`
- **TC_I_SM_005_SecurityInjection** ［integration］ — 3 用例
  - `test_service_name_with_shell_injection_rejected`
  - `test_action_injection_rejected`
  - `test_whitelist_service_name_not_injectable`
- **TC_E2E_SM_US001_ServiceList** ［e2e］ — 2 用例
  - `test_service_list_url_accessible`
  - `test_all_monitored_services_appear_in_list`
- **TC_E2E_SM_US002_ServiceDetail** ［e2e］ — 2 用例
  - `test_detail_returns_raw_output`
  - `test_detail_for_each_monitored_service`
- **TC_E2E_SM_US003_ServiceAction** ［e2e］ — 5 用例
  - `test_start_reflects_in_new_status`
  - `test_stop_reflects_in_new_status`
  - `test_restart_reflects_in_new_status`
  - `test_action_response_contains_message`
  - `test_unauthenticated_cannot_execute_action`
- **TC_E2E_SM_NFR_AdminOnlyWrite** ［e2e］ — 2 用例
  - `test_regular_user_can_call_action`
  - `test_admin_user_can_call_action`

### `api/tests/test_service_registry_v120.py`

- **WhitelistCompletenessTest** ［unit］ — 6 用例
  - `test_total_count_20`
  - `test_all_expected_services_present`
  - `test_newly_added_services_present`
  - `test_existing_services_retained`
  - `test_no_non_freeark_services`
  - `test_set_matches_list`
- **GetServiceEnabledTest** ［unit］ — 6 用例
  - `test_enabled`
  - `test_disabled`
  - `test_static`
  - `test_empty_returns_unknown`
  - `test_exception_returns_unknown`
  - `test_timeout_returns_unknown`
- **DashboardServicesEnabledTest** ［integration］ — 3 用例
  - `test_each_item_has_enabled_field`
  - `test_is_active_independent_of_enabled`
  - `test_disabled_service_reported`

### `api/tests/test_session_delete_view.py`

- **SessionDeleteViewTest** ［integration］ — 7 用例
  - `test_delete_own_session_returns_200`
  - `test_delete_marks_session_as_deleted_in_db`
  - `test_delete_removed_from_session_list`
  - `test_delete_other_user_session_returns_404`
  - `test_delete_nonexistent_session_returns_404`
  - `test_delete_idempotent_second_call_returns_404`
  - `test_delete_unauthenticated_returns_401`
- **MyMemoryViewSessionKeyFullTest** ［integration］ — 6 用例
  - `test_returns_session_key_full_field`
  - `test_deleted_sessions_excluded_from_list`
  - `test_empty_session_list_returns_empty_state`
  - `test_pagination_works`
  - `test_unauthenticated_returns_401`
  - `test_session_contains_required_fields`

### `api/tests/test_v100_dashboard_redesign.py`

- **DeviceListCondensationFieldTest** ［integration］ — 4 用例
  - `test_UT_CL_01_has_active_condensation_true`
  - `test_UT_CL_02_has_active_condensation_false_no_record`
  - `test_UT_CL_04_recovered_condensation_returns_false`
  - `test_UT_CL_field_always_present`
- **FaultSummaryAPITest** ［integration］ — 4 用例
  - `test_UT_FS_01_active_fault_count`
  - `test_UT_FS_02_affected_unit_count_distinct`
  - `test_UT_FS_03_no_fault_returns_zero`
  - `test_UT_FS_response_structure`
- **DeviceFaultSummaryAPITest** ［integration］ — 6 用例
  - `test_UT_DFS_01_returns_four_categories`
  - `test_UT_DFS_01b_device_node_total`
  - `test_UT_DFS_02_thermostat_includes_product_code_260001_and_120003`
  - `test_UT_DFS_02c_recovered_fault_not_counted`
  - `test_UT_DFS_03_empty_db_returns_zeros`
  - `test_UT_DFS_hydraulic_module_fault_count`
- **NewAPIAuthTest** ［integration］ — 2 用例
  - `test_UT_AUTH_01a_fault_summary_requires_auth`
  - `test_UT_AUTH_01b_device_fault_summary_requires_auth`

### `api/tests/test_waitress_config_v052.py`

- **TestWaitressConfigEnvironmentVariables** ［unit］ — 6 用例
  - `test_UT_V052_01_threads_from_env`
  - `test_UT_V052_02_threads_default_value`
  - `test_UT_V052_03_channel_timeout_from_env`
  - `test_UT_V052_04_connection_limit_from_env`
  - `test_UT_V052_05_invalid_env_var_raises_value_error`
  - `test_UT_V052_06_all_defaults_when_no_env_vars`
- **TestWaitressConfigServeCallSignature** ［unit］ — 4 用例
  - `test_serve_called_with_threads_keyword_arg`
  - `test_serve_called_with_all_three_params`
  - `test_serve_host_and_port_unchanged`
  - `test_serve_env_override_propagates_to_call`
- **TestWaitressConfigM3NoChange** ［unit］ — 2 用例
  - `test_settings_conn_max_age_is_300`
  - `test_settings_no_reconnect_true`

### `api/tests/test_workorder_v131.py`

- **CreateWorkOrderProposalTest** ［integration］ — 3 用例
  - `test_proposed_tool_sets_pending`
  - `test_no_tool_is_none`
  - `test_agent_blocked_write_persists_structured_proposal`
- **ListDetailTest** ［integration］ — 4 用例
  - `test_list_unauth_401`
  - `test_list_source_active_flags`
  - `test_list_filter_status`
  - `test_detail_fields_and_404`
- **ApproveWriteTest** ［integration］ — 5 用例
  - `test_non_admin_403`
  - `test_no_proposal_400`
  - `test_execute_success_marks_executed_and_in_progress`
  - `test_execute_failure_marks_failed_502`
  - `test_double_execute_blocked`
- **ResolveTest** ［integration］ — 2 用例
  - `test_user_403`
  - `test_admin_resolves`

### `api/tests/test_ws_session_resolve.py`

- **WsResolveSessionTest** ［integration］ — 4 用例
  - `test_no_session_key_creates_new`
  - `test_valid_own_session_key_reused`
  - `test_deleted_session_key_falls_back_to_new`
  - `test_other_users_session_key_falls_back_to_new`

### `api/tests_fault_count.py`

- **CountFaultsForRowTest** ［unit］ — 22 用例
  - `test_comm_fault_timeout_normal_zero`
  - `test_comm_fault_timeout_normal_none`
  - `test_comm_fault_timeout_fault_nonzero`
  - `test_comm_fault_timeout_fault_large_value`
  - `test_error_82_zero`
  - `test_error_82_none`
  - `test_error_82_fault`
  - `test_error_703_fault`
  - `test_error_non_digit_suffix_ignored`
  - `test_error_mixed_suffix_ignored`
  - `test_fresh_air_fault_status_zero`
  - `test_fresh_air_fault_status_none`
  - `test_fresh_air_fault_status_1_bit`
  - `test_fresh_air_fault_status_3_bits`
  - `test_fresh_air_fault_status_7_bits`
  - `test_fresh_air_fault_status_15_bits`
  - `test_fresh_air_fault_status_all_9_bits`
  - `test_temperature_param_ignored`
  - `test_system_switch_ignored`
  - `test_named_fault_param_zero`
  - `test_named_fault_param_one`
  - `test_fresh_air_unit_communication_error_fault`
- **IsFaultParamTest** ［unit］ — 7 用例
  - `test_comm_fault_timeout`
  - `test_known_fault_param`
  - `test_error_numeric`
  - `test_error_non_numeric`
  - `test_temperature_not_fault`
  - `test_system_switch_not_fault`
  - `test_fresh_air_fault_status_not_in_is_fault`
- **ComputeFaultCountV2Test** ［unit］ — 6 用例
  - `test_empty_records`
  - `test_all_normal`
  - `test_single_fault`
  - `test_mixed_fault_and_normal`
  - `test_multiple_sections_aggregated`
  - `test_none_value_not_counted`
- **ComputeFromDbBatchTest** ［unit］ — 7 用例
  - `test_single_section_with_faults`
  - `test_section_all_normal`
  - `test_unknown_section_returns_none`
  - `test_batch_multiple_sections`
  - `test_empty_list`
  - `test_error_n_field_counted`
  - `test_error_non_numeric_ignored`
- **SubTypeFilterTest** ［unit］ — 3 用例
  - `test_filter_out_subtype_not_in_available_set`
  - `test_all_subtypes_available_counts_all`
  - `test_param_without_device_config_still_counts`
- **FaultCacheTest** ［unit］ — 5 用例
  - `test_cache_miss_computes_from_db`
  - `test_cache_hit_returns_cached_value`
  - `test_invalidate_clears_cache`
  - `test_batch_cache_hit_miss_mix`
  - `test_ttl_expiry_triggers_recompute`
- **DeviceFaultCountViewTest** ［integration］ — 10 用例
  - `test_401_unauthenticated`
  - `test_400_missing_specific_part`
  - `test_400_too_many_specific_parts`
  - `test_200_single_section_with_faults`
  - `test_200_schema_fields`
  - `test_200_section_all_normal`
  - `test_200_nonexistent_section_returns_null`
  - `test_200_batch_query`
  - `test_fault_details_sorted_by_param_name`
  - `test_cache_hit_latency`
- **DeviceFaultSummaryViewTest** ［integration］ — 6 用例
  - `test_401_unauthenticated`
  - `test_400_invalid_min_fault_count`
  - `test_200_default_min_fault_count_1`
  - `test_200_sorted_by_fault_count_desc`
  - `test_200_building_filter`
  - `test_200_min_fault_count_2`
- **DeviceListFaultCountFieldTest** ［integration］ — 2 用例
  - `test_fault_count_field_present_in_results`
  - `test_fault_count_correct_value`
- **FaultCountPerformanceTest** ［integration］ — 1 用例
  - `test_api_response_under_100ms`

### `api/tests_fault_event.py`

- **TestIsFaultCandidate** ［unit］ — 8 用例
  - `test_comm_fault_timeout_recognized`
  - `test_named_sensor_fault_recognized`
  - `test_named_comm_error_recognized`
  - `test_fresh_air_fault_bit_pattern_recognized`
  - `test_error_n_pattern_recognized`
  - `test_non_fault_param_rejected`
  - `test_fresh_air_fault_bit_invalid_suffix_rejected`
  - `test_error_n_without_digit_rejected`
- **TestIsFaultActive** ［unit］ — 16 用例
  - `test_comm_fault_timeout_normal_is_false`
  - `test_comm_fault_timeout_other_string_is_true`
  - `test_comm_fault_timeout_none_is_false`
  - `test_error_n_zero_int_is_false`
  - `test_error_n_zero_str_is_false`
  - `test_error_n_nonzero_is_true`
  - `test_error_n_none_is_false`
  - `test_fresh_air_bit_zero_is_false`
  - `test_fresh_air_bit_one_is_true`
  - `test_fresh_air_bit_none_is_false`
  - `test_fresh_air_bit_invalid_value_is_false`
  - `test_named_fault_zero_is_false`
  - `test_named_fault_one_is_true`
  - `test_named_fault_none_is_false`
  - `test_named_fault_bool_false_is_false`
  - `test_named_fault_bool_true_is_true`
- **TestGetFaultTypeAndSeverity** ［unit］ — 12 用例
  - `test_comm_fault_timeout_exact`
  - `test_fresh_air_unit_stop_error_exact`
  - `test_comm_error_suffix`
  - `test_temp_sensor_suffix`
  - `test_humidity_sensor_suffix`
  - `test_external_temp_sensor_suffix`
  - `test_fresh_air_bit_returns_warning`
  - `test_error_n_returns_other_error`
  - `test_unknown_param_falls_back_to_other_error`
  - `test_hydraulic_module_exact`
  - `test_energy_meter_exact`
  - `test_exact_beats_suffix`
- **TestGetFaultMessage** ［unit］ — 5 用例
  - `test_underscores_replaced_by_spaces`
  - `test_first_letter_capitalized`
  - `test_max_length_255`
  - `test_known_param_format`
  - `test_fresh_air_bit_format`
- **TestStateMachineTransitions** ［unit］ — 9 用例
  - `test_t1_inserts_db_row`
  - `test_t1_adds_to_memory`
  - `test_t1_parameters_stored_correctly`
  - `test_t2_no_db_write_on_continued_fault`
  - `test_t3_sets_is_active_false_in_db`
  - `test_t3_updates_memory_is_active_false`
  - `test_normal_message_with_no_prior_state_does_nothing`
  - `test_t1_t2_t3_full_sequence`
  - `test_multiple_keys_independent`
- **TestT2ThrottledPersist** ［unit］ — 5 用例
  - `test_t2_within_window_does_not_persist`
  - `test_t2_beyond_window_persists`
  - `test_t2_persist_adds_no_new_rows`
  - `test_persist_resets_throttle_window`
  - `test_threshold_zero_persists_every_t2`
- **TestRebuildFromDb** ［unit］ — 5 用例
  - `test_rebuild_empty_db_returns_zero`
  - `test_rebuild_loads_active_faults`
  - `test_rebuild_skips_inactive_faults`
  - `test_rebuild_respects_10000_limit`
  - `test_rebuild_clears_old_state`
- **FaultViewTestBase** ［integration］ — 0 用例
- **TestFaultEventListAuth** ［integration］ — 2 用例
  - `test_unauthenticated_returns_401`
  - `test_authenticated_returns_200`
- **TestFaultEventListPagination** ［integration］ — 5 用例
  - `test_default_page_size_is_20`
  - `test_page2_has_remaining_5`
  - `test_custom_page_size`
  - `test_page_size_capped_at_100`
  - `test_empty_result`
- **TestFaultEventListFilters** ［integration］ — 13 用例
  - `test_filter_by_specific_part_partial`
  - `test_filter_by_fault_type_comm`
  - `test_filter_by_fault_type_multiple`
  - `test_filter_invalid_fault_type_ignored`
  - `test_filter_by_is_active_true`
  - `test_filter_by_is_active_false`
  - `test_filter_is_active_invalid_value_ignored`
  - `test_filter_by_sub_type_fresh_air_unit`
  - `test_filter_by_sub_type_invalid_ignored`
  - `test_filter_time_range_first_seen_after`
  - `test_filter_time_range_first_seen_before`
  - `test_filter_invalid_datetime_falls_back_to_7_days`
  - `test_combined_filters`
- **TestFaultEventListDefaultTimeRange** ［integration］ — 1 用例
  - `test_no_params_defaults_to_7_days`
- **TestFaultEventCategories** ［integration］ — 3 用例
  - `test_returns_fault_types`
  - `test_returns_sub_types`
  - `test_no_db_query_needed`
- **TestFaultEventSerializer** ［integration］ — 10 用例
  - `test_all_expected_fields_present`
  - `test_id_is_integer`
  - `test_is_active_is_boolean`
  - `test_recovered_at_null_when_not_set`
  - `test_recovered_at_not_null_when_set`
  - `test_datetime_fields_are_strings`
  - `test_fault_type_is_valid_choice`
  - `test_severity_is_valid_choice`
  - `test_string_fields_are_strings`
  - `test_no_extra_write_fields`
- **TestFaultCleanupCommand** ［unit］ — 10 用例
  - `test_dry_run_does_not_delete`
  - `test_dry_run_reports_count`
  - `test_dry_run_zero_when_nothing_to_delete`
  - `test_cleanup_deletes_matching_records`
  - `test_cleanup_does_not_delete_active_faults`
  - `test_cleanup_batch_size_respected`
  - `test_boundary_90_days_deleted`
  - `test_boundary_90_days_exact_not_deleted`
  - `test_boundary_91_days_deleted`
  - `test_days_zero_raises_command_error`
- **TestHandleMessageIntegration** ［integration］ — 8 用例
  - `test_fault_message_triggers_t1_insert`
  - `test_normal_value_after_fault_triggers_t3_recover`
  - `test_repeated_fault_messages_t2_no_new_db_rows`
  - `test_non_device_status_update_skipped`
  - `test_unknown_mac_skipped`
  - `test_invalid_json_does_not_crash`
  - `test_real_payload_format_attr_tag_triggers_t1`
  - `test_real_payload_non_fault_attr_tag_skipped`
- **TestFaultEventAPIIntegration** ［integration］ — 5 用例
  - `test_results_ordered_by_first_seen_desc`
  - `test_multi_page_total_count_accurate`
  - `test_sub_type_living_room_returns_sensor_and_comm`
  - `test_combined_sub_type_and_is_active`
  - `test_unique_constraint_prevents_duplicate_key`
- **TestFaultFilterParamFormatCompat** ［integration］ — 11 用例
  - `test_single_fault_type_filter`
  - `test_multi_fault_type_repeated_param_format`
  - `test_all_four_fault_types_selected`
  - `test_single_sub_type_filter_living_room`
  - `test_sub_type_fresh_air_unit_includes_bit_pattern`
  - `test_multi_sub_type_repeated_param_format`
  - `test_fault_type_and_is_active_combination`
  - `test_sub_type_and_is_active_combination`
  - `test_clear_filters_returns_all_within_7_days`
  - `test_invalid_fault_type_mixed_with_valid`
  - `test_invalid_sub_type_ignored`
- **TestBugFM004RoomNumberSegments** ［integration］ — 10 用例
  - `test_3_segment_input_matches_4_segment_db`
  - `test_3_segment_returns_all_floors_with_same_room`
  - `test_3_segment_does_not_match_different_unit`
  - `test_3_segment_does_not_match_different_building`
  - `test_4_segment_input_exact_match`
  - `test_1_segment_input_safe_fallback`
  - `test_2_segment_input_safe_fallback`
  - `test_5_segment_input_safe_fallback`
  - `test_3_segment_with_multi_digit_building_number`
  - `test_startswith_does_not_match_adjacent_unit_with_longer_number`
- **TestBugFM005SubTypeProductCodeFilter** ［integration］ — 14 用例
  - `test_living_room_main_matches_product_code_260001_error_n`
  - `test_living_room_main_does_not_match_product_code_120003`
  - `test_living_room_main_matches_product_code_260001`
  - `test_or_union_named_fault_code_still_hits`
  - `test_sub_type_thermostat_does_not_hit_unrelated_product`
  - `test_fresh_air_unit_covers_named_fault_code`
  - `test_fresh_air_unit_covers_bit_prefix`
  - `test_fresh_air_unit_covers_product_code_130004_error_n`
  - `test_fresh_air_unit_does_not_hit_unrelated`
  - `test_hydraulic_module_matches_product_code_270001`
  - `test_energy_meter_matches_product_code_250001`
  - `test_air_quality_sensor_matches_product_code_100007`
  - `test_bm003_regression_fresh_air_named_and_bit_still_work`
  - `test_invalid_sub_type_still_silently_ignored`
- **TestBugFM006RoomFilter** ［integration］ — 10 用例
  - `test_living_room_matches_product_code_260001_no_room_filter`
  - `test_study_room_panel_matches_study_only`
  - `test_master_bedroom_panel_matches_master_bedroom_only`
  - `test_children_room_panel_matches_children_room_only`
  - `test_secondary_bedroom_panel_matches_secondary_only`
  - `test_device_not_in_device_node_room_path_miss_but_named_fault_code_hits`
  - `test_device_not_in_device_node_and_no_named_fault_code_not_hit`
  - `test_multi_sub_type_merges_device_sns`
  - `test_fresh_air_unit_prefix_branch_unaffected`
  - `test_bm003_004_existing_behavior_unaffected`
- **TestBugFM007DeviceNameOverride** ［integration］ — 4 用例
  - `test_fresh_air_device_name_overridden_to_xinfengji`
  - `test_other_product_code_not_affected`
  - `test_device_name_cache_miss_no_exception`
  - `test_product_code_labels_fallback_still_works`
- **TestBugFM008FaultMessageZh** ［unit］ — 9 用例
  - `test_error_140_returns_chinese`
  - `test_error_82_returns_chinese`
  - `test_error_679_returns_chinese`
  - `test_unmapped_error_n_generic_fallback`
  - `test_comm_fault_timeout_returns_chinese`
  - `test_fresh_air_fault_bit_keeps_capitalize_logic`
  - `test_fresh_air_unit_stop_error_returns_chinese`
  - `test_result_length_within_255`
  - `test_backfill_command_dry_run_reports_nonzero_count`

### `api/tests_rag.py`

- **TestRagDocumentModel** ［unit］ — 5 用例
  - `test_default_status_is_pending`
  - `test_status_transition_to_indexed`
  - `test_status_transition_to_failed`
  - `test_uploaded_by_set_null_on_user_delete`
  - `test_chunk_cascade_delete`
- **TestRagUploadAPI** ［integration］ — 15 用例
  - `test_non_admin_upload_returns_403`
  - `test_non_admin_list_returns_403`
  - `test_unauthenticated_returns_401`
  - `test_invalid_extension_returns_400`
  - `test_fake_extension_wrong_magic_returns_400`
  - `test_oversized_file_returns_400`
  - `test_valid_pdf_upload_returns_201`
  - `test_valid_docx_upload_returns_201`
  - `test_list_returns_documents_ordered_by_created_desc`
  - `test_delete_document_returns_204`
  - `test_delete_nonexistent_returns_404`
  - `test_delete_parsing_doc_succeeds`
  - `test_retry_failed_doc_succeeds`
  - `test_retry_indexed_doc_returns_400`
  - `test_retry_without_file_returns_400`
- **TestRagService** ［unit］ — 13 用例
  - `test_cache_empty_search_returns_empty`
  - `test_cache_search_returns_top_k`
  - `test_cache_threshold_filters_low_scores`
  - `test_parse_docx_text_chunks`
  - `test_parse_pdf_text_chunks`
  - `test_ocr_image_returns_empty_when_no_ocr`
  - `test_embed_texts_returns_numpy_arrays`
  - `test_embed_query_returns_numpy_array`
  - `test_search_rag_degraded_on_embedding_failure`
  - `test_search_rag_empty_cache_returns_empty_not_degraded`
  - `test_ingest_pdf_success`
  - `test_ingest_embedding_failure_sets_failed`
  - `test_ingest_exits_safely_if_doc_deleted`
- **TestSearchTool** ［unit］ — 5 用例
  - `test_tool_returns_formatted_results`
  - `test_tool_returns_no_content_message`
  - `test_tool_returns_degraded_message`
  - `test_tool_marks_image_ocr_source`
  - `test_tool_fail_open_on_exception`
- **TestRagIntegration** ［integration］ — 3 用例
  - `test_upload_ingest_search_full_cycle`
  - `test_delete_triggers_cache_refresh`
  - `test_list_shows_correct_status_fields`
- **TestSystemPromptRAG** ［unit］ — 1 用例
  - `test_system_prompt_contains_rag_tool_section`
- **TestRagSerializer** ［unit］ — 3 用例
  - `test_serializer_returns_username_string`
  - `test_serializer_handles_deleted_user`
  - `test_all_required_fields_present`

### `api/tests_session_timeout.py`

- **SlidingWindowAuthenticationUnitTests** ［unit］ — 8 用例
  - `test_tc_sw_01_no_activity_record_creates_and_passes`
  - `test_tc_sw_02_within_timeout_passes`
  - `test_tc_sw_03_expired_raises_authentication_failed`
  - `test_tc_sw_04_sliding_window_resets_timer`
  - `test_tc_sw_05_throttle_limits_db_writes`
  - `test_tc_sw_06_cache_miss_reads_db`
  - `test_tc_sw_07_expired_with_empty_cache`
  - `test_tc_sw_08_invalid_token_raises`
- **LoginAPITests** ［integration］ — 7 用例
  - `test_tc_login_01_creates_token_activity`
  - `test_tc_login_02_last_login_refreshed`
  - `test_tc_login_03_failed_login_no_last_login_change`
  - `test_tc_login_04_valid_token_accesses_protected_endpoint`
  - `test_tc_login_05_expired_token_returns_401`
  - `test_tc_login_06_relogin_after_timeout_restores_access`
  - `test_tc_login_07_timeout_threshold_from_settings`
- **RememberMeTests** ［integration］ — 5 用例
  - `test_tc_rm_01_remember_me_true_sets_extended_session`
  - `test_tc_rm_02_remember_me_false_keeps_default`
  - `test_tc_rm_03_default_session_expires_at_short_timeout`
  - `test_tc_rm_04_extended_session_survives_short_timeout`
  - `test_tc_rm_05_relogin_overrides_extended_session`
- **RegisterAPITests** ［integration］ — 1 用例
  - `test_tc_register_01_creates_token_activity`
- **LogoutCascadeTests** ［integration］ — 1 用例
  - `test_tc_logout_01_token_activity_cascade_deleted`
- **ThrottleIntegrationTests** ［integration］ — 1 用例
  - `test_tc_throttle_01_multiple_requests_single_db_write`
- **TokenActivityModelTests** ［unit］ — 4 用例
  - `test_tc_model_01_create_and_retrieve`
  - `test_tc_model_02_one_to_one_constraint`
  - `test_tc_model_03_cascade_delete_with_token`
  - `test_tc_model_04_str_representation`

---

## C. 排除 / 卫星脚本（不在 `manage.py test api` 分层范围内）

| 脚本 | 说明 / 运行方式 |
|------|------------------|
| `api/tests/test_dashboard_perf.py` | 性能基准脚本（非 TestCase，需生产 token），手动运行 |
| `datacollection/tests/test_plc_write_subscriber.py` | pytest 风格，用 `pytest` 运行 |
| `datacollection/test_log_config_manager.py` | unittest，独立运行 `python -m unittest` |
| `tests/test_datacollection_refactor.py` | unittest/pytest，重构验证 |
| `test_plc_status_change_history.py` | 仓库根孤儿调试脚本（无断言）——不属正式套件 |
| `project_workspace/FreeArk_AsyncMQTT/test_mqtt_consumer_async.py` | 临时 PoC——不属正式套件 |
| `agents/langgraph-poc/test_delegation.py` | 孤儿验证脚本——不属正式套件 |

