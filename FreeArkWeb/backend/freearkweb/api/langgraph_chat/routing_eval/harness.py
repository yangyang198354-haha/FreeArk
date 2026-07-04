"""
api.langgraph_chat.routing_eval.harness —— 路由评测 harness（纯逻辑，langchain-free）

职责：装载 dataset.jsonl → 对每条用例跑给定 classifier → 汇总指标 → 渲染报告。

classifier 由调用方注入（mode-agnostic）：
  - 离线：lambda q: route_experts(_current_query(q)) 的等价物，即 classify_experts(None, q)
  - live ：classify_experts(orch.router_llm, q)
两者签名都是 (query: str) -> list[str]（同步可调用；async 由调用方用 async_to_sync 包好）。

指标：
  - exact_match accuracy：got 专家集合 == expected 专家集合（多标签按集合相等，顺序无关）
  - micro precision/recall/f1：把每条的专家标签摊平做 micro 平均（衡量过选/漏选）
  - by_category：按 category 分桶的 exact accuracy（便于看「知识/能耗/巡检/复合/域外」各自表现）
  - keyword_floor 回归：标了 keyword_floor=true 的用例若离线不精确命中即回归（P0-1 的地基）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Optional

# 合法专家集合与 category 取值（dataset 校验用）。
# 从 router 复用 EXPERT_NAMES，避免两处漂移；router 顶层 langchain-free，import 安全。
from ..router import (EXPERT_NAMES, _current_query, _keyword_hits,
                      keyword_shortcircuit_target, previous_turn_expert)

VALID_CATEGORIES = (
    "knowledge",      # 三恒原理/说明书/技术文档 → sanheng-knowledge
    "energy",         # 能耗/用电/看板/实时参数 → freeark-expert
    "inspection",     # 故障/PLC/在线离线/巡检 → inspection-expert
    "composite",      # 明确跨域 → 多专家
    "control",        # 写/控制类（Tier-2）→ freeark-expert
    "out_of_domain",  # 闲聊/自我介绍/跑题 → 理想应为空（当前强制 DEFAULT，记录 gap）
)

_DATASET_PATH = Path(__file__).with_name("dataset.jsonl")


@dataclass
class Case:
    id: str
    query: str
    expected: List[str]
    category: str
    keyword_floor: bool = False
    tags: List[str] = field(default_factory=list)
    source: str = ""
    notes: str = ""

    @property
    def expected_set(self) -> frozenset:
        return frozenset(self.expected)


@dataclass
class CaseResult:
    case: Case
    got: List[str]
    exact: bool


def load_dataset(path: Optional[Path] = None, validate: bool = True) -> List[Case]:
    """读 JSONL → list[Case]。validate=True 时校验 schema（专家名/category/唯一 id）。

    JSONL：每行一个 JSON 对象；空行与 // 开头的注释行忽略（JSONL 本不支持注释，仅作宽容）。"""
    p = Path(path) if path else _DATASET_PATH
    cases: List[Case] = []
    raw_lines = p.read_text(encoding="utf-8").splitlines()
    for lineno, line in enumerate(raw_lines, start=1):
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        try:
            obj = json.loads(s)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"dataset.jsonl 第 {lineno} 行 JSON 解析失败: {exc}") from exc
        cases.append(Case(
            id=obj["id"],
            query=obj["query"],
            expected=list(obj.get("expected", [])),
            category=obj["category"],
            keyword_floor=bool(obj.get("keyword_floor", False)),
            tags=list(obj.get("tags", [])),
            source=obj.get("source", ""),
            notes=obj.get("notes", ""),
        ))
    if validate:
        _validate(cases)
    return cases


def _validate(cases: List[Case]) -> None:
    seen = set()
    for c in cases:
        if c.id in seen:
            raise ValueError(f"重复用例 id: {c.id}")
        seen.add(c.id)
        if not c.query.strip():
            raise ValueError(f"用例 {c.id} query 为空")
        if c.category not in VALID_CATEGORIES:
            raise ValueError(f"用例 {c.id} category 非法: {c.category!r}（允许 {VALID_CATEGORIES}）")
        for e in c.expected:
            if e not in EXPERT_NAMES:
                raise ValueError(f"用例 {c.id} expected 含非法专家: {e!r}（允许 {EXPERT_NAMES}）")


