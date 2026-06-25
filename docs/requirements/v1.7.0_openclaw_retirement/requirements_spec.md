# v1.7.0 OpenClaw 集成退役 — 需求规格（范围文档）

**版本**: v1.7.0  
**日期**: 2026-06-25  
**状态**: APPROVED（用户已明确授权执行）  
**负责人**: main agent pm

---

## 1. 背景

FreeArk 生产聊天自 v1.3.0 起逐步迁移至进程内 LangGraph 编排（直连 DeepSeek），
生产 `.env` 已设 `CHAT_BACKEND=langgraph` + `FA_TOOLS_MODE=direct`。
OpenClaw Gateway（openclaw-gateway.service，端口 18789/18790）两天零聊天流量，
确认为完全 idle。本版本彻底退役 OpenClaw 集成，消除死代码与运维负担。

---

## 2. 做什么（IN SCOPE）

### 2.1 代码层（后端 Python）
- 新建 `api/chat_exceptions.py`，将 `OpenClawUnavailableError` 迁移至此作为通用聊天降级异常
- 修改 `api/consumers.py`、`api/langgraph_chat/adapter.py` 的 import 指向新位置
- 简化 `api/chat_backend.py`：移除 openclaw 分支，工厂无条件返回 `LangGraphAdapter`
- 清理 `api/apps.py`：移除 openclaw 条件守卫，预热逻辑无条件执行
- 删除 `api/openclaw_adapter.py`（搬走异常类后）
- 删除 `api/management/commands/create_openclaw_agent_user.py`
- 删除 openclaw 专属测试文件（`test_openclaw_integration.py`、`test_openclaw_unit.py`、`test_reasoning_stream.py`）
- 修正其他测试文件中的 openclaw import/patch 路径（`test_langgraph_phase_a.py`、`test_memory_consumer_v13.py`）

### 2.2 生产基建层（由主控执行 SSH）
- 停用并 disable `openclaw-gateway.service`（systemd 用户服务）
- 删除 nginx openclaw 反代配置（`/etc/nginx/sites-enabled/freeark-openclaw`）
- 删除 `~/.openclaw/`（含配置文件与明文 token）
- 删除 `~/.openclaw_gateway_token`
- 卸载全局 npm 包 `openclaw`（**保留 Node.js**，前端构建依赖）
- 清理生产 `.env` 中的 openclaw 相关键（`OPENCLAW_BASE_URL` 等 4 个键）
- 删除 `openclaw-agent` DRF Token（**暂缓删除 DB 用户账号**，见第 4 节）

---

## 3. 不做什么（OUT OF SCOPE）

- 不修改 `api/langgraph_chat/fa_direct.py` 的用户名字符串 `"openclaw-agent"`
  （此账号是 LangGraph 工具直调的 `force_authenticate` 身份，生产路径活跃依赖，需独立版本处理）
- 不修改 `api/views_device_settings.py` / `api/serializers_device_settings.py` 的
  `username == 'openclaw-agent'` 逻辑（工具写入的 operator 追溯，仍有意义）
- 不修改 `api/langgraph_chat/` 下仅含注释/docstring 的 openclaw 历史引用
- 不卸载 Node.js（前端构建必须）
- 不修改数据库 Schema
- 不改动前端代码

---

## 4. 重要说明：`openclaw-agent` DB 账号

`openclaw-agent` 数据库用户账号**本次不删除**，原因：

`api/langgraph_chat/fa_direct.py` 在 `FA_TOOLS_MODE=direct` 路径下调用
`get_user_model().objects.get(username="openclaw-agent")` 进行 `force_authenticate`，
是当前生产 LangGraph 工具调用的活跃鉴权机制。

删除该账号会导致所有 Tier-1 工具查询（能耗、巡检、三恒知识库等）抛 `DoesNotExist`，
聊天功能实质性损坏。

**建议后续独立处理**：重命名该账号（如 `freeark-agent`），同步修改
`fa_direct.py`、`views_device_settings.py`、`orchestrator.py` 中的用户名字符串，
并执行数据迁移。本版本不包含此工作。

---

## 5. 验收标准（退役后必须成立）

| AC# | 验收条件 | 验证方法 |
|-----|---------|---------|
| AC-1 | LangGraph 聊天端到端仍正常（流式回复、工具调用均通过） | 生产端 WS 连接测试 |
| AC-2 | 后端能正常 import 并启动（无 ImportError / ModuleNotFoundError） | 测试套件 collection 零报错 |
| AC-3 | 后端测试无新增回归（原通过的测试仍通过） | 1494 passed，8 个 baseline 失败不变 |
| AC-4 | Node.js 与前端 `npm run build` 不受影响 | 仅卸载 npm global package `openclaw`，不动 Node.js 本体 |
| AC-5 | openclaw-gateway 停用后聊天不受影响 | 生产 CHAT_BACKEND=langgraph，不走 gateway |
| AC-6 | `api/openclaw_adapter.py` 不再存在于代码库 | `git status` / `ls` 确认 |

---

## 6. 状态

| 阶段 | 状态 |
|------|------|
| 代码改动（AC-2, AC-3, AC-6） | **DONE** — 2026-06-25，测试通过，等待 commit |
| 生产基建退役（AC-5） | 待主控执行 runbook |
| `openclaw-agent` 账号重命名 | 推迟至独立版本 |
