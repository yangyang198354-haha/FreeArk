# CI/CD Pipeline — 方舟智能体 Reasoning 流式展示

```
file_header:
  document_id: CICD-REASONING-001
  project: FreeArk — freeark_lobster_reasoning_stream
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_devops_engineer (PM-orchestrated, PARTIAL_FLOW GROUP_E)
  created_at: 2026-05-26
  depends_on:
    - DEPLOY-REASONING-001 (deployment_plan.md)
    - SKILL.md (.claude/skills/freeark-prod-deploy/SKILL.md)
  scope: 手动部署 pipeline，本项目无自动化 CI/CD
```

---

> **声明**：FreeArk 当前生产部署为**手动 git pull 模式**。
> GitHub Actions self-hosted runner 虽然在服务器上存在，但**不用于自动部署**。
> 本文档描述完整的手动部署 pipeline 流程，所有步骤由运维人员手动执行。
> **生产部署须等待用户明确发出 PRODUCTION_DEPLOY_CONFIRM 信号后方可开始执行。**

---

## 1. Pipeline 总览（ASCII 流程图）

```
┌─────────────────────────────────────────────────────────────────────┐
│              FreeArk 手动部署 Pipeline                              │
│         freeark_lobster_reasoning_stream  v1.3/v1.2/v1.1            │
└─────────────────────────────────────────────────────────────────────┘

 开发机（Windows）                         生产（Pi / SSH）
 ══════════════════                         ════════════════
 
 [STAGE 1: 本地验证]
  │
  ├─ 运行本地测试
  │   python manage.py test
  │   api.tests.test_reasoning_stream
  │   → 34/34 PASS? ──No──→ [修复代码] ──┐
  │        │                              │
  │       Yes                          (循环)
  │        │                              │
  ├─ 检查 .env 不在 git stage ◄───────────┘
  │   git status / git diff --staged
  │
  ├─ 准备 commit 消息文件（PowerShell 中文安全）
  │   Set-Content commit_msg.txt "feat: ..."
  │
  ├─ git add / git commit -F commit_msg.txt
  │
  └─ git push origin main
              │
              ▼
 ══════════════════════════════════════════════
              │
 [GATE 1: 等待用户 PRODUCTION_DEPLOY_CONFIRM]
              │
    用户未确认 ──────────────────────────────→ [挂起，不执行后续步骤]
              │
    用户确认 PRODUCTION_DEPLOY_CONFIRM
              │
              ▼
 ══════════════════════════════════════════════
                                               [STAGE 2: 生产前置检查]
                                                │
                                                ├─ SSH 连接 Pi
                                                │   ssh -p 57279 yangyang@et116374mm892.vicp.fun
                                                │
                                                ├─ 依赖版本检查 (§1.1)
                                                │   python / node / pip packages
                                                │
                                                ├─ .env 配置核对 (§1.2)
                                                │   OPENCLAW_* / ALLOWED_HOSTS / DEBUG
                                                │
                                                ├─ 拉取范围核对 (§1.4)
                                                │   git fetch + git diff --name-only
                                                │   受保护文件不在 diff 中?
                                                │   .env / package-lock.json /
                                                │   heartbeat_broker_config.json
                                                │   ──No──→ [暂停，上报]
                                                │       Yes↓
                                                └─ 备份 (§1.5)
                                                    cp -r dist dist_backup_$(date...)
                                                    git log -1 > pre_deploy_head.txt
                                                              │
                                                              ▼
                                               [STAGE 3: 代码部署]
                                                │
                                                ├─ git pull origin main (fast-forward)
                                                │   ──conflict──→ [暂停，上报]
                                                │       │
                                                │      OK↓
                                                ├─ 验证关键文件落地
                                                │   grep _REASONING_FIELD adapter.py
                                                │   grep reasoning_token consumers.py
                                                │   grep reasoning_token ChatView.vue
                                                │   grep OPENCLAW_REASONING_EFFORT settings.py
                                                │   (四项均有输出?)
                                                │   ──No──→ [暂停，调查]
                                                │       Yes↓
                                                └─ (可选) pip install -r requirements.txt
                                                   (本次无新依赖，跳过)
                                                              │
                                                              ▼
                                               [STAGE 4: 前端构建]
                                                │
                                                ├─ cd FreeArkWeb/frontend
                                                ├─ npm run build (vite build)
                                                │   ──失败──→ [恢复 dist 备份，上报]
                                                │       │
                                                │      OK↓
                                                └─ 验证 dist/assets/ 时间戳更新
                                                              │
                                                              ▼
                                               [STAGE 5: 服务重启]
                                                │
                                                ├─ [ARCH-C-002 强制：adapter+consumer 同批次]
                                                │
                                                ├─ sudo systemctl restart freeark-backend
                                                │
                                                ├─ (条件) .env 有变化?
                                                │   systemctl --user restart openclaw-gateway
                                                │
                                                └─ sleep 3 / 确认 active (running)
                                                              │
                                                              ▼
                                               [STAGE 6: 部署后验证]
                                                │
                                                ├─ curl /api/health/ → 200 OK?
                                                │   ──No──→ [STAGE 7: 回滚]
                                                │       Yes↓
                                                ├─ journalctl 无 ERROR/TypeError?
                                                │   ──No──→ [STAGE 7: 回滚]
                                                │       Yes↓
                                                ├─ adapter import OK?
                                                ├─ 浏览器手动功能验证
                                                │   (聊天正常 / reasoning 展示 / 折叠)
                                                │
                                                └─ 全部通过?
                                                    ──No──→ [STAGE 7: 回滚]
                                                        Yes↓
                                               [STAGE 7A: 上线后验证]
                                                │
                                                ├─ 拉高日志 APP_LOG_LEVEL=INFO
                                                ├─ US-RSN-001 字段名验证
                                                │   reasoning_tokens > 0?
                                                │   ──No──→ [字段探查循环 §6.3]
                                                │       Yes↓
                                                ├─ US-RSN-009 基线测量
                                                │   T0 (baseline) / T0' (low effort)
                                                │   效果比 >= 50%?
                                                │   ──No──→ [上报 PM 决策]
                                                │       Yes↓
                                                └─ 清理临时 APP_LOG_LEVEL
                                                              │
                                                              ▼
                                                [DONE: 部署完成，上报 PM]
```

