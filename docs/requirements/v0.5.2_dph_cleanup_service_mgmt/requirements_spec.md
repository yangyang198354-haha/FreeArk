# 需求规格说明书

**文档编号**: REQ-SPEC-DPH-CLEANUP-MGMT-001
**项目名称**: FreeArk DPH 清理服务管理
**版本**: 0.2.0-PENDING-GATE
**状态**: PENDING_GATE（范围已按用户答复收敛，待门控确认后升级为 APPROVED）
**创建日期**: 2026-05-20
**最后更新**: 2026-05-20
**作者**: requirement-analyst (via pm-orchestrator)
**审核**: 待 pm-orchestrator 门控

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-20 | 初始草稿，含 Open Questions OQ-1~OQ-4 待确认 |
| 0.2.0-PENDING-GATE | 2026-05-20 | **范围收敛修订**：按用户对 OQ-1~OQ-4 全部答复重写，大幅简化范围（见第 0 节） |

---

## 0. 范围收敛说明（本次修订依据）

### 0.1 用户对 Open Questions 的答复（决定性）

| 问题编号 | 问题摘要 | 用户答复 | 对需求的影响 |
|---------|---------|---------|------------|
| OQ-1 | 清理结果是否持久化，以支持看板展示上次清理时间/删除行数 | **不需要持久化** | 移除所有清理结果指标的展示需求；移除新接口；移除数据库表/migration |
| OQ-2 | 看板是否展示当前 device_param_history 表行数 | **不展示行数** | 移除行数展示相关需求 |
| OQ-3 | UI 是否支持立即触发一次清理 | **本期不做** | 移除 UI 触发清理功能 |
| OQ-4 | "数据清理状态"卡片位置 | **在「系统运行状态」中**，不新增独立卡片 | 移除独立新卡片；看板展示依赖现有白名单动态渲染机制 |

### 0.2 因用户答复被移除的内容（变更前存在，变更后删除）

以下内容在 v0.1.0-DRAFT 中存在，已在本次修订中**全部移除**：

| 被移除项 | 原文档位置 | 移除原因 |
|---------|----------|---------|
| FR2-2：新增独立"数据清理状态"卡片 | 原 FR2 | OQ-4 答复：不新增独立卡片 |
| FR2-3：新增 `/api/dashboard/dph-cleanup-status/` 接口 | 原 FR2 | OQ-1 答复：不持久化，无需新接口 |
| FR2-4：卡片刷新策略 | 原 FR2 | 随 FR2-2/FR2-3 一并移除 |
| FR2-5：尚未执行过清理时的显示 | 原 FR2 | 随 FR2-2/FR2-3 一并移除 |
| 清理结果指标（上次清理时间、删除行数） | 原 FR2、NFR3-2、US-DPH-07 | OQ-1 答复：不持久化 |
| device_param_history 当前行数展示 | 原 FR2-2(d)、NFR2-1、OQ-2 | OQ-2 答复：不展示 |
| UI 立即触发清理 | 原 OQ-3 | OQ-3 答复：本期不做 |
| dph_cleanup_run 数据库表 / migration | 原 OQ-1 方案 B | OQ-1 答复：不需要 |
| OQ-1~OQ-4 全部 Open Questions 章节 | 原第 6 节 | 已全部决策，无遗留问题 |
| NFR1-5：新接口只读权限要求 | 原 NFR1-5 | 随 FR2-3 一并移除 |
| NFR2-1：接口 <500ms 及禁止 COUNT(*) | 原 NFR2-1 | 随 FR2-3 一并移除 |
| NFR3-2：看板卡片展示清理时间和删除行数 | 原 NFR3-2 | OQ-1 答复：不持久化 |
| NFR3-3：独立卡片红色警告样式 | 原 NFR3-3 | 随独立卡片一并移除 |

### 0.3 收敛后的最终范围（三项）

