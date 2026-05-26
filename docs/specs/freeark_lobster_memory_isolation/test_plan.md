# 测试计划 — 方舟龙虾记忆隔离（GROUP_D）

```
file_header:
  document_id: TP-MEMORY-001
  project: FreeArk — freeark_lobster_memory_isolation
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_test_engineer (GROUP_D)
  created_at: 2026-05-26
  reviewed_files:
    - api/models.py（ChatSession + ChatMessage）
    - api/chat_memory.py
    - api/consumers.py（v1.3）
    - api/memory_views.py
    - api/urls.py
    - scripts/skeleton_guard.sh
```

---

## 1. 测试目标与范围

### 1.1 测试目标

| 目标 | 来源需求 |
|------|---------|
| ChatSession / ChatMessage 模型 CRUD + CASCADE 删除 | REQ-FUNC-013, REQ-NFR-011 |
| chat_memory.py 业务层（load_history、build_inject_prefix、clear_memory 等） | REQ-FUNC-014, REQ-FUNC-016 |
| ChatConsumer v1.3 集成（历史注入、DB 写入、降级路径） | REQ-FUNC-013, REQ-FUNC-016, REQ-NFR-013 |
| memory REST API（GET/DELETE，权限校验） | REQ-FUNC-017a/b/c, REQ-NFR-010 |
| skeleton_guard.sh 子进程测试（init/verify/status） | REQ-FUNC-015, REQ-NFR-012 |
| 回归：reasoning_stream 协议不破坏（ARCH-C-006） | REQ-FUNC-010, ARCH-C-006 |

### 1.2 测试范围（本期）

**本期测试对象（GROUP_D PHASE_07-09）**：
- `api/tests/test_memory_models.py`
- `api/tests/test_memory_chat_memory.py`
- `api/tests/test_memory_consumer_v13.py`
- `api/tests/test_memory_views.py`
- `api/tests/test_memory_skeleton_guard_sh.py`

**不在本期范围**：
- 生产环境验证（不 SSH）
- skeleton_guard.sh lock/unlock 命令（需要 sudo + chattr，测试环境无权限）
- OpenClaw 真实 WS 连接

---

## 2. 测试矩阵（P0/P1/P2 分级）

### P0 — 必须通过，否则阻塞发布

