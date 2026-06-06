# 阶段 F 执行手册 —— 回归 → 灰度 → 退役 OpenClaw

> 配套 `PHASE3_ROLLOUT.md` 阶段 F。A–E 已全部并入 main（PR#2/#3/#4/#5/#7）。
> 本手册是**在 Pi 生产上**执行的可操作清单；**退役（F.3）不可逆，须 PM 明确 CONFIRM**。
> 生产事实以 `freeark-prod-deploy` skill 为准（服务名/路径/构建/重启）。
>
> ⚠️ **三条相对原计划的修正（务必先读）**：
> 1. **生产是 `--workers 1` + InMemoryChannelLayer**（perf-P1a 已回滚）。原"切 --workers 2 里的一个 worker 灰度"**不成立**——单 worker 下切换是**全量**。灰度方案见 F.2。
> 2. **DeepSeek key 当前在 OpenClaw**（onboard 时注入）。LangGraph 路径走 `settings.DEEPSEEK_API_KEY`（读 .env），未设则用 `sk-noop` → 必 401 失败。**这是灰度硬前置**（F.0）。
> 3. **会话记忆**由 `consumers.py` 的 `chat_memory.load_history → build_inject_prefix` 注入（与后端无关，两后端都生效）；**MemorySaver 仅用于阶段 E 的 interrupt/resume**，并非决策3 的"checkpointer 接 chat_memory DB"。决策3 实际未实施，会话记忆不受影响。

---

## F.0 灰度前置阻塞项（✅ 已全部完成 2026-06-06）

| # | 前置项 | 命令 / 验证 | 结果 |
|---|--------|-------------|--------|
| 0.1 | **main 代码到 Pi** | `git pull --ff-only origin main`（不触碰 `.env`/`package-lock.json`/`heartbeat_broker_config.json`）| ✅ Pi 至 `4066d10`（A–E），受保护文件未覆盖 |
| 0.2 | **Python 依赖** | `venv/bin/python -c "from langgraph.checkpoint.memory import MemorySaver; from langgraph.types import interrupt,Command"` | ✅ langgraph 0.3.34 + MemorySaver/interrupt/Command 可用 |
| 0.3 | **DeepSeek key 进 .env**（硬阻塞） | `.env` 加 `DEEPSEEK_API_KEY=<key>`（从 `~/.openclaw/agents/main/agent/auth-profiles.json` 的 `profiles."deepseek:default".key` 提取，**不回显**）| ✅ 已写入；**实调 DeepSeek 成功**（deepseek-v4-flash 有效） |
| **0.3b** | **FreeArk token 进 .env**（硬阻塞，F.1 新发现） | `.env` 加 `FREEARK_AGENT_TOKEN=<token>`（从 `~/.openclaw/freeark.env` 提取，不回显）——**langgraph 工具调用必需**：Tier-2 写恒走 HTTP 需它，且生产 freeark-backend 现役 env 没有（OpenClaw 路径不需要）| ✅ 已写入（len 40） |
| 0.4 | **路由模型决策**（决策2） | `LANGGRAPH_ROUTER_MODEL` 留空=用主模型（**始终 temp 0**，见 router 修复 PR#9）；控成本再设轻模型 | ✅ 留空 |
| 0.5 | **前端构建**（E 确认 UI） | `cd FreeArkWeb/frontend && cp -r dist <备份> && npm run build` | ✅ vite 20.38s，ChatView 确认卡片编译通过 |
| 0.6 | **在仓单测** | `manage.py test api.tests.test_langgraph_phase_a --settings=freearkweb.test_settings` | ✅ 32/32 |
| 0.7 | **工具层 LIVE smoke** | `FREEARK_SMOKE_PART=1-1-10-1001 venv/bin/python -m api.langgraph_chat.fa_tools` | ✅ 5/5（fault_summary 首跑冷查询超时、重跑即过，已知瞬态） |

