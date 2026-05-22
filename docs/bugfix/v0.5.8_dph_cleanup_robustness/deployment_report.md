# 生产部署报告 — DPH-CLEANUP-001 修复 (v0.5.8_dph_cleanup_robustness)
# version: v0.5.8_dph_cleanup_robustness
# author_agent: main_agent_pm
# status: DEPLOYED
# date: 2026-05-22
# production_deploy_confirm: true (用户明确授权)

---

## 1. 部署概览

| 项目 | 内容 |
|------|------|
| 修复版本 | v0.5.8_dph_cleanup_robustness |
| Bug ID | DPH-CLEANUP-001 |
| 提交 | `15d2a54` fix(dph-cleanup): _run_cleanup 异常容错加固，防止进程崩溃 (DPH-CLEANUP-001) |
| 变更文件 | `FreeArkWeb/backend/freearkweb/api/management/commands/dph_cleanup_service.py`（修改）、`FreeArkWeb/backend/freearkweb/api/tests/test_dph_cleanup_service.py`（新增，20 用例）、`docs/troubleshooting/DPH-CLEANUP-001_dph_cleanup_service_robustness.md`、`docs/troubleshooting/dph_oneshot_rca_2026-05-22.md` |
| 变更类型 | 后端 Python 服务逻辑修改 + 单元测试新增 + 文档；无 DB migration；无前端变更 |
| 部署方式 | plink + git pull（生产服务器） |
| 最终状态 | DEPLOYED |
| 停机时间 | 约 5 秒（仅 freeark-dph-cleanup.service 重启，前端/后端主服务不受影响） |

---

## 2. 部署授权记录

| 字段 | 内容 |
|------|------|
| PRODUCTION_DEPLOY_CONFIRM | true |
| 授权时间 | 2026-05-22（本次会话用户明确授权） |
| 授权范围 | v0.5.8_dph_cleanup_robustness — 生产服务器 git pull + freeark-dph-cleanup.service 重启 |
| 授权有效性 | 仅本次调用有效，不可复用 |

---

## 3. 部署前预检

### 3.1 生产工作树状态核实

生产服务器存在以下本地修改（生产专属配置，预期存在）：

| 文件 | 说明 | 处理 |
|------|------|------|
| `FreeArkWeb/backend/.env` | 生产 MySQL 凭据 | 不受本次 pull 影响，保留 |
| `FreeArkWeb/frontend/package-lock.json` | aarch64 依赖树扩展 | 不受本次 pull 影响，保留 |
| 若干 `.bak` 备份文件 | 历史快照 | 无关，忽略 |

本次提交的 4 个文件与上述本地修改文件无交集，pull 不会产生冲突，已核实通过。

### 3.2 部署前服务状态

| 服务 | 状态 | 说明 |
|------|------|------|
| `freeark-dph-cleanup.service` | active (running), PID 8683 | 今晨 03:00 cron 崩溃后，systemd Restart=on-failure 于 03:01:47 自动拉起的旧代码进程 |
| `dph-cleanup-oneshot.service` | failed | 今晨 03:00 一次性任务崩溃遗留，需后续 reset-failed 清理 |

---

## 4. 部署步骤执行记录

### Step 1: 开发机 — git commit + push

```
git add (dph_cleanup_service.py, test_dph_cleanup_service.py,
         docs/troubleshooting/DPH-CLEANUP-001_dph_cleanup_service_robustness.md,
         docs/troubleshooting/dph_oneshot_rca_2026-05-22.md)
git commit -m "fix(dph-cleanup): _run_cleanup 异常容错加固，防止进程崩溃 (DPH-CLEANUP-001)"
git push origin main
→ 190f860..15d2a54  main -> main
```

**状态: DONE** — 4 files changed。

注：本次提交前一轮方案曾误含不存在的文件（`test_csrf_relogin.py` / `test_settings.py`）、越界的 CSRF 文档、虚假的"查询优化"表述、文档误放到错误目录——均被 PM 复核拦截并修正，最终提交为干净的 DPH-only 4 文件。

### Step 2: 生产服务器 — SSH 连接确认

```
plink -ssh yangyang@et116374mm892.vicp.fun -P 57279
→ SSH_OK / yangyang / aarch64 (树莓派 ARM64)
```

**状态: DONE**

### Step 3: 生产服务器 — git pull 拉取源码

