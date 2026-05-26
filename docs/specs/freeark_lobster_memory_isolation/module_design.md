# 模块设计文档 — 方舟龙虾记忆隔离

```
file_header:
  document_id: MOD-MEMORY-001
  project: FreeArk — freeark_lobster_memory_isolation
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_system_architect (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-26
  depends_on:
    - ARCH-MEMORY-001 (architecture_design.md)
    - REQ-SPEC-MEMORY-001 (requirements_spec.md)
    - TECH-MEMORY-001 (tech_stack.md)
  note: >
    本文档的模块设计基于 ADR-009 推荐方案 D（Hybrid DB Stateless）。
    若用户选择其他方案（B 或 C），相应模块接口将在 GROUP_C 启动前更新。
    所有 ADR decision 均为 OPEN_FOR_USER_REVIEW。
```

---

## 0. 前提说明

本文档以 **ADR-009 方案 D（FreeArk DB 存历史 + OpenClaw 端 stateless）** 为基础设计模块接口。

已有模块（不改动）：
- **MOD-BE-02**：`openclaw_adapter.py` v1.3 — 无改动
- **MOD-FE-01**：`ChatView.vue` v1.1 — 可选新增"清空记忆"按钮（独立 UI 变更）

本期新增/修改模块：
- **MOD-BE-01（扩展）**：`consumers.py` v1.3（connect 新增记忆加载，disconnect 新增摘要写入）
- **MOD-BE-MEM**：`chat_memory.py`（新建，记忆管理业务逻辑层）
- **MOD-BE-MODEL**：`models.py`（新增 ChatSession / ChatMessage）
- **MOD-BE-API-MEM**：`views.py` 或新建 `memory_views.py`（新增记忆 CRUD API）
- **MOD-OPS-SKEL**：`scripts/skeleton_guard.sh`（骨架文件保护脚本）

---

## 1. 模块依赖图

```
[浏览器 WS] ──→ MOD-BE-01 (consumers.py v1.3)
                    │
                    ├──→ MOD-BE-02 (openclaw_adapter.py v1.3)  [不改动]
                    │        └──→ OpenClaw Gateway :18789        [外部，不改动]
                    │
                    └──→ MOD-BE-MEM (chat_memory.py)
                             │
                             └──→ MOD-BE-MODEL (models.py)
                                      └──→ MySQL (api_chat_session, api_chat_message)

[前端 HTTP] ──→ MOD-BE-API-MEM (memory_views.py)
                    └──→ MOD-BE-MEM (chat_memory.py)

[Pi 5 运维] ──→ MOD-OPS-SKEL (scripts/skeleton_guard.sh)
                    └──→ ~/.openclaw/workspace/ 骨架文件
```

**单向依赖**（无循环依赖）：
- consumers.py → chat_memory.py → models.py → MySQL
- memory_views.py → chat_memory.py → models.py → MySQL
- skeleton_guard.sh → 文件系统（独立，不依赖任何 Python 代码）

---

## 2. 模块详细设计

### MOD-BE-MODEL：models.py 新增（Django ORM）

**文件位置**：`FreeArkWeb/backend/freearkweb/api/models.py`（追加，不修改现有 Model）

**接口**：

```python
class ChatSession(models.Model):
    """
    per-user 对话会话记录，对应一次 WebSocket 连接生命周期。
    
    生命周期：
      创建：ChatConsumer.connect() 成功建立连接时
      更新（ended_at）：ChatConsumer.disconnect() 时
      删除：用户自助清空 / admin 清空 / 账号注销（CASCADE 删除关联 ChatMessage）
    """
    user       : ForeignKey(AUTH_USER_MODEL, on_delete=CASCADE)
    session_key: CharField(max_length=36)    # OpenClaw session UUID（同 ChatConsumer.session_key）
    started_at : DateTimeField(auto_now_add=True)
    ended_at   : DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'api_chat_session'
        indexes  = [Index(fields=['user', '-started_at'])]

class ChatMessage(models.Model):
    """
    per-session 消息记录。
    
    只存 content（不存 reasoning），role ∈ {'user', 'assistant'}。
    assistant 的 content 在 ChatConsumer stream 结束时（stream_end 收到后）一次性写入，
    不逐 token 写入（避免频繁 DB 写）。
    """
    session   : ForeignKey(ChatSession, on_delete=CASCADE, related_name='messages')
    role      : CharField(max_length=20)    # 'user' | 'assistant'
    content   : TextField()
    created_at: DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'api_chat_message'
        indexes  = [Index(fields=['session', 'created_at'])]
```

