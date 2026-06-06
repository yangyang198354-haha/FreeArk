# 第三阶段落地实施计划 —— LangGraph 编排替换 OpenClaw（生产灰度→退役）

> 前置：PoC 三件套已在树莓派真机验证（README §3.1）：单专家 31s→8.3s（≈3.7×）、
> 复合三专家 93s→35.6s（≈2.6×）。本文是把 PoC 搬进生产 ASGI 进程、灰度切换、
> 最终退役 OpenClaw 的**可执行步骤清单**，含每步回滚点与验收门。
>
> 总原则：**一次只动一层**；每步默认仍走 OpenClaw（开关默认 openclaw）；
> 每步可独立回滚（改一个 env 值）；不删 OpenClaw 直到灰度稳定。

---

## 0. 接缝事实（已核实，决定了本计划风险极低）

| 接缝 | 现状 | 落地动作 |
| --- | --- | --- |
| ChatConsumer 调用点 | `consumers.py:195` `async for kind, text in OpenClawAdapter.stream_chat(message, session_key)` | 不改这一行的语义，仅换 adapter 来源 |
| adapter 签名 | `stream_chat(message, session_key) -> AsyncGenerator[tuple[str,str]]`，kind∈{reasoning,content} | `LangGraphAdapter` **逐字同签名**（PoC 已验证） |
| 错误通道 | `consumers.py:236` `except OpenClawUnavailableError` | LangGraphAdapter 失败时 raise **同一个** `OpenClawUnavailableError` |
| 工具层 | `TIER1_HANDLERS`（纯函数，可 import） | `fa_tools.@tool` 已真直调（live 5/5 绿） |
| 专家提示 | `agents/{energy-expert,inspection-expert,sanheng-knowledge}/SYSTEM_PROMPT.md` 已就位（agent-builder 98/94/91） | 启动时读入 `EXPERT_PROMPTS` |
| 模型 | deepseek-v4-flash（OpenAI 兼容） | `ChatOpenAI(base_url=deepseek)` 直连（live 已验证） |
| 凭据 | `~/.openclaw/freeark.env` 的 FREEARK_AGENT_TOKEN / DeepSeek key 在 auth-profiles.json | 退役时改由 Django `.env` 注入（§阶段F） |

**结论：生产侧真正改动 = 新增 `api/langgraph/` 包 + `consumers.py` 一行 import 换成工厂 + settings 加开关。OpenClaw 代码一行不删，直到阶段 F。**

---

## 阶段 A —— 影子接入（开关默认 openclaw，零行为变化）

目标：把 PoC 代码搬进生产代码树并能被开关选中，**但默认不启用**，生产行为零变化。

### A.1 代码落位 ✅ 已落地（2026-06-02）
> ⚠️ 包名取 **`langgraph_chat`** 而非 `langgraph`——后者会遮蔽 pip 安装的第三方
> `langgraph` 顶层包（import footgun）。计划原写 `api/langgraph/`，落地时修正。

PoC 文件 → 生产包（去掉 mock 强依赖，mock 仅供单测）：
```
FreeArkWeb/backend/freearkweb/api/langgraph_chat/
  __init__.py        ← 轻量，不在 import 期构造图/LLM/工具
  fa_tools.py        ← 工具桥接（skill 路径 env>settings>仓内相对；FREEARK_POC_MOCK 仅单测）
  fake_llm.py        ← 离线假模型（LANGGRAPH_USE_FAKE_LLM=True 启用，CI/单测）
  prompts.py         ← 专家提示装载：已能从 SYSTEM_PROMPT.md 读真提示，缺失退回内置兜底
  router.py          ← 路由：阶段 A 关键词 route_experts()，阶段 D 换 LLM 分类器（签名不变）
  orchestrator.py    ← StateGraph：route→Send 并行 fan-out→expert→aggregate；_make_llm 读 settings
  adapter.py         ← LangGraphAdapter.stream_chat（同 OpenClawAdapter 签名）+ warm()
```
> `fa_tools.py` skill 路径优先级：env `FREEARK_SKILL_DIR` > `settings.LANGGRAPH_SKILL_DIR`
> > 仓内相对 `<repo>/agents/freeark-skill`。
> **prompts.py 已实测装载真实生产提示**（energy/inspection/sanheng = 6199/13050/8178 字符，
> 即 agent-builder 98/94/91 产物；sanheng 自动拼接 KNOWLEDGE.md）——阶段 C 提示装载实质已就绪，
> 文件缺失时安全退回内置兜底，不打挂聊天。

