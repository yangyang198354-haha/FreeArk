# 实施计划 — 方舟龙虾记忆隔离

```
file_header:
  document_id: IMPL-MEMORY-001
  project: FreeArk — freeark_lobster_memory_isolation
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_software_developer (GROUP_C)
  created_at: 2026-05-26
  depends_on:
    - ARCH-MEMORY-001 (architecture_design.md)
    - MOD-MEMORY-001 (module_design.md)
    - REQ-SPEC-MEMORY-001 (requirements_spec.md)
  adr_confirmed:
    - ADR-009: 方案 D（Hybrid DB Stateless）
    - ADR-010: 方案 10-A（完整日志 + 最近 N=20 轮截断注入）
    - ADR-011: 方案 11-B（chattr +i）+ 11-C（Git 哈希追踪）
    - ADR-012: 方案 12-A（废弃 USER.md 个性化，DB 统一管理）
    - ADR-013: 方案 13-B（chat_session + chat_message 两表）
```

---

## 0. 实施范围声明

GROUP_C 负责代码实现和文档，不执行以下操作：
- 不 SSH 生产服务器
- 不执行 `python manage.py migrate` 到生产
- 不执行 `chattr +i` 到生产文件
- 不改动 reasoning_stream 的任何规格文档或测试

---

## 1. 批次划分

### Batch-P0：核心记忆基础设施（P0 用户故事）

**涵盖**：US-MEM-001/002/003/007（记忆存储、隔离、注入核心）+ US-MEM-005（人格锁定脚本）

**文件变更**：
1. `api/models.py` — 追加 `ChatSession` + `ChatMessage` 两个 Model
2. `api/migrations/0025_chat_session_message.py` — Django migration（手工精确编写）
3. `api/chat_memory.py` — 新建，记忆管理业务逻辑层
4. `api/consumers.py` — v1.2 → v1.3，集成 chat_memory
5. `freearkweb/settings.py` — 追加 `CHAT_HISTORY_INJECT_TURNS`
6. `scripts/skeleton_guard.sh` — 新建，骨架文件保护脚本

**风险**：
- consumers.py 改动涉及 async/sync 边界（sync_to_async），需保证不阻塞 WS 事件循环
- 降级设计：DB 操作失败不阻断基础聊天功能（见 module_design.md §3 异常路径）

**回滚路径**：
- 回滚 consumers.py 到 v1.2（git revert 单文件）
- 保留 DB 表（不需要 rollback migration，因为新表与现有表独立）
- 聊天功能立即恢复，记忆功能丢失（可接受的降级）

---

### Batch-P1：记忆生命周期 REST API（P1 用户故事）

**涵盖**：US-MEM-008（用户自助清空）+ US-MEM-009（注销级联）+ 跨设备一致性（US-MEM-011 自然满足）

**文件变更**：
1. `api/memory_views.py` — 新建，REST endpoints
2. `api/urls.py` — 注册新 endpoints

**风险**：
- 低风险，独立新增，不影响现有 endpoint

**回滚路径**：
- 从 urls.py 移除新 URL patterns 即可

---

### Batch-P2：Admin 管理接口（P2 用户故事）

**涵盖**：US-MEM-010（admin 查看/清空记忆）+ US-MEM-006（授权修改骨架，已在 skeleton_guard.sh 中以 unlock/lock 命令覆盖）

**文件变更**：
- `api/memory_views.py` — 追加 `AdminMemoryView`（与 Batch-P1 同文件）

**风险**：低，独立新增

---

## 2. 文件改动清单

| Batch | 文件路径 | 操作 | 关键约束 |
|-------|---------|------|---------|
| P0 | `api/models.py` | 追加（末尾）| AUTH_USER_MODEL = 'api.CustomUser'，CASCADE |
| P0 | `api/migrations/0025_chat_session_message.py` | 新建 | 依赖 '0024_plcwriterecord_batch_request_id' |
| P0 | `api/chat_memory.py` | 新建 | 纯 sync，外部用 sync_to_async 包装 |
| P0 | `api/consumers.py` | 修改（v1.2 → v1.3）| 保持 reasoning/content/stream_end 不变，ARCH-C-006 |
| P0 | `freearkweb/settings.py` | 追加 1 行 | `CHAT_HISTORY_INJECT_TURNS` |
| P0 | `scripts/skeleton_guard.sh` | 新建（仓库根 scripts/）| 不执行，仅产出脚本 |
| P1 | `api/memory_views.py` | 新建 | IsAuthenticated + IsAdminUser |
| P1/P2 | `api/urls.py` | 追加 URL patterns | 不改现有 pattern |

---

## 3. 风险与降级策略

| 风险项 | 可能性 | 降级策略 |
|--------|--------|---------|
| DB 写入（append_message）失败 | 低 | logger.error，WS 不中断，历史丢失可接受 |
| DB 读取（load_history）失败 | 低 | logger.warning，以空历史继续，聊天正常 |
| create_session 失败 | 极低 | logger.warning，chat_session=None，后续 DB 操作跳过 |
| sync_to_async 阻塞 WS 事件循环 | 低 | DB 查询在 Django 默认线程池执行，不阻塞 asyncio loop |
| consumers.py 兼容性破坏 | 极低 | 已有 34 个回归测试；新增代码仅在 connect/disconnect 前后，不改 _handle_chat 核心流 |

---

## 4. migration 策略

migration 文件（`0025_chat_session_message.py`）手工精确编写，不依赖 `makemigrations`，原因：
- 避免开发环境 MySQL 连接问题（开发用 SQLite）
- 手工编写更精确，与 ADR-013 方案 13-B 的 SQL 设计完全对齐

**本地验证**：可在 SQLite 上 `python manage.py migrate` 验证 migration 语法正确性（可选，非强制）

---

## 5. 关键设计决策摘要

| 决策 | 内容 |
|------|------|
| 历史注入格式 | `[历史记忆开始]\n用户: ...\n助手: ...\n[历史记忆结束]\n` 前缀 |
| 截断策略 | 取最近 N 轮（默认 N=20，即 40 条消息），按 created_at DESC 倒序取，再升序拼接 |
| reasoning 不存 | `accumulated_content` 仅累积 kind=='content' 的 text |
| session_key | 每次 WS connect 生成新 UUID（保持现有行为），DB ChatSession.session_key 存此 UUID |
| 个性化注入 | 通过 chat_message history 自然注入（用户之前告知的称呼等会保留在历史消息中），不开 user_preference 表 |
| 账号注销级联 | ChatSession.user FK → CustomUser，on_delete=CASCADE，Django 自动级联删除 |
