# 意图路由优化总览（P1-3 / P0-1 / P0-2 / P1-2 / P1-1 / P2-1 / P2-2）

**文档编号**: ARCH-ROUTING-OVERVIEW-001
**状态**: 现状记录（7 项均已上线生产）
**最后更新**: 2026-06-27
**适用代码**: `FreeArkWeb/backend/freearkweb/api/langgraph_chat/{experts,router,orchestrator,semantic_router,adapter}.py`

> 本文是方舟智能体**意图路由**的单一现状参考。2026-06-27 一轮完成 5 项优化并全部上线。
> 各子项的细节见 `api/langgraph_chat/routing_eval/README.md`（P0-1/P0-2/P1-2）与
> `docs/{requirements,architecture}/v1.12.0_semantic_routing/`（P1-1，含 Phase-0 PoC 结果）。

---

## 1. 背景

聊天后端 = 进程内 LangGraph 直连 DeepSeek（v1.7.0 退役 OpenClaw）。路由 = 把当前用户问题
分发到 3 个专家之一/多个：`energy-expert`（能耗/实时参数）、`inspection-expert`（PLC/故障/巡检）、
`sanheng-knowledge`（三恒原理/说明书 RAG）。优化前痛点：纯 LLM 分类器每条 ~2.5s 串行延迟、
关键词兜底脆弱、追问失上下文、闲聊被塞给能耗专家。

---

## 2. 最终路由管线（四层互补，均可单独开关 + fail-open）

```
_route(当前问题 text)
  │
  ├─[1] 关键词短路 (P0-1)            唯一无撞车关键词命中 → 该专家           ~0s
  │        keyword_shortcircuit_target()
  │
  ├─[2] 语义短路 (P1-1)              仅当前问题【零关键词】时：embed+各专家     ~0.4s(预热后)
  │        SemanticRouter.route()    范例最大余弦，top≥τ 且 margin≥δ → 单专家
  │
  ├─[3] LLM 分类器 (阶段 D)          复合/域外/低置信；提示含能力摘要(P2-1)；   ~2.5s
  │        classify_experts(router_llm,…)   护栏纠误退居可选 backstop(P2-1)
  │
  └─ 兜底链：关键词命中 → 粘性(P0-2,上一轮专家) → 域外[](P1-2) → DEFAULT(energy)
```

**层间纪律**：高确定性/低延迟在前，语义/LLM 在后；关键词命中 1 个=P0-1 处理，命中 ≥2 个=复合
直落 LLM 做多专家 fan-out（语义层只在零关键词时介入，绝不短路复合）。每层未命中即穿透下一层，
任一层故障 fail-open 退到下层——**没有任何一层是单点**。

---

## 3. 五项一览