### A.2 后端工厂 + 开关（最小侵入 consumers.py）
新增 `api/chat_backend.py` ✅：
```python
from django.conf import settings
def get_chat_adapter():
    backend = getattr(settings, "CHAT_BACKEND", "openclaw")
    if backend == "langgraph":
        from api.langgraph_chat.adapter import LangGraphAdapter
        return LangGraphAdapter
    from api.openclaw_adapter import OpenClawAdapter
    return OpenClawAdapter
```
`consumers.py` 改动仅两处：
```python
# 顶部 import（保留 OpenClawUnavailableError 作为统一异常）
from api.openclaw_adapter import OpenClawUnavailableError
from api.chat_backend import get_chat_adapter
# 调用点（原 line 195）
adapter = get_chat_adapter()
async for kind, text in adapter.stream_chat(message, session_key):
```
`settings.py`：`CHAT_BACKEND = os.environ.get("CHAT_BACKEND", "openclaw")`。

### A.3 LangGraphAdapter 生产化改动
- 失败统一 `raise OpenClawUnavailableError(...)`（连不上 DeepSeek / 工具异常 / 超时），
  让 `consumers.py:236` 既有降级路径原样接管。
- `_ORCH` 单例移到 Django `AppConfig.ready()` 构造（warm 在 worker 启动时付一次），
  而非模块 import 时——避开 migrate/collectstatic 等管理命令误触发建连。
- DeepSeek key / FreeArk token 经 `settings`（读 `.env`），**不再读 openclaw.env**。

### A.4 aarch64 依赖纪律（硬约束，教训 [[freeark-channels-redis-multiworker]]）
**禁止在 x86 上想当然。** 必须在 Pi 上独立 venv：
```bash
pip install -r requirements.txt
python -c "import langgraph, langchain_core, langchain_openai, pydantic_core; print('ok')"
python -m pytest api/langgraph/tests/   # mock 模式离线单测
FREEARK_POC_LIVE=1 ... python -m api.langgraph.smoke   # live 工具 5/5
```
pydantic-core 是 Rust 扩展，确认 aarch64 wheel 可用；锁版本区间同 PoC。
**与现有 channels_redis / redis-py 版本同环境装，跑一次 WS 真收发**，确认不引入依赖冲突。

### A 已完成的本地验证（2026-06-02，Windows / Py3.11）
- 全部新增 + 改动文件 `py_compile` 通过（零语法错误）。
- 纯 Python 接缝实跑：`route_experts()` 单/复合意图命中正确；`prompts.py` 装载真实生产提示成功。
- 离线单测 `api/tests/test_langgraph_phase_a.py` 已就位（mock 工具 + 假模型，覆盖工厂/路由/run/run_serial/适配器 yield 协议/失败降级），本地因未装 langgraph 自动 skip。

### A 真机验证结果（2026-06-02，Pi 5 / aarch64 / Py3.13.5，/tmp 一次性 venv，未碰生产 venv/repo）
- ✅ **Gate 1 依赖**：pip 装 langgraph 0.3.34 / langchain-core 0.3.86 / langchain-openai 0.3.35 /
  **pydantic-core 2.46.4（Rust 扩展 aarch64 wheel 干净）** / django 5.2.14，全部 import 成功。
  channels_redis 式依赖雷区未重演。
- ✅ **Gate 2 工具层 LIVE**：`fa_tools` 真直调 handler 打 127.0.0.1:8000 → **5/5 全绿**（真实生产数据：
  看板摘要 / PLC 全量 / 故障 52 个专有部分 / 日用量 / 设备 1-1-10-1001 实时参数）。
  （首跑 fault_summary 撞 Tier-1 客户端 5s 超时，再跑即过——已知冷查询瞬态，非代码缺陷，见下方风险）
