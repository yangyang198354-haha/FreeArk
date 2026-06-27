# 架构设计 — v1.12.0 语义路由（P1-1）

**文档编号**: ARCH-SR-v1120-001
**项目名称**: FreeArk 意图路由语义化（v1.12.0_semantic_routing）
**版本**: 0.1.0
**状态**: DRAFT（提案，待 Phase-0 PoC + 门控评审）
**创建日期**: 2026-06-27
**对应需求**: REQ-SPEC-SR-v1120-001

---

## 1. 设计目标与定位

在现有路由管线中插入**语义相似度高置信中间层**，复用 v1.4.0 的 bge-m3 embedding 基建
（`api/rag_service.py`），把"短路"能力从字面关键词扩展到语义贴近，覆盖同义/改写/无关键词的
单意图问题；低置信穿透到 LLM 分类器（不回归）。全程 fail-open + 单一开关可逆。

**核心原则**：语义层是**叠加**而非替换。关键词短路（0 延迟、已验证零损失）保留在最前；
语义层只处理关键词够不着的；LLM 仍是低置信/复合/域外的最终判官。三层互补，任一层都能兜底。

---

## 2. 路由管线（目标态）

```
_route(text)
  │
  ├─[1] 关键词短路 keyword_shortcircuit_target(text)   ← P0-1，0 延迟，不变
  │       唯一无撞车命中 → 定该专家，跳过下游
  │
  ├─[2] 语义高置信短路  SemanticRouter.route(query)     ← 本期新增
  │       embed(query) → 各专家范例最大余弦 → top≥τ 且 margin≥δ
  │       命中 → 定该单专家，跳过 LLM
  │       未命中 / fail-open → 穿透 [3]
  │
  ├─[3] LLM 分类器 classify_experts(router_llm, …)      ← 阶段 D，~2.5s，不变
  │       含护栏；复合/域外/低置信都在这里解决
  │
  └─ 兜底链：关键词 → 粘性(P0-2) → 域外[](P1-2) → DEFAULT   ← 不变
```

语义层夹在 [1] 与 [3] 之间：只有"无唯一关键词命中"的查询才会进入 [2]；其中语义高置信者
被截留（省 LLM），其余（低置信/复合）继续走 [3]。

---

## 3. 组件设计

### 3.1 SemanticRouter（新增，`api/langgraph_chat/semantic_router.py`）

职责：持有各专家范例向量，对查询打分并给出高置信单专家或 None。**纯打分逻辑与 IO 分离**，
便于离线单测（注入向量 stub）。

```
class SemanticRouter:
    # 进程内单例（仿 RagVectorCache），懒加载
    _exemplars: dict[str, np.ndarray]   # expert -> (Ni, 1024) 范例向量矩阵
    _loaded: bool

    def _ensure_loaded():
        # 首次使用：读范例文本（OQ-SR-01）→ RagEmbedder.embed_texts 批量向量化 → 缓存
        # 失败（embedding 不可达）→ 置空，route() 恒返回 None（fail-open，穿透 LLM）

    def score(query_vec) -> list[(expert, score)]:
        # 纯函数：对每专家范例矩阵取最大余弦（OQ-SR-03=A），降序
        # 可单测（喂 query_vec + 预置 _exemplars）

    async def route(query: str) -> Optional[str]:
        # 1. embed_query(query)（有界超时；异常→None，fail-open）
        # 2. scored = score(vec)
        # 3. top, second = scored[0], scored[1]
        # 4. if top.score >= TAU and (top.score - second.score) >= MARGIN: return top.expert
        #    else: return None  （低置信/复合 → 穿透 LLM）
```

- 范例向量化复用 `rag_service.RagEmbedder`（同 bge-m3 端点、同 fail 行为），**不新增 embedding 客户端**。
- `route()` 是 async（embedding IO）；`score()` 同步纯函数。

### 3.2 orchestrator 集成（`_route`）

```python
async def _route(self, state):
    text = <last HumanMessage>
    if self.keyword_shortcircuit:
        t = keyword_shortcircuit_target(text)
        if t: return {"plan": [(t, text)], "route_text": text}
    if self.semantic_routing:                          # 新增开关
        sem = await self._semantic_router.route(_current_query(text))
        if sem is not None:
            return {"plan": [(sem, text)], "route_text": text}
    sticky = previous_turn_expert(text) if self.sticky_routing else None
    chosen = await classify_experts(self.router_llm, text,
                                    sticky_hint=sticky, allow_ood=self.ood_path)
    return {"plan": [(n, text) for n in chosen], "route_text": text}
```

语义层只产出**单专家或 None**；命中即等价一次"高置信短路"，下游 fan_out/expert/gate/aggregate 不变。

### 3.3 范例库（OQ-SR-01=A 倾向）

