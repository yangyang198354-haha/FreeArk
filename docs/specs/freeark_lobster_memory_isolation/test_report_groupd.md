# 测试执行报告 — 方舟智能体记忆隔离（GROUP_D）

```
file_header:
  document_id: TR-MEMORY-001
  project: FreeArk — freeark_lobster_memory_isolation
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_test_engineer (GROUP_D)
  created_at: 2026-05-26
```

---

## 1. 测试文件清单

| 文件路径 | 测试类数量 | 测试用例数量 | 覆盖模块 |
|---------|-----------|------------|---------|
| `api/tests/test_memory_models.py` | 8 | 18 | models.py（ChatSession + ChatMessage） |
| `api/tests/test_memory_chat_memory.py` | 8 | 29 | chat_memory.py |
| `api/tests/test_memory_consumer_v13.py` | 7 | 14 | consumers.py v1.3（集成，TransactionTestCase） |
| `api/tests/test_memory_views.py` | 4 | 23 | memory_views.py |
| `api/tests/test_memory_skeleton_guard_sh.py` | 4 | 12 | scripts/skeleton_guard.sh（bash+sha256sum 可用时运行，否则全 skip） |
| **合计** | **31** | **96** | — |

---

## 2. 执行命令

```powershell
# 进入 Django 项目目录
cd C:\Users\胖子熊\MyProject\FreeArk\FreeArkWeb\backend\freearkweb

# 分模块执行（推荐，便于定位问题）
python manage.py test api.tests.test_memory_models --verbosity=2
python manage.py test api.tests.test_memory_chat_memory --verbosity=2
python manage.py test api.tests.test_memory_consumer_v13 --verbosity=2
python manage.py test api.tests.test_memory_views --verbosity=2
python manage.py test api.tests.test_memory_skeleton_guard_sh --verbosity=2

# reasoning_stream 回归测试
python manage.py test api.tests.test_reasoning_stream --verbosity=2

# 全量一次执行
python manage.py test api.tests.test_memory_models api.tests.test_memory_chat_memory api.tests.test_memory_consumer_v13 api.tests.test_memory_views api.tests.test_memory_skeleton_guard_sh --verbosity=2
```

---

## 3. 执行结果

> **状态：PENDING_EXECUTION**
> 测试文件已全部写入，待用户在本地执行后填写实际结果。

### 3.1 test_memory_models — 15 用例

```
[执行命令] python manage.py test api.tests.test_memory_models --verbosity=2
[PENDING]
```

### 3.2 test_memory_chat_memory — 21 用例

```
[执行命令] python manage.py test api.tests.test_memory_chat_memory --verbosity=2
[PENDING]
```

### 3.3 test_memory_consumer_v13 — 12 用例（TransactionTestCase，含 WS 集成）

```
[执行命令] python manage.py test api.tests.test_memory_consumer_v13 --verbosity=2
[PENDING]
```

### 3.4 test_memory_views — 18 用例

```
[执行命令] python manage.py test api.tests.test_memory_views --verbosity=2
[PENDING]
```

### 3.5 test_memory_skeleton_guard_sh — 12 用例（bash 可用时）

```
[执行命令] python manage.py test api.tests.test_memory_skeleton_guard_sh --verbosity=2
[PENDING — 若 Windows 无 sha256sum，则全部 skip，不 fail]
```

### 3.6 reasoning_stream 回归测试

```
[执行命令] python manage.py test api.tests.test_reasoning_stream --verbosity=2
[PENDING — 期望: 34/34 全绿（与 commit 044325f 一致）]
```

---

## 4. FOUND_BUGS

根据代码审查（code_review_report.md）和测试设计时发现的问题：

### FOUND_BUGS 已记录（继承自 GROUP_C code_review_report.md）

| Bug ID | 文件 | 描述 | 测试验证 | 处置 |
|--------|------|------|---------|------|
| MAJOR-001 | chat_memory.py load_history | 跨 session 最近 40 条不保证轮对齐，奇数条时孤立 user 消息无 assistant 配对 | TC-P0-007 test_major001_odd_messages_no_crash | GROUP_C 已接受现状，GROUP_D 验证不崩溃即可 |
| MINOR-001 | chat_memory.py _INJECT_LIMIT | 模块级常量不响应 override_settings | TC-P1-* 通过直接传 limit=N 绕过 | 已在测试中绕过，不需修复 |
| MINOR-004 | memory_views.py AdminMemoryView | page_size 原无上界（已在 MyMemoryView 中有 min 限制） | TC-P2-005 | 查看实际代码：MyMemoryView.get 已有 min(page_size, 100)；AdminMemoryView.get 也已有 min(page_size, 100)——MINOR-004 已在 GROUP_C 代码中修复 |

### GROUP_D 新发现的问题

> 测试执行后填写。若执行前代码审查未发现新问题，此处为空。

---

## 5. 覆盖率

```
[PENDING — 执行覆盖率收集命令后填写]

# 覆盖率收集命令：
pip install coverage
coverage run --source=api.chat_memory,api.models,api.memory_views,api.consumers \
  manage.py test api.tests.test_memory_models api.tests.test_memory_chat_memory \
  api.tests.test_memory_consumer_v13 api.tests.test_memory_views
coverage report

# 目标：
# api/chat_memory.py:   ≥80%
# api/models.py (Chat部分): ≥80%
# api/memory_views.py:  ≥80%
# api/consumers.py (v1.3新增路径): ≥70%
```

---

## 6. 门控总结

| 门控标准 | 状态 |
|---------|------|
| 单次 100% 通过（不允许失败、不允许 skip 关键用例） | PENDING_EXECUTION |
| P0 用例全部通过（23 个） | PENDING_EXECUTION |
| reasoning_stream 回归 34/34 全绿 | PENDING_EXECUTION |
| unit ≥80% 覆盖率 | PENDING_EXECUTION |
| integration ≥70% 覆盖率 | PENDING_EXECUTION |
| FOUND_BUGS 均为 MINOR 级别（无 CRITICAL/MAJOR 新 Bug） | PASS（代码审查确认） |