| TC-ID | 测试文件 | 测试用例 | 需求/US | 验证重点 |
|-------|---------|---------|--------|---------|
| TC-P0-001 | test_memory_models.py | test_create_session | REQ-FUNC-013 | ChatSession 创建成功 |
| TC-P0-002 | test_memory_models.py | test_cascade_on_user_delete | REQ-NFR-011 | 删除 User → Session 级联删除 |
| TC-P0-003 | test_memory_models.py | test_cascade_on_session_delete | REQ-NFR-011 | 删除 Session → Message 级联删除 |
| TC-P0-004 | test_memory_models.py | test_user_isolation | REQ-FUNC-016 | 用户 A/B session 不混 |
| TC-P0-005 | test_memory_chat_memory.py | test_empty_history | US-MEM-006 | 空历史返回 [] |
| TC-P0-006 | test_memory_chat_memory.py | test_cross_user_isolation | US-MEM-005 | 用户 A 历史不出现在用户 B |
| TC-P0-007 | test_memory_chat_memory.py | test_major001_odd_messages_no_crash | MAJOR-001 | 奇数条消息时 build_inject_prefix 不崩溃 |
| TC-P0-008 | test_memory_chat_memory.py | test_limit_zero_returns_empty | AC-010-01 | INJECT_TURNS=0 时返回空 |
| TC-P0-009 | test_memory_chat_memory.py | test_clears_all_sessions | REQ-FUNC-017a | clear_memory 清空所有 session |
| TC-P0-010 | test_memory_consumer_v13.py | test_connect_creates_chat_session | REQ-FUNC-013 | connect 后 DB 有 ChatSession |
| TC-P0-011 | test_memory_consumer_v13.py | test_stream_end_writes_assistant_message | REQ-FUNC-016 | stream_end 后 assistant 消息写入 DB |
| TC-P0-012 | test_memory_consumer_v13.py | test_history_prefix_passed_to_openclaw | REQ-FUNC-014 | 注入前缀含 [历史记忆开始] |
| TC-P0-013 | test_memory_consumer_v13.py | test_user_b_does_not_see_user_a_history | US-MEM-005 | 跨用户隔离 |
| TC-P0-014 | test_memory_consumer_v13.py | test_reasoning_token_sequence_unchanged | ARCH-C-006 | reasoning 协议回归 |
| TC-P0-015 | test_memory_consumer_v13.py | test_create_session_failure_ws_still_connects | ARCH-C-011 | DB 失败 WS 仍建立 |
| TC-P0-016 | test_memory_views.py | test_get_returns_200 | REQ-FUNC-017a | GET /memory/me/ 正常 |
| TC-P0-017 | test_memory_views.py | test_delete_clears_own_memory | REQ-FUNC-017b | DELETE /memory/me/ 清空历史 |
| TC-P0-018 | test_memory_views.py | test_get_unauthenticated_returns_403 | REQ-NFR-010 | 未认证返回 401/403 |
| TC-P0-019 | test_memory_views.py | test_normal_user_access_admin_returns_403 | REQ-NFR-010 | 普通用户访问 admin → 403 |
| TC-P0-020 | test_memory_views.py | test_admin_get_target_user_sessions | REQ-FUNC-017c | admin 查看他人会话 |
| TC-P0-021 | test_memory_skeleton_guard_sh.py | test_init_creates_hash_file | REQ-FUNC-015 | init 写入 .skeleton_hashes |
| TC-P0-022 | test_memory_skeleton_guard_sh.py | test_verify_pass_when_files_unchanged | AC-NFR-012-01 | 文件未变 exit 0+PASS |
| TC-P0-023 | test_memory_skeleton_guard_sh.py | test_verify_fail_when_file_modified | AC-NFR-012-01 | 文件被改 exit 1+FAIL |

### P1 — 应通过，不阻塞发布但需在下个迭代修复

| TC-ID | 测试文件 | 测试用例 | 需求 | 验证重点 |
|-------|---------|---------|------|---------|
| TC-P1-001 | test_memory_models.py | test_update_ended_at | REQ-FUNC-013 | ended_at 可更新 |
| TC-P1-002 | test_memory_models.py | test_index_fields (ChatSession) | REQ-NFR-011 | 索引定义正确 |
| TC-P1-003 | test_memory_models.py | test_index_fields (ChatMessage) | REQ-NFR-011 | 索引定义正确 |
| TC-P1-004 | test_memory_chat_memory.py | test_limit_truncates_oldest | ADR-010 10-A | 超长历史截断正确 |
| TC-P1-005 | test_memory_chat_memory.py | test_cross_session_history | ADR-013 | 跨 session 聚合历史 |
| TC-P1-006 | test_memory_chat_memory.py | test_pagination_page1/page2 | REQ-FUNC-017a | get_sessions 分页 |
| TC-P1-007 | test_memory_consumer_v13.py | test_empty_history_no_prefix | US-MEM-006 | 空历史时无前缀 |
| TC-P1-008 | test_memory_consumer_v13.py | test_inject_turns_zero_no_prefix | AC-010-01 | turns=0 无前缀 |
| TC-P1-009 | test_memory_consumer_v13.py | test_disconnect_sets_ended_at | REQ-FUNC-013 | disconnect 写 ended_at |
| TC-P1-010 | test_memory_consumer_v13.py | test_no_reasoning_sequence_compat | ARCH-C-006 | 无 reasoning 向后兼容 |
| TC-P1-011 | test_memory_consumer_v13.py | test_reasoning_end_only_once | ARCH-C-004 | reasoning_end 只出现一次 |
| TC-P1-012 | test_memory_views.py | test_get_only_returns_own_sessions | REQ-FUNC-017a | 只返回自己的会话 |
| TC-P1-013 | test_memory_views.py | test_admin_delete_target_user_sessions | REQ-FUNC-017c | admin 清空他人会话 |
| TC-P1-014 | test_memory_skeleton_guard_sh.py | test_verify_fail_when_hash_file_missing | REQ-FUNC-015 | 基准不存在时 exit 1 |