直接复用 `routing_eval/dataset.jsonl`：按 `expected` 单专家分组，`query` 作范例
（仅取 `category ∈ {energy,inspection,knowledge,control}` 且单专家的用例；composite/out_of_domain 不作范例）。
优点：单一真源、随评测增长、含真实生产事故句。补盲点时在数据集加 `tags:["exemplar"]` 行或独立 exemplars 文件（OQ-SR-01=B）。

---

## 4. 关键架构决策（ADR）

**ADR-SR-01：语义层作中间层，叠加不替换。**
关键词短路在前（0 延迟、零损失已证），LLM 在后（复合/域外/低置信兜底）。语义只截留"关键词
够不着且语义高置信"的单意图问题。爆炸半径最小，三层互补。

**ADR-SR-02：范例源自 routing_eval 数据集。**
评测集已是 labeled、含事故、可增长的真值，天然适合作范例，避免再维护一套范例。单专家用例入范例，
composite/OOD 排除（它们不该被语义短路）。

**ADR-SR-03：专家分数 = 范例集最大余弦。**
抗类内多样（一个专家有多种问法），简单可解释；阈值 τ + 与次高 margin δ 双门控置信，复合意图因
两专家都高分→margin 小→自然穿透 LLM。

**ADR-SR-04：范例向量纯内存缓存、懒加载、远端 embed 一次（OQ-SR-02=A）。**
仿 `RagVectorCache`。量小（数十~百条）重算秒级，零 schema 改动。启动 embedding 失败 → 范例空 →
`route()` 恒 None → 穿透 LLM（fail-open）。若预热抖动成问题再转持久化（B）。

**ADR-SR-05：fail-open 复用 RagEmbedder，绝不外抛。**
`embed_query` 异常/超时 → `route()` 返回 None → 走今天的 LLM 管线。语义层故障对用户不可见
（最多失去一次提速）。与 `search_rag` 的 fail-open 一致。

**ADR-SR-06：默认关 + Phase-0 门控（OQ-SR-05=B）。**
不同于 P0 系列（默认开），本期在热路径新增**远端调用**，先上线代码默认关，PoC 实测延迟/准确率
满意后再 env 开 + 灰度。`LANGGRAPH_ROUTER_SEMANTIC` 默认 False。

---

## 5. 评测与标定（复用 routing_eval）

- **harness 语义模式**：新增分类器 `semantic_classify(query)` 注入 `evaluate()`，复用现有指标。
- **留一法**：对每条用例，用其余用例作范例避免自命中，embed 本条 → argmax 专家 → 比对 expected。
- **阈值标定**：扫 τ∈[0.3,0.7]×δ∈[0,0.15] 网格，画"准确率 vs 短路率"曲线，选高准确率下短路率最大点
  写入 `settings`。
- **三方对比**：语义 vs 关键词地板(78.6%) vs live LLM(86.8%)，重点验证 `know-010`/`insp-006` 等盲点。
- 报告新增"语义短路可达 / 留一法准确率"两行（仿现有 P0-1/P0-2 stat）。

---

## 6. 延迟与时序分析

| 路径 | 墙钟（目标/预估） | 说明 |
|------|------|------|
| 关键词短路 | ~0s | 纯字符串，不变 |
| 语义短路（命中） | embed_query 一次（**Phase-0 实测**，目标 < 1.5s） | bge-m3 短文本 + 内存余弦（µs 级） |
| LLM 分类器 | ~2.5s | 不变 |

净效应取决于 embedding 延迟与语义短路命中率：命中率高 + embed 快 → 平均路由延迟下降；embed 慢 →
仅覆盖/可维护收益（OQ-SR-06）。**Phase-0 实测是 go/no-go 依据。**

---

## 7. 分阶段交付

- **Phase 0｜PoC（只读，门控）**：Pi 上独立脚本测 embedding 延迟分布 + 留一法语义准确率 + 阈值曲线。产出 go/no-go + τ/δ 初值。
- **Phase 1｜实现（默认关）**：SemanticRouter + `_route` 集成 + 开关 + harness 语义模式 + 单测/不变式。本机全绿、push、Pi pull。
- **Phase 2｜灰度验证**：Pi 上 `LANGGRAPH_ROUTER_SEMANTIC=True` 跑评测 + 真实问句冒烟（含盲点用例），核对命中/穿透/fail-open log。
- **Phase 3｜上线**：重启 backend 生效；观察一段时间；记忆路线图更新。

每阶段可独立暂停/回退（开关默认关，Phase 1 上线本身零行为变化）。

---

## 8. 对既有系统的影响

- **零 DB 改动**（范例向量纯内存）。
- **零既有路由行为变化**（开关默认关；开后也只截留原本走 LLM 的部分）。
- 新增热路径远端依赖**仅在开关开启时**，且 fail-open 退回现状。
- 与 P0-1/P0-2/P1-2 正交：短路在前、兜底链在后，均不改。
- aarch64：无新增本地推理（embedding 走远端），符合纪律。
