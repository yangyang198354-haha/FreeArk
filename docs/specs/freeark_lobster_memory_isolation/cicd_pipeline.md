# CI/CD Pipeline — 方舟智能体记忆隔离

```
file_header:
  document_id: CICD-MEMORY-001
  project: FreeArk — freeark_lobster_memory_isolation
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_devops_engineer (PM-orchestrated, PARTIAL_FLOW GROUP_E)
  created_at: 2026-05-26
  depends_on:
    - DEPLOY-MEMORY-001 (deployment_plan.md)
    - TR-MEMORY-001 (test_report_groupd.md，130/130 通过)
    - SKILL.md (.claude/skills/freeark-prod-deploy/SKILL.md)
  scope: 手动部署流程文档，包含等待点和 Gate 决策
```

---

> **重要声明**：本文档描述手动部署流程，不触发任何自动化部署。
> FreeArk 当前采用手动 git pull 部署实践（生产 Pi 上有 GitHub Actions self-hosted runner，但当前不依赖其自动部署）。
> **Gate 1（PRODUCTION_DEPLOY_CONFIRM）是强制等待点，未收到用户明确信号前，Pipeline 在此挂起。**

---

## Pipeline 全局概览

```
╔══════════════════════════════════════════════════════════════════════════════╗
║         FreeArk Memory Isolation — 手动部署 Pipeline                        ║
║         项目：freeark_lobster_memory_isolation                               ║
║         生产：树莓派 Pi 5 / Debian 13 / MySQL 9.4.0                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

 开发机（Windows）                    生产 Pi（SSH）
 ─────────────────                    ────────────────────────────────────────

 [STAGE 0: 开发完成]
 │
 ├── GROUP_A~D 已完成（130/130 测试通过）
 ├── git push origin main（含 519ddb1）
 │
 ▼
 ╔════════════════════════════════╗
 ║  Gate 0: GROUP_D 门控          ║
 ║  GATE-D-001 PASS               ║
 ║  130 tests / 100%              ║
 ║  reasoning_stream 回归全绿      ║
 ╚════════╤═══════════════════════╝
          │ PASS（已完成）
          ▼
 ╔════════════════════════════════╗
 ║  >> WAIT: Gate 1               ║
 ║  PRODUCTION_DEPLOY_CONFIRM     ║    ◄── Pipeline 在此挂起
 ║                                ║        等待用户明确发出信号
 ║  用户须确认：                   ║
 ║  1. deployment_plan.md 已审阅  ║
 ║  2. 授权代码部署 + migrate      ║
 ║  3. 明确输入 PRODUCTION_       ║
 ║     DEPLOY_CONFIRM             ║
 ╚════════╤═══════════════════════╝
          │ CONFIRMED
          ▼
 [STAGE 1: 前置条件检查]           SSH → Pi
 │                                 ├── 检查依赖版本（Python/Node/pip）
 │                                 ├── 确认当前 HEAD = ef3c509
 │                                 ├── git fetch + diff 确认受保护文件不被覆盖
 │                                 ├── .env Token 一致性检查（TOKEN_MATCH）
 │                                 └── 创建备份（pre_deploy_memory_head_*.txt）
 │
 ▼
 [STAGE 2: MySQL 备份]             SSH → Pi
 │                                 └── mysqldump freeark → FreeArk_backup/
 │                                     验证备份文件大小 > 0
 │
 ▼
 [STAGE 3: migrate（高风险）]      SSH → Pi
 │                                 ├── migrate --plan（dry-run，确认无意外 SQL）
 │                                 ├── migrate api 0025_chat_session_message
 │                                 └── 验证：DESC api_chat_session / api_chat_message
 │                                     SHOW INDEX FROM api_chat_session / api_chat_message
 │
 │   ┌─── migrate 失败？
 │   │    └── 立即执行：migrate api 0024_plcwriterecord_batch_request_id
 │   │         验证 SHOW TABLES LIKE 'api_chat_%' → Empty set
 │   │         上报用户，Pipeline 终止
 │   │
 │   ▼ migrate 成功
 ▼
 [STAGE 4: 代码部署]               SSH → Pi
 │                                 ├── git status（确认工作树干净）
 │                                 ├── git pull origin main → 519ddb1
 │                                 ├── git log -1（确认 HEAD）
 │                                 └── 落地验证：grep ChatSession models.py
 │                                              grep chat_memory consumers.py
 │                                              grep CHAT_HISTORY_INJECT_TURNS settings.py
 │                                              ls scripts/skeleton_guard.sh
 │
 ▼
 [STAGE 5: 服务重启]               SSH → Pi
 │                                 ├── sudo systemctl restart freeark-backend
 │                                 ├── sleep 5
 │                                 ├── systemctl status freeark-backend → active (running)
 │                                 └── curl /api/health/ → {"status":"ok"}
 │
 ▼
 ╔════════════════════════════════════════════════════════════╗
 ║  Gate 2: 部署后验证（非阻塞 CONFIRM，运维人员自行确认）       ║
 ║                                                            ║
 ║  §8.1  curl /api/health/ → 200                            ║
 ║  §8.2  WS: connected + reasoning_token + reasoning_end    ║
 ║             + stream_token + stream_end                    ║
 ║  §8.3  DB 写入：chat_session/chat_message 有新记录          ║
 ║  §8.4  跨用户隔离：user A 历史不进 user B 注入              ║
 ║  §8.5  REST API: GET/DELETE /api/memory/me/                ║
 ║  §8.6  Django shell import 全部 OK                         ║
 ║                                                            ║
 ║  §9.1  US-RSN-001：reasoning_tokens > 0                   ║
 ║  §9.2  US-RSN-009：T0 基线采集（3次均值）                   ║
 ╚════════════════════════════════════════════════════════════╝
          │
          │ 所有验证 PASS
          ▼
 [代码部署完成]
 │
 │    ┌──────────────────────────────────────────────────────────┐
 │    │  [独立 CONFIRM 路径 A] skeleton_guard lock               │
 │    │  >> WAIT: SKELETON_LOCK_CONFIRM                          │
 │    │  ──────────────────────────────────────                  │
 │    │  用户须确认：                                             │
 │    │  1. 已确认骨架文件内容正确（如已先完成 USER.md 通用化）    │
 │    │  2. 接受 chattr +i OS 层不可逆锁定                        │
 │    │  3. 明确输入 SKELETON_LOCK_CONFIRM                        │
 │    │                                                          │
 │    │  确认后执行：                                             │
 │    │  ├── bash scripts/skeleton_guard.sh init                 │
 │    │  ├── bash scripts/skeleton_guard.sh lock                 │
 │    │  └── bash scripts/skeleton_guard.sh verify → PASS       │
 │    └──────────────────────────────────────────────────────────┘
 │
 │    ┌──────────────────────────────────────────────────────────┐
 │    │  [独立 CONFIRM 路径 B] USER.md 通用化                    │
 │    │  >> WAIT: USER_MD_CONFIRM                                │
 │    │  ──────────────────────────────────────                  │
 │    │  用户须确认：                                             │
 │    │  1. 已 cat USER.md 检查当前内容                           │
 │    │  2. 决定替换（或保留）                                    │
 │    │  3. 明确输入 USER_MD_CONFIRM（替换）或 USER_MD_SKIP（跳过）│
 │    │                                                          │
 │    │  替换时执行：                                             │
 │    │  ├── （若已 lock）skeleton_guard.sh unlock               │
 │    │  ├── nano ~/.openclaw/workspace/USER.md                  │
 │    │  ├── skeleton_guard.sh init                             │
 │    │  └── skeleton_guard.sh lock + verify                    │
 │    └──────────────────────────────────────────────────────────┘
 │
 ▼
 [Pipeline 完成]
```

