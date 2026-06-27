"""
api.langgraph_chat.semantic_router —— P1-1 语义路由（关键词短路与 LLM 之间的高置信中间层）

复用 rag_service.RagEmbedder（生产为 doubao 多模态 embedding，dim 2048，逐条 HTTP）embed
查询与各专家范例，对每专家范例取**最大余弦**；top ≥ τ 且与次高 margin ≥ δ → 高置信单专家
短路（跳过 LLM）；否则 None（穿透 LLM 分类器）。

设计（见 docs/.../v1.12.0_semantic_routing/）：
  - **叠加不替换**：仅处理关键词短路够不着、且语义高置信的单意图问题；复合（两专家都高分→
    margin 小）与低置信自然穿透 LLM。
  - **fail-open**：embedding/范例不可用、异常、超时 → route() 恒返回 None，退回今天的 LLM 管线，
    绝不外抛、绝不打挂聊天（与 rag_service.search_rag 一致）。
  - **范例来源**：routing_eval/dataset.jsonl 的单专家用例（OQ-SR-01=A，单一真源、随评测增长）。
  - 打分/判定为**纯函数**（score_experts / decide），可离线单测（注入向量 stub，无需网络）。

阈值 τ/δ 由 Phase-0 PoC 标定（默认 τ=0.65、δ=0.05，零误路由覆盖最大点）。
开关 LANGGRAPH_ROUTER_SEMANTIC 默认 False（首次往热路径加远端调用，保守默认关 + 灰度）。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Dict, List, Optional, Tuple

import numpy as np

from .router import _current_query  # noqa: F401  (剥历史由调用方做，这里仅备用)

logger = logging.getLogger("api.langgraph_chat.semantic_router")

# 语义层目标域：单专家类别。composite/out_of_domain 不作范例、不参与语义短路
# （复合交 LLM 并行 fan-out；域外由 P1-2 的 LLM [] 信号处理）。
SINGLE_EXPERT_CATS = ("energy", "inspection", "knowledge", "control")


def _normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    return v / (np.linalg.norm(v) + 1e-9)


def load_exemplar_texts() -> Dict[str, List[str]]:
    """从 routing_eval 数据集取单专家用例的「当前问题」作范例，按 expected 专家分组。
    失败 → {}（fail-open：无范例则 route 恒 None）。纯读取，无网络。"""
    try:
        from .routing_eval.harness import load_dataset
        groups: Dict[str, List[str]] = {}
        for c in load_dataset(validate=False):
            if len(c.expected) == 1 and c.category in SINGLE_EXPERT_CATS:
                groups.setdefault(c.expected[0], []).append(_current_query(c.query))
        return groups
    except Exception as exc:  # noqa: BLE001
        logger.warning("semantic_router: 范例装载失败（语义层将穿透 LLM）: %s", exc)
        return {}


def score_experts(query_vec, exemplars: Dict[str, np.ndarray]) -> List[Tuple[str, float]]:
    """纯函数：对每专家范例矩阵取最大余弦，降序返回 [(expert, score)]。

    query_vec：查询向量（内部归一化）。exemplars：expert -> (Ni, dim) **已归一化**矩阵。
    维度不匹配等异常由调用方（route）的 fail-open 捕获。"""
    q = _normalize(query_vec)
    out: List[Tuple[str, float]] = []
    for e, mat in exemplars.items():
        if mat is None or len(mat) == 0:
            continue
        sims = mat @ q  # (Ni,)
        out.append((e, float(sims.max())))
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def decide(scored: List[Tuple[str, float]], tau: float, margin: float) -> Optional[str]:
    """纯函数：top 分数 ≥ τ 且与次高的差 ≥ margin → 返回 top 专家；否则 None。

    margin 门让复合意图（两专家都高分→差小）与模糊问题自然落空、穿透 LLM。"""
    if not scored:
        return None
    top_e, top_s = scored[0]
    second_s = scored[1][1] if len(scored) > 1 else 0.0
    if top_s >= tau and (top_s - second_s) >= margin:
        return top_e
    return None


class SemanticRouter:
    """进程内语义路由器：懒加载范例向量（首次 route 时远端 embed 一次、缓存），打分判定。

    线程/事件循环安全：embedding 是同步网络 IO，route() 用 asyncio.to_thread 卸到线程池，
    不阻塞事件循环。范例缓存只读快照。"""

    def __init__(self, tau: float = 0.65, margin: float = 0.05):
        self.tau = tau
        self.margin = margin
        self._exemplars: Dict[str, np.ndarray] = {}  # expert -> normalized (Ni, dim)
        self._loaded = False
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> None:
        """首次调用：装载范例文本 → 远端 embed → 归一化缓存。失败 → 空范例（route 恒 None）。
        同步、阻塞（含远端调用）；由 route() 在 to_thread 中调用，不阻塞事件循环。"""
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            mats: Dict[str, np.ndarray] = {}
            texts = load_exemplar_texts()
            if texts:
                try:
                    from api.rag_service import RagEmbedder
                    emb = RagEmbedder()
                    for e, ts in texts.items():
                        vecs = emb.embed_texts(ts)  # list[np.ndarray]
                        mats[e] = np.array([_normalize(v) for v in vecs],
                                           dtype=np.float32)
                    logger.info("semantic_router: 范例向量化完成 %s",
                                {e: len(v) for e, v in mats.items()})
                except Exception as exc:  # noqa: BLE001
                    logger.warning("semantic_router: 范例向量化失败（穿透 LLM）: %s", exc)
                    mats = {}
            self._exemplars = mats
            self._loaded = True

    def route_with_vector(self, query_vec) -> Optional[str]:
        """已 embed 的查询向量 → 高置信单专家或 None（纯逻辑，离线可测）。"""
        if not self._exemplars:
            return None
        return decide(score_experts(query_vec, self._exemplars), self.tau, self.margin)

    def _route_sync(self, query: str) -> Optional[str]:
        """同步全流程（装载 + embed + 判定），供 route() 卸到线程池。"""
        self._ensure_loaded()
        if not self._exemplars:
            return None
        from api.rag_service import RagEmbedder
        qv = RagEmbedder().embed_query(query)
        return self.route_with_vector(qv)

    async def route(self, query: str) -> Optional[str]:
        """高置信单专家或 None。fail-open：任何异常（embedding 故障/超时/维度不匹配）→ None。"""
        try:
            return await asyncio.to_thread(self._route_sync, query)
        except Exception as exc:  # noqa: BLE001
            logger.warning("semantic_router.route 失败（穿透 LLM）: %s", exc)
            return None
