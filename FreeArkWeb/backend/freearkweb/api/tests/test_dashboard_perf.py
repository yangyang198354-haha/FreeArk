"""
FreeArk 看板性能测试脚本
测试计划: sdlc/perf_test_plan.md PT-001 ~ PT-008

【使用方法】
  # 安装依赖（若未安装）
  pip install httpx

  # 设置环境变量后执行
  # Windows PowerShell:
  $env:PERF_TEST_TOKEN="your_token_here"
  $env:PERF_TEST_BASE_URL="http://192.168.31.51:8000"
  python test_dashboard_perf.py

  # Linux/macOS:
  export PERF_TEST_TOKEN="your_token_here"
  export PERF_TEST_BASE_URL="http://192.168.31.51:8000"
  python test_dashboard_perf.py

【获取 Token 方法】
  方法1: 浏览器 → 打开 FreeArk → 按 F12 → Application → Local Storage → 找 userToken 的值
  方法2: curl -X POST http://<host>:8000/api/auth/login/ -H "Content-Type: application/json"
           -d '{"username":"admin","password":"your_password"}'

【注意事项】
  - 本脚本完全只读（GET 请求），不修改数据库，不修改配置
  - PT-008 需要用户手动修改 start_waitress_server.py 并重启服务（见测试计划说明）
  - 建议在业务低峰期（凌晨）执行
"""

import asyncio
import os
import statistics
import time
from typing import Any, Dict, List, Optional, Tuple

# 检查 httpx 是否安装
try:
    import httpx
except ImportError:
    print("ERROR: 未安装 httpx，请先执行: pip install httpx")
    import sys
    sys.exit(1)

# ===========================================================================
# 配置
# ===========================================================================
BASE_URL = os.environ.get("PERF_TEST_BASE_URL", "http://192.168.31.51:8000").rstrip("/")
TOKEN = os.environ.get("PERF_TEST_TOKEN", "")
TIMEOUT_SECONDS = 30  # 单请求超时上限（远低于浏览器默认60s，避免脚本挂起）

HEADERS = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json",
}

# 看板全量端点（与 HomeView.vue onMounted 一致）
DASHBOARD_ENDPOINTS = [
    "/api/dashboard/total-energy/?start_date=2026-01-01&end_date=2026-05-20",
    "/api/dashboard/summary/",
    "/api/dashboard/plc-online-rate/",
    "/api/dashboard/screen-online-rate/",
    "/api/dashboard/trend/?days=7",
    "/api/dashboard/services/",
    "/api/dashboard/activities/?limit=20",
]

# 单端点名称映射（用于报告输出）
ENDPOINT_NAMES = {
    "/api/dashboard/total-energy/": "total-energy",
    "/api/dashboard/summary/": "summary",
    "/api/dashboard/plc-online-rate/": "plc-rate",
    "/api/dashboard/screen-online-rate/": "screen-rate",
    "/api/dashboard/trend/": "trend",
    "/api/dashboard/services/": "services",
    "/api/dashboard/activities/": "activities",
}


# ===========================================================================
# 工具函数
# ===========================================================================

def short_name(endpoint: str) -> str:
    """从端点 URL 提取简短名称用于日志输出。"""
    base = endpoint.split("?")[0]
    for k, v in ENDPOINT_NAMES.items():
        if base.startswith(k):
            return v
    return base.split("/")[-2] or base


def percentile(data: List[float], p: float) -> float:
    """计算 data 的第 p 百分位数（p=50 表示中位数）。"""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    index = int(len(sorted_data) * p / 100)
    index = min(index, len(sorted_data) - 1)
    return sorted_data[index]


def print_stats(label: str, durations: List[float], failures: int, total: int) -> None:
    """打印统计摘要。"""
    if not durations:
        print(f"  {label}: 全部失败 ({failures}/{total})")
        return
    p50 = percentile(durations, 50)
    p95 = percentile(durations, 95)
    p99 = percentile(durations, 99)
    avg = statistics.mean(durations)
    max_t = max(durations)
    min_t = min(durations)
    print(f"  {label}:")
    print(f"    成功={total - failures}/{total}  失败={failures}/{total}")
    print(f"    min={min_t*1000:.0f}ms  avg={avg*1000:.0f}ms  P50={p50*1000:.0f}ms  "
          f"P95={p95*1000:.0f}ms  P99={p99*1000:.0f}ms  max={max_t*1000:.0f}ms")