---

## Stage 说明

### Stage 0 — 开发完成（当前已完成）

| 检查项 | 状态 |
|--------|------|
| GROUP_A 需求分析 | APPROVED |
| GROUP_B 架构设计 | APPROVED |
| GROUP_C 代码实现 | APPROVED（code_review CRITICAL=0） |
| GROUP_D 测试 | APPROVED（130/130，含 34 reasoning_stream 回归） |
| phase_status.md | GROUP_D_APPROVED_AWAITING_GROUP_E |
| git push origin main | 519ddb1 已推送 |

### Gate 1 — PRODUCTION_DEPLOY_CONFIRM（强制等待点）

**等待条件**：用户明确输入 `PRODUCTION_DEPLOY_CONFIRM` 信号。

**信号有效范围**：仅对本次部署（代码 pull + migrate + 服务重启）有效。不覆盖 skeleton lock（需要独立 SKELETON_LOCK_CONFIRM）。

**等待期间状态**：
- 生产当前仍运行 ef3c509（reasoning_stream GROUP_E 部署后状态）
- 聊天功能正常（无记忆隔离）
- APP_LOG_LEVEL=INFO 仍激活

### Stage 1~5 — 部署执行

见 deployment_plan.md §1~§5（完整命令）。

Pipeline 在此阶段的**唯一等待点**是 Gate 1 前。Stage 1~5 执行期间，若任何步骤失败，运维人员须暂停并上报用户，不得自行决策继续或回滚。

