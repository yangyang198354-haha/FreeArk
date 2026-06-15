# 需求规格说明书 — v1.2.0 服务注册表与看板完整化

**文档编号**: REQ-SPEC-SRD-001
**项目名称**: FreeArk Service Registry & Dashboard Completeness (v1.2.0)
**版本**: 1.0.0
**状态**: DRAFT
**创建日期**: 2026-06-16
**作者**: requirement-analyst (via pm-orchestrator)
**审核**: ✅ 开放决策已拍板（2026-06-16，见 §4 各 OQ 决议）；范围已按 Pi `list-unit-files` 实测校正；待实现

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 1.0.0 | 2026-06-16 | 初始草稿，含开放决策 OQ-1~OQ-5 待用户拍板 |

---

## 0. 问题陈述

### 0.1 背景现状

FreeArk 当前已有：
- **服务管理**（ServicesView.vue + `/api/services/list/`）：展示白名单服务列表，支持启停重启
- **系统看板 / 系统运行状态**（HomeView.vue + `/api/dashboard/services/`）：展示白名单服务的 active/inactive 状态

两者均以 `MONITORED_SERVICES` 白名单（`api/views.py:1143`）为唯一数据源，前端动态渲染，无硬编码服务名。

**当前白名单（9个，实测代码）**：

| 序号 | 服务名 | 类型 |
|------|-------|------|
| 1 | freeark-backend | 常驻（Django Web） |
| 2 | freeark-mqtt-consumer | 常驻（MQTT） |
| 3 | freeark-screen-heartbeat | 常驻 |
| 4 | freeark-daily-usage | 常驻 |
| 5 | freeark-monthly-usage | 常驻 |
| 6 | freeark-plc-cleanup | 常驻（内置 cron） |
| 7 | freeark-dph-cleanup | 常驻（内置 cron） |
| 8 | freeark-plc-connection-monitor | 常驻 |
| 9 | freeark-task-scheduler | 常驻 |

**仓库中已有 systemd unit 文件但未进入白名单的服务**（以 `deployment/systemd/` 为准）：

| 服务名 | unit 文件 | 类型 | 部署状态 |
|-------|---------|------|---------|
| freeark-fault-consumer | freeark-fault-consumer.service | 常驻（MQTT） | 已部署（v0.6.0，运行中） |
| freeark-fault-cleanup | freeark-fault-cleanup.service + .timer | 定时（oneshot via timer） | 已部署（v0.6.0） |
| freeark-condensation-consumer | freeark-condensation-consumer.service | 常驻（MQTT） | 已部署（v0.7.0，运行中） |
| freeark-condensation-cleanup | freeark-condensation-cleanup.service + .timer | 定时（oneshot via timer） | 已部署（v0.7.0） |
| freeark-inspection-agent | freeark-inspection-agent.service | 常驻（Agent） | unit 已装，**disabled + stopped**（v1.1.0，待用户决策启用） |

**背景记录（skill 文档提及但需实测核实的服务）**：

| 服务名 | 来源 | 性质 | 是否在仓库 unit |
|-------|------|-----|--------------|
| freeark-fault-cleanup.timer | skill §3 | 定时器单元 | 是（deployment/systemd/） |
| openclaw-gateway.service | skill §3 | 用户服务（非 freeark-*） | 否 |
| redis-server | skill §3 | apt 系统服务 | 否 |

> **注意**：skill 文档清单为参考，**权威状态以生产 Pi 上 `systemctl list-units 'freeark-*'` 实测为准**。
> 人工复核方法：在生产服务器执行 `systemctl list-units 'freeark-*' --all` 并与本文档核对。

### 0.2 核心缺口