---

### MOD-BE-MEM：chat_memory.py（新建）

**文件位置**：`FreeArkWeb/backend/freearkweb/api/chat_memory.py`

**职责**：记忆管理的业务逻辑层，封装 DB 操作，供 consumers.py 和 memory_views.py 调用。所有方法为 sync（由调用方用 `sync_to_async` 包装）。

**接口定义**：

```python
# FreeArkWeb/backend/freearkweb/api/chat_memory.py

from django.conf import settings
from .models import ChatSession, ChatMessage

MEMORY_INJECT_LIMIT = getattr(settings, 'MEMORY_INJECT_LIMIT', 20)
# 注入最近 N 轮（= 2N 条消息，user + assistant 各一条）
# 默认 20 轮（40 条），可在 settings.py / .env 中覆盖

def create_session(user, session_key: str) -> ChatSession:
    """
    创建 ChatSession 记录（ChatConsumer.connect 时调用）。
    
    Args:
        user: Django User 实例
        session_key: ChatConsumer 生成的 UUID 字符串
    Returns:
        ChatSession 实例
    """

def close_session(session: ChatSession) -> None:
    """
    设置 ChatSession.ended_at（ChatConsumer.disconnect 时调用）。
    
    Args:
        session: create_session() 返回的 ChatSession 实例
    """

def append_message(session: ChatSession, role: str, content: str) -> ChatMessage:
    """
    追加一条消息记录。
    
    Args:
        session: ChatSession 实例
        role: 'user' | 'assistant'
        content: 消息正文（不含 reasoning）
    Returns:
        ChatMessage 实例
    Raises:
        ValueError: role 不在 ('user', 'assistant') 时
    """

def load_history(user, limit: int = MEMORY_INJECT_LIMIT) -> list[dict]:
    """
    加载用户最近 limit 轮对话历史，供注入 LLM 上下文。
    
    Args:
        user: Django User 实例
        limit: 加载的最大轮数（每轮含 user + assistant 两条）
    Returns:
        按时间升序排列的消息字典列表：
        [
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."},
            ...
        ]
        最多 limit*2 条，不足时返回全部
    """

def clear_memory(user) -> int:
    """
    清空用户的所有历史记忆（ChatSession + ChatMessage，CASCADE 删除）。
    
    Args:
        user: Django User 实例
    Returns:
        删除的 ChatSession 数量（ChatMessage 由 CASCADE 自动删除）
    """

def get_sessions(user, page: int = 1, page_size: int = 20) -> dict:
    """
    分页获取用户的 ChatSession 列表（admin 查看接口用）。
    
    Returns:
        {
            "total": int,
            "page": int,
            "sessions": [
                {
                    "id": int,
                    "session_key": str[:8] + "...",  # 脱敏
                    "started_at": ISO8601,
                    "ended_at": ISO8601 | None,
                    "message_count": int
                },
                ...
            ]
        }
    """

def build_inject_prefix(history: list[dict]) -> str:
    """
    将历史消息列表格式化为注入前缀字符串。
    
    格式：
    [历史记忆开始]
    用户: <content>
    助手: <content>
    ...
    [历史记忆结束]
    
    Args:
        history: load_history() 的返回值
    Returns:
        待注入的字符串（追加到 augmented_message 之前）
        若 history 为空，返回空字符串 ""
    """
```

---

### MOD-BE-01（扩展）：consumers.py v1.3

**文件位置**：`FreeArkWeb/backend/freearkweb/api/consumers.py`

**版本**：v1.2 → v1.3

**变更点**（最小化改动，不影响现有 v1.2 逻辑）：

```
v1.3 相对 v1.2 的变更：
  1. connect()：成功鉴权后，调用 chat_memory.create_session(user, session_key)
     → 新增 self.chat_session 实例变量（存储 ChatSession 对象）
     → 使用 sync_to_async 包装（模式同 _get_user_by_token）
  
  2. disconnect()：新增 close_session + 写入 pending assistant message
     → sync_to_async 调用 chat_memory.close_session(self.chat_session)
     → 若 self._pending_assistant_content 非空，写入最后一条 assistant 消息
  
  3. _handle_chat()：
     a. 开始时：调用 chat_memory.load_history(user) 并 build_inject_prefix()
        → augmented_message 前缀追加历史注入块
        → load_history 使用 sync_to_async 包装
     b. 用户消息已确认后（发送给 OpenClaw 前）：sync_to_async 调用 
        chat_memory.append_message(session, 'user', user_message)
     c. stream 结束时（stream_end 发送后）：sync_to_async 调用
        chat_memory.append_message(session, 'assistant', accumulated_content)
        → accumulated_content 在 _handle_chat 中累积（kind=='content' 时追加）
  
  4. 新增实例变量：
     self.chat_session: ChatSession | None = None
     self._pending_assistant_content: str = ""  （防止 disconnect 时丢失未写入的内容）
```

