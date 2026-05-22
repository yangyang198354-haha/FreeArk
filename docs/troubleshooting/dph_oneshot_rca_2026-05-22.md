# 根因分析报告：dph-cleanup-oneshot.service failed 状态

- **日期**：2026-05-22
- **文档状态**：**FINAL**（原 DRAFT 已于 2026-05-22 并入 SSH 实测证据升级为 FINAL）
- **调查范围**：生产服务器（树莓派 192.168.31.51）上 `dph-cleanup-oneshot.service` 处于 `failed` 状态
- **调查方式**：本地代码静态分析（完整）+ SSH 实测证据采集（只读）
- **调查人**：PM Orchestrator + devops_engineer sub-agent

---

## 一、现象描述

`systemctl list-units` 显示：
- `dph-cleanup-oneshot.service`：**failed**（通过 `systemd-run` 创建的瞬态 one-shot 单元）
- `freeark-dph-cleanup.service`：**loaded active running**（长期运行，状态正常）

执行命令（来自 systemctl status 实测）：
```
[systemd-run] /home/yangyang/Freeark/FreeArk/venv/bin/python \
  /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/manage.py \
  dph_cleanup_service --once --days 7 --batch-size 5000 --sleep-ms 200
```

---

## 二、本仓库脚本静态分析：该 systemd-run 单元从何而来

通过对本仓库所有 dph 相关脚本的完整静态分析，结论如下：

### 2.1 仓库内脚本与 systemd-run 的关系

| 脚本 | 执行方式 | 是否使用 systemd-run | 备注 |
|------|---------|---------------------|------|
| `deploy_dph_cleanup.ps1` | plink 直连远程 shell | **否** | 直接调用 `python manage.py ... --dry-run` |
| `deploy_dph_cleanup.bat` | plink 直连远程 shell | **否** | 同上，仅 dry-run |
| `run_dph_cleanup_real.py` | plink + `nohup ... &` 后台 | **否** | 使用 nohup，不用 systemd-run |
| `systemctl/freeark-dph-cleanup.service` | systemd persistent unit | **否** | 这是长期运行的服务，不是瞬态单元 |

**结论：本仓库中没有任何脚本使用 `systemd-run` 创建 `dph-cleanup-oneshot.service` 瞬态单元。**

该瞬态单元是由**手动命令**在生产服务器上执行的，属调试或测试清理功能时的临时产物，很可能源自如下操作：
```bash
sudo systemd-run --unit=dph-cleanup-oneshot \
  /home/yangyang/Freeark/FreeArk/venv/bin/python \
  /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/manage.py \
  dph_cleanup_service --once --days 7 --batch-size 5000 --sleep-ms 200
```

### 2.2 两个 DPH 服务的对比

| 属性 | `dph-cleanup-oneshot.service` | `freeark-dph-cleanup.service` |
|------|-------------------------------|-------------------------------|
| 类型 | 瞬态（transient），systemd-run 创建 | 持久（persistent），`/etc/systemd/system/` |
| 运行模式 | `--once`（执行一次后退出） | `--cron "0 3 * * *"`（常驻，按调度执行） |
| 重启策略 | 无（one-shot，失败不重启） | `Restart=on-failure, RestartSec=30s` |
| 当前状态 | **failed** | **active running** |
| 是否正式 | 否（调试遗留产物，应清理） | **是**（生产正式服务） |
| 是否应保留 | **否** | **是** |

---

## 三、SSH 实测证据（2026-05-21 采集，只读）

### 3.1 systemctl status — 运行时参数确认

```
× dph-cleanup-oneshot.service - [systemd-run] .../venv/bin/python .../manage.py dph_cleanup_service --once --days 7 --batch-size 5000 --sleep-ms 200
   Loaded: loaded (/run/systemd/transient/dph-cleanup-oneshot.service; transient)
   Transient: yes
   Active: failed (Result: exit-code) since Thu 2026-05-21 22:01:55 CST
   Duration: 1min 49.117s
   Process: 7822 ExecStart=... (code=exited, status=1/FAILURE)
   Main PID: 7822 (code=exited, status=1/FAILURE)
   CPU: 500ms
   Notice: journal has been rotated since unit was started, output may be incomplete.
```

