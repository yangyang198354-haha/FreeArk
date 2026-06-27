"""
semantic_route_poc —— P1-1 语义路由 Phase-0 PoC（只读，go/no-go 门控）

在 Pi 上用真实 bge-m3 端点（RagEmbedder，复用 v1.4.0 基建）实测：
  1) embedding 查询延迟分布（p50/p90/p99/max + 失败率）——决定语义路由是否为延迟收益。
  2) 留一法语义路由准确率：对每条单专家用例，用其余单专家用例作各专家范例，embed 本条 →
     各专家范例最大余弦 → argmax；扫 τ/δ 网格出「短路率 vs 命中精度」。
  3) 关键词盲点（know-010「除湿换气」/insp-006「异常情况」等）是否被语义救回。

只读：仅调 embedding API，无 DB 写、无设备副作用、无生产改动。

用法（Pi 上，backend/freearkweb 在 sys.path 或设 DJANGO_SETTINGS_MODULE）：
  DJANGO_SETTINGS_MODULE=freearkweb.settings venv/bin/python scripts/analysis/semantic_route_poc.py
"""

import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2] / "FreeArkWeb" / "backend" / "freearkweb"
if _BACKEND.is_dir():
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "freearkweb.settings")

import django  # noqa: E402

django.setup()

import numpy as np  # noqa: E402

from api.langgraph_chat.router import _current_query  # noqa: E402
from api.langgraph_chat.routing_eval.harness import load_dataset  # noqa: E402
from api.rag_service import RagEmbedder  # noqa: E402

# 语义层只处理「单专家」用例；composite/out_of_domain 不作范例、不参与语义准确率
# （它们应交 LLM，见架构 ADR-SR-01/03）。
SINGLE_EXPERT_CATS = ("energy", "inspection", "knowledge", "control")