1. **FR1 — systemd 服务安装与启用**：将已有 unit 文件在生产树莓派上安装并 enable，使清理任务每天 03:00 自动执行。
2. **FR2（简化）— 服务注册进监控白名单**：后端 `MONITORED_SERVICES` 加入 `freeark-dph-cleanup`（1 行改动）。加入后，看板"系统运行状态"卡片自动展示该服务运行/停止状态，无需新接口、新卡片、新表。
3. **FR3 — 服务页面管理**：运维可在服务管理页面对该服务执行启动/停止/重启/查看详情，与现有其他服务完全一致，前端零改动。

---

## 1. 业务背景与目标

### 1.1 背景

FreeArk 生产数据库中，`device_param_history` 表因持续写入 PLC 采集数据，已膨胀至约 3600 万行 / 11.6 GB。由于 MySQL InnoDB 缓冲池仅 128 MB（树莓派物理内存限制），该表的膨胀严重拖慢了 Dashboard 接口及其他查询。

为此，已开发并生产部署了分批清理管理命令 `dph_cleanup_service`（位于 `FreeArkWeb/backend/freearkweb/api/management/commands/dph_cleanup_service.py`），并已准备好对应的 systemd unit 文件（`systemctl/freeark-dph-cleanup.service`），但该 unit 尚未在生产安装启用。

### 1.2 目标

本特性最终范围收敛为两项：

1. **systemd 服务化**：将已有的 `dph_cleanup_service` 管理命令注册为 systemd 服务 `freeark-dph-cleanup`，使其能够：开机自启、按计划（每天凌晨 03:00）执行清理、失败后自动重启。
2. **纳入现有监控与管理体系**：后端将 `freeark-dph-cleanup` 加入 `MONITORED_SERVICES` 白名单（1 行代码），实现：
   - 看板"系统运行状态"卡片自动展示该服务运行/停止状态（依赖现有白名单动态渲染，无新接口）；
   - 服务管理页面自动支持对该服务的启动/停止/重启/详情查看（依赖现有接口，无前端改动）。

**明确不在本期范围内**：清理结果持久化、清理指标展示、独立 Dashboard 卡片、新后端接口、新数据库表、UI 触发清理、行数展示（已由用户答复 OQ-1~OQ-4 排除）。

### 1.3 约束（来自项目基础设施）

- **C1** 物理机部署，FreeArk 应用禁止 Docker；生产环境为树莓派（192.168.31.51），ARM 架构。
- **C2** 生产部署必须通过 `plink + git pull`，禁止 `pscp` 逐文件上传。
- **C3** systemd 服务以 `yangyang` 用户运行（与现有所有服务一致）。
- **C4** 服务管理操作（start/stop/restart）需鉴权：当前实现要求 `IsAuthenticated`，执行时调用 `sudo systemctl`（需 sudoers 配置）。本特性沿用该安全模型，不引入新的权限系统。

---

## 2. 现状勘察结论（需求分析前置）

在撰写需求前，已对现有代码进行勘察，结论如下：

### 2.1 已存在，本特性可直接复用（无需新建）

| 资产 | 位置 | 状态 |
|------|------|------|
| 清理管理命令 | `api/management/commands/dph_cleanup_service.py` | 已部署生产，dry-run 已验证 |
| systemd unit 文件 | `systemctl/freeark-dph-cleanup.service` | 已在仓库，**未在生产安装** |
| 后端 `_get_service_status()` | `api/views.py:1121` | 调用 `systemctl is-active`，已有 |
| 后端 `_get_service_detail()` | `api/views.py:1135` | 调用 `systemctl status`，已有 |
| 后端 `service_management_action()` | `api/views.py:1296` | 支持 start/stop/restart，已有 |
| 后端 `dashboard_services()` | `api/views.py:1187` | 看板服务状态接口，已有 |
| 服务名白名单 `MONITORED_SERVICES` | `api/views.py:1103` | 目前 8 个服务，**不含** dph-cleanup |
| 前端服务列表页 | `frontend/src/views/ServicesView.vue` | 完整实现，调用 `/api/services/list/` |
| 前端看板服务卡片 | `frontend/src/views/HomeView.vue:125` | 已有"系统运行状态"卡片，轮询 `/api/dashboard/services/` |
| 日志配置 | `settings.py:492` | `dph_cleanup_service` logger 已配置，写入 `dph_cleanup_service.log` |

