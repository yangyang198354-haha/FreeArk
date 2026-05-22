# 修复结案报告 — DPH-CLEANUP-001: dph_cleanup_service 异常容错加固

**版本**: v0.5.8
**日期**: 2026-05-22
**状态**: DEPLOYED — 已修复、通过 20 个单元测试用例，并于 2026-05-22 13:01:55 CST 完成生产部署（commit `15d2a54`，freeark-dph-cleanup.service PID 9586 启动，服务稳定运行）
**负责人**: Yang Yang

> **交叉引用**: 本报告是修复实施结案报告，与根因分析报告互补。
> 完整根因分析（含 SSH 实测证据、退出码、时序分析）见：
> `docs/troubleshooting/dph_oneshot_rca_2026-05-22.md`（状态：FINAL）

---

## 1. 问题描述

`dph_cleanup_service`（device_param_history 定时清理服务）在生产环境运行时，
当 MySQL 连接因表膨胀查询超时断开，`OperationalError` 异常从 `_run_cleanup()`
向上冒泡穿透 `while True` 主调度循环，导致整个服务进程崩溃（非正常退出）。

依赖 systemd `Restart=on-failure` 重启固然能恢复，但重启窗口期内服务中断，
且重启后连接池状态污染（坏连接未关闭），下一轮清理同样大概率再次崩溃。

完整根因（含生产服务器 SSH 实测证据：退出码=1、CPU 500ms/墙钟 109s、dmesg OOM 排查）
详见交叉引用的 RCA 文档。

---

## 2. 根因摘要

修复前 `_run_cleanup()` 无 try/except，任何 DB 异常直接传播到调用方（`schedule` job 包装函数）。
`schedule` 库的 job runner 未对异常做任何捕获，导致异常穿透至 `while True` 主循环，
最终令整个 `handle()` 方法崩溃退出。

深层根因：生产 `device_param_history` 表已膨胀至 **3600 万行 / 11.6 GB**，
而 InnoDB buffer pool 仅 **128 MB**，边界查询阻塞 100 秒以上触发 MySQL 连接超时。
此问题与 Dashboard 接口超时同源，均由表膨胀 + buffer pool 不足引发。

完整触发链路见 RCA 文档 §4.3。

---

## 3. 本次代码改动（实际变更，共 3 项）

### 3.1 新增 import：`OperationalError`

```python
from django.db import connection, OperationalError
```

修复前仅 import `connection`，`OperationalError` 未引入，无法分类捕获。

### 3.2 `while True` 主循环新增 `try/except Exception` 兜底

```python
while True:
    try:
        schedule.run_pending()
    except Exception as exc:
        # 防止 schedule 内部任何未被 _run_cleanup 捕获的异常冲出主循环。
        # 正常情况下 _run_cleanup 已自行捕获所有异常，此处是最后一道防线。
        log_error(logger, 'dph_cleanup schedule loop unexpected error', exc)
        self.stderr.write(f'[dph_cleanup] 调度循环异常（已捕获，服务继续运行）: {exc}')
    time.sleep(1)
```

针对 `schedule` 库自身 bug 或其他极端情况的最后一道防线。

### 3.3 `_run_cleanup()` 整体包进 `try`，新增 `except OperationalError` 和 `except Exception`

```python
except OperationalError as exc:
    # MySQL "Lost connection to MySQL server during query" (errno 2013)
    # 或 "MySQL server has gone away" (errno 2006)。
    err_msg = (
        f'[dph_cleanup] DB OperationalError（可能为 MySQL Lost connection 或超时）: {exc}。'
        f'本次清理轮次中止，等待下次调度。'
    )
    log_error(logger, 'dph_cleanup OperationalError', exc)
    self.stderr.write(err_msg)
    connection.close()   # 关闭已损坏的数据库连接，避免后续请求复用坏连接

except Exception as exc:
    # 捕获所有其他未预期异常，同样防止进程崩溃
    err_msg = f'[dph_cleanup] 未预期异常: {exc}，本次清理轮次中止。'
    log_error(logger, 'dph_cleanup unexpected error', exc)
    self.stderr.write(err_msg)
    connection.close()
```

关键设计点：
- **不重新抛出**（no re-raise）：异常被完全吞没在 `_run_cleanup` 内，调用方 `job()` 正常返回。
- **`connection.close()` 强制清理坏连接**：防止后续 ORM 复用已断开的连接池条目。
- 捕获后继续等待下一次 `schedule` 触发，服务进程存活。

**注**：边界查询 `ORDER BY collected_at DESC LIMIT 1`（而非 `MAX(id)` 聚合）是本次提交之前
已经存在的实现（基线 `63169a2` 中已存在，代码注释中明确记录了设计意图），**不是本次改动**。

---

## 4. 测试覆盖

**测试文件**: `api/tests/test_dph_cleanup_service.py`
**运行方式**: `python manage.py test api.tests.test_dph_cleanup_service --verbosity=2`
**测试数据库**: SQLite 内存库（DB 访问通过 `unittest.mock.patch` 完全拦截，无需 test_settings.py）
**实际运行结果**: `Found 20 test(s)` / `Ran 20 tests ... OK`

