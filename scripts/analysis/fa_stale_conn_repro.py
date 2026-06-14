"""
fa_stale_conn_repro —— 确定性复现 langgraph worker 读路径根因（线程池连接腐烂）

机制：langchain 在线程池线程里跑同步 DirectClient→DRF view→Django ORM。该线程的
MySQL 连接活在 Django 请求生命周期之外，无 close_old_connections 兜底；闲置超过
MySQL wait_timeout 被服务端丢弃后，复用死连接 → OperationalError → "服务器连接异常"。

复现：钉住单线程执行器 → 跑一次 view（开线程本地连接，取 CONNECTION_ID）→ 主线程
KILL 该连接（模拟 idle 超时）→ 同线程再跑 view → 期望抛连接错误。

用法（Pi 上，PYTHONPATH 指向 backend/freearkweb）：
  DJANGO_SETTINGS_MODULE=freearkweb.settings python /tmp/fa_stale_conn_repro.py
"""
import json
from concurrent.futures import ThreadPoolExecutor

import django
django.setup()

from django.db import connection  # noqa: E402
from api.langgraph_chat.fa_direct import DirectClient  # noqa: E402

PATH = "/api/dashboard/summary/"
pool = ThreadPoolExecutor(max_workers=1)  # 单线程：保证两次任务复用同一线程/连接


def run_view():
    """在当前（池）线程里跑 view，返回 (conn_id, envelope)。"""
    with connection.cursor() as c:
        c.execute("SELECT CONNECTION_ID()")
        cid = c.fetchone()[0]
    out = DirectClient().get(PATH, {})
    return cid, out


def main():
    # 1) 首次：开线程本地连接
    cid1, out1 = pool.submit(run_view).result()
    print(f"[1 first call]  conn_id={cid1}  ok={out1.get('success')}  "
          f"{json.dumps(out1.get('data'), ensure_ascii=False)[:90]}")

    # 2) 主线程从另一条连接 KILL 掉线程池那条连接（模拟 MySQL wait_timeout 丢弃）
    from django.db import connections
    killer = connections.create_connection("default")
    with killer.cursor() as c:
        c.execute(f"KILL {cid1}")
    killer.close()
    print(f"[2 killed]      conn_id={cid1} 已 KILL（模拟服务端 idle 超时丢弃）")

    # 3) 同线程再跑 view：复用已死连接
    try:
        cid2, out2 = pool.submit(run_view).result()
        print(f"[3 reuse dead] conn_id={cid2}  ok={out2.get('success')}  "
              f"error={out2.get('error')}  data={json.dumps(out2.get('data'), ensure_ascii=False)[:90]}")
        if not out2.get("success"):
            print(">>> 复现成功：死连接复用导致 view 失败 → 即生产 '服务器连接异常' 根因")
        else:
            print(">>> 未复现（Django 可能自动重连了；需检查 CONN_MAX_AGE / 重连逻辑）")
    except Exception as e:  # noqa: BLE001
        print(f"[3 reuse dead] EXC {type(e).__name__}: {e}")
        print(">>> 复现成功（抛异常形态）：死连接复用 → 即生产根因")


if __name__ == "__main__":
    main()