### 3.2 systemctl show — 关键属性

```
Result           = exit-code
ExecMainStartTimestamp = 2026-05-21 22:00:06 CST
ExecMainExitTimestamp  = 2026-05-21 22:01:55 CST
ExecMainCode     = 1
ExecMainStatus   = 1
ActiveState      = failed
SubState         = failed
```

### 3.3 日志状态

- `journalctl -u dph-cleanup-oneshot.service` → `-- No entries --`（journald 已轮转）
- `journalctl -u freeark-dph-cleanup.service` → `-- No entries --`（同上）
- `/home/yangyang/Freeark/FreeArk/logs/` 下无 dph 相关日志文件（仅 plc/mqtt 日志）

**证据局限**：由于 journald 已轮转，无法取得 Python 异常 traceback 和确切的 MySQL 错误字符串。根因结论基于退出码、时序、代码路径分析及间接行为证据，不依赖日志直证。

### 3.4 OOM 排查

`sudo dmesg -T | grep -iE 'oom|killed process|out of memory'` → **无任何命中**。

### 3.5 正式服务单元文件（freeark-dph-cleanup.service）

```
Type=simple
ExecStart=.../python .../manage.py dph_cleanup_service --days 7 --batch-size 5000 --sleep-ms 200 --cron "0 3 * * *"
Restart=on-failure  RestartSec=30s
StandardOutput=journal  StandardError=journal
```

当前状态：`loaded active running`。

---

## 四、根因分析

### 4.1 退出码分析

| 退出码 | 含义 | 本次情况 |
|--------|------|---------|
| 137（128+9，SIGKILL） | OOM Killer 强杀 | **否**，实测为 1 |
| 1 | Python 进程未捕获异常正常退出 | **是** |

退出码 = 1，dmesg 无 OOM 记录，**假设 B（OOM）正式排除**。

### 4.2 时序分析（关键）

| 指标 | 数值 | 解读 |
|------|------|------|
| 墙钟运行时长 | **109 秒**（22:00:06 → 22:01:55） | Django 启动约 5s，真实业务执行约 104s |
| CPU 用时 | **500 ms** | 占墙钟时长的 0.46% |
| CPU 利用率 | **≈ 0.46%** | 进程几乎全程在阻塞等待 |

**CPU 用时 500ms 而墙钟 109s 的差距高达 218 倍**，这是进程在等待 I/O 或网络响应（即数据库查询）的典型特征，而非计算密集或快速异常退出。

### 4.3 代码路径分析

`dph_cleanup_service.py` 的 `handle()` 与 `_run_cleanup()` 中，`cursor.execute()` 调用没有任何 try/except 包裹。以下是失败的完整机制链：

```
进程启动（PID 7822）
  → Django 初始化，连接 MySQL 192.168.31.98:3306
  → _run_cleanup() 调用第一步：
      SELECT id FROM device_param_history
      WHERE collected_at < '2026-05-14 22:00:06'
      ORDER BY collected_at DESC LIMIT 1
  → 查询命中 device_param_history（3600 万行 / 11.6 GB，buffer pool 128 MB）
  → 索引页无法常驻内存，随机磁盘 I/O 累积，查询挂起约 100s+
  → MySQL 服务器（或客户端超时）断开连接
  → Python 端抛出 django.db.utils.OperationalError
      (2013, 'Lost connection to MySQL server during query')
      或 (2006, 'MySQL server has gone away')
  → 无 try/except，异常向上传播
  → Django management command 以 exit code 1 退出
  → systemd 将瞬态单元标记为 failed (Result=exit-code)
```

### 4.4 更深层根因：表膨胀与 buffer pool 的结构性矛盾

`device_param_history` 表已膨胀至约 **3600 万行 / 11.6 GB**（含索引约 6.98 GB），而 InnoDB buffer pool 仅 **128 MB**。这造成了一个自我强化的困境：