def evaluate(classifier: Callable[[str], Iterable[str]],
             cases: Optional[List[Case]] = None) -> dict:
    """对每条用例跑 classifier，汇总指标。classifier 抛错时该条记为 got=['ERROR:..']（不精确）。"""
    cases = cases if cases is not None else load_dataset()
    results: List[CaseResult] = []
    tp = fp = fn = 0
    by_cat: dict = {}
    floor_total = 0
    floor_failures: List[CaseResult] = []
    mismatches: List[CaseResult] = []

    for c in cases:
        try:
            got = list(classifier(c.query))
        except Exception as exc:  # noqa: BLE001
            got = [f"ERROR:{type(exc).__name__}:{exc}"]
        got_set = frozenset(got)
        exp_set = c.expected_set
        exact = got_set == exp_set
        results.append(CaseResult(case=c, got=got, exact=exact))

        # micro PRF（按专家标签摊平）
        tp += len(got_set & exp_set)
        fp += len(got_set - exp_set)
        fn += len(exp_set - got_set)

        bucket = by_cat.setdefault(c.category, {"total": 0, "exact": 0})
        bucket["total"] += 1
        bucket["exact"] += 1 if exact else 0

        if c.keyword_floor:
            floor_total += 1
            if not exact:
                floor_failures.append(results[-1])
        if not exact:
            mismatches.append(results[-1])

    # P0-1：短路可达 = 唯一无撞车关键词命中（这些查询将跳过 LLM 分类器）。
    sc_reachable = sum(1 for c in cases if keyword_shortcircuit_target(c.query) is not None)
    # P0-2：粘性可恢复 = 当前问题零关键词（会落兜底）且上一轮专家恰好等于 expected。
    sticky_recoverable = sum(
        1 for c in cases
        if not _keyword_hits(_current_query(c.query))
        and previous_turn_expert(c.query) is not None
        and [previous_turn_expert(c.query)] == c.expected)

    total = len(cases)
    exact_count = sum(1 for r in results if r.exact)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    for b in by_cat.values():
        b["accuracy"] = b["exact"] / b["total"] if b["total"] else 0.0

    return {
        "total": total,
        "exact_match": exact_count,
        "accuracy": exact_count / total if total else 0.0,
        "micro": {"precision": precision, "recall": recall, "f1": f1,
                  "tp": tp, "fp": fp, "fn": fn},
        "by_category": by_cat,
        "keyword_floor_total": floor_total,
        "keyword_floor_failures": floor_failures,
        "shortcircuit_reachable": sc_reachable,
        "sticky_recoverable": sticky_recoverable,
        "mismatches": mismatches,
        "results": results,
    }


def _fmt_experts(xs: Iterable[str]) -> str:
    xs = list(xs)
    return "[" + ", ".join(xs) + "]" if xs else "[]（无/通用）"


def format_report(result: dict, mode: str = "offline", show_mismatches: bool = True) -> str:
    """渲染人读报告（纯文本/markdown 友好）。"""
    lines: List[str] = []
    acc = result["accuracy"]
    m = result["micro"]
    lines.append(f"=== 路由评测报告（{mode}）===")
    lines.append(f"用例总数        : {result['total']}")
    lines.append(f"精确命中(集合相等): {result['exact_match']}/{result['total']}  "
                 f"准确率 {acc:.1%}")
    lines.append(f"micro 标签       : P={m['precision']:.1%}  R={m['recall']:.1%}  "
                 f"F1={m['f1']:.1%}  (tp={m['tp']} fp={m['fp']} fn={m['fn']})")
    sc = result.get("shortcircuit_reachable", 0)
    st = result.get("sticky_recoverable", 0)
    lines.append(f"P0-1 短路可达    : {sc}/{result['total']} = {sc / result['total']:.1%}"
                 if result['total'] else "P0-1 短路可达    : 0")
    lines.append("  （这些查询唯一命中关键词，将跳过 LLM 分类器省 ~2s/条）")
    lines.append(f"P0-2 粘性可恢复  : {st}/{result['total']}"
                 + "（零信号追问由上一轮专家正确承接，否则盲落 DEFAULT）")
    lines.append("")
    lines.append("--- 分类别准确率 ---")
    for cat, b in sorted(result["by_category"].items()):
        lines.append(f"  {cat:14s} {b['exact']}/{b['total']}  {b['accuracy']:.1%}")
    lines.append("")
    floor_fail = result["keyword_floor_failures"]
    lines.append(f"--- 关键词地板回归（keyword_floor=true 共 {result['keyword_floor_total']} 条）---")
    if not floor_fail:
        lines.append("  ✓ 无回归（所有 keyword_floor 用例离线精确命中）")
    else:
        lines.append(f"  ✗ {len(floor_fail)} 条回归：")
        for r in floor_fail:
            lines.append(f"    [{r.case.id}] {r.case.query[:30]} "
                         f"期望={_fmt_experts(r.case.expected)} 实得={_fmt_experts(r.got)}")
    if show_mismatches:
        lines.append("")
        lines.append(f"--- 全部未精确命中（{len(result['mismatches'])} 条，含已知 gap）---")
        for r in result["mismatches"]:
            tagstr = (" #" + ",".join(r.case.tags)) if r.case.tags else ""
            lines.append(f"  [{r.case.id}/{r.case.category}{tagstr}] {r.case.query[:34]}")
            lines.append(f"      期望={_fmt_experts(r.case.expected)} "
                         f"实得={_fmt_experts(r.got)}"
                         + (f"  ({r.case.notes})" if r.case.notes else ""))
    return "\n".join(lines)