1. **freeark-fault-consumer**、**freeark-condensation-consumer** 是长期运行的生产关键服务（已实际部署），但**不在白名单**，无法在服务管理或系统看板中看到或操作。
2. **freeark-fault-cleanup.timer**、**freeark-condensation-cleanup.timer**（及其对应 .service）：定时清理单元，已部署，未在白名单。
3. **freeark-inspection-agent**：v1.1.0 本周期刚部署的新服务，unit 已装于 `/etc/systemd/system/`，当前 disabled+stopped，也不在白名单。
4. **状态语义坑**：现有看板仅以 `is_active = (status == 'active')` 区分"运行中"和"已停止"，对定时类服务（非执行时段 inactive 属正常）和 disabled 服务（intentionally 停用）会**误报为故障/停止**，引起运维误判。

---

## 1. 业务目标

| 目标 | 描述 |
|------|------|
| BG-01 | 服务管理页面列出**所有** freeark-* 系统服务，让运维有完整管控视角 |
| BG-02 | 系统看板"系统运行状态"展示**所有** freeark-* 服务的运行状态，且状态语义正确、不误报 |
| BG-03 | 不因遗漏服务而在系统异常时错失告警线索 |
| BG-04 | 最小化改动：复用现有白名单机制，不引入新架构层次 |

---

## 2. 功能需求

### FR-01：更新 MONITORED_SERVICES 白名单

**来源**：BG-01, BG-02, BG-03

**描述**：在 `FreeArkWeb/backend/freearkweb/api/views.py` 的 `MONITORED_SERVICES` 列表中，追加以下服务（具体服务范围见 OQ-1 待用户决策）：

**必须追加（无争议项，均为 freeark-* 生产服务，有仓库 unit 文件）**：

| 追加条目 | 理由 |
|---------|------|
| `freeark-fault-consumer` | 故障 MQTT 消费者，已运行，未在白名单 |
| `freeark-condensation-consumer` | 结露预警消费者，已运行，未在白名单 |
| `freeark-inspection-agent` | 本周期新部署，disabled+stopped，需可见 |

**待用户决策项（见 OQ-1）**：

| 候选条目 | 争议 |
|---------|------|
| `freeark-fault-cleanup` | 定时清理 oneshot，OQ-1 需决定是否纳入；其 .timer 是实际触发单元 |
| `freeark-fault-cleanup.timer` | 含 `.timer` 后缀，systemctl is-active 对 timer 单元返回 "active"（等待触发中） |
| `freeark-condensation-cleanup` | 同上 |
| `freeark-condensation-cleanup.timer` | 同上 |

**追加后白名单总数**：最少12个（仅加3个无争议项），最多16个（全加）。

**安全约束**：所有服务名均为合法 systemd 服务名（字母、数字、连字符、点号），不含 shell 特殊字符，满足现有白名单安全设计。

**验收标准**：`_MONITORED_SERVICES_SET = set(MONITORED_SERVICES)` 自动同步，无需额外改动；新加的服务名已在 Pi 上以 `systemctl is-active <name>` 可以返回有效状态值（active/inactive/failed）。

---

### FR-02：系统看板状态语义修正

**来源**：BG-02；解决 §0.2 状态语义坑

**描述**：当前看板"系统运行状态"展示逻辑：

```
is_active = (status == 'active')  →  "运行中" | "已停止"
```

问题：定时类服务（cleanup 系列）在非执行时段 status=inactive，被误报为"已停止"；inspection-agent 当前 disabled+stopped 也被误报；运维无法区分"正常停止"和"故障停止"。

**修正方案**（两个子项，均需用户决策 OQ-2、OQ-3 后定稿）：

**FR-02a（后端）**：`/api/dashboard/services/` 接口在现有 `name, status, is_active` 基础上，追加 `enabled` 字段（`systemctl is-enabled` 的返回值：enabled/disabled/static）。

```json
{
  "name": "freeark-fault-cleanup.timer",
  "status": "inactive",
  "is_active": false,
  "enabled": "enabled"
}
```

**FR-02b（前端）**：`HomeView.vue` 的"系统运行状态"卡片，在展示服务状态时区分以下语义（OQ-3 决定展示粒度）：

