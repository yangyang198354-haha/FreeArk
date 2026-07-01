# CI/CD 流水线说明 — v0.6.1-FM-UX 故障管理 UX 调整

```
file_header:
  document_id: CICD-v0.6.1-FM-UX
  title: 故障管理 UX 调整 — CI/CD 流水线说明
  author_agent: sub_agent_devops_engineer (via PM Orchestrator, PARTIAL_FLOW GROUP_E)
  project: FreeArk 住宅能耗 / 暖通监控平台
  version: v0.6.1-FM-UX
  created_at: 2026-05-28
  status: APPROVED
  references:
    - docs/requirements/v0.6.1_fault_mgmt_ux/requirements_spec.md
    - docs/implementation/v0.6.1_fault_mgmt_ux/implementation_plan.md
    - docs/testing/v0.6.1_fault_mgmt_ux/unit_test_report.md
```

---

## 1. 概述

本期 v0.6.1-FM-UX **无自动化 CI/CD 流水线**。所有构建、测试、部署操作均为人工执行，通过 plink/Bash SSH 连接生产服务器（树莓派 Raspberry Pi 5）并执行 `git pull` 的方式完成代码交付。

这是由项目基础设施约束决定的（物理机部署，禁止 Docker，内网 Pi 不具备 GitHub Actions Runner 安装条件）。

---

## 2. 当前部署架构

```
开发者本地 (Windows 11)
    │
    │  git commit + git push
    ▼
GitHub (origin/main)
    │
    │  plink SSH → git pull origin main
    ▼
生产服务器 (树莓派 Pi 5, 192.168.31.51)
    ├─ /home/yangyang/Freeark/FreeArk/       ← 仓库根
    ├─ venv/                                  ← Python 虚拟环境
    ├─ FreeArkWeb/frontend/dist/              ← 前端静态产物（nginx serve）
    └─ systemd services                       ← freeark-backend.service 等
```

---

## 3. 手工流水线步骤（本期实际执行流程）

| 步骤 | 执行位置 | 操作 | 工具 |
|------|---------|------|------|
| Step 0 | 文档产出 | 生成 cicd_pipeline.md + deployment_plan.md | Claude Code |
| Step 1 | 生产服务器 | 部署前检查：git status + git log | plink + Bash |
| Step 2 | 生产服务器 | git pull origin main（fast-forward 到 c7aa7fd） | plink + Bash |
| Step 3 | 生产服务器 | 验证落地（文件存在性 + grep 关键内容） | plink + Bash |
| Step 4 | 生产服务器 | 前端构建（备份 dist + npm run build） | plink + Bash |
| Step 5 | 生产服务器 | 重启后端（systemctl restart freeark-backend） | plink + Bash |
| Step 6 | 生产服务器 | 烟测（curl health + serializer 字段验证） | plink + Bash |
| Step 7 | 文档产出 | 生成 deployment_report_2026-05-28.md | Claude Code |

---

## 4. 测试阶段（部署前已完成）

| 阶段 | 结果 | 说明 |
|------|------|------|
| 单元测试（本期新增 27 用例） | 27/27 通过 | pytest，本地执行 |
| 回归测试（全量 112 用例） | 112/112 通过 | 无回归 |
| E2E 验证 | 用户明确授权跳过本地 E2E | 由生产部署后生产端实时验证替代 |

---

## 5. 未来 CI/CD 改进建议（不在本期范围）

| 优先级 | 建议 | 说明 |
|-------|------|------|
| P1 | GitHub Actions self-hosted runner on Pi | 自动触发 `git pull + npm build + restart` |
| P2 | 自动化冒烟测试 | 部署后自动 curl 验证关键接口 |
| P3 | 前端构建产物缓存 | node_modules 缓存减少 npm install 时间 |
| P4 | 回滚自动化 | git revert + 重新部署脚本化 |

---

*本文档由 sub_agent_devops_engineer（via PM Orchestrator）生成，记录 v0.6.1-FM-UX 实际部署流程。*
