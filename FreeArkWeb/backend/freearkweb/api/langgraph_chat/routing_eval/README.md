# 意图路由评测集（routing_eval）— P1-3

把散落在 `scripts/analysis/router_probe.py`、单测 `RouterClassifierTests`、以及 `router.py`
生产事故注释里的路由用例，收敛成**一份外置、可版本化、可增长的 labeled 数据集**
（`dataset.jsonl`）+ 一个产出指标的评测 harness。

这是 P0-1（关键词短路）与护栏退役的**前置依赖**：没有评测集，任何路由改动都无法量化是否回归。

## 文件

| 文件 | 作用 |
|---|---|
| `dataset.jsonl` | labeled 用例，一行一个 JSON 对象 |
| `harness.py` | 装载/评测/渲染（langchain-free，可离线 import） |
| `../../tests/test_routing_eval.py` | 数据集完整性 + 离线关键词地板回归门（`@tag('unit')`，进 CI） |
| `../../../../../scripts/analysis/routing_eval.py` | CLI：离线默认 / `--live` |

## 数据集 schema（每行一个对象）

```json
{"id": "ener-003", "query": "查一下用电量", "expected": ["freeark-expert"],
 "category": "energy", "keyword_floor": true, "tags": [], "source": "unit-test", "notes": ""}
```

| 字段 | 含义 |
|---|---|
| `id` | 唯一短 id，前缀按类别（know-/ener-/insp-/comp-/ctrl-/guard-/hist-/ood-） |
| `query` | 用户问题；可含会话历史前缀 + `[__freeark_user__:..]` 标签（测 `_current_query` 剥历史） |
| `expected` | 期望专家集合（**理想行为**，非当前行为）。`[]` = 应路由到「无/通用」 |
| `category` | `knowledge` / `energy` / `inspection` / `composite` / `control` / `out_of_domain` |
| `keyword_floor` | 确定性关键词路由（`classify_experts(None, q)`）是否应精确命中 `expected`。**回归门据此断言** |
| `tags` | 横切标签：`keyword-miss` / `keyword-collision` / `history-pollution` / `guard-incident` / `chitchat` / `write` / `doc` / `default-coincidence` / `triple` / `debatable-label` |
| `source` | 出处：`router_probe` / `unit-test` / `router-comment` / `router_history_repro` / `synthetic` / `prod-log`（未来） |
| `notes` | 说明（尤其 gap/争议标签） |

`keyword_floor=false` 表示该用例靠纯关键词路由拿不到正确结果（需 LLM，或当前是 gap），
离线评测会把它记为未命中——这是**有意的**，量化 LLM 路由的增量价值与 P1-2 缺口。

## 运行

```bash
# 离线（本机/CI；确定性、免费）。Windows 上前置 PYTHONUTF8=1 绕 cp1252。
python scripts/analysis/routing_eval.py

# live：真实 router_llm(temp 0)，需 DEEPSEEK_API_KEY，建议在 Pi 上跑
DJANGO_SETTINGS_MODULE=freearkweb.settings python scripts/analysis/routing_eval.py --live

# 只看某类别
python scripts/analysis/routing_eval.py --category out_of_domain

# CI 门控：keyword_floor 回归即退出码 1（--fail-under 另设总准确率阈值）
python scripts/analysis/routing_eval.py

# 单测（数据集完整性 + 关键词地板回归门）
cd FreeArkWeb/backend/freearkweb
python manage.py test api.tests.test_routing_eval --settings=freearkweb.test_settings -v2
```

## 指标

- **精确命中准确率**：`got 专家集合 == expected 集合`（多标签，顺序无关）
- **micro P/R/F1**：把专家标签摊平做 micro 平均（衡量过选 fp / 漏选 fn）
- **分类别准确率**：定位哪类意图最弱
- **关键词地板回归**：`keyword_floor=true` 用例离线若不精确命中即回归（P0-1 地基）