async def single_request(
    client: httpx.AsyncClient, endpoint: str
) -> Tuple[float, bool, Optional[int]]:
    """执行单个 GET 请求，返回 (耗时秒, 是否成功, HTTP状态码)。"""
    url = f"{BASE_URL}{endpoint}"
    t0 = time.monotonic()
    try:
        resp = await client.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        elapsed = time.monotonic() - t0
        success = resp.status_code == 200
        return elapsed, success, resp.status_code
    except httpx.TimeoutException:
        elapsed = time.monotonic() - t0
        print(f"    TIMEOUT: {short_name(endpoint)} 超时 ({elapsed:.1f}s)")
        return elapsed, False, None
    except Exception as e:
        elapsed = time.monotonic() - t0
        print(f"    ERROR: {short_name(endpoint)} 出错: {e}")
        return elapsed, False, None


# ===========================================================================
# PT-001~004: 单请求基线
# ===========================================================================

async def run_baseline_tests(repeat: int = 10) -> Dict[str, Any]:
    """PT-001~004: 对各端点进行单请求基线测试。"""
    print("\n" + "=" * 60)
    print(f"PT-001~004: 单请求基线测试（每端点重复 {repeat} 次）")
    print("=" * 60)

    endpoints = [
        ("/api/dashboard/total-energy/?start_date=2026-01-01&end_date=2026-05-20",
         "PT-001 total-energy", 500, 2000),
        ("/api/dashboard/summary/", "PT-002 summary", 300, 1000),
        ("/api/dashboard/trend/?days=7", "PT-003 trend", 500, 1500),
        ("/api/dashboard/services/", "PT-004 services", 1000, 3000),
    ]

    results = {}
    async with httpx.AsyncClient() as client:
        for endpoint, label, p50_target, p99_target in endpoints:
            durations = []
            failures = 0
            for i in range(repeat):
                elapsed, success, _ = await single_request(client, endpoint)
                if success:
                    durations.append(elapsed)
                else:
                    failures += 1
                await asyncio.sleep(0.1)  # 避免过于密集

            p50 = percentile(durations, 50)
            p99 = percentile(durations, 99)
            passed = (p50 * 1000 <= p50_target) and (p99 * 1000 <= p99_target)

            print_stats(label, durations, failures, repeat)
            print(f"    目标: P50≤{p50_target}ms, P99≤{p99_target}ms → "
                  f"{'PASS' if passed else 'FAIL'}")
            results[label] = {
                "durations": durations,
                "failures": failures,
                "p50_ms": p50 * 1000,
                "p99_ms": p99 * 1000,
                "passed": passed,
            }

    return results


# ===========================================================================
# PT-005: 看板全量并发请求（7并发复现「归零」场景）
# ===========================================================================

async def run_concurrent_dashboard(rounds: int = 20) -> Dict[str, Any]:
    """PT-005: 模拟用户打开看板，同时触发 7 个并发请求。"""
    print("\n" + "=" * 60)
    print(f"PT-005: 看板全量并发测试（7并发 × {rounds} 轮）")
    print("=" * 60)

    endpoint_stats: Dict[str, List[float]] = {e: [] for e in DASHBOARD_ENDPOINTS}
    endpoint_failures: Dict[str, int] = {e: 0 for e in DASHBOARD_ENDPOINTS}
    timeouts: int = 0

    async with httpx.AsyncClient() as client:
        for round_n in range(rounds):
            # 7 个请求同时发出（模拟 onMounted 行为）
            tasks = [single_request(client, ep) for ep in DASHBOARD_ENDPOINTS]
            round_results = await asyncio.gather(*tasks)

            for ep, (elapsed, success, status) in zip(DASHBOARD_ENDPOINTS, round_results):
                if success:
                    endpoint_stats[ep].append(elapsed)
                else:
                    endpoint_failures[ep] += 1
                    if status is None:  # timeout
                        timeouts += 1

            if (round_n + 1) % 5 == 0:
                print(f"  已完成 {round_n + 1}/{rounds} 轮...")

            await asyncio.sleep(0.5)  # 轮次间隔

    print(f"\n  超时总次数: {timeouts}")
    print(f"  各端点统计:")
    for ep in DASHBOARD_ENDPOINTS:
        name = short_name(ep)
        print_stats(f"  {name}", endpoint_stats[ep],
                    endpoint_failures[ep], rounds)

    return {
        "endpoint_stats": endpoint_stats,
        "endpoint_failures": endpoint_failures,
        "total_timeouts": timeouts,
    }


# ===========================================================================
# PT-007: 慢请求阻塞线程池验证
# ===========================================================================

