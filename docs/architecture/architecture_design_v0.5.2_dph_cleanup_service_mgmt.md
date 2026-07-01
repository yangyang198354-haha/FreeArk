# 架构设计文档 — v0.5.2 DPH 清理服务管理

**文档编号**: ARCH-DPH-CLEANUP-MGMT-001
**版本**: 1.0.0
**状态**: APPROVED
**创建日期**: 2026-05-20
**作者**: pm-orchestrator (sub_agent_system_architect)
**关联需求**: REQ-SPEC-DPH-CLEANUP-MGMT-001 v0.2.0

---

## 1. 架构决策摘要

本特性**不引入任何新的架构层次或组件**。其全部实现通过复用现有 systemd 服务框架 + 白名单监控机制完成。

| 维度 | 决策 | 理由 |
|------|------|------|
| 后端实现 | 复用 MONITORED_SERVICES 白名单（追加 1 行） | 完全对齐 freeark-plc-cleanup 先例，无需新接口或新表 |
| 前端实现 | 零改动 | 服务管理页和看板均动态渲染白名单内容，无硬编码服务名 |
| 系统服务 | 复用现有 systemd unit 文件（已在仓库） | unit 文件已完整配置，仅需生产安装 |
| 数据存储 | 无新表、无 migration | 用户答复 OQ-1：不持久化清理结果 |

---

## 2. 现有架构集成点

### 2.1 集成点全景