### 2.2 同类参照（freeark-plc-cleanup 的对比）

`freeark-plc-cleanup` 是现有同类清理服务。经勘察：
- 其 unit 文件与 `freeark-dph-cleanup.service` 结构完全一致。
- 其服务名 `freeark-plc-cleanup` **已在** `MONITORED_SERVICES` 白名单中（`views.py:1109`）。
- 在看板的"系统运行状态"卡片中显示为服务状态 tag。
- 在服务管理页面中支持 start/stop/restart/详情。
- `freeark-plc-cleanup` 没有专用的看板卡片展示清理结果指标——本特性与此完全对齐，同样不建独立卡片。

### 2.3 本特性需新增的内容

| 层次 | 需新增内容 |
|------|-----------|
| 后端 | `freeark-dph-cleanup` 加入 `MONITORED_SERVICES` 白名单（**1 行代码**） |
| 运维 | 生产服务器安装并 enable `freeark-dph-cleanup.service`（部署阶段执行） |
| 前端 | **零改动**（看板"系统运行状态"卡片与服务管理页均由白名单动态渲染）— 此假设需在架构/开发阶段实测验证 |

---

## 3. 功能性需求

### FR1 — systemd 服务安装与启用

**来源**: 用户需求——"增加一个 systemd，包裹这个管理命令"

**背景**: `systemctl/freeark-dph-cleanup.service` 已存在于仓库，ExecStart 已正确配置（`--days 7 --batch-size 5000 --sleep-ms 200 --cron "0 3 * * *"`），以 `yangyang` 用户运行。本 FR 描述的是**该 unit 在生产服务器上的安装与注册**，属于部署阶段的操作性需求。

| 编号 | 需求描述 | 已有/新增 |
|------|----------|---------|
| FR1-1 | 生产服务器上，将 `freeark-dph-cleanup.service` 通过 `git pull` 后 `sudo cp` 至 `/etc/systemd/system/`，执行 `systemctl daemon-reload` 与 `systemctl enable freeark-dph-cleanup`。 | 新增（部署操作） |
| FR1-2 | 服务以 `systemd Type=simple` 模式运行，以 `yangyang` 用户身份执行，工作目录 `/home/yangyang/Freeark/FreeArk/`，与现有服务保持一致。 | 已有（unit 文件已写明） |
| FR1-3 | 服务在失败时自动重启（`Restart=on-failure`，`RestartSec=30s`），与 `freeark-plc-cleanup` 一致。 | 已有（unit 文件已写明） |
| FR1-4 | 日志输出到 `journald`（`StandardOutput=journal`），同时由 Django logging 写入 `dph_cleanup_service.log`（已配置）。运维可通过 `journalctl -u freeark-dph-cleanup` 查看实时日志。 | 已有（unit + settings 已配置） |
| FR1-5 | 服务启动时以常驻 cron 模式运行（`--cron "0 3 * * *"`），每天凌晨 03:00 执行一次清理，保留最近 7 天数据。 | 已有（unit ExecStart 已写明） |

---

### FR2 — 服务注册进监控白名单（看板与服务页自动生效）

**来源**: 用户答复 OQ-4——"在系统运行状态中"（复用现有卡片，不新增独立卡片）；用户答复 OQ-1——"不需要持久化"（无新接口）。

**背景**: 现有后端 `MONITORED_SERVICES` 白名单控制两个前端功能：（1）看板"系统运行状态"卡片的服务列表（`/api/dashboard/services/` 接口按白名单返回状态）；（2）服务管理页面的服务列表及操作权限。将 `freeark-dph-cleanup` 加入白名单（1 行代码）后，两个前端页面自动生效，无需前端改动。