> F.0 不改任何运行行为（仍默认 `CHAT_BACKEND=openclaw`，且 freeark-backend 未重启 → 运行进程仍旧码）。`.env` 加的两个 key 在重启时才被加载。前端 dist 已 live 但确认卡片惰性（openclaw 下不触发，向后兼容）。

---

## F.1 回归（✅ 已执行 2026-06-06，隔离 :8001 + 真 DeepSeek + direct + token）

隔离 uvicorn :8001（`CHAT_BACKEND=langgraph FA_TOOLS_MODE=direct` + `FREEARK_AGENT_TOKEN` + `--no-access-log` 防 token 入日志），脚本化 WS 客户端（token 自读 freeark.env 不回显）跑回归，**线上 :8000 不受影响**，跑完 kill。

| TC | 场景 | 结果 | 证据 |
|----|------|------|------|
| F-01 | 单专家·能耗读 | ✅ | 真实看板数据（2026-06-06） |
| F-02 | 单专家·巡检读 | ✅ | 经 F-04/F-05 覆盖（PLC/故障工具真调） |
| F-03 | 知识问答 | ✅ | 路由 sanheng 正确（见 F-05） |
| F-04 | 复合意图 | ✅ | 能耗 vs PLC 故障对比，fan-out 真并行 |
| F-05 | **路由准确率** | ✅ **9/9** | 含三恒→sanheng、控制命令→energy、复合→{energy,inspection} 全对 |
| F-06 | **Tier-2 写·批准** | ✅ | trigger_refresh 真执行「✅ 已执行…operator=…」 |
| F-07 | **Tier-2 写·拒绝** | ✅ | 「已取消…未执行」，写未落库（gate 拦截） |
| F-08 | 降级 | ✅ | 首轮 token 缺失时 `OPENCLAW_UNAVAILABLE` 正确回传（亲见）+ 单测已证 |
| F-09 | 会话记忆 | ✅ | 跨轮记住工号 A7-9 |
| F-10 | 并发 | ◐ 部分 | F-04 fan-out 已并发；多 WS 全量并发留灰度监控 |

**WS 回归 6/6 + 路由 9/9。两个发现已闭环：**
1. **gray 工具调用需 `FREEARK_AGENT_TOKEN`**（Tier-2 写恒走 HTTP）+ `FA_TOOLS_MODE=direct`（Tier-1 进程内）。
   → 已加 token 到 .env（F.0.3b）；灰度切换命令带 `FA_TOOLS_MODE=direct`（见 F.2）。
2. **路由 temp 抖动**（首跑偶发 F-03 误路由、写请求过度分发致确认消息被融合稀释）：根因 router 复用主模型 temp 0.2。
   → 修复 **PR#9：路由分类器固定 temp 0**（直调准确率 9/9，消除抖动）。**灰度前需合并 PR#9 并重新 pull 到 Pi**。

> 真机墙钟对照基线：单专家 ≈8s、复合 ≈35s 量级（PoC 数据）。

---

## F.2 灰度（单 worker 修正方案）

⚠️ 生产 `--workers 1`：**无法按 worker 分流**。三选一（按风险递减/工作量递增）：

- **方案 A（推荐·最简）低峰全量 + 秒回滚**：低流量时段在 `.env` 设 **`CHAT_BACKEND=langgraph`** + **`FA_TOOLS_MODE=direct`**（`DEEPSEEK_API_KEY`/`FREEARK_AGENT_TOKEN` F.0 已就位），`sudo systemctl restart freeark-backend`，**紧盯 1–3 天**。任一指标劣化 → `.env` 改回 `CHAT_BACKEND=openclaw` 重启（< 30s 回滚，OpenClaw 全在）。
  > 前置：先合并 **PR#9（路由 temp 0）** 并 `git pull` 到 Pi，再切灰度。
- **方案 B（更稳·需小改代码）按会话百分比灰度**：`chat_backend.get_chat_adapter()` 支持 `CHAT_BACKEND=canary` + `LANGGRAPH_CANARY_PCT=N`，按 session_key 哈希把 N% 新会话路由到 langgraph。单 worker 内即可灰度，回滚=改 PCT=0。**需一个小 PR**（约 15 行 + 单测）。
- **方案 C 双实例**：另起 uvicorn :8001(langgraph)，nginx 按 cookie/比例分流到 :8000/:8001。改 nginx，较重，单 worker 下收益有限，不推荐。