| active_state | enabled | 语义解读 | 建议显示 |
|-------------|---------|---------|---------|
| active | enabled/static | 正常运行 | 绿色"运行中" |
| inactive | enabled | 正常待机（定时/idle） | 蓝色/灰色"待机" |
| inactive | disabled | 已停用（intentionally） | 灰色"已停用" |
| failed | * | 异常退出 | 红色"异常" |
| unknown | * | 无法查询 | 黄色"未知" |

**备注**：FR-02b 涉及前端改动，与现有仅加白名单的零前端改动方案不同；需用户决策 OQ-3。

---

### FR-03：服务管理页面完整展示（零改动复用）

**来源**：BG-01

**描述**：`ServicesView.vue`（`/api/services/list/`）已支持动态渲染，完成 FR-01 后自动包含新服务，**无需前端改动**。

服务管理列表已展示：服务名、active_state（含 enabled 标签）、启动/停止/重启/详情操作。

**前提条件**：FR-01 完成（白名单已追加）。

**验收标准**：在服务管理页面能看到 freeark-fault-consumer、freeark-condensation-consumer、freeark-inspection-agent（以及 OQ-1 决定的其他服务），并可对其执行 detail 操作（start/stop/restart 操作对 disabled 服务需额外 sudoers 配置，见架构设计）。

---

### FR-04（可选，依 OQ-3）：看板增加"服务类型"标注

**来源**：BG-02，用户可选决策

**描述**：若 OQ-3 决定在看板展示更多字段，可在服务名旁增加类型标注（常驻/定时/Agent），辅助运维理解状态语义。

**技术实现**：类型标注可在后端 MONITORED_SERVICES 改为列表中的字典结构，或在前端维护静态映射表，或完全不做（仅依赖 enabled 字段隐含的语义）。

---

## 3. 非功能需求

| 编号 | 类别 | 需求 | 说明 |
|------|------|------|------|
| NFR-01 | 性能 | `/api/dashboard/services/` 接口 P95 < 3s | 每增加一个服务多一次 systemctl 调用（~50ms），12-16个服务约 600-800ms，仍在 TTL=30s 缓存保护内 |
| NFR-02 | 安全 | 新增服务名通过现有白名单机制保护 | 不引入新的命令注入风险；服务名均已验证为合法字符 |
| NFR-03 | 可维护性 | 新增服务只需修改 MONITORED_SERVICES 一处 | 现有架构已满足，_MONITORED_SERVICES_SET 自动同步 |
| NFR-04 | 部署 | git pull + 重启 freeark-backend 生效 | 白名单改动在 views.py，重启 backend 即可；无 migration；无前端发版（FR-01、FR-03） |
| NFR-05 | 可观测 | 后端日志已有 service_management_action 审计日志 | 无需新增日志 |
| NFR-06 | 回滚 | 代码回滚：git revert + 重启 backend | 零风险回滚 |

---

## 4. 开放决策（用户须拍板，方可推进架构最终化）

> 以下5个问题当前均无明确用户决策，本文档已标注推荐方案，但需用户确认。

### OQ-1：服务范围 — 定时清理类服务和非 freeark-* 服务是否纳入？

**背景**：
- `freeark-fault-cleanup`（service + timer）、`freeark-condensation-cleanup`（service + timer）为定时 oneshot，由 timer 触发，日常 status=inactive。
- `openclaw-gateway.service` 为用户服务，不在 systemd 系统单元路径；`redis-server` 为 apt 服务，均非 freeark-* 命名空间。

**选项**：
- A（推荐）：仅纳入 freeark-* 系统服务；定时类纳入 .timer 单元（而非 .service 单元）；不纳入 openclaw-gateway 和 redis-server
- B：纳入所有 freeark-* 包含 .service 和 .timer；不纳入非 freeark-*
- C：仅纳入3个无争议服务（fault-consumer, condensation-consumer, inspection-agent），定时类暂不处理
- D：全部纳入，包含 openclaw-gateway 和 redis-server

