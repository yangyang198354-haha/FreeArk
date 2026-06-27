# 技术栈与环境 — 方舟智能体记忆隔离

```
file_header:
  document_id: TECH-MEMORY-001
  project: FreeArk — freeark_lobster_memory_isolation
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_system_architect (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-26
  depends_on:
    - ARCH-MEMORY-001 (architecture_design.md)
    - REQ-SPEC-MEMORY-001 (requirements_spec.md)
```

---

## 1. 继承技术栈（来自前序项目，无变更）

| 组件 | 版本 | 备注 |
|------|------|------|
| Python | 3.13.x | venv `/home/yangyang/Freeark/FreeArk/venv` |
| Django | 现有版本 | 保持不变 |
| Django Channels | 现有版本 | AsyncWebsocketConsumer，`InMemoryChannelLayer` |
| Uvicorn ASGI | 现有版本 | `--workers 1`（InMemoryChannelLayer 不支持多 worker）|
| aiohttp | 现有版本 | OpenClawAdapter WS RPC 客户端 |
| MySQL | 9.4.0 | 生产 DB @ 192.168.31.98:3306，库名 `freeark` |
| OpenClaw Gateway | 2026.5.20 | loopback :18789，不修改 |
| DeepSeek | v4-flash | reasoning 模型，不修改 |
| Node.js | 22.22.2 | OpenClaw 运行时，不修改 |
| Vue3 + Vite | 现有版本 | 前端，可能新增"清空记忆"按钮 |

---

## 2. 本期新增技术组件

### 2.1 Django Model 层（ADR-013 方案 13-B）

**新增 Django App：api（现有），新增 Models**

```python
# FreeArkWeb/backend/freearkweb/api/models.py 新增：

class ChatSession(models.Model):
    """per-user 对话会话记录（对应一次 WS 连接）"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_sessions'
    )
    session_key = models.CharField(max_length=36)  # OpenClaw session UUID
    started_at  = models.DateTimeField(auto_now_add=True)
    ended_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', '-started_at'])
        ]

class ChatMessage(models.Model):
    """per-session 消息记录"""
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant')]
    session  = models.ForeignKey(ChatSession, on_delete=models.CASCADE,
                                 related_name='messages')
    role     = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content  = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['session', 'created_at'])
        ]
```

**Migration**：`manage.py makemigrations api` 生成，由 GROUP_C 执行

**注意**：测试用 SQLite（manage.py test），生产 MySQL；两者 DateTimeField 行为一致（Django ORM 抽象）

### 2.2 骨架文件保护脚本（ADR-011 方案 11-B + 11-C）

**新增文件**：`scripts/skeleton_guard.sh`（仓库追踪，但只在 Pi 上执行）

功能：
1. `skeleton_guard.sh init`：计算骨架文件哈希基准，存入 `~/.openclaw/workspace/.skeleton_hashes`
2. `skeleton_guard.sh verify`：比对当前哈希与基准，输出 PASS/FAIL，返回值 0（PASS）/ 1（FAIL）
3. `skeleton_guard.sh lock`：`sudo chattr +i` 骨架文件列表
4. `skeleton_guard.sh unlock`：`sudo chattr -i` 骨架文件列表（授权修改时使用）

**骨架文件清单**（硬编码在脚本中，以下为默认值，可由用户调整）：
```
~/.openclaw/workspace/SOUL.md
~/.openclaw/workspace/AGENTS.md
~/.openclaw/workspace/TOOLS.md
~/.openclaw/workspace/USER.md
```

### 2.3 新增 Django API 端点（REQ-FUNC-017）

| 端点 | 方法 | 权限 | 功能 |
|------|------|------|------|
| `/api/memory/me/` | GET | 已登录用户 | 查看自己的历史记忆（分页） |
| `/api/memory/me/` | DELETE | 已登录用户 | 清空自己的历史记忆 |
| `/api/admin/memory/<user_id>/` | GET | admin | 查看指定用户记忆 |
| `/api/admin/memory/<user_id>/` | DELETE | admin | 清空指定用户记忆 |

鉴权复用现有 DRF Token Authentication；admin 检查复用 `request.user.is_staff`。

---

## 3. 需要验证的 OpenClaw 能力（来自 ADR-009 VERIFY 清单）