**关键接口签名（新增/修改部分）**：

```python
# consumers.py v1.3 修改点摘要

class ChatConsumer(AsyncWebsocketConsumer):
    
    # 新增实例变量（在 connect 中初始化）
    chat_session: 'ChatSession | None'       # DB 会话对象
    _pending_assistant_content: str           # 当前未写入 DB 的 assistant content 累积

    async def connect(self):
        # ... 现有鉴权逻辑不变 ...
        # 新增（鉴权成功后）：
        self.chat_session = await sync_to_async(
            chat_memory.create_session
        )(self.user, self.session_key)
        self._pending_assistant_content = ""
        # ... 其余 connect 逻辑不变 ...

    async def disconnect(self, close_code):
        # 新增：关闭会话记录
        if self.chat_session is not None:
            if self._pending_assistant_content:
                await sync_to_async(chat_memory.append_message)(
                    self.chat_session, 'assistant',
                    self._pending_assistant_content
                )
            await sync_to_async(chat_memory.close_session)(self.chat_session)
        # ... 现有 disconnect 日志不变 ...

    async def _handle_chat(self, user_message: str):
        # 新增（在 augmented_message 构建前）：
        history = await sync_to_async(
            chat_memory.load_history
        )(self.user)
        inject_prefix = chat_memory.build_inject_prefix(history)
        
        # 修改（CONFIRM-7 行）：
        chat_user = getattr(self.user, 'username', 'unknown')
        augmented_message = (
            f"{inject_prefix}"                              # 历史注入（空时为 ""）
            f"[__freeark_user__:{chat_user}] {user_message}"
        )
        
        # 新增：记录用户消息
        await sync_to_async(chat_memory.append_message)(
            self.chat_session, 'user', user_message
        )
        
        # 新增：累积 assistant content
        accumulated_content = ""
        
        async for kind, text in OpenClawAdapter.stream_chat(...):
            if kind == 'content':
                accumulated_content += text          # 新增：累积
            # ... 其余路由逻辑不变（reasoning_token / stream_token / reasoning_end）...
        
        # 新增：流结束后写入 assistant 消息
        if accumulated_content:
            await sync_to_async(chat_memory.append_message)(
                self.chat_session, 'assistant', accumulated_content
            )
            self._pending_assistant_content = ""     # 清空 pending
        
        # ... stream_end 发送不变 ...
```

**向后兼容验证**：
- `stream_chat` 调用签名不变（仍传 message 和 session_key）
- reasoning_token / reasoning_end / stream_token / stream_end 的发送逻辑不变
- `_get_user_by_token` 不变
- 原有 34 个 test_reasoning_stream.py 测试逻辑不涉及 connect/disconnect DB 写入，兼容性风险极低

---

### MOD-BE-API-MEM：memory_views.py（新建）

**文件位置**：`FreeArkWeb/backend/freearkweb/api/memory_views.py`

**URL 注册**：在 `api/urls.py` 中追加（不修改现有 URL 配置）

**接口**：

```python
# GET /api/memory/me/ — 查看自己的记忆（分页）
# DELETE /api/memory/me/ — 清空自己的记忆
# GET /api/admin/memory/<user_id>/ — admin 查看指定用户记忆
# DELETE /api/admin/memory/<user_id>/ — admin 清空指定用户记忆

class MyMemoryView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request) -> Response:
        """
        返回当前用户的历史会话列表（分页）。
        Response: {
            "total": int,
            "page": int,
            "sessions": [...] (session_key 脱敏为前8字符+"...")
        }
        """
    
    def delete(self, request) -> Response:
        """
        清空当前用户的所有历史记忆。
        Response: {"deleted_sessions": int, "message": "记忆已清空"}
        """

class AdminMemoryView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get(self, request, user_id: int) -> Response:
        """
        Admin 查看指定用户的历史会话列表（分页）。
        Response: 同 MyMemoryView.get，含目标用户的 username
        """
    
    def delete(self, request, user_id: int) -> Response:
        """
        Admin 清空指定用户的所有历史记忆。
        Response: {"deleted_sessions": int, "target_user": username, "message": "..."}
        审计：自动记录至 Django logger（admin 用户名 + 操作时间 + 目标 user_id）
        """
```