### Gate 2 — 部署后验证

Gate 2 是**验证门**（不是额外的 CONFIRM 等待点）。运维人员自行完成 §8 的所有验证项后，确认 PASS，记录结果，上报用户。若任一验证项 FAIL，上报用户，由用户决策是否回滚。

### 独立 CONFIRM 路径

两条独立 CONFIRM 路径（skeleton lock 和 USER.md 通用化）在代码部署完成后**随时可触发**，与主 Pipeline 解耦。用户可以：

- 先做代码部署（Gate 1 CONFIRM），观察一段时间，确认功能正常后再做 skeleton lock（SKELETON_LOCK_CONFIRM）
- USER.md 通用化可以在 skeleton lock 之前或之后执行（若在 lock 之后，需要先 unlock 再改再 lock）
- 两条路径均可跳过（若用户决定暂不锁定骨架文件，或暂不通用化 USER.md）

---

## CONFIRM 等待清单汇总

| CONFIRM 信号 | 触发操作 | 独立于 |
|-------------|---------|-------|
| `PRODUCTION_DEPLOY_CONFIRM` | git pull + migrate + 服务重启 | — |
| `SKELETON_LOCK_CONFIRM` | skeleton_guard init + lock + verify | PRODUCTION_DEPLOY_CONFIRM |
| `USER_MD_CONFIRM` | 编辑 USER.md + 重新 init + lock | PRODUCTION_DEPLOY_CONFIRM 和 SKELETON_LOCK_CONFIRM |

**三个 CONFIRM 互相独立，不得合并授权，不得从历史 CONFIRM 推断当前授权。**

---

## 回滚触发条件速查

| 现象 | 回滚类型 | 回滚命令摘要 |
|------|---------|------------|
| migrate 失败（表创建报错） | migration 回滚 | `migrate api 0024_plcwriterecord_batch_request_id` |
| git pull 后服务无法启动（ImportError） | 代码回滚 | `git checkout ef3c509 -- consumers.py models.py settings.py` + 重启 |
| 服务启动但聊天 TypeError | 代码回滚 | 同上 |
| chat_session/chat_message 表不存在（ORM 报错） | 代码回滚（迁移已完成时不需 migration 回滚） | 回滚代码即可，孤立表不影响旧代码 |
| chattr +i 后需要修改骨架文件 | skeleton unlock | `skeleton_guard.sh unlock` → 修改 → init → lock |

完整回滚命令见 deployment_plan.md §10。

---

## 当前状态记录（Pipeline 入口状态）

```
生产 HEAD:         ef3c509 (reasoning_stream GROUP_E 部署后)
远端 main HEAD:    519ddb1 (memory-isolation GROUP_D 完成)
待拉取 commit 数:  3（d584d1b → 752faf0 → 519ddb1）
APP_LOG_LEVEL:     INFO（已激活，reasoning_stream 验证期遗留）
OPENCLAW_REASONING_EFFORT: （已清空，RISK-003 接受现状）
freeark-backend PID: 35086（已重启过两次）
skeleton guard 状态: 未执行 init/lock（本期首次部署）
Gate 1 状态:       WAITING（等待 PRODUCTION_DEPLOY_CONFIRM）
```
