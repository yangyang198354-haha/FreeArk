# 用 LangGraph 替换 OpenClaw 多 agent 编排 —— 方案 + PoC

> 目标：**完全移除 OpenClaw**，用 LangChain/LangGraph 重建「方舟龙虾 + 3 专家」编排机制，
> 显著降低延迟。本目录是可运行 PoC + 设计方案。

---

## 1. 为什么换 —— 现状 31s 的延迟去哪了

当前链路（实测见 `docs/sdlc/multiagent-framework/detailed_design.md` §1.2.3，记忆 `openclaw-multiagent-capabilities`）：

```
浏览器 ──WS──> ChatConsumer ──aiohttp WS──> OpenClaw Gateway(systemd, Node.js)
                                                  └─ main agent 方舟龙虾 (deepseek-v4-flash)
                                                       └─ exec `openclaw agent --agent X --json`   ← 每次子进程冷启动 + 反连 gateway
                                                            └─ 专家 agent ──exec python3 freeark_tool.py──> Django REST   ← 每个工具又一次子进程
```

单专家委派实测 ~31s 稳定。这 31s 的成分（定性）：
| 成分 | 说明 | LangGraph 能否消除 |
| --- | --- | --- |
| LLM 推理（deepseek-v4-flash 单/多轮） | 主体，~半数以上 | ❌ 同一模型，省不了 |
| `openclaw agent` CLI 冷启动 + 反连 gateway | 每次委派一次进程拉起 | ✅ 进程内调用，归零 |
| 工具 `exec python3 freeark_tool.py` 子进程 | 每个工具调用一次 | ✅ @tool 进程内直调 |
| gateway WS 跳转 / 序列化 | 一跳 | ✅ 编排嵌入后端进程，归零 |
| **复合意图：3 专家串行委派** | **3×31 ≈ 93s** | ✅ **并行 fan-out → max ≈ 31s** |

**结论**：LangGraph 省不了 LLM 那一段，但能消除冷启动/子进程/跳转，并把**复合意图从线性累加变成取最大值**。
单专家约提速到「纯推理 + 几百 ms 编排」；复合意图（最常见的"看能耗又看故障"类）是最大赢点。

---

## 2. 目标架构 —— 编排嵌入 Django/Channels 进程

```
浏览器 ──WS──> ChatConsumer ──(进程内 await)──> LangGraphAdapter.stream_chat
                                                  └─ Orchestrator(编译一次，常驻)
                                                       route ──Send fan-out──┬─ energy-expert  ┐
                                                                             ├─ inspection      │ 并行
                                                                             └─ sanheng         ┘
                                                                                  │ @tool 进程内直调 Django ORM/REST
                                                                             aggregate ──token stream──> 浏览器
```

关键：**没有独立 gateway 进程，没有 CLI 子进程，没有 WS 跳转**。编排器在 ASGI 进程里常驻，
工具就是 `TIER1_HANDLERS` 那批函数直接 import。

### 组件逐项映射
| OpenClaw 现状 | LangGraph 替代 | 本 PoC 文件 |
| --- | --- | --- |
| main agent 方舟龙虾 | `route` + `aggregate` 节点 | `orchestrator.py` |
| exec `openclaw agent --agent X` | `Send("expert", payload)`（进程内并发） | `orchestrator.py:_fan_out` |
| 专家 agent（systemPromptOverride） | `expert` 节点 + `EXPERT_PROMPTS` | `orchestrator.py` |
| `freeark_tool.py` 子进程 + 16 个 handler | `@tool` 包装，**直接复用** `TIER1_HANDLERS` | `fa_tools.py` |
| OpenClaw Gateway WS + `OpenClawAdapter` | `LangGraphAdapter.stream_chat`（同签名 drop-in） | `adapter.py` |
| SKILL.md 教 LLM 用工具 | `bind_tools` + tool docstring | （框架内建） |
| Tier-2 二次确认协议（SKILL.md 文本） | LangGraph `interrupt()` 人审打断 | 见 §6 |
| deepseek-v4-flash（经 gateway） | `ChatOpenAI(base_url=deepseek)` 直连 | `orchestrator.py:_make_llm` |

---

## 3. PoC：跑法与结果