### 基线（2026-06-27，38 用例；后随 P0-2 增至 42 用例）

> 下表为 P0-1 落地时的 38 用例快照。P0-2 新增 4 条 sticky 用例后共 42 条；纯关键词离线
> 因含 2 条"故意够不着"的零信号追问降至 33/42=78.6%，但 P0-2 粘性可恢复其中 3 条
> （报告"P0-2 粘性可恢复"行）。floor 回归仍 0。

| 指标 | 离线(关键词地板) | live(router_llm temp0, 真 DeepSeek) |
|---|---|---|
| 精确命中准确率 | 31/38 = 81.6% | **33/38 = 86.8%** |
| micro P / R / F1 | 83.7% / 94.7% / 88.9% | **88.4% / 100% / 93.8%** |
| knowledge | 91.7% | **100%**（修好 know-010 无关键词"除湿换气"） |
| inspection | 85.7% | **100%**（修好 insp-006 无关键词"异常情况"） |
| keyword_floor 回归 | 0 | 0 |
| 单次延迟 | ~0ms | ~2.1s/条（38 条共 1m20s @ Pi） |

**live 仍有的 5 条未命中没有一条是真正的 LLM 路由错误**：
- `ener-001`（总能耗+在线率→ energy+inspection）：LLM 可能是对的（问题确实跨域），是标签存疑（`debatable-label`）。
- 4 条 OOD（你好/再见…）：LLM 正确返回 `[]`，但 `classify_experts` 的 `if names:` 丢弃空数组、
  回退 DEFAULT energy——**结构性缺口（P1-2）**，非 LLM 质量问题。

**对 P0-1（关键词短路）的判决**：30 条 `keyword_floor=true` 用例离线/live 均 100% 命中；LLM 的全部
增量都落在关键词够不着处（无关键词的知识/巡检问题、撞车多命中）。故"仅当关键词命中**唯一**专家
且**无撞车**时才短路、否则走 LLM"是**零精度损失**的——可为约 30 条单意图查询省 ~2s/条而不牺牲
任何已知用例。这正是 P0-1 缺的量化依据。

## P0-1 关键词短路（已实现，2026-06-27）

`orchestrator._route` 在**唯一无撞车关键词命中**时直接采用关键词结果、**跳过 LLM 分类器**
（省 ~2s/条）。判定函数 `router.keyword_shortcircuit_target(text)`：当前问题恰好命中 1 个专家
关键词 → 返回该专家；0 命中（需语义判断）或 ≥2 命中（撞车/复合）→ None（交 LLM）。

- **开关**：`settings.LANGGRAPH_ROUTER_KEYWORD_SHORTCIRCUIT`（env 同名，默认 `True`）。置 `False`
  一键回退「恒走 LLM 分类器」。`classify_experts`/护栏/兜底链均不变，与短路解耦。
- **零精度损失保证**：`test_routing_eval.test_shortcircuit_zero_regression_invariant` 钉死——凡短路
  触发的用例，`[target]` 必等于 `expected` 且必为 `keyword_floor=true`。即短路只在"它一定对"处触发。
- **覆盖率**：本数据集 38 条中 **27 条（71.1%）短路可达**（评测报告"P0-1 短路可达"行）。这 27 条
  在离线与 live 下结果一致且全对，故短路省下的是纯延迟、不动正确性。
- **残留风险**：含数据关键词的纯知识问题（如"故障率怎么定义"命中"故障"）会被短路到数据专家。
  关键词表已刻意规避（不收"控制/调节"等）；如生产暴露新例 → 加入本数据集并按需收窄，或关开关。

## P0-2 粘性路由（已实现，2026-06-27）

`orchestrator._route` 在当前问题**零路由信号**（LLM 返回空 + 无关键词）时，承接**上一轮专家**
而非盲目落 `DEFAULT_EXPERT=energy`，接住"那上个月呢/再详细点"这类自身无领域词的追问。