| 验证编号 | 内容 | 是否必须（根据 ADR-009 选择） | 验证优先级 |
|---------|------|--------------------------|---------|
| VERIFY-001 | chat.send 是否支持独立 systemPrompt 参数 | 方案 A 变体 2 时必须，方案 D 不需要 | 低（方案 D 不依赖） |
| VERIFY-002 | agent.create 工具可用性 + 参数格式 | 方案 B 时必须 | 中（如用户想评估方案 B）|
| VERIFY-003 | chat.send 动态 agent_name 路由 | 方案 B 时必须 | 中 |
| VERIFY-004 | OpenClaw 运行时 workspace 切换 | 方案 C 时必须 | 低（方案 C 风险极高） |
| VERIFY-005 | LLM 工具 symlink 写文件行为 | 方案 C 时必须 | 低 |

**若 ADR-009 确定为方案 D：所有 VERIFY 均可跳过，GROUP_C 可直接启动。**

---

## 4. Django migration 影响评估

| Migration | 表 | 影响 | 上线风险 |
|----------|---|------|---------|
| 新增 `api_chat_session` | 纯新增 | 不影响现有表 | 低 |
| 新增 `api_chat_message` | 纯新增 | 不影响现有表 | 低 |

**回滚方案**：`manage.py migrate api <prev_migration>` 回滚两张新表（数据丢失，可接受）

---

## 5. 性能基线与扩展性评估（REQ-NFR-011）

### 5.1 Pi 5 资源现状

| 资源 | 现状 | 本期新增负担 |
|------|------|------------|
| RAM | 4GB，OpenClaw + Django + Nginx + MySQL 已占用约 1.5~2GB | 记忆注入逻辑为内存操作，新增 < 10MB |
| 磁盘 | MySQL @ 192.168.31.98（独立 NAS），不受 Pi 5 磁盘限制 | chat_session + chat_message：10 用户 × 100 轮 × 平均 1KB ≈ 1MB，可忽略 |
| CPU | Pi 5（Arm v8.2），4 核 | DB 查询（索引命中）< 5ms per request |

### 5.2 记忆注入延迟估算（REQ-NFR-011 AC-NFR-011-01）

场景：10 并发用户，每人注入最近 20 轮对话（40 条消息）

```
DB 查询（INDEX user_id + created_at）：
  Pi 5 MySQL 远程 LAN（192.168.31.98）RTT ≈ 1ms
  40 条消息扫描（TEXT 字段，avg 200 byte × 40 = 8KB）
  估算：< 20ms per user

消息拼接（Python 内存操作）：
  40 条 × 200 byte = 8KB 字符串拼接
  估算：< 1ms

总计：< 21ms per user（远小于 500ms 目标）
```

**扩展性（100 用户）**：
- DB 连接：Django 每个 async handler 通过 `sync_to_async` 在线程池中执行 DB 操作，uvicorn `--workers 1` 时线程池大小为 Django 默认（CPU 核数 × 5 = 20），并发 100 用户时 DB 查询排队等待，但每次 < 20ms，总吞吐可接受

---

## 6. 技术约束汇总（与前序项目的兼容性）

| 约束 | 影响 | 处理方式 |
|------|------|---------|
| ChatConsumer 新增 DB 读写（connect/disconnect） | 原 ChatConsumer 完全无状态 | 使用 `sync_to_async` 包装 ORM 操作，不阻塞 async event loop（现有 `_get_user_by_token` 的模式） |
| `--workers 1`（InMemoryChannelLayer 约束） | 多 worker 下 channel 状态不共享 | 不变，单 worker 足够（Pi 5 4 核，聊天场景不 CPU 密集） |
| MySQL read_timeout = 60s（settings.py） | DB 查询若超时（不可能，< 20ms） | 无影响 |
| 测试用 SQLite | chat_session/message 的测试 ORM 兼容 | DateTimeField / TextField 在 SQLite 兼容，无问题 |
| api/tests/ 包结构（PM-DEC-002） | 新测试必须放 api/tests/test_*.py | 新建 `api/tests/test_memory_isolation.py` |

---

## 7. 向后兼容验证点（ARCH-C-006）

本期改动与 reasoning_stream 的兼容性验证计划：

| 验证点 | 验证方法 | 预期结果 |
|-------|---------|---------|
| openclaw_adapter.py v1.3 无改动 | 代码 diff 确认 | 0 行改动 |
| consumers.py v1.2 connect() 新增 DB 读取不影响现有 WS 握手流程 | 单测 `test_connect_with_memory_load` | WS 握手成功，连接时间 < 100ms |
| reasoning_token / stream_token / stream_end 消息流不变 | 运行现有 34 个 test_reasoning_stream.py 测试 | 34/34 通过 |
| 新 API 端点不干扰现有 `/api/` 路由 | URL 冲突检查 | 无路由冲突 |