**推荐**：方案 A。.timer 单元反映调度状态（active=等待触发，符合预期），比 .service 更有意义。非 freeark-* 服务不在 FreeArk 管理职责内，白名单应保持聚焦。

**✅ 决议（2026-06-16，用户拍板「全部 freeark-*」）**：纳入**所有** freeark-* 安装单元（不含非-freeark 的 openclaw-gateway / redis-server）。Pi `systemctl list-unit-files 'freeark-*'` 实测权威清单 = **16 个 .service + 4 个 .timer = 20 个单元**：

`.service`（16）：freeark-backend、freeark-mqtt-consumer、freeark-fault-consumer、freeark-condensation-consumer、freeark-screen-heartbeat、freeark-daily-usage、freeark-monthly-usage、freeark-plc-connection-monitor、freeark-dph-cleanup、freeark-task-scheduler、freeark-plc-cleanup、freeark-fault-cleanup、freeark-condensation-cleanup、freeark-netwatch、freeark-wifi-watchdog、freeark-inspection-agent
`.timer`（4）：freeark-fault-cleanup.timer、freeark-condensation-cleanup.timer、freeark-netwatch.timer、freeark-wifi-watchdog.timer

相对现有 9 项白名单：**新增 11 项**（fault-consumer、condensation-consumer、fault-cleanup、condensation-cleanup、netwatch、wifi-watchdog、inspection-agent 共 7 个 .service + 4 个 .timer）；**保留全部现有 9 项**。

**实测校正**：
- `freeark-plc-cleanup.service` **存在**（状态 disabled，故未出现在 `list-units --all`）——**并非失效项，保留**（早先"删除 plc-cleanup"的设想已撤销）。
- 新发现 `freeark-netwatch`、`freeark-wifi-watchdog`（.service+.timer，均 static/enabled）——skill 文档与原始白名单均遗漏，本次纳入。
- cleanup/netwatch/wifi-watchdog 的 `.service` 为 **static**（由各自 .timer 触发），`is-enabled` 返回 `static`；状态语义见 OQ-2 决议。

---

### OQ-2：状态展示语义 — 看板是否区分"正常待机"和"已停用"？

**背景**：当前看板仅显示"运行中"/"已停止"，无法区分 inspection-agent 的 disabled（管理员主动停用）和 fault-cleanup 的 inactive（正常等待触发）。

**选项**：
- A（推荐）：区分4种状态：运行中（active）/ 待机（inactive+enabled）/ 已停用（inactive+disabled）/ 异常（failed）
- B：仅区分"运行中"和"非运行中"（维持现状，不改前端）
- C：仅区分"运行中"和"异常"，inactive 均视为正常

**推荐**：方案 A。需要后端追加 enabled 字段（FR-02a，约3行代码）+ 前端修改状态显示逻辑（FR-02b，约20行代码）。改动量小，用户体验收益明显。

**✅ 决议（2026-06-16，用户拍板「四态语义」）**：看板「系统运行状态」区分 4 态。状态映射须正确处理 **static**（不可只看 enabled/disabled）：

| 显示态 | 颜色 | 判定（is-active / is-enabled） |
|--------|------|------------------------------|
| 运行中 | 绿 | is-active = `active`（含 .timer 的 active=waiting） |
| 待机 | 蓝灰 | is-active = `inactive` 且 is-enabled ∈ {`enabled`, `static`}（定时/timer 触发，正常） |
| 已停用 | 灰 | is-active = `inactive` 且 is-enabled = `disabled`（管理员主动停用，如 inspection-agent、plc-cleanup） |
| 异常 | 红 | is-active = `failed`（或 systemctl 调用异常 unknown） |

含 OQ-3/B（状态徽章旁显示 enabled 文字）。后端在 `/api/dashboard/services/` 每服务追加 `enabled` 字段（多一次 `systemctl is-enabled`）。

---

