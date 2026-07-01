# CI/CD 流水线说明 — v0.6.4-FM 故障管理"实际房间"过滤 + 房间列

```
file_header:
  document_id: CICD-v0.6.4-FM-ROOM
  title: 故障管理按实际房间 5 类过滤 + 房间列 — CI/CD 流水线说明
  author_agent: sub_agent_devops_engineer (via PM Orchestrator, PARTIAL_FLOW GROUP_E)
  project: FreeArk 住宅能耗 / 暖通监控平台
  version: v0.6.4
  created_at: 2026-05-29
  status: APPROVED
  references:
    - docs/deployment/v0.6.4_fault_mgmt_room_column/deployment_plan.md
```

---

## 1. 概述

本期 v0.6.4-FM **无自动化 CI/CD 流水线**。所有构建、测试、部署操作均为人工执行，通过
Bash SSH 连接生产服务器（树莓派 Raspberry Pi 5）并执行 `git pull` 的方式完成代码交付。

这是由项目基础设施约束决定的（物理机部署，禁止 Docker，Pi 作为 GitHub Actions runner
的自动触发部署当前未启用）。

---

## 2. 当前部署架构

```
开发者本地 (Windows 11)
    │
    │  git commit + git push
    ▼
GitHub (origin/main)   ← 当前已含 commit a5a8c70
    │
    │  Bash SSH → git pull origin main
    ▼
生产服务器 (树莓派 Pi 5, 192.168.31.51)
    ├─ /home/yangyang/Freeark/FreeArk/           ← 仓库根
    ├─ venv/bin/python                            ← Python 3.13 虚拟环境
    ├─ FreeArkWeb/frontend/dist/                  ← 前端静态产物（nginx serve）
    └─ systemd services
         ├─ freeark-backend.service               ← Django Uvicorn ASGI :8000
         ├─ freeark-mqtt-consumer.service
         └─ freeark-fault-consumer.service        ← fault_event 写入路径
```

---

## 3. 手工流水线步骤（本期实际执行流程）

| 步骤 | 执行位置 | 操作 | 工具 |
|------|---------|------|------|
| Step 0 | 文档产出 | 生成 cicd_pipeline.md + deployment_plan.md | Claude Code |
| Step 1 | 生产服务器 | 停止 freeark-fault-consumer（migration 安全前提） | Bash SSH |
| Step 2 | 生产服务器 | git pull origin main（fast-forward 到 a5a8c70） | Bash SSH |
| Step 3 | 生产服务器 | 验证 HEAD == a5a8c70 | Bash SSH |
| Step 4 | 生产服务器 | migrate api 0027（DDL：ADD COLUMN room_name + room_id） | Bash SSH venv/bin/python |
| Step 5 | 生产服务器 | migrate api 0028（历史回填 ~3094 行，<10s） | Bash SSH venv/bin/python |
| Step 6 | 生产服务器 | 重启 freeark-backend + freeark-mqtt-consumer | Bash SSH systemctl |
| Step 7 | 生产服务器 | 启动 freeark-fault-consumer | Bash SSH systemctl |
| Step 8 | 生产服务器 | 前端构建（备份 dist + npm run build + rsync/reload） | Bash SSH |
| Step 9 | 生产服务器 | 部署后验证（systemctl status + showmigrations + SQL + API 烟测） | Bash SSH |
| Step 10 | 文档产出 | 生成 deployment_report_2026-05-29.md（含每步真实 stdout） | Claude Code |

---

## 4. 测试阶段（部署前已完成）

| 阶段 | 结果 | 说明 |
|------|------|------|
| 单元测试（本期新增） | 20/20 通过 | pytest，本地执行 |
| 集成测试（本期新增） | 18/18 通过 | pytest TransactionTestCase，本地 SQLite |
| 主线手工修复 bug（3 处） | 已含在 a5a8c70 中 | migration 0028 编码问题 + bulk_update fields + state_machine FK attname |
| E2E 验证 | 由生产部署后烟测替代 | 见 deployment_plan.md §6 |

---

## 5. SSH 连接方式

```bash
# 标准连接（本地 DNS 正常时）
ssh -p 57279 yangyang@et116374mm892.vicp.fun '<remote command>'

# DNS 故障绕过（公司 DNS 不识别 vicp.fun TLD 时）
IP=$(nslookup et116374mm892.vicp.fun 8.8.8.8 | awk '/^Address: / && !/8\.8\.8\.8/{print $2; exit}')
ssh -p 57279 \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=no \
    -o HostKeyAlias=et116374mm892.vicp.fun \
    yangyang@${IP} '<remote command>'
```

> 注：v0.6.3 部署时本地 DNS 异常，实际用 IP `115.236.153.170` + HostKeyAlias 直连。
> v0.6.4 部署前须重新 nslookup 获取当前 IP（花生壳 IP 可能已变）。

---

## 6. 未来 CI/CD 改进建议（不在本期范围）

| 优先级 | 建议 | 说明 |
|-------|------|------|
| P1 | GitHub Actions self-hosted runner on Pi | 自动触发 git pull + migrate + restart |
| P2 | 自动化冒烟测试 | 部署后自动 curl 验证关键接口 |
| P3 | 前端构建产物缓存 | node_modules 常驻 Pi，减少 npm install 时间 |
| P4 | 回滚自动化脚本 | git reset + 逐级 migrate 回滚脚本化 |

---

*本文档由 sub_agent_devops_engineer（via PM Orchestrator）生成，记录 v0.6.4-FM 实际部署流程。*
