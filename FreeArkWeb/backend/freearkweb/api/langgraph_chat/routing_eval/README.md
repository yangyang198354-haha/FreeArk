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
{"id": "ener-003", "query": "查一下用电量", "expected": ["energy-expert"],
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

### 基线（2026-06-27，38 用例）

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

## 如何增长

1. 新事故/新意图 → 在 `dataset.jsonl` 追加一行（保持一行一对象）。
2. 据真实关键词表判断 `keyword_floor`：纯关键词能精确命中则 `true`，否则 `false`。
   不确定就先 `false`，跑 `python manage.py test api.tests.test_routing_eval`——若标错为 `true`
   会被回归门抓到。
3. 未来可由 `classify_experts` 的生产决策日志（P1-3 下一步）自动沉淀真实流量用例
   （`source: prod-log`），人工标注后并入。
