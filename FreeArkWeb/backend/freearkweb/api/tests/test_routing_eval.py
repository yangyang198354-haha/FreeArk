"""
单元测试 —— 路由评测集（P1-3）：数据集完整性 + 离线关键词地板回归门

全离线、确定性、可进 CI：只跑 classify_experts(llm=None, ...) 的纯关键词路由，不连
任何 LLM/后端。真实 LLM 路由质量由 scripts/analysis/routing_eval.py --live 在 Pi 上度量。

两类断言：
  1. 数据集 schema 完整性（专家名/category 合法、id 唯一、query 非空、覆盖全类别）。
  2. 关键词地板回归：标了 keyword_floor=true 的用例，离线关键词路由必须精确命中
     expected。这是 P0-1（关键词短路）的地基——一旦关键词表改动打破这些命中即回归。

运行：
  cd FreeArkWeb/backend/freearkweb
  python manage.py test api.tests.test_routing_eval --settings=freearkweb.test_settings -v2
"""

import os

# 与既有 langgraph 套件一致：置 mock 标志，杜绝任何 transitively import 触发真实建连。
os.environ.setdefault("FREEARK_POC_MOCK", "1")

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, tag

from api.langgraph_chat.router import (
    classify_experts, keyword_shortcircuit_target, previous_turn_expert)
from api.langgraph_chat.routing_eval.harness import (
    VALID_CATEGORIES, evaluate, format_report, load_dataset)


def _offline(query: str):
    """生产同款入口、llm=None → 纯关键词路由 + DEFAULT 兜底（确定性，**不含粘性**）。
    保持"关键词地板"语义纯粹：粘性恢复由 _offline_sticky / 专门测试覆盖。"""
    return async_to_sync(classify_experts)(None, query)


def _offline_sticky(query: str):
    """离线 + P0-2 粘性：零信号时承接上一轮专家（与 orchestrator._route 离线行为一致）。"""
    sticky = previous_turn_expert(query)
    return async_to_sync(classify_experts)(None, query, sticky_hint=sticky)


@tag('unit')
class RoutingEvalDatasetTests(SimpleTestCase):
    """数据集完整性 + 离线评测地基。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cases = load_dataset(validate=True)  # validate 会校验 schema，非法即抛

    def test_dataset_nontrivial_and_covers_all_categories(self):
        self.assertGreaterEqual(len(self.cases), 30, "评测集规模过小")
        covered = {c.category for c in self.cases}
        self.assertEqual(covered, set(VALID_CATEGORIES),
                         f"类别覆盖不全：缺 {set(VALID_CATEGORIES) - covered}")

    def test_ids_unique(self):
        ids = [c.id for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)), "存在重复用例 id")

    def test_keyword_floor_cases_pass_offline(self):
        """keyword_floor=true 的用例，离线关键词路由必须精确命中（核心回归门）。"""
        failures = []
        for c in self.cases:
            if not c.keyword_floor:
                continue
            got = set(_offline(c.query))
            if got != set(c.expected):
                failures.append(f"[{c.id}] {c.query[:30]!r} 期望={c.expected} 实得={sorted(got)}")
        self.assertEqual(failures, [],
                         "关键词地板回归（P0-1 地基被破坏）：\n" + "\n".join(failures))

    def test_harness_runs_clean_offline(self):
        """harness.evaluate 端到端可跑，且统计自洽；keyword_floor 回归数为 0。"""
        result = evaluate(_offline, self.cases)
        self.assertEqual(result["total"], len(self.cases))
        self.assertEqual(len(result["keyword_floor_failures"]), 0,
                         format_report(result, mode="offline"))
        # 报告可渲染（不抛错）
        self.assertIn("路由评测报告", format_report(result, mode="offline"))

    def test_shortcircuit_zero_regression_invariant(self):
        """P0-1 零精度损失不变式：凡短路触发（keyword_shortcircuit_target 非 None）的用例，
        其结果 [target] 必精确等于 expected，且该用例必为 keyword_floor=true。

        这把「短路只在它一定对的地方触发」钉成回归门——P0-1 安全的核心保证。"""
        violations = []
        fired = 0
        for c in self.cases:
            target = keyword_shortcircuit_target(c.query)
            if target is None:
                continue
            fired += 1
            if [target] != c.expected:
                violations.append(f"[{c.id}] 短路→{target} 但 expected={c.expected}")
            if not c.keyword_floor:
                violations.append(f"[{c.id}] 短路触发却 keyword_floor=false")
        self.assertEqual(violations, [],
                         "P0-1 短路零精度损失不变式被破坏：\n" + "\n".join(violations))
        self.assertGreater(fired, 0, "无任何短路触发，数据集异常")

    def test_sticky_recovers_followups_offline(self):
        """P0-2：标 followup 的零信号追问，纯关键词会盲落 DEFAULT、粘性能精确恢复 expected。"""
        regressions = []   # 纯关键词错 → 粘性应修对
        for c in self.cases:
            if "followup" not in c.tags:
                continue
            sticky_out = set(_offline_sticky(c.query))
            if sticky_out != set(c.expected):
                regressions.append(
                    f"[{c.id}] 粘性后仍错：期望={c.expected} 实得={sorted(sticky_out)}")
        self.assertEqual(regressions, [],
                         "P0-2 粘性未能恢复追问：\n" + "\n".join(regressions))

    def test_sticky_never_overrides_keyword_hit(self):
        """P0-2 安全不变式：当前问题自带关键词时（topic-switch），粘性绝不改变结果。
        即 _offline_sticky 与 _offline（无粘性）对所有"当前有关键词"用例结果一致。"""
        from api.langgraph_chat.router import _current_query, _keyword_hits
        diffs = []
        for c in self.cases:
            if not _keyword_hits(_current_query(c.query)):
                continue  # 只看当前自带关键词的用例
            if set(_offline_sticky(c.query)) != set(_offline(c.query)):
                diffs.append(c.id)
        self.assertEqual(diffs, [],
                         f"粘性覆盖了关键词命中（不应发生）：{diffs}")