- ✅ **Gate 3 编排图**：`pi_validate.py`（fake LLM + mock 工具）→ 单专家路由 / 并行 fan-out(3) /
  串行 全部正确，exit 0。证明 StateGraph / Send / operator.add reducer / astream 在 aarch64 跑通；
  提示缺失时优雅回退内置兜底（不崩）也一并验证。

### A 生产部署 + 在仓验证结果（2026-06-02，Pi）
- ✅ **依赖装入 prod venv（纯增量）**：`comm -23` 安装前后快照为空——**无任何现有包被改版本**
  （redis 5.3.1 / channels 4.3.2 / Django 5.2.8 / DRF 3.16.1 全不变；langgraph/langchain 不依赖 redis）。
  回滚锚：`/tmp/venv-freeze-before.txt`。
- ✅ **代码部署进生产 repo**：新文件（langgraph_chat/ + chat_backend.py + 测试）+ 覆盖 consumers.py/apps.py/
  requirements.txt（与基线一致，安全）+ settings.py 外科手术追加 CHAT_BACKEND 块（保留 Pi 多出的 6 行）。
  回滚锚：`/tmp/deploy-bak/`。**部署后默认 CHAT_BACKEND=openclaw，线上行为零改变。**
- ✅ **item 3 在仓单测**：`manage.py test api.tests.test_langgraph_phase_a --settings=freearkweb.test_settings`
  → **8 tests OK**（不再 skip）。
- ✅ **item 4 真 WS + 真 Redis 无冲突**：隔离 uvicorn :8001（CHAT_BACKEND=langgraph + 真 Redis channel layer
  + fake LLM + mock 工具），WS 客户端往返 → **connected/stream_token/stream_end 全收到，PASS**。
  channels_redis 4.x RESP3 超时 bug **未重演**，langgraph 与 channels_redis 同 ASGI 进程共存、WS receive 正常。
- ⚠️→✅ **安全事故已闭环**：WS 测试把 token 放 `?token=` query string，被 uvicorn access log 记录并进入对话。
  **已轮换 openclaw-agent token**（`--force-regenerate-token` → 从 DB 写回 freeark.env[env==db 校验通过]
  → 重启 gateway[active] → `/api/auth/me/` 200 验证；旧 token 已 DB 删除作废；openclaw.json 无残留）。
  教训记入 [[freeark-ws-token-query-string-leak]]：WS 鉴权测试勿把 token 放 URL；consumer 从 query string
  读 token 本身易泄露，长期应改 header/subprotocol（可在 LangGraph 落地时顺带修）。

### A 仍待办
- 灰度前：把 Pi 上这批 uncommitted 改动正式 commit（PR），而非长期挂在工作树。
- DeepSeek 真 LLM 的端到端 WS（非 fake）可在切灰度时一并验。

### ⚠️ 已知限制（阶段 B 再优化，非阻塞）
- **单专家答复不逐 token 流式**：单专家时 aggregate 是 passthrough（不调 LLM），
  `stream_mode="messages"` 捕获不到 aggregate 的 token，适配器退回整段一次 yield。
  语义正确、用户拿到完整答复，但失去打字机效果。复合意图（aggregate 调 LLM）正常流式。
  待修（独立项，非阶段 B）：单专家时直接透传 expert 节点 token，或最终答复统一过 aggregate 流式。

### ✅ A 验收门 / 回滚
- 验收：`CHAT_BACKEND=openclaw`（默认）时聊天行为与上线前**逐字节一致**；
  手动 `CHAT_BACKEND=langgraph` 重启一个 worker，能跑通一次单专家对话。
- 回滚：删 env / 改回 `openclaw`，重启。无 DB 变更、无 OpenClaw 改动。

---

## 阶段 B —— 工具层去 HTTP 自打一跳 ✅ 已实现（2026-06-03）