### P2 — 锦上添花，不影响发布

| TC-ID | 测试文件 | 测试用例 | 验证重点 |
|-------|---------|---------|---------|
| TC-P2-001 | test_memory_models.py | test_str_representation | __str__ 格式 |
| TC-P2-002 | test_memory_models.py | test_related_manager | 反向关联管理器 |
| TC-P2-003 | test_memory_chat_memory.py | test_invalid_role_raises | role 参数校验 |
| TC-P2-004 | test_memory_chat_memory.py | test_clear_only_affects_target_user | 隔离清空 |
| TC-P2-005 | test_memory_views.py | test_get_page_size_capped_at_100 | MINOR-004 page_size 上界 |
| TC-P2-006 | test_memory_views.py | test_admin_get_nonexistent_user_returns_404 | 404 处理 |
| TC-P2-007 | test_memory_skeleton_guard_sh.py | test_status_exits_zero | status 命令正常运行 |
| TC-P2-008 | test_memory_skeleton_guard_sh.py | test_invalid_command_shows_usage | 无效命令用法提示 |

---

## 3. 边界用例覆盖

| 边界 | 来源 | 对应 TC |
|-----|------|--------|
| 奇数条消息（孤立 user 无 assistant 配对） | MAJOR-001 | TC-P0-007 |
| CHAT_HISTORY_INJECT_TURNS=0 | PM 指定 | TC-P0-008, TC-P1-008 |
| 空历史（第一次对话） | PM 指定 | TC-P0-005, TC-P1-007 |
| 超长历史（>20轮截断） | ADR-010 10-A | TC-P1-004 |
| DB 错误降级（WS 不中断） | ARCH-C-011 | TC-P0-015, P1 中多个 |
| 跨 session 历史聚合 | ADR-013 | TC-P1-005 |
| page_size 无上界（MINOR-004）| code_review | TC-P2-005 |
| HASH_FILE 不存在时 verify | REQ-FUNC-015 | TC-P1-014 |

---

## 4. 测试策略

### 4.1 数据库

测试运行时自动使用 SQLite（settings.py 的 `_RUNNING_TESTS` 检测），
migration 0025 已改为升序索引，兼容 SQLite。

### 4.2 WS 集成测试

- 使用 `channels.testing.WebsocketCommunicator`（Django Channels >= 4.0）
- 必须用 `TransactionTestCase`（避免事务隔离导致 sync_to_async 无法访问 ORM）
- mock `OpenClawAdapter.stream_chat` 返回 AsyncGenerator，避免真实 WS 连接

### 4.3 skeleton_guard.sh 测试

- 使用 subprocess + tempfile.mkdtemp
- 注入 `HOME` 环境变量使脚本路径可控
- 若 bash 不可用自动 skip（不 fail）
- lock/unlock 需要 sudo + chattr，不在本期测试范围

### 4.4 覆盖率目标

| 模块 | 目标 | 类型 |
|------|------|------|
| api/chat_memory.py | ≥80% | 单元 |
| api/models.py（Chat* 部分） | ≥80% | 单元 |
| api/memory_views.py | ≥80% | 单元 |
| api/consumers.py（v1.3 新增路径） | ≥70% | 集成 |
| scripts/skeleton_guard.sh（init/verify/status 分支） | ≥70% | 子进程 |

---

## 5. 风险记录

| 风险 | 影响 | 缓解 |
|-----|------|------|
| skeleton_guard.sh 在 Windows bash 下 sha256sum 路径不同 | test 可能 skip | skip 策略已实现，不 fail |
| TransactionTestCase 较慢 | 集成测试耗时较长 | 接受，必要成本 |
| MINOR-001：_INJECT_LIMIT 模块级常量不响应 override_settings | 部分测试需直接传 limit 参数 | 已在测试中通过 limit=N 参数绕过 |