| 项 | 一句话 | 关键实现 | 开关（env，默认） | 上线 commit |
|----|--------|----------|-------------------|-------------|
| **P1-3** 路由评测集 | 把散落用例收敛成可版本化、可增长的 labeled 数据集 + 指标 harness + 回归门 | `routing_eval/{dataset.jsonl,harness.py}`、`scripts/analysis/routing_eval.py`、`tests/test_routing_eval.py` | —（纯工具） | 90276dc / 31e5232 |
| **P0-1** 关键词短路 | 唯一无撞车关键词命中 → 跳过 LLM，省 ~2.5s | `router.keyword_shortcircuit_target` | `LANGGRAPH_ROUTER_KEYWORD_SHORTCIRCUIT`=True | 5880d8a |
| **P0-2** 粘性路由 | 零信号追问承接上一轮专家而非盲落 DEFAULT | `router.previous_turn_expert` + `classify_experts(sticky_hint=)` | `LANGGRAPH_ROUTER_STICKY`=True | e754eca |
| **P1-2** 域外路径 | LLM 明确表态域外 → 通用应答节点（寒暄/能力引导），不塞能耗专家 | `router.parse_route_response_ex` + `orchestrator._general` 节点 | `LANGGRAPH_ROUTER_OOD_PATH`=True | 7094850 |
| **P1-1** 语义路由 | 关键词盲点经 embedding 高置信短路（覆盖同义/无关键词单意图） | `semantic_router.SemanticRouter` | `LANGGRAPH_ROUTER_SEMANTIC`=True（代码默认 False，生产 .env 开）；`SEM_TAU`=0.65、`SEM_MARGIN`=0.05 | c91d943 / ee681df |
| **P2-1** 能力路由 | 据工具表派生能力摘要注入 LLM 提示，按"谁有能力"分派；手写护栏转可选 backstop | `router.build_capability_digest` + `classify_experts(guard=)` | `LANGGRAPH_ROUTER_CAPABILITY_PROMPT`=True、`LANGGRAPH_ROUTER_GUARD`=True | bf83ce0 |
| **P2-2** 专家注册表 | 5 处按专家并列声明（名/关键词/CN/数据标记/兜底提示/委托）收敛为单一真源，各模块派生 | `experts.py`（ExpertSpec 注册表，langchain-free） | —（纯重构，无开关） | 9061db0 |

---

## 4. 评测基线与实测（routing_eval，2026-06-27）

| 指标 | 值 | 备注 |
|------|----|------|
| 数据集规模 | 42 用例 | 单专家 35 + 复合 3 + 域外 4；含真实事故/历史污染/撞车/追问 |
| 离线关键词地板（精确） | 33/42 = 78.6% | 纯关键词路由（含 2 条"故意够不着"的追问计为 miss） |
| live LLM 分类器（精确） | 33/38 = 86.8% | 旧 38 用例基线（Pi 实测，micro F1 93.8%） |
| 语义留一法 argmax | 30/35 = 85.7% | Phase-0 PoC（doubao 2048），≈ live LLM |
| 语义零误路由操作点 | τ=0.65/δ=0 覆盖 51% 精度 100% | 故取 τ=0.65、δ=0.05 上线 |
| P0-1 短路可达 | 28/42 = 66.7% | 唯一关键词命中、跳过 LLM |
| embedding 查询延迟（Pi） | p50 1.36s / p90 1.48s | doubao 多模态，比 LLM ~2.5s 快约 1.1s |

**Pi 真实聊天冒烟（P1-1 上线后）**：盲点「异常情况」→巡检诊断(语义短路)、关键词「总能耗」→
能耗分析(P0-1 0s)、复合「能耗和故障」→能耗分析+巡检诊断(LLM 多专家)，均真实答复零错误。

---

## 5. 回归守护（不变式，全部进 `tests/test_routing_eval.py` + `test_langgraph_phase_a.py`，共 122 测试）

- **关键词地板不变式**：`keyword_floor=true` 用例离线必精确命中（改词表打破即红）。
- **P0-1 零精度损失不变式**：凡短路触发的用例，`[target]==expected` 且必为 `keyword_floor=true`。
- **P0-2 不变式**：followup 用例经粘性恢复 expected；**粘性绝不覆盖关键词命中**（topic-switch 安全）。
- **P1-2 不变式**：域外用例（LLM 信号 []）路由到空（通用节点）；**域外路径绝不劫持领域问题**。
- **P1-1 不变式**：复合关键词查询绝不被语义短路成单专家；fail-open（embed 故障→穿透 LLM）。

每项开关默认态切换均**逐字节向后兼容**（默认值下行为与该项上线前一致），全部可一键回退。

---

## 6. 关键事实与踩坑（供后人）

1. **生产 embedding ≠ bge-m3**：实为 **doubao 多模态 `ep-20260618...`，dim 2048**，逐条 HTTP
   （`RAG_EMBEDDING_API_STYLE=doubao_multimodal`）。纠正了"沿用 v1.4.0 bge-m3"的过时认知。