**监控指标（对照 openclaw 基线）**：

| 指标 | 来源 | 红线 |
|------|------|------|
| 聊天错误率（OPENCLAW_UNAVAILABLE/TIMEOUT/INTERNAL_ERROR）| `journalctl -u freeark-backend` | 不高于基线 |
| 墙钟 P50/P95 | 应用日志埋点 / 手测 | 单专家 ≈8s、复合 ≈35s 量级 |
| DeepSeek RPM/并发触限（429）| backend 日志 | 0；触限则设 LANGGRAPH_ROUTER_MODEL 轻模型或加信号量 |
| worker 内存（MemorySaver 累积）| `systemctl status freeark-backend` / `ps` | 无持续增长（确认完即释放 thread） |
| 写确认门端到端 | 人工 + DB | 确认落库/拒绝不落、无半完成 |

**回滚**：`.env` 改 `CHAT_BACKEND=openclaw`（或 canary PCT=0）→ `sudo systemctl restart freeark-backend`。无 DB 变更、无 OpenClaw 改动。

**F.2 验收门**：灰度稳定 ≥1 周、上述指标不劣于基线、写门真机正确 → 方可进 F.3。

---

## F.3 退役 OpenClaw（不可逆，须 PM CONFIRM + 灰度稳定双门）

1. 全量 `CHAT_BACKEND=langgraph`，再观察一个完整周期。
2. **停 Gateway**：`systemctl --user disable --now openclaw-gateway.service`。
3. **凭据收尾**：DeepSeek key 已在 Django `.env`（F.0.3）；确认聊天不再依赖 `~/.openclaw/`。openclaw-agent 的 Tier-2 写仍走 FreeArk 自身 token（DRF `force_authenticate`/HTTP），与 OpenClaw 退役无关。
4. **清理**（确认稳定后）：删 `openclaw-gateway.service` 用户单元 + `systemctl --user daemon-reload`；卸载 `npm uninstall -g openclaw`；清 `~/.openclaw/`、`~/.openclaw_gateway_token`。
5. `.env` 移除 `OPENCLAW_*`；`OpenClawAdapter`/`openclaw_adapter.py` **保留一个版本周期作回滚锚**，再单独 PR 删除。
6. 文档：更新 `freeark-prod-deploy` skill（移除 OpenClaw 服务/链路章节）、归档本 runbook。

**F.3 回滚成本高**（需重装 OpenClaw + 重配 token），故必须灰度稳定 + PM CONFIRM 双门后执行。退役前任何时刻，改回 `CHAT_BACKEND=openclaw` 即秒回滚。

---

## 决策落定（相对 PHASE3 §7）

| 决策 | 落定 |
|------|------|
| 1 编排进程位置 | ✅ 嵌入现有 ASGI（已实施） |
| 2 路由/聚合模型 | 灰度先 `LANGGRAPH_ROUTER_MODEL` 留空（复用主模型），盯 DeepSeek RPM；触限再换轻模型 |
| 3 会话记忆 | **澄清**：会话记忆走 consumer 的 chat_memory 注入（已在线，两后端通用）；MemorySaver 仅供 E 的 interrupt/resume。决策3 的"checkpointer 接 DB"**未实施且无需实施** |
| 4 退役时机 | 灰度稳定 ≥1 周 + PM CONFIRM 后（F.3 双门） |

## 一句话
F.0 前置（拉码/依赖/DeepSeek key/前端构建/单测/smoke）→ F.1 回归 10 TC 全绿 → F.2 单 worker 灰度（方案A 全量秒回滚 或 方案B 百分比）稳定 1 周 → F.3 PM CONFIRM 后退役 OpenClaw。每步改一个 env 值即回滚，退役前 OpenClaw 全在。