---

## 2. 各 Stage 详细说明

### Stage 1：本地验证（开发机）

**目的**：确保本地所有测试通过，commit 合规，推送前无误。

**执行位置**：Windows 开发机，PowerShell 或 Bash 工具

```powershell
# 1a. 运行测试（在 FreeArkWeb/backend/freearkweb/ 目录）
# 使用 Bash 工具（推荐，避免 PowerShell 路径问题）：
# cd /c/Users/胖子熊/MyProject/FreeArk/FreeArkWeb/backend/freearkweb
# python manage.py test api.tests.test_reasoning_stream -v 2
# 预期：Ran 34 tests — OK

# 1b. 确认 .env 不在 stage 区域
git status
git diff --staged --name-only
# 不应出现 .env / heartbeat_broker_config.json

# 1c. 准备 commit 消息文件（PowerShell 中文安全方案）
$commitMsg = "feat(reasoning-stream): adapter v1.3 + consumer v1.2 + ChatView v1.1 reasoning stream"
Set-Content -Path "docs/specs/freeark_lobster_reasoning_stream/commit_msg_deploy.txt" `
  -Value $commitMsg -Encoding UTF8

# 1d. 提交
git add FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py
git add FreeArkWeb/backend/freearkweb/api/consumers.py
git add FreeArkWeb/frontend/src/views/ChatView.vue
git add FreeArkWeb/backend/freearkweb/freearkweb/settings.py
git add FreeArkWeb/backend/freearkweb/api/tests/test_reasoning_stream.py
git add docs/specs/freeark_lobster_reasoning_stream/
git commit -F docs/specs/freeark_lobster_reasoning_stream/commit_msg_deploy.txt

# 1e. 推送
git push origin main
```

**通过条件**：
- 34/34 测试通过
- push 成功，远端 main 更新
- .env 等受保护文件不在 commit 中

---

### Gate 1：等待 PRODUCTION_DEPLOY_CONFIRM

**此处为强制等待点。未收到用户明确确认，不得执行任何后续 Stage。**

用户发出 PRODUCTION_DEPLOY_CONFIRM 信号的方式：在会话中明确回复确认部署。

**确认内容**（运维人员向用户展示，等待回复）：
```
准备部署以下改动到生产（Pi 192.168.31.51）：
- openclaw_adapter.py v1.3（双路 reasoning 解析 + reasoning_effort 透传）
- consumers.py v1.2（reasoning_token/reasoning_end 消息类型）
- ChatView.vue v1.1（reasoning 折叠展示）
- settings.py（OPENCLAW_REASONING_EFFORT env var）