| 编号 | 需求描述 | 已有/新增 |
|------|----------|---------|
| FR2-1 | 在 `api/views.py` 的 `MONITORED_SERVICES` 列表中追加 `"freeark-dph-cleanup"`。同时确认 `_MONITORED_SERVICES_SET` 同步更新（如其由列表推导，则自动生效；若为手动维护，需同步添加）。 | **新增（1 行后端改动）** |
| FR2-2 | 白名单加入后，看板"系统运行状态"卡片的服务列表中自动出现 `freeark-dph-cleanup`，展示 active/inactive/failed 状态 tag（绿色运行中 / 红色已停止）。该行为由现有前端代码动态渲染，无需前端改动。 | 依赖 FR2-1（前端已有） |
| FR2-3 | 白名单加入后，`/api/services/list/` 接口响应中自动包含 `freeark-dph-cleanup` 条目，服务管理页面无需代码修改即可展示并管理该服务。 | 依赖 FR2-1（前端已有） |

**注意（待架构/开发阶段验证）**: 上述"前端零改动"基于现有白名单动态渲染机制的假设。实际开发阶段需验证 `HomeView.vue` 和 `ServicesView.vue` 确实按白名单动态渲染，若存在硬编码服务名列表，则需相应前端改动。

---

### FR3 — 服务页面：管理 freeark-dph-cleanup

**来源**: 用户需求——"在服务页面进行管理"

**背景**: 现有 `ServicesView.vue` 已完整实现服务管理（调用 `/api/services/list/`、`/api/services/<name>/detail/`、`/api/services/<name>/action/`）。本 FR 的实现完全依赖 FR2-1（白名单加入），前端无需任何改动。

| 编号 | 需求描述 | 已有/新增 |
|------|----------|---------|
| FR3-1 | 服务管理页面的服务列表中，展示 `freeark-dph-cleanup` 的运行状态（active_state）和自启状态（enabled）。 | 依赖 FR2-1（后端 1 行） |
| FR3-2 | 运维用户可对 `freeark-dph-cleanup` 执行**启动**操作（`POST /api/services/freeark-dph-cleanup/action/` `{"action":"start"}`）。 | 依赖 FR2-1（后端白名单） |
| FR3-3 | 运维用户可对 `freeark-dph-cleanup` 执行**停止**操作（`{"action":"stop"}`）。停止后服务不再按计划执行清理，直到下次启动。 | 依赖 FR2-1（后端白名单） |
| FR3-4 | 运维用户可对 `freeark-dph-cleanup` 执行**重启**操作（`{"action":"restart"}`）。 | 依赖 FR2-1（后端白名单） |
| FR3-5 | 运维用户可查看 `freeark-dph-cleanup` 的**详情**（`GET /api/services/freeark-dph-cleanup/detail/`），展示 active_state、sub_state、PID、内存占用和 `systemctl status` 原始输出。 | 依赖 FR2-1（后端白名单） |
| FR3-6 | 前端 `ServicesView.vue` **无需修改**（服务加入后端白名单后，`/api/services/list/` 响应中自动包含该服务，现有前端代码自动渲染）。 | 已有（前端不变） |

---

## 4. 非功能性需求

### NFR1 — 安全性

| 编号 | 需求描述 |
|------|----------|
| NFR1-1 | 服务管理操作（start/stop/restart）的所有接口均受 `IsAuthenticated` 权限保护，未登录用户返回 HTTP 401。现有实现已满足，本特性沿用，不削弱。 |
| NFR1-2 | 服务名白名单（`MONITORED_SERVICES` 和 `_MONITORED_SERVICES_SET`）是防止命令注入的核心安全控制。将 `freeark-dph-cleanup` 加入白名单时，必须同时更新这两个数据结构（如 `_MONITORED_SERVICES_SET` 为手动维护），不得引入字符串拼接。 |
| NFR1-3 | `sudo systemctl` 调用需在生产服务器的 sudoers 中明确配置（参考现有服务管理部署说明），本特性不新增 sudo 权限需求，沿用现有配置。 |
| NFR1-4 | 后端 action 接口在 Django logger 中记录操作审计日志（`用户 <username> 对服务 <name> 执行 <action>`），现有实现 `views.py:1339` 已覆盖，本特性沿用。 |