```
cd /home/yangyang/Freeark/FreeArk && git pull origin main
→ Updating 190f860..15d2a54 — Fast-forward — 5 files changed
  （含 a00c815 的 CSRF 部署报告回填，共 5 文件）
→ HEAD now at 15d2a54
```

**状态: DONE** — 快进无冲突。`.env`、`package-lock.json` 本地修改完好保留，未被覆盖。

### Step 4: 验证修复代码落地

```
grep -n "except OperationalError" \
  FreeArkWeb/backend/freearkweb/api/management/commands/dph_cleanup_service.py
→ 第 257 行: except OperationalError as exc:
```

**状态: DONE** — 核心修复代码已确认存在于生产文件。

### Step 5: 重启 freeark-dph-cleanup.service

```
sudo systemctl restart freeark-dph-cleanup.service
→ 旧进程 PID 8683 干净停止
→ 新进程 PID 9586，active (running) since 2026-05-22 13:01:55 CST
```

**状态: DONE** — 新代码进程已接管服务。

### Step 6: 清除 oneshot failed 状态

```
sudo systemctl reset-failed dph-cleanup-oneshot.service
→ exit 0
→ dph-cleanup-oneshot.service: failed → inactive
```

**状态: DONE** — 今晨遗留的 failed 状态已清除。

---

## 5. 部署后验证

### 5.1 服务健康检查

| 验证项 | 预期 | 实际 | 通过 |
|-------|------|------|------|
| `freeark-dph-cleanup.service` 状态 | active (running) | active (running), PID 9586, since 13:01:55 CST | PASS |
| 启动日志无异常 | 正常调度日志 | `[dph_cleanup] 调度: 每天 03:00` / `[dph_cleanup] 常驻模式启动，cron=0 3 * * *，按 Ctrl+C 退出` | PASS |
| 生产 HEAD commit | 15d2a54 | 15d2a54 | PASS |
| `dph-cleanup-oneshot.service` 状态 | inactive | inactive | PASS |

### 5.2 dry-run 功能验证

```
python manage.py dph_cleanup_service --once --days 7 --batch-size 5000 --dry-run
→ exit code: 0
→ 待删 id 范围: [70001, 26529083]
→ 预计待删行数: 约 26,459,083 行（collected_at < 2026-05-15）
→ 约 5,292 批次
```

**状态: PASS** — exit 0，边界查询瞬间返回（InnoDB buffer pool 此时命中缓存）。
确认服务在修复后代码下可正常执行完整流程（参数解析、DB 连接、边界查询、dry-run 输出）。

说明：本次 dry-run 未触发 OperationalError（DB 此刻索引页恰在 buffer pool 命中，查询未超时），
OperationalError 捕获路径由 20 个单元测试覆盖验证，详见 5.3。

### 5.3 单元测试

```
python manage.py test api.tests.test_dph_cleanup_service
→ Ran 20 tests ... OK
```

**状态: PASS** — 20/20 用例全部通过（SQLite 内存库，DB 访问通过 mock 完全拦截）。
OperationalError 捕获路径（TC-U-DPH-001/010）、主循环健壮性（TC-U-DPH-003/004）、
connection.close() 连接清理（TC-U-DPH-010/011）均已覆盖。

---

## 6. 回滚计划

本次修改为纯异常捕获逻辑加固，无 DB migration，无 API 接口变更，无前端变更。

```bash
# 如需回滚（极端情况）
# 开发机
git revert 15d2a54 --no-edit && git push origin main
# 生产服务器
plink ... "cd /home/yangyang/Freeark/FreeArk && git pull origin main \
  && sudo systemctl restart freeark-dph-cleanup.service"
```

回滚时间 < 3 分钟。DB 不受影响，前端/主后端服务不受影响。

---

## 7. 遗留风险与后续建议（步骤 D — 建议单独立项）

本次修复仅解决"DB 超时时服务优雅不崩溃"的问题，以下根本性问题**未在本次范围内解决**：