| 用例ID | 描述 | 覆盖点 |
|--------|------|--------|
| TC-U-DPH-001 | OperationalError 被捕获，不重抛 | 核心修复验证 |
| TC-U-DPH-002 | 通用 Exception 被捕获，不重抛 | 兜底捕获 |
| TC-U-DPH-003 | cron 主循环中 OperationalError 不冲出 | 循环健壮性 |
| TC-U-DPH-004 | schedule.run_pending() 异常主循环不崩溃 | 主循环兜底 |
| TC-U-DPH-005 | --once 模式 OperationalError，handle() 正常返回 | 一次性模式 |
| TC-U-DPH-006 | --once 模式 Exception，handle() 正常返回 | 一次性模式兜底 |
| TC-U-DPH-007 | --dry-run 模式输出预计行数，无 DELETE | dry-run 正确性 |
| TC-U-DPH-008 | 无超期数据时正常返回，输出「无需删除」 | 空数据路径 |
| TC-U-DPH-009 | 正常删除流程，分批执行，输出批次日志 | 主路径 |
| TC-U-DPH-010 | OperationalError 后调用 connection.close() | 连接清理 |
| TC-U-DPH-011 | Exception 后调用 connection.close() | 连接清理兜底 |
| TC-U-DPH-012 | 有效 cron 表达式注册每日任务 | 调度配置 |
| TC-U-DPH-013 | 无效 cron 表达式退回默认 03:00 | 调度 fallback |

---

## 5. 部署说明

**服务文件**: `api/management/commands/dph_cleanup_service.py`
**测试文件**: `api/tests/test_dph_cleanup_service.py`
**部署方式**: 生产服务器 plink + git pull

生产环境首次运行建议先 dry-run 确认待删数量：
```bash
python manage.py dph_cleanup_service --once --days 7 --batch-size 5000 --dry-run
```
确认无误后正式执行：
```bash
python manage.py dph_cleanup_service --once --days 7 --batch-size 5000
```
长期运行（配合 systemd）：
```bash
python manage.py dph_cleanup_service --days 7 --cron "0 3 * * *"
```

---

## 6. 遗留问题与后续建议

| 问题 | 优先级 | 建议 |
|------|--------|------|
| innodb_buffer_pool_size 仅 128MB，远低于表体积（11.6GB） | HIGH | 升级生产 DB 服务器内存，或将 buffer pool 调至 1-2GB |
| device_param_history 已 3600 万行 | HIGH | 执行首次 dph_cleanup_service 清理，将表缩减至 7 天保留量 |
| 缺少按保留量的自动告警 | MEDIUM | 在 dph_cleanup_service 中加入行数/体积监控，超阈值告警 |
| `collected_at` 索引的 backward scan 在极端表膨胀下仍可能慢 | LOW | 可在 `collected_at` 上加 DESC 函数索引（MySQL 8.0+ 支持） |

---

## 7. 参考

- 根因分析（FINAL，含 SSH 实测证据）: `docs/troubleshooting/dph_oneshot_rca_2026-05-22.md`
- 生产 DB 性能问题背景: `memory/project_db_perf_dashboard_timeout.md`
- `plc_data_clean_up_service.py` — 同模式参考实现（已有稳定运行记录）

---

## 8. 【2026-05-22 更正】深层根因归因修正（DPH-CLEANUP-002）

**更正时间**：2026-05-22 ｜ **更正人**：PM Orchestrator（Yang Yang 核实）
**保留原文不删除，本节追加更正，保持可追溯性。**

### 8.1 原文错误

§2「根因摘要」与 §6「遗留问题」把深层根因 / 遗留风险归结为 "InnoDB buffer pool 仅 128MB"。

### 8.2 实测更正

2026-05-22 生产 MySQL 9.4.0（192.168.31.98）`SHOW VARIABLES` 实测：`innodb_buffer_pool_size` = 2147483648 = **2 GB**（非 128 MB）。2026-05-20 dashboard 调查时 buffer pool 确为 128MB（当时正确），之后已由运维调大到 2GB；本结案报告沿用了过时的 128MB 旧值。

### 8.3 真实深层根因

真凶是 `settings.py` MYSQL_DATABASE OPTIONS 中的 **`read_timeout=60` / `write_timeout=60`**（客户端 socket 超时 60 秒）——耗时超 60s 的清理查询被客户端强行断开。服务端未设此类限制（`max_execution_time=0`）。

### 8.4 DPH-CLEANUP-001 修复的有效性

**DPH-CLEANUP-001 的 `except OperationalError` / `except Exception` 修复依然完全正确、保留。**
DPH-CLEANUP-002 在此基础上增加：① 客户端读写超时放大（read/write_timeout → 600s，仅清理进程），使 OperationalError 极少发生、容错块成为纵深防御；② `--max-batches` 单轮批次上限，分多轮清理约 2646 万行积压。详见 `docs/troubleshooting/dph_oneshot_rca_2026-05-22.md` §九。