---

### MOD-OPS-SKEL：scripts/skeleton_guard.sh（新建）

**文件位置**：`scripts/skeleton_guard.sh`（仓库追踪，在 Pi 上执行）

**接口**：

```bash
# skeleton_guard.sh <command>
# Commands:
#   init    — 计算骨架文件哈希基准，写入 HASH_FILE
#   verify  — 比对当前哈希与基准，输出 PASS/FAIL，exit 0/1
#   lock    — sudo chattr +i 骨架文件（需要 sudo）
#   unlock  — sudo chattr -i 骨架文件（需要 sudo，授权修改前使用）
#   status  — 显示骨架文件的 chattr 属性和当前哈希

# 骨架文件清单（硬编码，可在脚本顶部修改）
SKELETON_FILES=(
    "$HOME/.openclaw/workspace/SOUL.md"
    "$HOME/.openclaw/workspace/AGENTS.md"
    "$HOME/.openclaw/workspace/TOOLS.md"
    "$HOME/.openclaw/workspace/USER.md"
)
HASH_FILE="$HOME/.openclaw/workspace/.skeleton_hashes"
```

**verify 命令输出格式**（机器可读，满足 AC-NFR-012-01）：
```
[PASS] SOUL.md OK
[PASS] AGENTS.md OK
[FAIL] TOOLS.md CHANGED (expected: abc123... got: def456...)
Exit code: 1
```

---

## 3. 状态机：ChatConsumer v1.3 生命周期

```
DISCONNECTED
    │ connect() 鉴权通过
    │ → create_session(user, session_key)  [DB WRITE]
    ▼
CONNECTED (idle)
    │ receive() chat_message
    │ → load_history(user)               [DB READ]
    │ → append_message('user', ...)      [DB WRITE]
    ▼
STREAMING
    │ OpenClawAdapter.stream_chat()
    │ kind='reasoning' → send reasoning_token
    │ kind='content'   → send stream_token + accumulate
    │ 流结束           → send stream_end
    │ → append_message('assistant', accumulated) [DB WRITE]
    ▼
CONNECTED (idle)   ← 等待下一条消息
    │ disconnect()
    │ → close_session()                  [DB WRITE]
    ▼
DISCONNECTED
```

**异常路径**：
- connect() 时 DB 写入失败（create_session 抛出异常）：记录 WARNING，继续建立连接（记忆功能降级，但 WS 功能正常）
- _handle_chat() 时 load_history 失败：记录 WARNING，以空历史继续（降级，非阻断）
- _handle_chat() 结束后 append_message 失败：记录 ERROR，但 WS 连接不受影响（历史丢失可接受）
- disconnect() 时 close_session 失败：记录 WARNING，ended_at 为 null（数据不完整，无业务影响）

**降级设计原则**：记忆功能失败不应影响基础聊天功能（向后兼容 ARCH-C-006 的精神延伸）

---

## 4. 接口类型化汇总

| 接口 | 输入类型 | 输出类型 | 异常 |
|------|---------|---------|------|
| `create_session(user, session_key)` | `User, str` | `ChatSession` | `IntegrityError` (DB) |
| `close_session(session)` | `ChatSession` | `None` | `OperationalError` (DB) |
| `append_message(session, role, content)` | `ChatSession, str, str` | `ChatMessage` | `ValueError` (role), `OperationalError` |
| `load_history(user, limit)` | `User, int=20` | `list[dict]` | `OperationalError` |
| `clear_memory(user)` | `User` | `int` | `OperationalError` |
| `get_sessions(user, page, page_size)` | `User, int=1, int=20` | `dict` | `OperationalError` |
| `build_inject_prefix(history)` | `list[dict]` | `str` | 无 |
| `ChatConsumer.connect()` | — | 无 | 鉴权失败 → close(4001) |
| `ChatConsumer.disconnect(close_code)` | `int` | 无 | 降级（记日志，不抛出） |
| `ChatConsumer._handle_chat(user_message)` | `str` | 无 | OpenClawUnavailableError（已有处理）|
| `MyMemoryView.get(request)` | `Request` | `Response(200)` | `401 Unauthorized` |
| `MyMemoryView.delete(request)` | `Request` | `Response(200)` | `401 Unauthorized` |
| `AdminMemoryView.get(request, user_id)` | `Request, int` | `Response(200)` | `401/403` |
| `AdminMemoryView.delete(request, user_id)` | `Request, int` | `Response(200)` | `401/403/404` |