### NFR2 — 性能

| 编号 | 需求描述 |
|------|----------|
| NFR2-1 | 服务管理操作接口（start/stop/restart）保持现有 30s 超时上限，超时返回 HTTP 504，现有实现已覆盖。 |
| NFR2-2 | 清理任务在凌晨 03:00 执行时，已有分批 + sleep 机制（batch_size=5000，sleep_ms=200）保护 DB，无需额外性能需求。 |

### NFR3 — 可观测性

| 编号 | 需求描述 |
|------|----------|
| NFR3-1 | 清理任务每批次执行结果写入 `dph_cleanup_service.log`（Django RotatingFileHandler，已配置），运维可通过日志查看逐批删除行数。 |
| NFR3-2 | 看板"系统运行状态"卡片中，`freeark-dph-cleanup` 与其他服务统一展示状态 tag；若服务处于 failed 状态，以与 inactive 一致的非绿色样式展示，不要求额外告警推送。 |

---

## 5. 范围边界与排除项

| 项目 | 是否在本期范围 | 说明 |
|------|--------------|------|
| freeark-dph-cleanup.service unit 文件内容修改 | 否 | unit 已符合要求，不改 |
| 清理参数（--days / --batch-size 等）的 Web 配置化 | 否 | 本期不支持从 UI 调整参数 |
| 主动告警（钉钉/邮件）服务异常通知 | 否 | 超出本期范围 |
| 清理任务的即时 UI 触发 | **否（用户答复 OQ-3：本期不做）** | 服务管理页可通过 restart 间接触发，但不提供专用触发按钮 |
| 清理结果持久化（数据库表 / 日志解析 / JSON 文件） | **否（用户答复 OQ-1：不需要持久化）** | 已排除 |
| 看板清理结果指标（上次清理时间、删除行数） | **否（用户答复 OQ-1）** | 已排除 |
| device_param_history 当前行数展示 | **否（用户答复 OQ-2：不展示行数）** | 已排除 |
| 新增独立"数据清理状态"Dashboard 卡片 | **否（用户答复 OQ-4：复用系统运行状态卡片）** | 已排除 |
| 新增 `/api/dashboard/dph-cleanup-status/` 接口 | **否（随 OQ-1/OQ-4 一并排除）** | 已排除 |
| dph_cleanup_run 数据库表 / Django migration | **否（随 OQ-1 一并排除）** | 已排除 |
| `device_param_history` 表结构变更或分区 | 否 | 超出本期范围 |
| 角色权限细分（管理员 vs 普通用户） | 否 | 沿用现有 `IsAuthenticated` 统一权限 |

---

## 6. 待确认问题

**需求已收敛，无开放问题。**

用户对 OQ-1~OQ-4 的全部答复已于 2026-05-20 收到，所有疑点均已消除。本文档已按答复完成修订，可进入门控评审。

---

## 7. 与已有文档的关系

本文档为独立的特性需求规格，与以下文档平行：

| 文档 | 关系 |
|------|------|
| `docs/requirements/requirements_spec.md`（设备参数设置，v0.4.0） | 无关联，不同特性 |
| `docs/requirements/v0.5.1_mode_alignment_and_energy_supply/requirements_spec.md` | 无关联，不同特性 |
| `api/management/commands/dph_cleanup_service.py` | 已有实现，本特性在其上叠加管理能力 |
| `systemctl/freeark-dph-cleanup.service` | 已有 unit，本特性触发其在生产的安装启用 |
| `api/views.py`（MONITORED_SERVICES 白名单） | 本特性追加 `freeark-dph-cleanup` 至白名单 |