现状 `fa_tools → TIER1_HANDLERS → FreeArkClient(urllib) → 打 127.0.0.1:8000 自己`。
编排已在 ASGI 进程内，自己 HTTP 调自己 = 多余一跳 + 序列化 + **占用自身一个 worker**
（--workers 2 下自调用有 worker 争用风险——这是比延迟更重要的动机）。

**实现方式（最终选型，优于原计划的 B1/B2）**：`langgraph_chat/fa_direct.py` 的
`DirectClient` 与 `FreeArkClient` **同接口**（`.get(path,params)→{success,data,http_status}`），
内部用 `django.urls.resolve(path)` 定位 view + `RequestFactory`+`force_authenticate(openclaw-agent)`
**进程内直接调用 DRF view 函数**，不走 HTTP/网络/uvicorn 路由。
`FA_TOOLS_MODE=direct` 时把共享模块 `tier1_readonly._client` **monkeypatch** 成 DirectClient——
16 个 handler **一行不改、输出字节级一致**（只换传输层）；OpenClaw 是独立子进程，patch
仅在本 Django 进程生效，不影响 live OpenClaw 路径。装配失败自动退回 http。
- 异步安全：tools 经 `await tool.ainvoke()`，langchain 把同步 tool 放线程池执行，不阻塞 event loop。
- 鉴权：force_authenticate 以 openclaw-agent 身份，Tier-1 只读视图无 per-user 过滤；不走 token。
- Tier-2 写仍走 HTTP（DirectClient.post 抛 NotImplementedError），保留 operator 追溯/二次确认，见阶段 E。

### ✅ B 真机验证（2026-06-03，Pi，未碰生产 venv/repo——临时部署跑完即 checkout 还原）
- 在仓单测 12/12 OK（含 4 个 direct 路由用例：url_name 解析 / 404 信封 / 模式解析）。
- direct 模式工具 LIVE 5/5，数据与 http **逐项一致（parity OK）**。
- 墙钟对比（best of 3，真实生产数据）：

  | 工具 | http(现状) | direct | 提速 |
  | --- | --- | --- | --- |
  | dashboard | 50.7ms | **28.4ms** | ~44% |
  | plc | 58.0ms | **18.3ms** | ~68% |
  | fault（DB 重） | 142.9ms | **122.0ms** | ~15% |

  读法：省掉 localhost HTTP 往返（~20–40ms/调用）；DB 重的查询里 HTTP 占比小、收益小。
  **更大的价值是消除 worker 自调用争用**（架构正确性，非单看延迟）。

### ✅ B 验收门 / 回滚
- 验收：单测 12/12；direct 模式 smoke 5/5 且与 http parity；单工具墙钟下降。✅ 全部满足。
- 回滚：`FA_TOOLS_MODE=http`（默认）即恢复现状自打 REST；direct 装配失败也自动退回 http。

---

## 阶段 C —— 专家提示装载 ✅ 已实现（2026-06-03）

> ⚠️ 关键修正：原计划是「直接读 OpenClaw 的 `SYSTEM_PROMPT.md` 当 EXPERT_PROMPTS」（阶段 A
> 的 prompts.py 已这么做）。但实读发现这 3 个 OpenClaw 提示**深度绑定 OpenClaw 协议**，
> 直接用于 LangGraph 是**错的**：
> - 指示「用 `exec python3 freeark_tool.py` 调工具」——LangGraph 是原生 `bind_tools`，照做会让
>   LLM 输出文本而非 tool_call。
> - 强制输出 orchestrator 机器 JSON（`{"status":...,"data":...}`）+ `[ROUTE_REQUIRED]` 路由标记，
>   且「只面向 orchestrator、禁止面向用户」——但 LangGraph 单专家答复**直接给用户看**。
> - inspection-expert 原版面向**另一个待开发 skill**（`inspect_tool.py` + journald 日志），与其在
>   LangGraph 的实际工具（PLC/故障/实时参数 REST）**不符**。
> （之前 live bench 能跑通，是因为 bind_tools 把真实工具喂给模型、模型忽略了 CLI 文本；但输出
>  框架仍是错的。）