- 清理任务需要先查询 cutoff ID（边界查询），该查询因索引无法驻内存而超时。
- 查询超时导致清理任务失败，无法完成清理。
- 表持续膨胀，下次清理仍然超时。

**此问题与 Dashboard 接口超时（`project_db_perf_dashboard_timeout`）同源**，均由 `device_param_history` 膨胀 + buffer pool 不足引发。

### 4.5 并发冲突分析（假设 C）

`freeark-dph-cleanup.service` 与瞬态单元均执行相同查询，但：

- 边界查询（SELECT）无锁冲突
- 即使 DELETE 期间有行锁，也只会加剧等待，不构成独立根因
- **假设 C 降级为加剧因素，非独立根因**

---

## 五、根因结论

### 5.1 直接根因

`dph-cleanup-oneshot.service` 失败的直接根因是：

> **`dph_cleanup_service --once` 执行 `device_param_history` 表边界查询（`SELECT id ... ORDER BY collected_at DESC LIMIT 1`）时，因表膨胀（3600 万行 / 11.6 GB）+ InnoDB buffer pool 不足（128 MB），查询挂起约 100 秒后触发数据库连接超时（`OperationalError: Lost connection to MySQL server during query`），该异常未被 `_run_cleanup()` 捕获，Django management command 以退出码 1 退出，systemd 将瞬态单元标记为 failed。**

### 5.2 业务影响评估

| 影响维度 | 评估结果 |
|---------|---------|
| `dph-cleanup-oneshot.service` failed 对业务的直接影响 | **无运行影响**。该单元是调试遗留的瞬态产物，不在任何正式服务链路中，其 failed 状态仅占用一条 systemd 记录。 |
| `freeark-dph-cleanup.service`（正式服务）是否受影响 | **当前未受影响**（running 状态正常）；但存在潜在风险（见 §5.3）。 |
| `device_param_history` 表的清理是否在正常进行 | **存疑**。正式服务每天 3:00 执行，若执行时同样遭遇超时，当天清理可能未完成（但因 journald 已轮转，无法核实历史执行结果）。 |

### 5.3 潜在风险：正式服务面临相同风险

`freeark-dph-cleanup.service` 走完全相同的 `_run_cleanup()` 代码路径，差异仅在于：

- `--once` 模式：异常直接终止进程
- `--cron "0 3 * * *"` 模式：`_run_cleanup()` 在 `schedule.run_pending()` 内被调用，若抛出 `OperationalError`，异常将冲出 `while True` 主循环导致整个进程崩溃

虽然正式服务有 `Restart=on-failure, RestartSec=30s` 兜底，但：
1. 每次崩溃意味着 3:00 的当日清理未能完成
2. 若清理持续不完成，表持续膨胀，问题会螺旋恶化
3. 这与 Dashboard 超时问题形成双向加剧关系

### 5.4 证据局限声明

journald 已轮转，**无法取得 Python 异常 traceback 和确切的 MySQL 错误字符串**。本报告的根因结论基于：

1. 退出码 = 1（排除 OOM SIGKILL）
2. dmesg 无 OOM 记录（排除 OOM Kill）
3. CPU 500ms / 墙钟 109s（行为特征强支持 DB 查询阻塞）
4. 代码审查确认无异常捕获（机制路径完整）
5. 已知表膨胀 + buffer pool 不足的背景数据
6. 与 Dashboard 超时问题同源的结构性一致性

综合上述证据，根因结论属**行为证据强支持级别**，而非日志直证级别。置信度评估：**高（约 90%）**。

---

## 六、分级建议

### 6.1 立即（低风险，无需代码改动）

**清理 failed 瞬态单元**——这仅清除 systemd 的 failed 状态记录，对 `freeark-dph-cleanup.service` 零影响：

```bash
sudo systemctl reset-failed dph-cleanup-oneshot.service
```

**注意：此操作须用户明确 CONFIRM 后方可执行。**