def _pct(sorted_vals, p):
    if not sorted_vals:
        return float("nan")
    idx = min(len(sorted_vals) - 1, int(round((p / 100.0) * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def main():
    cases = load_dataset(validate=True)
    # 单专家用例（语义层目标域）
    se = [c for c in cases
          if len(c.expected) == 1 and c.category in SINGLE_EXPERT_CATS]
    print(f"=== P1-1 语义路由 PoC ===")
    print(f"数据集 {len(cases)} 条，其中单专家用例 {len(se)} 条（语义层目标域）")

    embedder = RagEmbedder()
    # 探针：模型/维度
    try:
        probe = embedder.embed_query("能耗")
        print(f"embedding 模型就绪，维度={probe.shape[0]}")
    except Exception as e:  # noqa: BLE001
        print(f"[FATAL] embedding 探针失败，PoC 终止: {e}")
        return 2

    # ── 1) 逐条 embed（计时）；向量入内存供留一法 ─────────────────────────────
    vecs = {}       # case_id -> np.ndarray
    latencies = []  # 成功调用墙钟
    failures = 0
    for c in se:
        q = _current_query(c.query)
        t0 = time.time()
        try:
            v = embedder.embed_query(q)
            dt = time.time() - t0
            latencies.append(dt)
            vecs[c.id] = v / (np.linalg.norm(v) + 1e-9)  # 预归一化
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"  [embed 失败] {c.id} {q[:20]!r}: {e}")

    lat = sorted(latencies)
    print("\n--- 1) embedding 查询延迟（n=%d，失败 %d）---" % (len(lat), failures))
    if lat:
        print(f"  p50={_pct(lat,50):.2f}s  p90={_pct(lat,90):.2f}s  "
              f"p99={_pct(lat,99):.2f}s  max={lat[-1]:.2f}s  min={lat[0]:.2f}s")
        print(f"  目标：p90 < 1.5s 则语义短路有明确延迟收益（对比 LLM ~2.5s）")

    # ── 2) 留一法：每专家范例向量分组 ─────────────────────────────────────────
    groups = {}  # expert -> list[(case_id, vec)]
    for c in se:
        if c.id in vecs:
            groups.setdefault(c.expected[0], []).append((c.id, vecs[c.id]))
    experts = sorted(groups)
    print(f"\n--- 2) 留一法语义路由（范例专家组："
          + "，".join(f"{e}×{len(groups[e])}" for e in experts) + "）---")

    def score_excluding(case_id, qvec):
        """对各专家取范例最大余弦（排除 case 自身向量，留一）。返回 [(expert, score)] 降序。"""
        out = []
        for e in experts:
            sims = [float(qvec @ v) for cid, v in groups[e] if cid != case_id]
            if sims:
                out.append((e, max(sims)))
        out.sort(key=lambda x: x[1], reverse=True)
        return out

    # 预计算每条用例的 (top_expert, top_score, second_score, expected, correct_argmax)
    rows = []
    for c in se:
        if c.id not in vecs:
            continue
        scored = score_excluding(c.id, vecs[c.id])
        if not scored:
            continue
        top_e, top_s = scored[0]
        second_s = scored[1][1] if len(scored) > 1 else 0.0
        rows.append({
            "id": c.id, "expected": c.expected[0], "top": top_e,
            "top_s": top_s, "second_s": second_s,
            "margin": top_s - second_s, "argmax_ok": top_e == c.expected[0],
            "kw_floor": c.keyword_floor, "query": _current_query(c.query),
        })

    # 纯 argmax 准确率（不设阈值，看语义本身分得开吗）
    argmax_ok = sum(1 for r in rows if r["argmax_ok"])
    print(f"  纯 argmax 准确率（无阈值）: {argmax_ok}/{len(rows)} = "
          f"{argmax_ok/len(rows):.1%}" if rows else "  无可评数据")

    # ── 3) τ/δ 网格：短路率 vs 命中精度 ───────────────────────────────────────
    print("\n--- 3) τ/δ 网格（routed=短路触发；prec=短路命中精度；cov=短路覆盖率）---")
    print(f"  {'τ':>5} {'δ':>5} {'routed':>7} {'correct':>8} {'prec':>7} {'cov':>7}")
    taus = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
    deltas = [0.0, 0.03, 0.05, 0.08, 0.10]
    best = None
    for tau in taus:
        for delta in deltas:
            routed = [r for r in rows if r["top_s"] >= tau and r["margin"] >= delta]
            correct = sum(1 for r in routed if r["argmax_ok"])
            prec = correct / len(routed) if routed else 0.0
            cov = len(routed) / len(rows) if rows else 0.0
            # 只打印有代表性的几档（routed 非空），并记录"精度=100% 下覆盖最大"的点
            if routed and (delta in (0.0, 0.05, 0.10)):
                print(f"  {tau:>5.2f} {delta:>5.2f} {len(routed):>7} {correct:>8} "
                      f"{prec:>6.1%} {cov:>6.1%}")
            if prec >= 0.999 and routed:
                if best is None or len(routed) > best[2]:
                    best = (tau, delta, len(routed), cov)
    if best:
        print(f"\n  >>> 零误路由下覆盖最大点：τ={best[0]:.2f} δ={best[1]:.2f} "
              f"→ 短路 {best[2]}/{len(rows)} 条（覆盖 {best[3]:.1%}），命中精度 100%")
    else:
        print("\n  >>> 无「零误路由」操作点——语义分不够干净，需回炉范例/阈值")

    # ── 4) 关键词盲点是否被语义救回 ───────────────────────────────────────────
    print("\n--- 4) 关键词盲点聚焦（keyword_floor=false 的单专家用例）---")
    blind = [r for r in rows if not r["kw_floor"]]
    if not blind:
        print("  （数据集无 keyword_floor=false 的单专家用例）")
    for r in blind:
        flag = "✓救回" if r["argmax_ok"] else "✗仍错"
        print(f"  [{flag}] {r['id']:10} {r['query'][:22]:24} "
              f"top={r['top']}({r['top_s']:.2f}) margin={r['margin']:.2f} "
              f"期望={r['expected']}")

    # ── 5) argmax 错判明细（语义把谁判错了）──────────────────────────────────
    wrong = [r for r in rows if not r["argmax_ok"]]
    if wrong:
        print(f"\n--- 5) argmax 错判 {len(wrong)} 条（语义混淆点）---")
        for r in wrong:
            print(f"  {r['id']:10} {r['query'][:22]:24} "
                  f"判={r['top']}({r['top_s']:.2f}) 期望={r['expected']} margin={r['margin']:.2f}")

    print("\n=== PoC 结束。判定见 requirements_spec §5 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