```
┌─────────────────────────────────────────────────────────────────┐
│                        生产服务器（树莓派）                       │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                     systemd                              │   │
│  │                                                          │   │
│  │  freeark-backend.service  ←── 现有                       │   │
│  │  freeark-plc-cleanup.service  ←── 现有（参照）            │   │
│  │  freeark-dph-cleanup.service  ←── v0.5.2 新增（安装）     │   │
│  │    ExecStart: venv/python manage.py dph_cleanup_service  │   │
│  │             --days 7 --batch-size 5000 --sleep-ms 200    │   │
│  │             --cron "0 3 * * *"                           │   │
│  │    User: yangyang, Restart: on-failure, RestartSec: 30s  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                          │                                       │
│                          │ 每天 03:00 触发                        │
│                          ▼                                       │
│  ┌────────────────────────────────────────────────────────┐     │
│  │              Django Backend (waitress)                  │     │
│  │                                                         │     │
│  │  MONITORED_SERVICES = [                                 │     │
│  │      'freeark-plc-cleanup',   ← 现有                    │     │
│  │      'freeark-dph-cleanup',   ← v0.5.2 新增（1 行）      │     │
│  │      ...（共 9 个）                                      │     │
│  │  ]                                                      │     │
│  │  _MONITORED_SERVICES_SET = set(MONITORED_SERVICES)      │     │
│  │           ↑ 由列表推导自动同步，无需手动维护              │     │
│  │                                                         │     │
│  │  GET /api/dashboard/services/  → 按白名单返回状态        │     │
│  │  GET /api/services/list/       → 按白名单返回列表        │     │
│  │  GET /api/services/<n>/detail/ → 白名单校验后返回详情    │     │
│  │  POST /api/services/<n>/action/ → 白名单校验后执行操作   │     │
│  └────────────────────────────────────────────────────────┘     │
│                          │                                       │
└──────────────────────────┼───────────────────────────────────────┘
                           │ HTTP/JSON
┌──────────────────────────┼───────────────────────────────────────┐
│                    前端 Vue 3 (nginx)      无改动                  │
│                          │                                       │
│  HomeView.vue:fetchServices()                                    │
│    → GET /api/dashboard/services/                                │
│    → services.value = res.data  ← 动态渲染，无硬编码服务名        │
│                                                                  │
│  ServicesView.vue:fetchList()                                    │
│    → GET /api/services/list/                                     │
│    → serviceList.value = resp.data  ← 动态渲染                   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 集成点详细说明

#### A. MONITORED_SERVICES 白名单（api/views.py:1103）

**作用**：所有服务管理相关接口的统一安全白名单。加入白名单后：
- `_MONITORED_SERVICES_SET`（`set(MONITORED_SERVICES)`）自动同步，无需手动维护
- `/api/dashboard/services/` 接口遍历白名单调用 `systemctl is-active`，自动包含新服务
- `/api/services/list/` 接口遍历白名单，自动包含新服务
- `/api/services/<name>/detail/` 和 `/api/services/<name>/action/` 用 `_MONITORED_SERVICES_SET` 做安全校验

**关键安全设计**：白名单是防止命令注入的核心控制。`freeark-dph-cleanup` 仅为合法 systemd 服务名（字母、数字、连字符），不含任何 shell 特殊字符。

#### B. systemd unit 文件（systemctl/freeark-dph-cleanup.service）

**现状**：已在 git 仓库，内容已正确（勘察确认）：
- `User=yangyang`：与所有现有服务一致
- `WorkingDirectory=/home/yangyang/Freeark/FreeArk/`：与生产路径一致
- `ExecStart=/home/yangyang/Freeark/FreeArk/venv/bin/python .../manage.py dph_cleanup_service --days 7 --batch-size 5000 --sleep-ms 200 --cron "0 3 * * *"`
- `Restart=on-failure, RestartSec=30s`：与 freeark-plc-cleanup 一致
- **注意：不含 `--dry-run`，生产启动后将执行真实删除**

**需要做的**：生产服务器安装（`git pull` 后 `sudo cp` + `daemon-reload` + `enable` + `start`），这是部署阶段的操作。

#### C. 前端（HomeView.vue + ServicesView.vue）

**勘察结论：前端零改动假设成立。**

- `HomeView.vue:338`：`services.value = res.data`，直接绑定后端返回的数组，无硬编码服务名列表
- `ServicesView.vue:206`：`serviceList.value = resp.data || []`，同上
- 两个组件均使用 `v-for` 动态渲染，服务名通过 `svc.name` 展示，不做任何白名单过滤

---

## 3. ADR（架构决策记录）

### ADR-001：不引入新接口，复用白名单机制

**背景**：需要在看板和服务管理页面展示 freeark-dph-cleanup 的运行状态。

**方案 A（选定）**：将 `freeark-dph-cleanup` 加入现有 `MONITORED_SERVICES` 白名单（1 行改动），复用全部现有接口和前端渲染逻辑。

**方案 B（否决）**：新增独立的清理状态接口 `/api/dashboard/dph-cleanup-status/`，返回清理结果指标（上次清理时间、删除行数等）。

**决策依据**：
- 用户答复 OQ-1（不持久化）使方案 B 无法实现（无持久化数据，无法返回历史清理结果）
- 用户答复 OQ-4（复用系统运行状态卡片，不新增独立卡片）与方案 B 不兼容
- 方案 A 代码改动量最小，风险最低，与同类服务（freeark-plc-cleanup）完全对齐
- 方案 A 无需数据库迁移，无需前端发版

---

## 4. 数据流

```
[每天 03:00]
systemd 触发 → dph_cleanup_service (--cron "0 3 * * *")
            → 分批查询 device_param_history WHERE collected_at < NOW()-7d
            → 批次删除（batch_size=5000，sleep_ms=200）
            → 写入 dph_cleanup_service.log（每批次 INFO + 最终摘要）
            → 进程正常退出（systemd type=simple 检测到退出，等待下次触发）

[运维查看状态]
前端 → GET /api/dashboard/services/
     ← [{name: "freeark-dph-cleanup", status: "active"|"inactive", is_active: bool}, ...]

[运维操作服务]
前端 → POST /api/services/freeark-dph-cleanup/action/ {action: "start"|"stop"|"restart"}
     → 后端白名单校验 → sudo systemctl <action> freeark-dph-cleanup
     ← {success: true, new_status: "active"|"inactive"}
```

---

## 5. 非功能性约束（架构层面）

| 约束 | 说明 |
|------|------|
| 物理机，无 Docker | systemd unit 以 yangyang 用户运行，无容器化需求 |
| 部署方式 | git pull + sudo cp（不可 pscp），白名单代码变更需重启 freeark-backend 生效 |
| 安全 | 白名单双重保护（MONITORED_SERVICES list + _SET），service_name 不做字符串拼接 |
| 性能 | 清理任务分批+sleep（已有），不影响白天负载；看板接口遍历 9 个服务调用 systemctl，无性能影响 |
| 回滚 | 代码回滚：git revert + 重启 backend；服务回滚：systemctl stop/disable + rm unit + daemon-reload |

---

## 6. 与现有架构的差异

与现有 freeark-plc-cleanup 的架构完全对齐，无差异。本特性是对现有模式的一次标准复制。