34/34 测试已通过。
本次部署需重启 freeark-backend 服务（短暂中断聊天功能）。
请确认：回复 PRODUCTION_DEPLOY_CONFIRM 授权部署。
```

---

### Stage 2：生产前置检查

参见 deployment_plan.md §1（前置条件检查清单）。全部通过后进入 Stage 3。

**SSH 连接**（须用 Bash 工具，不要 PowerShell）：
```bash
ssh -p 57279 yangyang@et116374mm892.vicp.fun
```

---

### Stage 3：代码部署

参见 deployment_plan.md §4（后端代码部署步骤）。

**关键检查**（落地验证）：
```bash
git log -1 --oneline
# 确认 HEAD 为本次 commit
grep -c "_REASONING_FIELD" FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py
# 应 >= 1
```

---

### Stage 4：前端构建

参见 deployment_plan.md §3（前端构建步骤）。

**耗时预估**：15-30 秒（Pi 5）

---

### Stage 5：服务重启

参见 deployment_plan.md §5（systemd 服务重启清单）。

**ARCH-C-002 检查点**（在此 Stage 执行前最后确认）：
```bash
# 确认 git pull 已包含 adapter + consumer 同批次改动
grep -c "reasoning_token" FreeArkWeb/backend/freearkweb/api/consumers.py
grep -c "_REASONING_FIELD" FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py
# 两个值均 >= 1，才允许重启 freeark-backend
```

---

### Stage 6：部署后验证

参见 deployment_plan.md §8（部署后验证清单）。

**快速验证（60 秒内）**：
```bash
systemctl status freeark-backend --no-pager | grep Active
curl -s http://127.0.0.1:8080/api/health/
sudo journalctl -u freeark-backend -n 20 --no-pager | grep -E "ERROR|Traceback|TypeError"
# 最后一条无输出 = 无错误
```

**回滚判断**：上述任意一项不通过 → 立即进入 Stage 7（回滚），不等待。

---

### Stage 7：回滚（异常时执行）

参见 deployment_plan.md §9（回滚方案）。

**回滚判断矩阵**：

| 异常现象 | 回滚范围 | 优先级 |
|---------|---------|--------|
| freeark-backend 无法启动 | 代码回滚（§9.2）+ 服务重启 | 紧急 |
| TypeError in consumers.py（adapter/consumer 版本不匹配）| 同上 | 紧急 |
| 前端 JS 报错 / ChatView 白屏 | 前端 dist 恢复备份 | 高 |
| /api/health/ 返回 5xx | 代码回滚 | 紧急 |
| reasoning 不展示但功能正常 | 不回滚，进入 §6.3 字段探查 | 低（可运行中修复） |

---

### Stage 7A：上线后验证（功能增强验证）

参见 deployment_plan.md §6 和 §7。

**此 Stage 不阻塞服务运行**，可在 Stage 6 确认正常后异步执行。

---

## 3. 关键时间节点与等待点汇总

| 序号 | 时间节点 | 类型 | 说明 |
|------|---------|------|------|
| T1 | 本地测试通过 | 自动验证 | 34/34，无阻塞才允许 push |
| T2 | git push origin main | 动作 | 远端 main 更新 |
| **G1** | **等待 PRODUCTION_DEPLOY_CONFIRM** | **强制等待** | **用户明确授权后才进入 Stage 2** |
| T3 | SSH 连接 Pi + 前置检查 | 手动操作 | 约 5-10 分钟 |
| T4 | git pull fast-forward | 动作 | 约 1 分钟 |
| T5 | npm run build | 动作 | 约 15-30 秒 |
| T6 | sudo systemctl restart freeark-backend | 动作 | 约 3 秒（含等待） |
| T7 | 部署后验证通过 | 验证 | 约 5 分钟 |
| T8 | US-RSN-001 字段验证 | 验证 | 可异步，约 5-30 分钟 |
| T9 | US-RSN-009 基线测量 | 验证 | 可异步，约 20-30 分钟 |

---

## 4. 分支与版本管理约定

| 约定 | 规则 |
|------|------|
| 主分支 | `main`（单一主干，不用 feature branch） |
| 生产 HEAD | 与 `origin/main` 保持一致（fast-forward only） |
| Commit 消息规范 | `feat` / `fix` / `test` / `docs`（Conventional Commits） |
| PowerShell commit | `git commit -F <txt 文件>`（避免中文断字） |
| 禁止事项 | 不直接在 Pi 上 `git commit`；不 push .env；不 merge commit（保持线性历史） |
| Tag（可选） | 本次部署后可打 tag：`git tag v0.5.10-reasoning-stream && git push origin --tags` |

---

## 5. 无 CI 环境说明与未来改进建议

### 5.1 当前状态

FreeArk 使用 GitHub Actions self-hosted runner（`actions.runner.*` 服务在 Pi 上运行），但**当前部署实践为手动 git pull**，不通过 Actions 自动触发部署。

原因：
1. 生产 .env 含敏感凭据，不适合在 Actions workflow 中管理
2. 前端构建须在 ARM 环境（Pi）执行，无跨平台 runner
3. 服务重启须 sudo 权限，Actions runner 以普通用户运行需额外配置

### 5.2 手动 Pipeline 的质量保障措施

在无自动化 CI/CD 的情况下，以下措施替代自动化检查：

| 自动化能力 | 当前替代方案 |
|-----------|------------|
| 自动触发测试 | 开发者本地手动运行（Stage 1a 强制要求） |
| 自动化测试报告 | GROUP_D test_plan.md + 34/34 本地确认 |
| 自动化部署 | 本文档手动 Pipeline（含强制 Gate 1 等待点） |
| 自动化回滚 | deployment_plan.md §9 手动回滚方案 |
| 部署通知 | PM 汇报 + 本会话状态更新 |

### 5.3 未来 CI/CD 改进方向（供参考，不在本期 scope）

若未来需要引入自动化部署，建议路径（需 PM 另开迭代）：

1. **测试自动化**：GitHub Actions workflow，push to main 触发本地 runner 执行 `python manage.py test`，无需部署权限
2. **分离 .env**：使用 GitHub Actions secrets + Pi 上脚本注入，避免 .env 进仓库
3. **前端构建缓存**：Actions workflow 在 Pi runner 上 build，产物缓存到 `/home/yangyang/FreeArk_backup/`
4. **半自动部署**：Actions workflow 仅到"代码验证"步骤，实际服务重启保留手动确认（维持 Gate 1 模式）

---

## 6. 环境对照表

| 环境 | 描述 | 触发方式 | 数据库 |
|------|------|---------|--------|
| 本地开发 | Windows 开发机，SQLite | 手动 | SQLite（自动切换） |
| 本地测试 | 同上，`python manage.py test` | 手动（Stage 1a） | SQLite |
| 生产 | Pi Debian 13，MySQL 9.4.0 | 手动 git pull（本文档） | MySQL @ 192.168.31.98:3306 |

> 注：无独立 staging 环境。本期变更（reasoning 流式展示）不写 MySQL，生产风险较低。
> 若未来引入数据库 migration，建议先建立 staging 环境。

---

## 附录：速查命令表

```bash
# ── 本地（开发机 Bash 工具）──────────────────────────────────────
# 运行测试
cd FreeArkWeb/backend/freearkweb
python manage.py test api.tests.test_reasoning_stream -v 2

# SSH 连接生产
ssh -p 57279 yangyang@et116374mm892.vicp.fun

# ── 生产（Pi SSH 内）─────────────────────────────────────────────
# 检查拉取范围
git fetch origin main && git diff --name-only HEAD origin/main

# 拉取
git pull origin main

# 前端构建
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend
npm run build

# 重启主服务
sudo systemctl restart freeark-backend
sleep 3 && systemctl status freeark-backend --no-pager | grep Active

# 健康检查
curl -s http://127.0.0.1:8080/api/health/

# 错误日志
sudo journalctl -u freeark-backend -n 30 --no-pager | grep -E "ERROR|Traceback|TypeError"

# INFO 日志（reasoning 统计）
sudo journalctl -u freeark-backend -n 50 --no-pager | grep stream_complete

# Gateway 状态
systemctl --user status openclaw-gateway.service --no-pager | grep Active
curl -s http://127.0.0.1:18789/health
```