async def run_blocking_test() -> None:
    """
    PT-007: 验证 4 个线程被占用时，新请求的等待时间。
    方法：先发出 4 个大时间范围的 total-energy 查询，
          紧接着发出 1 个 summary 查询，测量其延迟是否远高于基线。
    """
    print("\n" + "=" * 60)
    print("PT-007: 线程阻塞验证")
    print("=" * 60)

    # 大时间范围查询（争占线程）
    blocking_ep = "/api/dashboard/total-energy/?start_date=2020-01-01&end_date=2026-05-20"
    fast_ep = "/api/dashboard/summary/"

    print("  步骤1: 并发发出 4 个大时间范围 total-energy 查询...")
    async with httpx.AsyncClient() as client:
        # 4 个阻塞请求 + 1 个 summary（同时发出）
        all_tasks = [single_request(client, blocking_ep) for _ in range(4)]
        all_tasks.append(single_request(client, fast_ep))

        t0 = time.monotonic()
        results = await asyncio.gather(*all_tasks)
        total_elapsed = time.monotonic() - t0

        blocking_times = [results[i][0] for i in range(4)]
        summary_elapsed, summary_success, summary_status = results[4]

        print(f"  4个阻塞查询耗时: {[f'{t*1000:.0f}ms' for t in blocking_times]}")
        print(f"  summary 查询耗时: {summary_elapsed*1000:.0f}ms "
              f"(成功={summary_success}, 状态={summary_status})")
        print(f"  总体耗时: {total_elapsed*1000:.0f}ms")

        # 判断是否出现阻塞
        # PT-002 中 summary 基线 P50 <= 300ms
        if summary_elapsed * 1000 > 1000:
            print("  结论: summary 延迟 > 1s，线程排队效应明显。VERIFIED H-01")
        elif summary_elapsed * 1000 > 500:
            print("  结论: summary 延迟 > 500ms（高于基线），有一定排队效应。PARTIAL H-01")
        else:
            print("  结论: summary 延迟正常，未检测到线程排队（可能线程数已调大，或阻塞查询较快）")


# ===========================================================================
# PT-006: 多用户并发
# ===========================================================================

async def run_multiuser_test(users: int = 3, rounds: int = 5) -> None:
    """PT-006: 模拟 users 个用户同时打开看板（users × 7 并发请求）。"""
    print("\n" + "=" * 60)
    print(f"PT-006: 多用户并发测试（{users} 用户 × 7 请求 = {users*7} 并发，重复 {rounds} 轮）")
    print("=" * 60)

    all_durations: List[float] = []
    all_failures: int = 0
    total_requests: int = 0

    async with httpx.AsyncClient() as client:
        for round_n in range(rounds):
            tasks = []
            for _ in range(users):
                for ep in DASHBOARD_ENDPOINTS:
                    tasks.append(single_request(client, ep))

            total_requests += len(tasks)
            results = await asyncio.gather(*tasks)

            for elapsed, success, _ in results:
                if success:
                    all_durations.append(elapsed)
                else:
                    all_failures += 1

            print(f"  轮次 {round_n + 1}/{rounds} 完成")
            await asyncio.sleep(1.0)

    print_stats("所有请求汇总", all_durations, all_failures, total_requests)


# ===========================================================================
# 主入口
# ===========================================================================

async def main() -> None:
    """按测试计划顺序执行所有测试用例。"""
    print("=" * 60)
    print("FreeArk 看板性能测试")
    print(f"目标服务: {BASE_URL}")
    if not TOKEN:
        print("\nWARNING: PERF_TEST_TOKEN 未设置！")
        print("请设置环境变量后重试。")
        print("  PowerShell: $env:PERF_TEST_TOKEN='your_token'")
        print("  Bash:        export PERF_TEST_TOKEN='your_token'")
        return
    print(f"Token: {TOKEN[:8]}...（前8位显示）")
    print("=" * 60)

    # 连通性预检
    print("\n[预检] 验证 API 连通性...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{BASE_URL}/api/health/",
                timeout=5
            )
            print(f"  健康检查: HTTP {resp.status_code}")
        except Exception as e:
            print(f"  ERROR: 无法连接到 {BASE_URL}: {e}")
            print("  请确认 BASE_URL 正确且服务已运行。")
            return

    # PT-001~004: 单请求基线
    await run_baseline_tests(repeat=10)

    # PT-005: 7 并发复现
    await run_concurrent_dashboard(rounds=20)

    # PT-007: 线程阻塞验证
    await run_blocking_test()

    # PT-006: 多用户（可选，对生产有轻微影响，注释掉避免意外）
    # await run_multiuser_test(users=3, rounds=5)

    print("\n" + "=" * 60)
    print("测试完成。请将输出复制至 sdlc/perf_test_report.md 的执行结果章节。")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
