"""
fa_direct_async_repro —— 复现 langgraph worker 读路径"服务器连接异常"根因

假设：worker 用 await tool.ainvoke()（langchain 把同步 @tool 丢线程池，在 ASGI 事件循环下
跑同步 Django ORM/view）→ 连接异常；而同步 tool.invoke()（主线程）正常。

本脚本在 standalone（django.setup）下对照三条路径，并对失败路径打印完整 traceback：
  A. 同步 tool.invoke()           —— 期望成功（已知 good）
  B. asyncio.run(tool.ainvoke())  —— 复现 worker 路径
  C. asyncio.run(to_thread(DirectClient.get)) + 捕获裸异常 traceback

用法（Pi 上）：
  cd FreeArkWeb/backend/freearkweb
  DJANGO_SETTINGS_MODULE=freearkweb.settings ../../../venv/bin/python /tmp/fa_direct_async_repro.py
"""
import asyncio
import json
import traceback

import django
django.setup()

from api.langgraph_chat import fa_tools as f  # noqa: E402


def show(tag, out):
    s = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
    print(f"[{tag}] {s[:200]}")


def main():
    tool = f.get_dashboard_summary

    # A. 同步
    try:
        show("A sync invoke", tool.invoke({}))
    except Exception as e:  # noqa: BLE001
        print(f"[A sync invoke] EXC {type(e).__name__}: {e}")

    # B. 异步 ainvoke（复现 worker）
    try:
        show("B async ainvoke", asyncio.run(tool.ainvoke({})))
    except Exception as e:  # noqa: BLE001
        print(f"[B async ainvoke] EXC {type(e).__name__}: {e}")

    # C. 在事件循环里经线程池直调 DirectClient.get，捕获裸异常 + traceback
    from api.langgraph_chat.fa_direct import DirectClient

    async def via_thread():
        dc = DirectClient()
        return await asyncio.to_thread(dc.get, "/api/dashboard/summary/", {})

    try:
        out = asyncio.run(via_thread())
        show("C to_thread DirectClient.get", out)
    except Exception as e:  # noqa: BLE001
        print(f"[C to_thread DirectClient.get] EXC {type(e).__name__}: {e}")

    # C2. 直接在 to_thread 里跑 view 并打印完整 traceback（不被 DirectClient 包成信封）
    async def via_thread_raw():
        def call():
            from django.urls import resolve
            from rest_framework.test import force_authenticate
            from django.contrib.auth import get_user_model
            from django.test import RequestFactory
            path = "/api/dashboard/summary/"
            match = resolve(path)
            req = RequestFactory().get(path)
            force_authenticate(req, user=get_user_model().objects.get(username="openclaw-agent"))
            resp = match.func(req, *match.args, **match.kwargs)
            return getattr(resp, "status_code", None), getattr(resp, "data", None)
        return await asyncio.to_thread(call)

    try:
        st, data = asyncio.run(via_thread_raw())
        print(f"[C2 raw view in thread] status={st} data={json.dumps(data, ensure_ascii=False)[:160]}")
    except Exception:  # noqa: BLE001
        print("[C2 raw view in thread] EXC traceback:")
        traceback.print_exc()


if __name__ == "__main__":
    main()