PoC 用**真实 LangGraph 机器**（图遍历 / `bind_tools` / `Send` 并行 / `astream`），
仅把「LLM 推理耗时」换成可调延迟的假模型（`fake_llm.py`，合规 `BaseChatModel` 子类），
因此**编排层开销是真实测得的**，可离线无 key 跑。

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
FREEARK_POC_MOCK=1 POC_FAKE_LATENCY=2 python bench.py
```

实测输出（LangGraph 0.3.34 / langchain-core 0.3.86，假模型单轮 2.0s）：
```
[1] 单专家 1st=2.01s 2nd=2.01s Δ=0.00s → 无 per-request 冷启动
[2] 复合查询·专家并行       = 4.01s   命中 3 专家
[3] 复合查询·专家串行(委派) = 8.03s   命中 3 专家
[结果] 端到端加速 2.00×（3 专家）；专家阶段净加速 ≈ 3×
```

读法：并行 = `route(0) + max(L,L,L) + aggregate(L)`；串行 = `route(0) + 3L + aggregate(L)`。
- **专家阶段**净加速 = N×（N 个专家），与延迟无关。
- **端到端**被固定的 aggregate 稀释为 `(N·L + S)/(L + S)`；S（聚合/综合）越轻，越接近 N×。
  生产可让 route/aggregate 走更快的轻模型（如 Haiku/flash-mini），把 S 压小。

把 L 换成真实单专家 ~31s：复合三专家从 **~93s+ 降到 ~31s 量级**。单专家从 31s 降到「纯推理 + 几百 ms」。

### 3.1 真机 live 实测（2026-06-02，树莓派 Pi 5，真实 deepseek-v4-flash + 真实工具）

工具层 LIVE 冒烟（`fa_tools.py --smoke`，真直调 `TIER1_HANDLERS` 打 127.0.0.1:8000）：
```
[OK] get_dashboard_summary / get_plc_status / get_fault_summary(52 个故障) /
     get_usage_daily / get_realtime_params(设备 1-1-10-1001)  → 5/5 全绿（真实生产数据）