### OQ-3：看板展示粒度 — 是否展示 enabled 状态和服务类型？

**背景**：看板卡片当前只展示服务名 + 状态徽章，服务增多后可读性下降。

**选项**：
- A：仅状态徽章（使用 OQ-2/A 的4态语义），不展示 enabled/类型
- B（推荐）：状态徽章 + 在状态徽章旁显示 enabled 文字（enabled/disabled）
- C：增加服务类型标注（常驻/定时/Agent），需维护额外映射表

**推荐**：方案 B。enabled 字段后端已有（FR-02a 追加），前端只需在现有 badge 旁展示，无额外接口需求。

---

### OQ-4：操作权限 — 服务管理是否对 disabled 服务开放启停操作？

**背景**：`freeark-inspection-agent` 当前 disabled+stopped。用户是否希望在服务管理页面可以手动启动/启用它（需要 sudo systemctl enable + start）？

**选项**：
- A（推荐）：仅允许 start/stop/restart（不含 enable/disable），与现有其他服务一致；inspection-agent 可以手动 start（临时启动），但不 enable（不自动开机启动）
- B：增加 enable/disable 操作按钮；需扩展后端 action 逻辑和 sudoers 配置
- C：对 disabled 服务在服务管理页面显示只读状态，不展示操作按钮

**推荐**：方案 A。不引入新的 enable/disable 操作，保持与现有服务一致；运维如需持久化启用，通过 SSH 手动执行 systemctl enable。

---

### OQ-5：生产核实方式 — 是否在需求确认前先 SSH 实测 Pi 上的实际服务清单？

**背景**：本需求文档基于仓库 deployment/systemd/ 目录推断生产状态，实际 Pi 上可能有差异（如某些服务未实际安装 unit，或有额外未入仓库的 unit）。

**选项**：
- A（推荐）：用户在 Pi 上执行 `systemctl list-units 'freeark-*' --all` 并将输出提供给 PM，确认后再推进代码改动
- B：基于仓库推断，直接推进，部署时如有不一致再修正

**推荐**：方案 A。`人工复核命令`：

```bash
# 在生产 Pi（192.168.31.51）执行：
systemctl list-units 'freeark-*' --all --no-legend
# 同时检查 timer：
systemctl list-timers 'freeark-*' --all --no-legend
# 检查 inspection-agent 状态：
systemctl status freeark-inspection-agent
```

---

## 5. 排除范围

以下内容**明确不在本次 v1.2.0 范围内**：

| 排除项 | 原因 |
|-------|------|
| 新增服务状态持久化（数据库表） | 无持久化需求，实时查询 systemctl 已足够 |
| openclaw-gateway.service 纳入管理 | 非 freeark-* 命名空间，用户服务，不在 FreeArk 职责范围 |
| redis-server 纳入管理 | apt 服务，同上 |
| 服务告警（push 通知） | 超出本期范围 |
| 服务 enable/disable 操作（OQ-4/B） | 除非用户选择方案 B |
| 修改 api/langgraph_chat/ 或 agents/ | 与本需求无关 |
| 新增数据库 migration | 白名单在 views.py 内存中维护，无 DB 变更 |

---

## 6. 约束与假设

| 约束/假设 | 说明 |
|---------|------|
| 禁 Docker，物理 Pi5 | systemd 管服务，无容器化 |
| 部署一律 git pull | 白名单改动随 git pull + 重启 backend 生效，无需 pscp |
| 后端 sudoers 已配置 | 现有服务管理的 start/stop/restart 已通过 sudo systemctl，新加服务同样适用 |
| 前端零改动（FR-01/03） | 仅修改白名单时，前端 v-for 动态渲染自动包含新服务 |
| 前端有改动（FR-02b） | 若 OQ-2 选方案 A，需修改 HomeView.vue 的状态显示逻辑 |
| 实测为准 | 服务清单以 Pi 上 systemctl 实测为权威，本文档基于仓库推断 |
