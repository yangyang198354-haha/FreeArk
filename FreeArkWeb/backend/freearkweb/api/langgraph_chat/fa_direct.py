"""
api.langgraph_chat.fa_direct —— 工具层进程内直调（阶段 B：去自打 HTTP 一跳）

现状链路：fa_tools → TIER1_HANDLERS → FreeArkClient(urllib) → HTTP 打 127.0.0.1:8000（自己）。
编排已在 ASGI 进程内，自己 HTTP 调自己 = 多余一跳 + 序列化 + **占用自身一个 worker**
（--workers 2 下自调用有 worker 争用风险）。

本模块提供 `DirectClient`，接口与 `lib/freeark_client.FreeArkClient` **完全一致**
（`.get(path, params) -> {"success","data","http_status"}`），但内部用 Django URL 解析
定位 view、`RequestFactory` + `force_authenticate` 进程内直接调用 DRF view 函数，
**不走 HTTP/网络/uvicorn 路由**。

接入方式（见 fa_tools.py）：FA_TOOLS_MODE=direct 时把共享模块 `tier1_readonly._client`
monkeypatch 成 DirectClient——16 个 handler 一行不改、输出字节级一致（只换传输层）。
OpenClaw 是独立子进程，patch 仅在本 Django 进程生效，不影响 live OpenClaw 路径。

鉴权：force_authenticate 以 energy-agent 服务账号身份调用（与 HTTP 路径同一身份），Tier-1
只读视图均为全局系统数据、无 per-user 过滤；不需要 token，亦不绕过 view 的业务逻辑。

异步安全：tools 经 `await tool.ainvoke()` 调用，langchain 把同步 tool 放线程池执行，
故此处同步 ORM/视图调用不阻塞 event loop。

文档引用：agents/langgraph-poc/PHASE3_ROLLOUT.md 阶段 B
"""

from __future__ import annotations

import logging

# 模块级导入（django.db 的 import 不需要 settings 已配置——连接是惰性代理）；
# 置于模块级亦便于单测 patch（见 test_langgraph_phase_a.FaDirectConnectionHealthTests）。
from django.db import OperationalError, close_old_connections

logger = logging.getLogger("api.langgraph_chat.fa_direct")

_AGENT_USER = None  # 缓存 energy-agent 服务账号 User（只读，跨调用复用）
_FACTORY = None


def _agent_user():
    global _AGENT_USER
    if _AGENT_USER is None:
        from django.contrib.auth import get_user_model
        _AGENT_USER = get_user_model().objects.get(username="energy-agent")
    return _AGENT_USER


def _factory():
    global _FACTORY
    if _FACTORY is None:
        from django.test import RequestFactory
        _FACTORY = RequestFactory()
    return _FACTORY


class DirectClient:
    """与 FreeArkClient 同接口的进程内直调客户端。

    仅实现 Tier-1 所需的 GET（只读）。post（Tier-2 写）暂不在阶段 B 范围，
    保留 NotImplementedError 以便 Tier-2 仍走 HTTP 路径（见 §阶段 E）。
    """

    def get(self, path: str, params: dict | None = None, timeout: int = 5) -> dict:
        from django.urls import resolve, Resolver404
        from rest_framework.test import force_authenticate

        try:
            match = resolve(path)  # path 形如 /api/dashboard/summary/，按 ROOT_URLCONF 解析
        except Resolver404:
            return {"success": False, "error": f"no route: {path}", "http_status": 404}

        # 连接健康兜底（修复 2026-06-14 根因：worker 线程池连接腐烂）：
        # 本方法在 langchain 工具线程池里跑，这些线程活在 Django 请求生命周期之外，
        # request_started/finished 信号不触发 → close_old_connections() 从不被调用 →
        # 线程本地 MySQL 连接闲置超 CONN_MAX_AGE(300s)/服务端 wait_timeout 后腐烂，
        # 复用即 OperationalError(2013 Lost connection)，被 LLM 转述为"服务器连接异常"。
        # 这里手动调用，让 CONN_MAX_AGE 对工具线程真正生效（超龄/不可用连接被关→取新连接）。
        close_old_connections()

        def _invoke():
            req = _factory().get(path, data=params or {})
            force_authenticate(req, user=_agent_user())
            return match.func(req, *match.args, **match.kwargs)

        try:
            resp = _invoke()
        except OperationalError as exc:
            # 罕见：连接在 CONN_MAX_AGE 内被服务端丢弃（无 errors_occurred 标记，上面的
            # close_old_connections 当时未关它）→ 关掉坏连接后重试一次（取新连接）。
            logger.warning("DirectClient 连接失效，关连接重试一次 path=%s: %s", path, exc)
            close_old_connections()
            try:
                resp = _invoke()
            except Exception as exc2:  # noqa: BLE001 — 重试仍失败，包成统一信封
                logger.warning("DirectClient 重试仍失败 path=%s: %s", path, exc2)
                return {"success": False, "error": f"view error: {exc2}", "http_status": 500}
        except Exception as exc:  # noqa: BLE001 — view 内部异常包成统一信封
            logger.warning("DirectClient view 调用异常 path=%s: %s", path, exc)
            return {"success": False, "error": f"view error: {exc}", "http_status": 500}

        status = getattr(resp, "status_code", 200) or 200
        data = getattr(resp, "data", None)
        if status >= 400:
            return {"success": False, "error": f"HTTP {status}", "http_status": status,
                    "data": data}
        return {"success": True, "data": data, "http_status": status}

    def post(self, path: str, data: dict, timeout: int = 8) -> dict:
        # Tier-2 写仍走 HTTP（保留 operator 追溯 / 二次确认协议，见阶段 E）
        raise NotImplementedError("DirectClient 仅支持 Tier-1 只读 GET；Tier-2 写请走 HTTP 路径")
