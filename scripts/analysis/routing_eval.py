"""
routing_eval —— 意图路由评测集 CLI（P1-3）

对 api/langgraph_chat/routing_eval/dataset.jsonl 跑评测，产出指标报告。

两种模式（同一份数据集）：
  离线（默认）：classify_experts(llm=None) = 纯关键词路由 + DEFAULT 兜底。确定性、免费、
                可在任意装了 Django 的机器跑（本机/CI）。度量「关键词路由地板」——P0-1 用。
  --live      ：用生产同款 router_llm(temp 0) 跑真实 LLM 路由。需 DEEPSEEK_API_KEY，
                建议在 Pi 上跑（每条 = 一次 DeepSeek 调用）。度量真实 LLM 路由质量。

用法（在 backend/freearkweb 目录，或设好 DJANGO_SETTINGS_MODULE / PYTHONPATH）：
  # 离线（本机即可；Windows 上加 PYTHONUTF8=1 绕 cp1252）
  python scripts/analysis/routing_eval.py
  # live（Pi 上）
  DJANGO_SETTINGS_MODULE=freearkweb.settings python scripts/analysis/routing_eval.py --live
  # CI 门控：离线准确率低于阈值则退出码 1
  python scripts/analysis/routing_eval.py --fail-under 1.0   # keyword_floor 不许回归

退出码：0=通过；1=低于 --fail-under 或存在 keyword_floor 回归；2=运行错误。
"""

import argparse
import os
import sys
from pathlib import Path

# 允许 `python scripts/analysis/routing_eval.py` 直跑：把 backend/freearkweb 注入 sys.path。
_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2] / "FreeArkWeb" / "backend" / "freearkweb"
if _BACKEND.is_dir():
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "freearkweb.settings")
os.environ.setdefault("FREEARK_POC_MOCK", "1")  # 离线路径不连后端

import django  # noqa: E402

django.setup()

from asgiref.sync import async_to_sync  # noqa: E402

from api.langgraph_chat.router import classify_experts  # noqa: E402
from api.langgraph_chat.routing_eval.harness import (  # noqa: E402
    evaluate, format_report, load_dataset)


def _make_offline_classifier():
    def classify(q):
        return async_to_sync(classify_experts)(None, q)
    return classify


def _make_live_classifier():
    # 仅 live 才构造 Orchestrator（会建真 LLM 客户端）。
    from api.langgraph_chat.orchestrator import Orchestrator
    orch = Orchestrator()

    def classify(q):
        return async_to_sync(classify_experts)(orch.router_llm, q)
    return classify


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="意图路由评测集（P1-3）")
    ap.add_argument("--live", action="store_true",
                    help="用真实 router_llm 跑（需 DEEPSEEK_API_KEY，建议 Pi 上）")
    ap.add_argument("--category", default="",
                    help="只跑指定 category（knowledge/energy/inspection/composite/control/out_of_domain）")
    ap.add_argument("--fail-under", type=float, default=None,
                    help="精确命中准确率低于此值则退出码 1（CI 门控，如 1.0）")
    ap.add_argument("--no-mismatches", action="store_true",
                    help="报告不列逐条未命中明细")
    args = ap.parse_args(argv)

    try:
        cases = load_dataset(validate=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] 数据集装载/校验失败: {exc}", file=sys.stderr)
        return 2
    if args.category:
        cases = [c for c in cases if c.category == args.category]
        if not cases:
            print(f"[ERROR] category={args.category!r} 无匹配用例", file=sys.stderr)
            return 2

    mode = "live (router_llm temp 0)" if args.live else "offline (关键词路由地板)"
    try:
        classifier = _make_live_classifier() if args.live else _make_offline_classifier()
        result = evaluate(classifier, cases)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] 评测运行失败: {exc}", file=sys.stderr)
        return 2

    print(format_report(result, mode=mode, show_mismatches=not args.no_mismatches))

    rc = 0
    if result["keyword_floor_failures"]:
        print("\n[FAIL] 存在 keyword_floor 回归（见上）。", file=sys.stderr)
        rc = 1
    if args.fail_under is not None and result["accuracy"] < args.fail_under:
        print(f"\n[FAIL] 准确率 {result['accuracy']:.1%} < 阈值 {args.fail_under:.1%}",
              file=sys.stderr)
        rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