**实现**：新增 3 个 **LangGraph 适配版** `agents/<expert>/SYSTEM_PROMPT.langgraph.md`（**不动**
OpenClaw 原版 `SYSTEM_PROMPT.md`，live OpenClaw 不受影响），对齐各专家**实际绑定的工具** +
面向用户的自然语言输出，并保留安全脚手架（注入防御 / 不杜撰 / 不泄密 / 通用-vs-FreeArk 标注）。
`prompts.py` 装载优先级改为 `.langgraph.md` > `SYSTEM_PROMPT.md`（OpenClaw 兜底）> 内置兜底；
sanheng 仍追加 `KNOWLEDGE.md`。

### ✅ C 真机验收（2026-06-03，Pi 真 DeepSeek-v4-flash，三专家各一题，跑完 checkout 还原）
- **三专家输出全为干净的用户向中文 prose，零协议/CLI 残留**（无 `{"status}`、无 `[ROUTE_REQUIRED]`、
  无 `exec`/`freeark_tool.py`）。
- inspection：plain-language 巡检结论「需关注」+ 真实数据（634 总 / 529 在线 / 105 离线 / 83.44%）+
  故障接口超时时如实说明、不杜撰 + 处置建议。
- sanheng（7.0s，无工具）：原理讲解清晰，正确标注「FreeArk 实际阈值以系统数据为准」，未伪造专属值。
- energy：dashboard 工具超时 → 如实「数据获取失败，建议重试」、不编造（提示要求的诚实行为）。
  （dashboard/fault 的 5s 超时是已知 http 路径冷查询瞬态，与提示无关；阶段 B 的 direct 模式可规避。）

### 设计取舍：fail-fast vs 兜底
原计划要求「文件缺失 fail-fast」。落地选择**保守兜底**（`.langgraph.md`→OpenClaw→内置），并对每个
专家 INFO 日志记录实际装载来源——避免因提示文件缺失把聊天打挂（聊天路径优先可用性）。已偏离原计划，记录在此。

### ✅ C 验收门 / 回滚
- 验收：三专家代表性问题答复为用户向 prose、口径正确、无协议残留、不杜撰。✅ 满足。
- 回滚：删 `.langgraph.md` 即自动退回 OpenClaw 原版（prompts.py 优先级链）。

---

## 阶段 D —— 路由升级（关键词 → LLM 分类器）

PoC 的 `_route` 是关键词命中（离线可测但易漏判）。生产换 `router.py`：
- **LLM 分类器**：一次轻量调用返回命中专家集合（JSON）。用**更轻的模型**（决策 2）。
- 或 **supervisor handoff**：main agent 第一轮 tool_calls 决定派发哪些专家。
- 兜底：分类失败 → 关键词路由 → 仍空 → energy-expert（保留 PoC 兜底链）。

### ✅ D 验收门
- 路由准确率：用 detailed_design §8.2 的 TC 问题集 + 复合意图问题，命中专家集合正确率 ≥ 既有水平；
  单意图不要误触发多专家（控成本/并发）。

---

## 阶段 E —— Tier-2 写操作人审门（安全，不可跳过）

现状二次确认靠 SKILL.md **文本协议**（软约束）。LangGraph 用
`interrupt()` 把它变成**图级强制门**（硬约束，README §6）：
- 写工具（TIER2_HANDLERS）前插 interrupt 节点 → 暂停、回传待确认动作给前端 →
  用户确认后 `Command(resume=...)` 继续。
- 需要 checkpointer 才能 interrupt/resume（见决策 3）。
- 保留 `operator_override = openclaw-agent::<chatuser>` 追溯格式（记忆 lobster-agent-architecture）。

### ✅ E 验收门
- 写操作（如设 24°C）**必须**经前端确认才落库；未确认时 DB 无变化（实测一条）。
- 拒绝/超时路径不留半完成状态。

---

## 阶段 F —— 回归 + 灰度 + 退役 OpenClaw