- **上一轮专家来源**：聊天历史只存 role/content（`chat_memory`），不记录每轮专家。故
  `router.previous_turn_expert(text)` 从注入的历史块（`[历史记忆开始]...[历史记忆结束]`）取
  **最后一轮用户问题**做关键词路由反推（唯一命中才用）。这是当前架构下最稳的来源——历史前缀
  每轮必带，无需改 schema、无额外 LLM 调用。
- **严格安全**：仅改"零信号"兜底分支。关键词命中 / P0-1 短路 / LLM 明确结果**全不经过**粘性，
  故粘性**不可能**让任何当前正确的路由变差（topic-switch 如"现在看故障"自带关键词→短路，永不触发粘性）。
- **开关**：`settings.LANGGRAPH_ROUTER_STICKY`（env 同名，默认 `True`）。置 `False` 回退"零信号恒落 DEFAULT"。
- **不变式（test_routing_eval）**：① followup 用例经粘性精确恢复 expected；② 凡当前自带关键词的用例，
  开/关粘性结果完全一致（`test_sticky_never_overrides_keyword_hit`）。
- **覆盖**：数据集 4 条 sticky 用例，报告"P0-2 粘性可恢复 3/42"（3 条零信号追问被正确承接；
  stick-004 是 topic-switch 反例，验证粘性不越界）。
- **残留**：若 LLM 对追问**自信地**误判（返回非空但错），粘性（仅兜底）不介入。如评测暴露此类，
  再考虑 v2 给 LLM 注入粘性提示；当前刻意不做以控风险。

## P1-2 域外/闲聊路径（已实现，2026-06-27）

LLM 明确表态问题**不属任何专家**（且无关键词、无粘性）时，路由到 `general` 通用应答节点
（友好寒暄 + 能力引导），而非盲目塞给系统管家。解决"你好/你是谁/今天天气/谢谢再见"被
系统管家别扭作答的问题（评测 4 条 OOD 用例）。

- **关键区分**：`parse_route_response_ex` 把"LLM 解析出空数组（`[]`/`["foo"]`）"与"输出无法
  解析/异常"分开——只有前者（`saw_empty=True`）才是可信的域外信号，后者仍按解析失败兜底。
  这避免把 LLM 偶发故障误判成闲聊。
- **优先级**：LLM 命中 → 关键词 → 粘性 → **域外 `[]`** → DEFAULT。域外在粘性之后：有上一轮
  专家时优先承接对话（追问不被误判为闲聊）；故域外主要在**会话起始**的寒暄触发（无粘性）。
- **图路径**：`route` 空 plan → `_fan_out` 转 `Send("general")` → `_general`（纯 LLM 无工具）
  → `aggregate` 打包。`general` 节点 token 经 `adapter._drive` 直接流（`node=='general'`）。
- **开关**：`settings.LANGGRAPH_ROUTER_OOD_PATH`（env 同名，默认 `True`）。置 `False` 域外恒落 DEFAULT。
- **离线 vs live**：域外检测**依赖 LLM**——offline（无 LLM）无法判定，故 4 条 OOD 用例在
  offline 报告里仍计为 miss（out_of_domain 0/4），属预期。live 下 LLM 返回 `[]` → general 节点。
  单测用 stub 模拟 `[]` 验证（`test_ood_cases_route_to_general_with_llm_signal`），并有安全不变式
  `test_ood_path_never_hijacks_domain_questions`（关键词命中的领域问题绝不被误判域外）。

## 如何增长

1. 新事故/新意图 → 在 `dataset.jsonl` 追加一行（保持一行一对象）。
2. 据真实关键词表判断 `keyword_floor`：纯关键词能精确命中则 `true`，否则 `false`。
   不确定就先 `false`，跑 `python manage.py test api.tests.test_routing_eval`——若标错为 `true`
   会被回归门抓到。
3. 未来可由 `classify_experts` 的生产决策日志（P1-3 下一步）自动沉淀真实流量用例
   （`source: prod-log`），人工标注后并入。