| 风险 ID | 描述 | 严重级别 | 建议处理 |
|---------|------|---------|---------|
| RISK-DPH-001 | 生产 `innodb_buffer_pool_size` 仅 128MB，远低于 `device_param_history` 表体积（11.6GB），DB 性能随机抖动（昨晚 03:00 边界查询超时 104s，今日 13:02 同一查询瞬间返回） | HIGH | 升级生产 DB 服务器内存或将 buffer pool 调至 1-2GB（步骤 D） |
| RISK-DPH-002 | 待删积压约 2,646 万行。即使每天 03:00 不崩溃，单轮 5,292 批次清理量极大，可能跑很久或无法在单日窗口内跑完，积压持续存在 | HIGH | 先做一次性历史数据清理（分批、非高峰时段），再依赖定时任务维持增量（步骤 D） |
| RISK-DPH-003 | `collected_at` 索引在极端表膨胀下 backward scan 仍可能慢 | LOW | 可在 `collected_at` 上加 DESC 函数索引（MySQL 8.0+） |
| RISK-DPH-004 | 缺少行数/体积自动告警 | MEDIUM | 在 dph_cleanup_service 中加入超阈值告警 |

**建议**: 将上述 RISK-DPH-001 和 RISK-DPH-002 纳入"步骤 D — DPH 表瘦身 + DB 性能根治"专项，单独立项跟踪，不阻塞本次修复关闭。

---

## 8. 部署观察

| ID | 说明 | 影响 |
|----|------|------|
| OBS-1 | 生产端 buffer pool 抖动导致验证阶段 dry-run 查询瞬间返回（与今晨崩溃时 104s 超时对比鲜明），说明 OperationalError 捕获路径依赖单元测试覆盖而非本次生产实跑验证 | 低 — 20 个单元测试已全面覆盖该路径，风险可接受 |
| OBS-2 | 生产 HEAD 含 a00c815（CSRF 部署报告回填）和 15d2a54（本次修复）两个未同步到生产的提交，一并 fast-forward 拉取，无干扰 | 无影响 |

---

## 9. 交付物清单

| 文件 | 说明 |
|------|------|
| `FreeArkWeb/backend/freearkweb/api/management/commands/dph_cleanup_service.py` | 核心修复：`except OperationalError` + 主循环兜底 + `connection.close()` |
| `FreeArkWeb/backend/freearkweb/api/tests/test_dph_cleanup_service.py` | 20 个单元测试，20/20 PASS |
| `docs/troubleshooting/DPH-CLEANUP-001_dph_cleanup_service_robustness.md` | 修复结案报告（状态已升级为 DEPLOYED） |
| `docs/troubleshooting/dph_oneshot_rca_2026-05-22.md` | 根因分析报告（FINAL） |
| `docs/bugfix/v0.5.8_dph_cleanup_robustness/deployment_report.md` | 本报告 |

---

## 10. 最终判定

```
final_status: DEPLOYED
部署时间: 2026-05-22 13:01:55 CST (freeark-dph-cleanup.service 新进程启动)
commit: 15d2a54
服务状态: active (running), 无重启, 无崩溃
遗留风险: RISK-DPH-001/002 (HIGH) — 建议步骤 D 单独立项
```

---

## 11. 【2026-05-22 更正】RISK-DPH-001 根因更正（DPH-CLEANUP-002）

**更正时间**：2026-05-22 ｜ **更正人**：PM Orchestrator（Yang Yang 核实）
**保留原文不删除，本节追加更正，保持可追溯性。**

§7「遗留风险」中 RISK-DPH-001 原文：「生产 `innodb_buffer_pool_size` 仅 128MB，远低于表体积（11.6GB）」。

**更正**：2026-05-22 生产 MySQL 9.4.0 实测 `innodb_buffer_pool_size = 2147483648 = 2 GB`，非 128MB。2026-05-20 dashboard 调查时 buffer pool 确为 128MB（当时正确），之后已由运维调大到 2GB；本报告 §7 沿用了过时旧值。

`OperationalError 'Lost connection'` 的真因是 Django 客户端 `read_timeout=60s`（settings.py OPTIONS），而非 buffer pool 不足。RISK-DPH-001 应重述为：**DPH-CLEANUP-001 仅解决了"异常不传播、进程不崩溃"，未解决 60s 客户端超时导致清理慢查询被频繁掐断的问题**——该问题由 DPH-CLEANUP-002（read/write_timeout 放大到 600s）修复。

RISK-DPH-002（积压约 2646 万行）描述依然准确，由 DPH-CLEANUP-002 的 `--max-batches` 分轮清理策略 + 一次性后台全量清理共同解决。

详见 `docs/troubleshooting/dph_oneshot_rca_2026-05-22.md` §九。