### F.1 回归
跑 `docs/sdlc/multiagent-framework/detailed_design.md` §8.2 TC-01~08（两后端各跑一遍对拍）：
- 单专家、复合意图、Tier-2 写确认、降级（DeepSeek 不可达）、会话记忆、并发。
- 串行通过率门控（沿用 test-engineer 既有标准）。

### F.2 灰度
- 先 `CHAT_BACKEND=langgraph` 切**一个** worker（--workers 2 里的一个），观察 1~3 天：
  错误率、墙钟 P50/P95、DeepSeek RPM/并发是否触限（决策 2）。
- 监控指标对照基线：单专家应 ≈8s 量级、复合 ≈35s 量级。

### F.3 退役（确认稳定后，需 PM CONFIRM）
1. 全量切 `CHAT_BACKEND=langgraph`，观察一个周期。
2. 停 `openclaw-gateway.service`（systemd --user disable + stop）。
3. 删 OpenClaw 多 agent 配置：`openclaw.json` skills 注册、freeark-skill 注册。
4. 凭据迁移：FreeArk token / DeepSeek key 改由 Django `.env`（沿用现有机制），
   不再依赖 `~/.openclaw/freeark.env`。**openclaw-agent 会话超时问题随之消失**
   （不再走 SlidingWindowToken 那条机器人账号链路；或保留 token 但本地直调免会话窗口）。
5. 卸载 OpenClaw 包、清 `~/.openclaw/`、删 systemd unit + daemon-reload。
6. `OpenClawAdapter` / `openclaw_adapter.py` 可保留一版本周期作回滚锚，再删。

### ✅ F 验收门 / 回滚
- 灰度期任一指标劣化 → 改回 `openclaw` 重启即回滚（退役前 OpenClaw 全在）。
- 退役后回滚成本高（需重装），故退役必须在灰度稳定 + PM 明确 CONFIRM 后。

---

## §7 四个待决策 —— 本计划采用的默认（可推翻）

| 决策 | 本计划默认 | 理由 |
| --- | --- | --- |
| 1. 编排进程位置 | **嵌入现有 ASGI**（不独立微服务） | 最低延迟，drop-in 已验证；独立服务多一跳违背提速初衷 |
| 2. 路由/聚合模型 | **route/aggregate 用更轻模型**（flash-mini/Haiku 级） | live 实测复合并行只 1.56×，瓶颈在重 aggregate + DeepSeek 并发；压 S 可推向 3×。**同时确认 DeepSeek 账号 RPM/并发额度** |
| 3. 会话记忆 | **LangGraph checkpointer 接现有 `chat_memory` DB**（不新建表） | 已有 DB 记忆；阶段 E 的 interrupt/resume 也依赖 checkpointer，一并解决 |
| 4. 退役时机 | **灰度稳定 1 周 + PM CONFIRM 后退役** | 退役前 OpenClaw 全在可秒回滚；退役不可逆需双门 |

---

## 风险与纪律小结

- **aarch64 依赖**：阶段 A 必须 Pi 上真装真 import 真 smoke（pydantic-core Rust 扩展）。
- **event loop 阻塞**：同步工具/ORM 调用一律 `asyncio.to_thread`；编排全 async。
- **DeepSeek 并发限流**：fan-out 同发 N 请求，灰度盯 RPM；必要时给 expert 调用加信号量。
- **凭据**：DeepSeek key / token 全程经 settings/.env，不进 git、不进对话、不进 openclaw.json。
- **生产改动逐层可回滚**；OpenClaw 不删直到阶段 F；退役需 PM CONFIRM。
- 不动 `.env` / `package-lock.json` / `openclaw.json`（直到退役且经确认）/ `.claude/`。

---

## 一句话路线图
A(影子接入·零变化) → B(去自打 HTTP) → C(装真提示) → D(LLM 路由) →
E(Tier-2 interrupt 硬门) → F(回归→单 worker 灰度→全量→退役 OpenClaw)。
每步默认仍走 openclaw，改一个 env 值即回滚。