---

## 5. 需求覆盖矩阵

| 需求 ID | 简述 | 覆盖模块 | 覆盖方式 |
|--------|------|---------|---------|
| REQ-FUNC-013 | per-user 历史记忆持久化 | MOD-BE-MEM, MOD-BE-01, MOD-BE-MODEL | DB 存储 + connect 时注入 |
| REQ-FUNC-014 | per-user 记忆隔离边界 | MOD-BE-MEM (user_id 过滤), MOD-BE-API-MEM (权限控制) | ORM user_id WHERE 子句 + DRF 权限 |
| REQ-FUNC-015 | 人格骨架锁定 | MOD-OPS-SKEL | chattr +i + 哈希巡检 |
| REQ-FUNC-016 | 记忆读取注入机制 | MOD-BE-MEM (build_inject_prefix), MOD-BE-01 | augmented_message 前缀注入 |
| REQ-FUNC-017a | 账号注销时清理记忆 | MOD-BE-MEM (clear_memory), Django signal | CASCADE DELETE + post_delete signal |
| REQ-FUNC-017b | 用户自助清空记忆 | MOD-BE-API-MEM (MyMemoryView.delete) | DELETE /api/memory/me/ |
| REQ-FUNC-017c | admin 查看/清空记忆 | MOD-BE-API-MEM (AdminMemoryView) | IsAdminUser 权限 + GET/DELETE |
| REQ-NFR-010 | 安全隔离 | MOD-BE-MEM (user_id), MOD-BE-API-MEM (IsAuthenticated) | ORM 层隔离 + API 层鉴权 |
| REQ-NFR-011 | 性能 < 500ms | MOD-BE-MEM (索引查询 < 20ms) | INDEX user_id + created_at |
| REQ-NFR-012 | 骨架完整性可审计 | MOD-OPS-SKEL (verify 命令) | sha256sum -c + exit code |
| REQ-NFR-013 | 向后兼容 reasoning_stream | MOD-BE-01（不改 _handle_chat 核心流程，不改 adapter） | 仅在 connect/disconnect 新增 DB 调用 |
| REQ-NFR-014 | 跨设备一致性 | MOD-BE-MODEL (user FK), MOD-BE-MEM | 记忆与 user_id 绑定而非 session |

---

## 6. 测试设计要点（供 GROUP_D 参考）

| 测试文件 | 测试类 | 测试要点 |
|---------|-------|---------|
| `api/tests/test_memory_isolation.py` | `ChatMemoryCreateSessionTest` | create_session 写 DB；session_key 匹配 |
| | `ChatMemoryLoadHistoryTest` | load_history 返回正确用户的历史；空历史返回 []；limit 截断 |
| | `ChatMemoryIsolationTest` | 用户 A 的历史不出现在用户 B 的 load_history 结果中（核心隔离测试）|
| | `ChatMemoryClearTest` | clear_memory 后 load_history 返回 []；CASCADE 删除 ChatMessage |
| | `ChatMemoryBuildPrefixTest` | 空历史 → prefix="" ；非空历史 → 正确格式前缀字符串 |
| | `ChatConsumerV13ConnectTest` | connect 成功后 chat_session 不为 None；DB 中存在对应 ChatSession |
| | `ChatConsumerV13DisconnectTest` | disconnect 后 ended_at 不为 None；pending content 写入 |
| | `ChatConsumerV13HandleChatTest` | _handle_chat 后 DB 中存在 user + assistant 消息；inject_prefix 不为空（有历史时）|
| | `MemoryAPITest` | GET /api/memory/me/ 200；DELETE /api/memory/me/ 200；跨用户访问 403 |
| | `AdminMemoryAPITest` | admin GET /api/admin/memory/<user_id>/ 200；普通用户 403 |
| `api/tests/test_reasoning_stream.py` | 现有 34 个测试 | 回归：0 failures（向后兼容验证）|

**注意**：`ChatConsumerV13ConnectTest` / `DisconnectTest` / `HandleChatTest` 涉及 WS + DB，需使用 `TransactionTestCase`（PM-DEC-002 教训延续）