2. **P1-2 的核心区分**：LLM 返回 `[]`（可信域外）vs 输出无法解析（故障）必须分开——前者才走域外
   节点，后者按失败兜底。`parse_route_response_ex` 返回 `(experts, saw_empty)` 实现。
3. **P1-1 Phase-2 灰度抓到真 bug**：复合查询「对比能耗和故障」被语义误短路成单 inspection、丢了
   能耗半。修法=语义层**仅当前问题零关键词**时介入（≥2 关键词=复合直落 LLM）。灰度验证不可省。
4. **P1-1 冷启动**：首次 route 触发 ~50s 范例预热（35 范例逐条远端 embed）会拖垮首请求；改为
   构造时**后台线程预热**（fake/测试模式跳过）。
5. **路由只看当前问题**：`classify_experts`/短路/语义/粘性都先 `_current_query` 剥历史前缀，
   防故障-heavy 历史把能耗查询带偏（F-03 生产事故）。粘性是受控例外（只取上一轮专家名作信号）。
6. **范例源 = 评测集**：P1-1 语义范例直接复用 `routing_eval/dataset.jsonl` 的单专家用例（单一真源、
   随评测增长），composite/out_of_domain 不作范例。

---

## 7. 一键回退

任一项异常时改对应 env 为 `False` + 重启 `freeark-backend` 即回退该层（其余层不受影响）：

```
LANGGRAPH_ROUTER_CAPABILITY_PROMPT=False     # 回退 P2-1 预防层（路由 LLM 提示不含能力摘要）
LANGGRAPH_ROUTER_GUARD=False                 # 退役 P2-1 backstop 护栏（验证充分后才建议）
LANGGRAPH_ROUTER_SEMANTIC=False              # 回退 P1-1（恒走 LLM 分类器）
LANGGRAPH_ROUTER_OOD_PATH=False              # 回退 P1-2（域外恒落 DEFAULT energy）
LANGGRAPH_ROUTER_STICKY=False                # 回退 P0-2（零信号恒落 DEFAULT）
LANGGRAPH_ROUTER_KEYWORD_SHORTCIRCUIT=False  # 回退 P0-1（恒走 LLM 分类器）
```

各开关代码默认值：`SEMANTIC`=False（生产 .env 显式开 True），其余布尔开关默认 True；
`SEM_TAU=0.65`、`SEM_MARGIN=0.05`。`CAPABILITY_PROMPT`/`GUARD` 默认 True 随 P2-1 重启生效。
修改生产 `.env`（Pi）前务必备份（已有 `.env.bak.semantic.*` 等历史备份）。

---

## 8. 后续可选（未立项）

- **退役护栏 backstop**（P2-1 收尾）：P2-1 能力提示已上线作预防；待一个专门的"误路由测试集"
  证明 LLM（带能力摘要）不再把数据查询分给 tool-less 专家后，置 `LANGGRAPH_ROUTER_GUARD=False`
  退役确定性护栏。当前护栏仍 default-on 作廉价 backstop（且其历史事故已被 P0-1 关键词短路在前层拦下）。
- **进一步收敛**（P2-2 之上，可选）：把 `ROUTER_SYSTEM_PROMPT` 散文中的专家描述、semantic_router
  的范例分类、fa_tools 的工具挂载也纳入/对齐 `experts.py` 注册表，使「加一个专家」逼近"一处声明 +
  一份提示文件 + 一组工具"。当前 P2-2 已收敛 langchain-free 元数据（名/关键词/CN/数据标记/兜底提示/委托）。
- **P1-1 v2（视数据）**：若评测暴露 LLM 对追问自信误判，再考虑给 LLM 注入粘性提示；语义范例随
  生产真实问句扩充（评测集增长即范例增长）。
- **关键词表瘦身**：语义层吸收长尾后，`ROUTE_KEYWORDS` 可冻结或精简（先靠评测集守住地板）。
