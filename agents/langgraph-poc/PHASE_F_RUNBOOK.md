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

## F.0 灰度前置阻塞项（全部 ✅ 才可进入 F.2 灰度）

| # | 前置项 | 命令 / 验证 | 回滚锚 |
|---|--------|-------------|--------|
| 0.1 | **main 代码到 Pi** | `cd /home/yangyang/Freeark/FreeArk && git pull origin main`（确认 fast-forward，不触碰 `.env`/`package-lock.json`/`heartbeat_broker_config.json`）；`git log -1 --oneline` 应见 PR#7 合并 | `git reset --hard <旧HEAD>` |
| 0.2 | **Python 依赖** | `venv/bin/python -c "import langgraph,langchain_core,langchain_openai; from langgraph.checkpoint.memory import MemorySaver; from langgraph.types import interrupt,Command; print('ok')"`（D 无新依赖；E 的 MemorySaver 在 langgraph-checkpoint，langgraph 0.3.34 传递依赖，理应已在阶段A装入）。缺则 `venv/bin/pip install -r FreeArkWeb/backend/requirements.txt` | `/tmp/venv-freeze-before.txt`（阶段A留） |
| 0.3 | **DeepSeek key 进 .env**（硬阻塞） | 在 `FreeArkWeb/backend/.env` 加 `DEEPSEEK_API_KEY=<key>`（与 OpenClaw 用的同一 key；从 `~/.openclaw/` auth 配置取，**绝不入仓/对话**）。可选 `DEEPSEEK_BASE_URL`、`LANGGRAPH_MODEL=deepseek-v4-flash` | 删该行 |
| 0.4 | **路由模型决策**（决策2） | 默认 `LANGGRAPH_ROUTER_MODEL` 留空=复用主模型。若控成本/限流，设更轻模型名。灰度先留空、看 RPM 再定 | 删该行=复用主模型 |
| 0.5 | **前端构建**（E 确认 UI） | `cd FreeArkWeb/frontend && cp -r dist /home/yangyang/FreeArk_backup/dist_backup_$(date +%Y%m%d%H%M%S) && npm run build`（ChatView.vue 的 confirm_required 卡片）| 还原 dist_backup |
| 0.6 | **在仓单测** | `cd FreeArkWeb/backend/freearkweb && ../../../venv/bin/python manage.py test api.tests.test_langgraph_phase_a --settings=freearkweb.test_settings` → **32/32 OK** | — |
| 0.7 | **工具层 LIVE smoke**（只读，不触写） | `cd FreeArkWeb/backend/freearkweb && FREEARK_SMOKE_PART=<有效设备号> ../../../venv/bin/python -m api.langgraph_chat.fa_tools` → 5/5（验 direct/http 工具真打后端）| — |

> F.0 不改任何运行行为（仍默认 `CHAT_BACKEND=openclaw`）。只有 0.3/0.4 动 `.env`，但未切后端前不影响线上。

---

## F.1 回归（Pi 上，langgraph 后端，与 openclaw 对拍）

在**隔离实例**（独立 uvicorn :8001，`CHAT_BACKEND=langgraph` + 真 DeepSeek）上跑下表，避免动线上 :8000。
通过标准沿用 test-engineer 串行通过率门控：**全绿才进 F.2**。

| TC | 场景 | 期望 | 验收 |
|----|------|------|------|
| F-01 | 单专家·能耗读（"今天能耗看板"） | 调 get_dashboard_summary，自然语言答、真实数据、无 JSON 信封/无 exec 文本 | ✅ |
| F-02 | 单专家·巡检读（"PLC 在线情况""有哪些故障"） | 调 get_plc_status/get_fault_summary，真实数据 | ✅ |
| F-03 | 知识问答（"三恒系统原理"） | sanheng 纯文本，通用/FreeArk 标注正确，不杜撰 | ✅ |
| F-04 | 复合意图（"对比能耗与故障并讲原理"） | fan-out 多专家、aggregate 融合为一段 | ✅ |
| F-05 | **路由准确率**（D 验收）| detailed_design §8.2 问题集 + 复合意图：命中专家集合正确率 ≥ 关键词基准；单意图不误触发多专家 | ✅ |
| F-06 | **Tier-2 写·批准**（E）"把 X 设成 24 度"→确认 | confirm_required 卡片 → 确认 → DB **落库**、回"已执行"、operator=openclaw-agent::<user> | ✅ |
| F-07 | **Tier-2 写·拒绝**（E）同上 → 取消 | DB **无变化**、回"已取消"、无半完成态 | ✅ |
| F-08 | 降级（临时改 DEEPSEEK_API_KEY 为错值） | 前端收 `OPENCLAW_UNAVAILABLE` 错误（统一降级通道），不白屏不 500 | ✅ |
| F-09 | 会话记忆（连续两轮，第二轮引用第一轮） | inject_prefix 注入历史，答复体现上下文 | ✅ |
| F-10 | 并发（多 WS 同时复合意图） | 无串扰、无 worker 饿死；盯 DeepSeek RPM 是否触限（决策2）| ✅ |

> F-06/F-07 的 DB 核验：`echo "SELECT ... FROM device_param_history/相关表 WHERE ... ORDER BY id DESC LIMIT 5;" | venv/bin/python manage.py dbshell`，对比确认/取消两次的落库差异。
> 真机墙钟对照基线：单专家 ≈8s、复合 ≈35s 量级（PoC 数据）。

---

## F.2 灰度（单 worker 修正方案）

⚠️ 生产 `--workers 1`：**无法按 worker 分流**。三选一（按风险递减/工作量递增）：

- **方案 A（推荐·最简）低峰全量 + 秒回滚**：低流量时段把 `.env` 设 `CHAT_BACKEND=langgraph`，`sudo systemctl restart freeark-backend`，**紧盯 1–3 天**。任一指标劣化 → 改回 `openclaw` 重启（< 30s 回滚，OpenClaw 全在）。
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