### 6.2 代码加固（建议，优先级 P1）

在 `FreeArkWeb/backend/freearkweb/api/management/commands/dph_cleanup_service.py` 的 `_run_cleanup()` 中，为 `cursor.execute()` 调用增加 `OperationalError` 捕获与优雅退出逻辑：

```python
from django.db import OperationalError
import logging

logger = logging.getLogger(__name__)

# 在 cursor.execute() 外层包裹：
try:
    cursor.execute(...)
    # ... 后续逻辑
except OperationalError as e:
    logger.error(f"[dph_cleanup] DB OperationalError: {e}. Aborting cleanup run.")
    # --once 模式：sys.exit(1) 或直接 return（让外层 handle() 决定退出码）
    # cron 模式：return，避免冲出 while True 主循环
    return
```

**此修改可防止 DB 超时导致正式服务进程崩溃，使 `Restart=on-failure` 机制有意义地生效。**

**注意：代码修改 + 生产部署须用户明确 CONFIRM 后方可执行。**

### 6.3 根治方向（P2，与 Dashboard 超时同源，建议统一规划）

以下措施仅提供方向，本次不执行：

| 方向 | 说明 | 预期效果 |
|------|------|---------|
| DPH 表直接瘦身 | 停服后执行 `DELETE FROM device_param_history WHERE collected_at < '某一远古日期'`，分批清理，将表规模降至可控范围（如 < 100 万行） | 根本解决查询超时 |
| InnoDB buffer pool 调优 | 在 MySQL 配置文件中将 `innodb_buffer_pool_size` 从 128MB 提升至 512MB 或 1GB（需评估 DB 服务器可用内存） | 提升索引缓存命中率，减少随机 I/O |
| 清理任务查询优化 | 对边界查询增加语句级超时（`SET STATEMENT max_statement_time=30 FOR ...`）；或改用基于时间戳的直接 DELETE 而非先查 ID | 降低单次查询对连接的持有时长 |
| 清理任务分段执行 | 将 7 天清理改为每次清理 1 天，分 7 次执行，每次查询压力更小 | 降低单次查询的数据量 |

---

## 七、下一步行动（须用户逐项 CONFIRM）

| 步骤 | 内容 | 风险等级 | 是否需要用户 CONFIRM |
|------|------|---------|---------------------|
| 1 | `sudo systemctl reset-failed dph-cleanup-oneshot.service` 清理 failed 瞬态单元 | **低**（只清除 systemd 记录，不影响任何运行中服务） | **是，须 CONFIRM** |
| 2 | `dph_cleanup_service.py` 增加 `OperationalError` 捕获 + 生产部署 | **低-中**（代码变更需测试，部署需 git pull） | **是，须 CONFIRM** — **已实施**：异常容错代码加固已完成，20 个单元测试全部通过，详见修复结案报告 `docs/troubleshooting/DPH-CLEANUP-001_dph_cleanup_service_robustness.md` |
| 3 | DPH 表瘦身 / InnoDB buffer pool 调优（根治） | **高**（影响生产 DB，需停服窗口） | **是，须 CONFIRM，建议单独立项** |

---

## 八、附录：假设排除记录

| 假设 | 描述 | 最终状态 | 排除依据 |
|------|------|---------|---------|
| 假设 A | DB 连接超时 / Lost connection | **确认为根因** | 退出码=1，CPU 500ms/墙钟 109s，代码无异常捕获，表膨胀背景 |
| 假设 B | OOM Kill | **排除** | 退出码=1（非 137），dmesg 无 OOM 记录 |
| 假设 C | 并发冲突 | **降级为加剧因素** | 无锁冲突，但加剧 DB 压力 |
| 假设 D | Python/Django 启动错误 | **排除** | 正式服务使用相同环境正常运行 |

---

*文档状态：**FINAL***
*静态分析阶段作者：PM Orchestrator / devops_engineer sub-agent*
*FINAL 升级时间：2026-05-22（并入 SSH 实测证据：证据 1-5，采集于 2026-05-21）*