```

端到端墙钟（`live_bench.py`，DeepSeek V4 Flash，experts 真调工具，单专家答复含真实 6654 kWh）：
| 场景 | LangGraph 实测 | OpenClaw 现状 | 提速 |
| --- | --- | --- | --- |
| **单专家** | **8.33s** | ~31s（exec 委派） | **≈3.7×** |
| **复合三专家·并行** | **35.58s** | ~93s（串行委派） | **≈2.6×** |
| 复合三专家·串行（进程内对照 run_serial） | 55.34s | — | 并行/串行 1.56× |

读法：
- **单专家 31s→8.3s 是最大、最确定的赢点**：省掉的全是 OpenClaw 的非 LLM 开销（CLI 冷启动 + 反连 gateway + main→expert 两段 LLM 接力）。同一模型，纯推理没变。
- **复合并行 vs 串行只有 1.56×（理论 3×）**：被两件事稀释——① 固定的 aggregate 综合调用（大 prompt，较重）；② DeepSeek 账号对 3 个并发请求可能部分排队，未必满并行。→ 印证 §7 决策 2：route/aggregate 换更轻的模型、确认账号并发额度，可把它推向 3×。
- warm 6.48s 是首次建连/首 token；进程常驻后不再付（对照 OpenClaw 每次委派都付冷启动）。

复现命令（Pi 上，凭据从 `~/.openclaw/agents/main/agent/auth-profiles.json` 取 DeepSeek key、从 `~/.openclaw/freeark.env` 取 FreeArk token，全程脱敏，详见 `run_live.sh`）：
```bash
FREEARK_POC_LIVE=1 DEEPSEEK_API_KEY=... DEEPSEEK_BASE_URL=https://api.deepseek.com \
POC_MODEL=deepseek-v4-flash FREEARK_AGENT_TOKEN=... FREEARK_API_BASE=http://127.0.0.1:8000 \
FREEARK_SKILL_DIR=.../agents/freeark-skill python live_bench.py
```
> ⚠️ openclaw-agent token 受 v0.9.0 会话超时（30min）影响，跑前需「保活」重置 `TokenActivity.last_active_at`（见 `run_live.sh` step 1 / 记忆 lobster-agent-architecture）。

---

## 4. 文件清单
| 文件 | 作用 |
| --- | --- |
| `fa_tools.py` | 把生产 `TIER1_HANDLERS` 进程内包成 LangChain `@tool`（含离线 mock） |
| `fake_llm.py` | 带模拟延迟的确定性假模型，离线跑通真实 LangGraph |
| `orchestrator.py` | StateGraph：route → Send 并行 fan-out → expert → aggregate；`_make_llm` 工厂 |
| `adapter.py` | `LangGraphAdapter.stream_chat`，与 `OpenClawAdapter` 同签名的 drop-in |
| `bench.py` | 并行 vs 串行 + 冷启动基准 |
| `requirements.txt` | langgraph / langchain-core / langchain-openai（版本区间） |

---

## 5. 迁移计划（分阶段，不一刀切）
1. **影子并行**：保留 OpenClaw，新增 `langgraph_adapter.py` 到 `api/`，加 `CHAT_BACKEND=langgraph|openclaw` 开关。默认仍 openclaw。
2. **工具对齐**：`fa_tools.py` 升级为真直调 `TIER1/TIER2_HANDLERS`（去掉 mock），`FreeArkClient` 的 urllib 换 httpx 连接池（或直接调 Django ORM，省掉自打 HTTP 的一跳）。
3. **专家提示装载**：读 `agents/<expert>/SYSTEM_PROMPT.md` 填 `EXPERT_PROMPTS`（已有 phase-3 产物，agent-builder 98/94/91 分）。
4. **路由升级**：`route` 从关键词换成 LLM 分类器（或 supervisor handoff tool_calls）。
5. **回归 + 灰度**：跑 `detailed_design.md` §8.2 TC-01~08；开关切 langgraph，观察一段；稳定后**移除 OpenClaw**（gateway systemd unit、freeark-skill 注册、`openclaw.json` 多 agent 配置）。
6. **退役**：卸载 OpenClaw 包、删 `~/.openclaw/`、清 systemd unit。token 注入改为 Django settings 读 env（沿用现有 `.env` 机制）。

---

## 6. 取舍与风险（诚实清单）
- **失去 OpenClaw 的能力**：gateway 多端接入、SKILL.md 热重载、内建会话存储。
  - 会话记忆：FreeArk 已有 `chat_memory`（DB），LangGraph 用 `MemorySaver`/`checkpointer` 接 DB 即可，反而更可控。
  - Tier-2 写操作二次确认：现在靠 SKILL.md 文本协议。LangGraph 用 **`interrupt()` 人审打断**，把确认从"提示词约定"变成"图级强制门"——更安全。需在 `expert`/写工具前插 interrupt 节点。
- **Pi aarch64 依赖风险**（重要教训 [[freeark-channels-redis-multiworker]]）：langgraph/langchain 纯 Python，但 pydantic-core 是 Rust 扩展，**必须在 Pi 上 `pip install -r requirements.txt` 后逐一 import + 跑 bench + live 冒烟**，别在 x86 上想当然。
- **流式粒度**：`astream(stream_mode="messages")` 的 token 增量依赖模型是否真流式。deepseek-v4-flash 经 ChatOpenAI 支持 SSE 流；假模型非流式时本 PoC 走整段兜底（已验证 yield 协议正确）。
- **进程内 = 阻塞风险**：编排跑在 ASGI 进程，长任务占 event loop。LangGraph 全 async（本 PoC 已用 `ainvoke`/`astream`），工具若有同步阻塞调用需 `asyncio.to_thread` 包裹。
- **成本/限流**：直连 DeepSeek 后并发 fan-out 会同时发 N 个请求，注意账号 RPM/并发额度。

---

## 7. 待决策（需你拍板）
1. **编排进程位置**：嵌入现有 ASGI（最低延迟，本方案默认）vs 独立 FastAPI/LangServe 微服务（隔离但多一跳）？
2. **路由模型**：route/aggregate 是否用更轻的模型压 S（端到端更接近 N×）？
3. **会话记忆**：LangGraph checkpointer 接现有 `chat_memory` DB 表，还是新建？
4. **移除 OpenClaw 的时机**：先影子灰度多久再退役 gateway？

> 本 PoC 不改任何生产文件、不动 `.env`/`openclaw.json`/systemd。仅 `agents/langgraph-poc/` 新增目录。
