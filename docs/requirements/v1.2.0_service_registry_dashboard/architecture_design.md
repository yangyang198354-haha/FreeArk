# 架构设计文档 — v1.2.0 服务注册表与看板完整化

**文档编号**: ARCH-SRD-001
**版本**: 1.0.0
**状态**: DRAFT（待用户确认 OQ-1~OQ-5 后升级为 APPROVED）
**创建日期**: 2026-06-16
**作者**: system-architect (via pm-orchestrator)
**关联需求**: REQ-SPEC-SRD-001 v1.0.0
**关联用户故事**: US-SRD-001 v1.0.0

---

## 1. 架构决策摘要

本特性**不引入任何新的架构层次或组件**。所有实现通过复用现有白名单机制完成，与 v0.5.2（dph-cleanup）采用完全相同的模式。

| 维度 | 决策 | 理由 |
|------|------|------|
| 服务清单来源 | 硬编码白名单（MONITORED_SERVICES 列表追加） | 见 ADR-001 |
| 状态取数方式 | 复用现有 `systemctl is-active` + `is-enabled`（已有） | 见 ADR-002 |
| 后端改动 | views.py: MONITORED_SERVICES 追加服务名（必须）；dashboard_services 追加 enabled 字段（OQ-2/A） | 最小改动 |
| 前端改动 | 服务管理（ServicesView.vue）：零改动；看板（HomeView.vue）：状态语义修正（OQ-2/A） | 依 OQ-2 决策 |
| 数据存储 | 无新表、无 migration | 白名单在 views.py 内存维护 |
| 部署 | git pull + 重启 freeark-backend | 无 migration，无前端发版（仅 FR-01/03） |

---

## 2. 现有架构现状分析

### 2.1 完整集成点全景图

```
┌──────────────────────────────────────────────────────────────────────┐
│                       生产服务器（树莓派 Pi5）                         │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                         systemd                              │    │
│  │                                                              │    │
│  │  [常驻-已在白名单]                                            │    │
│  │  freeark-backend.service          ← active (running)         │    │
│  │  freeark-mqtt-consumer.service    ← active (running)         │    │
│  │  freeark-screen-heartbeat.service ← active (running)         │    │
│  │  freeark-daily-usage.service      ← active (running)         │    │
│  │  freeark-monthly-usage.service    ← active (running)         │    │
│  │  freeark-plc-cleanup.service      ← 内置cron,常驻            │    │
│  │  freeark-dph-cleanup.service      ← 内置cron,常驻            │    │
│  │  freeark-plc-connection-monitor   ← active (running)         │    │
│  │  freeark-task-scheduler.service   ← active (running)         │    │
│  │                                                              │    │
│  │  [常驻-漏网，本次追加]                                         │    │
│  │  freeark-fault-consumer.service      ← active,已运行v0.6.0   │    │
│  │  freeark-condensation-consumer.service ← active,已运行v0.7.0 │    │
│  │  freeark-inspection-agent.service    ← disabled+stopped v1.1 │    │
│  │                                                              │    │
│  │  [定时-漏网，OQ-1决策是否追加]                                 │    │
│  │  freeark-fault-cleanup.timer      ← active(等待触发)          │    │
│  │  freeark-fault-cleanup.service    ← inactive(oneshot)        │    │
│  │  freeark-condensation-cleanup.timer ← active(等待触发)        │    │
│  │  freeark-condensation-cleanup.service ← inactive(oneshot)    │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                              │                                        │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │              Django Backend (waitress)                        │    │
│  │                                                              │    │
│  │  MONITORED_SERVICES = [         ← api/views.py:1143          │    │
│  │      'freeark-backend',         ← 现有9个                     │    │
│  │      ...                                                      │    │
│  │      'freeark-fault-consumer',  ← v1.2.0 新增（必须）         │    │
│  │      'freeark-condensation-consumer', ← v1.2.0 新增（必须）   │    │
│  │      'freeark-inspection-agent', ← v1.2.0 新增（必须）        │    │
│  │      'freeark-fault-cleanup.timer',  ← OQ-1/A 方案           │    │
│  │      'freeark-condensation-cleanup.timer', ← OQ-1/A          │    │
│  │  ]                                                            │    │
│  │  _MONITORED_SERVICES_SET = set(MONITORED_SERVICES)  ← 自动同步│    │
│  │                                                              │    │
│  │  GET /api/dashboard/services/                                │    │
│  │    → 遍历白名单，systemctl is-active 每个服务                  │    │
│  │    → 返回 [{name, status, is_active, enabled(新)}]           │    │
│  │    → @cache_dashboard(ttl=30)  ← 现有30s缓存保护             │    │
│  │                                                              │    │
│  │  GET /api/services/list/                                     │    │
│  │    → 遍历白名单，systemctl is-active + is-enabled             │    │
│  │    → 返回 [{name, active_state, is_active, enabled}]         │    │
│  │                                                              │    │
│  │  GET /api/services/<n>/detail/  ← 白名单校验                  │    │
│  │  POST /api/services/<n>/action/ ← 白名单校验 + sudo           │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                              │                                        │
└──────────────────────────────┼────────────────────────────────────────┘
                               │ HTTP/JSON
┌──────────────────────────────┼────────────────────────────────────────┐
│                     前端 Vue 3 (nginx)                                 │
│                              │                                        │
│  HomeView.vue:fetchServices()                                         │
│    → GET /api/dashboard/services/                                     │
│    → services.value = res.data  ← 动态渲染，无硬编码服务名              │
│    → [OQ-2/A] 4态状态显示逻辑（约20行改动）                             │
│                                                                       │
│  ServicesView.vue:fetchList()                                         │
│    → GET /api/services/list/                                          │
│    → serviceList.value = resp.data  ← 动态渲染（零改动）               │
└───────────────────────────────────────────────────────────────────────┘
```

### 2.2 systemctl 调用现状

现有 `_get_service_status(name)` 已调用 `systemctl is-active`，`service_management_list()` 已调用 `systemctl is-enabled`，返回 enabled/disabled/static 字符串。

**关键发现**：`/api/dashboard/services/` 视图当前**未调用** `is-enabled`，只返回 `status` 和 `is_active`。`/api/services/list/` 已返回 `enabled` 字段。

因此，FR-02a 的修改点仅为 `dashboard_services` 视图（`api/views.py:1231`），追加一次 `is-enabled` 调用并在返回体中加入 `enabled` 字段。

---

## 3. ADR（架构决策记录）

### ADR-001：服务清单来源——复用硬编码白名单，不引入动态查询

**背景**：需要将新服务纳入监控，有两种主流方案：

**方案 A（选定）**：将新服务名追加到 `MONITORED_SERVICES` 列表（硬编码白名单）。

**方案 B（否决）**：动态查询 `systemctl list-units 'freeark-*'`，自动发现所有 freeark-* 服务，无需手动维护白名单。

**方案 A 优势**：
- 安全性：白名单是防止命令注入的核心控制，动态查询引入 shell 通配符展开，增加攻击面
- 可控性：运维人员明确知道哪些服务受监控，避免意外纳入测试/临时服务
- 实现简单：1-5行代码改动，无新函数，无新逻辑
- 与现有架构完全一致（v0.5.2、v0.6.0、v0.7.0 均用此方案）

**方案 B 劣势**：
- 安全审计复杂：动态 shell 通配符展开需要额外转义和输出解析验证
- 需要新的解析逻辑（`systemctl list-units` 输出格式复杂，跨版本有差异）
- 引入"未知服务自动纳入"风险：新部署的测试服务可能自动出现在 UI
- 现有架构没有此模式的先例，改动量大

**决策**：方案 A。白名单追加即可满足本期需求，与项目一贯的安全设计原则一致。

---

### ADR-002：状态取数——复用现有 systemctl subprocess 调用，追加 enabled 字段

**背景**：看板状态语义问题（inactive 不等于故障），需要引入 `enabled` 字段。

**方案 A（选定）**：在 `/api/dashboard/services/` 返回体中追加 `enabled` 字段（每服务多一次 `systemctl is-enabled` subprocess 调用），前端用 enabled 字段参与状态语义判断。

**方案 B（否决）**：在后端直接推断语义（如 `"display_state": "standby" | "running" | "disabled" | "failed"`），前端仅展示后端推断结果。

**方案 C（否决）**：前端维护静态服务类型映射表（`{service: "timer"}`），不修改后端。

**方案 A 优势**：
- `is-enabled` 调用已在 `service_management_list()` 中存在，模式成熟
- 原始数据（enabled 字符串）比后端推断更灵活，前端可自行组合逻辑
- 后端不承担 UI 语义职责，关注点分离

**方案 A 性能影响**：每增加一个 is-enabled 调用约 +50ms。当前白名单 9 个，若增至 14 个，总计约 700ms（含 is-active + is-enabled 各一次）。`@cache_dashboard(ttl=30)` 缓存保护，正常用户交互下无性能问题。

**决策**：方案 A。最小改动，与现有模式一致。

---

### ADR-003：前端状态展示——4态语义显示逻辑

**背景**（依赖 OQ-2/A 用户决策）：

**现有逻辑**（HomeView.vue:295）：
```javascript
svc.is_active ? '运行中' : '已停止'
// badge class: svc.is_active ? 'on' : 'off'
```

**目标逻辑**（FR-02b，OQ-2/A）：

```javascript
// 状态语义函数（约15行）
function svcDisplayState(svc) {
  if (svc.status === 'active') return { label: '运行中', cls: 'on' }
  if (svc.status === 'failed') return { label: '异常',   cls: 'err' }
  if (svc.status === 'inactive') {
    if (svc.enabled === 'disabled') return { label: '已停用', cls: 'disabled' }
    return { label: '待机', cls: 'standby' }  // enabled/static + inactive = 正常待机
  }
  return { label: '未知', cls: 'unknown' }
}
```

**改动范围**：
- HomeView.vue：新增 `svcDisplayState` 函数（约15行）；修改 template 中 badge class 绑定（约3行）；新增 CSS class（err/disabled/standby/unknown，约20行）
- 不改动 ServicesView.vue（已有 el-tag 动态类型逻辑，语义已足够清晰）
- 不改动后端接口路由

**决策**：方案已确定，等待 OQ-2 用户拍板后执行。

---

## 4. 改动清单（Diff 边界）

### 4.1 必须改动（无争议，不依赖 OQ）

**文件**：`FreeArkWeb/backend/freearkweb/api/views.py`
**改动位置**：第 1143-1153 行（MONITORED_SERVICES 列表）
**改动内容**：追加3行

```python
# 改动前（当前）：
MONITORED_SERVICES = [
    'freeark-backend',
    'freeark-mqtt-consumer',
    'freeark-screen-heartbeat',
    'freeark-daily-usage',
    'freeark-monthly-usage',
    'freeark-plc-cleanup',
    'freeark-dph-cleanup',
    'freeark-plc-connection-monitor',
    'freeark-task-scheduler',
]

# 改动后（v1.2.0，必须部分）：
MONITORED_SERVICES = [
    'freeark-backend',
    'freeark-mqtt-consumer',
    'freeark-screen-heartbeat',
    'freeark-daily-usage',
    'freeark-monthly-usage',
    'freeark-plc-cleanup',
    'freeark-dph-cleanup',
    'freeark-plc-connection-monitor',
    'freeark-task-scheduler',
    # v1.2.0: 补入漏网的生产关键服务
    'freeark-fault-consumer',
    'freeark-condensation-consumer',
    'freeark-inspection-agent',
]
```

**生效条件**：重启 freeark-backend.service
**风险**：无。`_MONITORED_SERVICES_SET` 自动同步，新加服务名已为合法 systemd 服务名格式。

---

### 4.2 OQ-1/A 决策后追加（.timer 单元纳入）

**文件**：同上
**改动内容**：在上述列表末尾再追加2行

```python
    # v1.2.0 OQ-1/A: 定时任务 timer 单元（active=调度运行中）
    'freeark-fault-cleanup.timer',
    'freeark-condensation-cleanup.timer',
```

**说明**：`.timer` 后缀的单元名对 `systemctl is-active` 和 `systemctl is-enabled` 完全合法。timer 处于调度待机时，`is-active` 返回 `active`，符合语义。

**人工复核**：在 Pi 上执行 `systemctl is-active freeark-fault-cleanup.timer`，预期返回 `active`。

---

### 4.3 OQ-2/A 决策后修改（后端 enabled 字段）

**文件**：`FreeArkWeb/backend/freearkweb/api/views.py`
**改动位置**：`dashboard_services` 函数（约第 1231-1250 行）
**改动内容**：遍历时追加 `systemctl is-enabled` 调用，返回 enabled 字段

```python
# 改动前：
def dashboard_services(request):
    services = []
    for name in MONITORED_SERVICES:
        svc_status = _get_service_status(name)
        services.append({
            'name': name,
            'status': svc_status,
            'is_active': svc_status == 'active',
        })
    return Response({'success': True, 'data': services})

# 改动后：
def dashboard_services(request):
    services = []
    for name in MONITORED_SERVICES:
        svc_status = _get_service_status(name)
        try:
            enabled_result = subprocess.run(
                ['systemctl', 'is-enabled', name],
                capture_output=True, text=True, timeout=5,
            )
            enabled_str = enabled_result.stdout.strip() or 'unknown'
        except Exception:
            enabled_str = 'unknown'
        services.append({
            'name': name,
            'status': svc_status,
            'is_active': svc_status == 'active',
            'enabled': enabled_str,  # 新增字段
        })
    return Response({'success': True, 'data': services})
```

**注意**：此改动会使看板接口每次调用多执行 N 次（N=白名单总数）`systemctl is-enabled`。由于 `@cache_dashboard(ttl=30)` 的保护，实际 subprocess 调用频率为每 30 秒最多一次，无性能问题。

---

### 4.4 OQ-2/A + OQ-3 决策后修改（前端4态显示）

**文件**：`FreeArkWeb/frontend/src/views/HomeView.vue`
**改动位置**：
1. `<script>` 的 `setup()` 中，`fetchServices()` 函数之后，新增 `svcDisplayState()` 函数（约15行）
2. `<template>` 第 290-300 行，将 badge class 绑定从 `svc.is_active ? 'on' : 'off'` 改为调用 `svcDisplayState(svc).cls`，文字从 `svc.is_active ? '运行中' : '已停止'` 改为调用 `svcDisplayState(svc).label`
3. `<style>` 新增 `.badge.err`、`.badge.disabled`、`.badge.standby`、`.badge.unknown` 的 CSS 样式（约20行）

**改动量**：约50行（新增40行，修改10行），风险极低。

**改动前后对比（template 核心部分）**：

```html
<!-- 改动前 -->
<span :class="['badge', svc.is_active ? 'on' : 'off']" class="status-badge">
  <span class="bd"></span>
  {{ svc.is_active ? '运行中' : '已停止' }}
</span>

<!-- 改动后 -->
<span :class="['badge', svcDisplayState(svc).cls]" class="status-badge">
  <span class="bd"></span>
  {{ svcDisplayState(svc).label }}
</span>
```

**改动前后对比（script 新增函数）**：

```javascript
// 新增函数（在 return 语句之前）
function svcDisplayState(svc) {
  const s = svc.status || 'unknown'
  const e = svc.enabled || 'unknown'
  if (s === 'active')   return { label: '运行中', cls: 'on' }
  if (s === 'failed')   return { label: '异常',   cls: 'err' }
  if (s === 'inactive') {
    if (e === 'disabled') return { label: '已停用', cls: 'disabled' }
    return { label: '待机', cls: 'standby' }
  }
  return { label: '未知', cls: 'unknown' }
}
// 同时在 return { ... } 中暴露 svcDisplayState
```

**向后兼容性**：新函数对现有9个服务的显示逻辑：
- active + enabled → '运行中'（on class）：与现有相同
- inactive + enabled → '待机'（standby class）：原显示"已停止"，语义更准确
- 无 failed 状态的现有服务不受影响

---

## 5. 数据流

```
[看板页面加载 / 刷新]
前端 fetchServices()
  → GET /api/dashboard/services/
  → @cache_dashboard(ttl=30): 若30s内已调用，直接返回缓存

[缓存未命中时]
  → 遍历 MONITORED_SERVICES（12-16个）
    → 每个服务: subprocess.run(['systemctl', 'is-active', name], timeout=5)
    → [OQ-2/A] 每个服务: subprocess.run(['systemctl', 'is-enabled', name], timeout=5)
  → 返回 [{name, status, is_active, enabled?}, ...]

[前端渲染]
  → services.value = res.data
  → v-for: 每个服务渲染一个 status-item
  → [OQ-2/A] svcDisplayState(svc) 决定徽章文字和颜色

[服务管理页面加载]
前端 fetchList()
  → GET /api/services/list/
  → 遍历 MONITORED_SERVICES
    → 每个服务: is-active + is-enabled (已有，无需改动)
  → 前端 serviceList.value = resp.data
  → el-table v-for 动态渲染（已有，无需改动）

[服务管理操作]
前端 handleAction(row, 'start'/'stop'/'restart')
  → POST /api/services/{name}/action/
  → 后端白名单校验（_MONITORED_SERVICES_SET）
  → subprocess.run(['sudo', 'systemctl', action, name], timeout=30)
  → 返回 {success, new_status}
```

---

## 6. 非功能性约束（架构层面）

| 约束 | 说明 |
|------|------|
| 物理机，无 Docker | 全部服务均为 systemd unit，无容器化 |
| 部署方式 | git pull + 重启 freeark-backend（白名单改动）；若有前端改动需 npm build + nginx reload |
| 安全 | 白名单双重保护（list + set）；新加服务名均为合法字符，不含 shell 特殊字符；.timer 后缀合法 |
| 性能 | 看板接口 TTL=30s 缓存保护；每次调用时间约 50ms×N，N=14 约 700ms，在缓存间隔内可接受 |
| 回滚 | 代码回滚：`git revert` + 重启 backend；零风险，MONITORED_SERVICES 是单纯的 Python 列表 |
| 兼容性 | 新加的 enabled 字段为追加（不破坏现有调用方）；前端 svcDisplayState 对现有服务的显示语义兼容（active 服务仍显示"运行中"） |
| 不触碰 | api/langgraph_chat/、agents/、migrations/（无 DB 变更） |

---

## 7. 部署步骤（供后续 DevOps 阶段参考，本期不执行）

以下步骤仅供记录，**部署须用户明确 CONFIRM**，当前阶段不执行。

```bash
# 1. 拉取代码（在 Pi 上执行）
cd /home/yangyang/Freeark/FreeArk && git pull

# 2. 重启 backend（使白名单改动生效）
sudo systemctl restart freeark-backend

# 3. [若有前端改动 OQ-2/A] 构建前端
cd FreeArkWeb/frontend && npm run build
# （nginx 自动 serve 新 dist，无需重启 nginx）

# 4. 验证
# 4a. 后端接口
curl -s 'http://localhost:8000/api/dashboard/services/' \
  -H 'Cookie: ...' | python3 -m json.tool | grep -E 'name|status|enabled'
# 预期：包含 freeark-fault-consumer, freeark-condensation-consumer, freeark-inspection-agent

# 4b. 看板页面
# 打开浏览器，进入系统看板，确认「系统运行状态」卡片服务数量 >= 12

# 4c. 服务管理
# 进入服务管理，确认新服务在列表中，点击详情，确认弹窗正常
```

**人工复核检查单（部署后由用户执行）**：

| 检查项 | 方法 | 预期结果 |
|-------|------|---------|
| 白名单生效 | `curl .../api/dashboard/services/` 检查 data 数组 | 包含12+个服务 |
| fault-consumer 可见 | 服务管理页面截图 | freeark-fault-consumer 在列表中，active_state=active |
| condensation-consumer 可见 | 同上 | freeark-condensation-consumer 在列表中，active_state=active |
| inspection-agent 可见 | 同上 | freeark-inspection-agent 在列表中，enabled=disabled |
| 看板无回归 | 系统看板截图 | 原有9个服务仍正常展示 |
| [OQ-2/A] timer 不显示红色 | 看板截图 | freeark-fault-cleanup.timer 显示绿色或蓝色 |
| [OQ-2/A] inspection 显示灰色 | 看板截图 | freeark-inspection-agent 显示"已停用"灰色 |

---

## 8. 与现有架构的差异

| 对比维度 | v0.5.2（参照） | v1.2.0（本次） |
|--------|-------------|-------------|
| MONITORED_SERVICES 追加行数 | 1行 | 3-5行（按OQ-1决策） |
| 后端接口改动 | 无 | dashboard_services 追加 enabled 字段（OQ-2/A，约10行） |
| 前端改动 | 零 | 仅 HomeView.vue 状态语义（OQ-2/A，约50行） |
| systemd unit 需安装 | 1个 | 0个（所有 unit 已在 Pi 上安装，仅白名单漏掉） |
| 状态语义处理 | 不涉及 | 新增4态展示逻辑（解决定时服务误报） |

**关键差异说明**：与 v0.5.2 不同，本次不需要在 Pi 上安装新 unit（fault-consumer、condensation-consumer、inspection-agent 的 unit 均已安装）。本次唯一的生产服务器操作是 `git pull + systemctl restart freeark-backend`。

---

## 9. 开放决策对架构的影响矩阵

| OQ | 用户选择 | 对架构的影响 | 代码改动量 |
|----|---------|------------|---------|
| OQ-1/A（推荐） | 纳入5个服务（含2个.timer） | MONITORED_SERVICES +5行 | 5行 |
| OQ-1/C（最小） | 仅纳入3个无争议服务 | MONITORED_SERVICES +3行 | 3行 |
| OQ-2/A（推荐） | 4态展示 | 后端+10行，前端+50行 | 60行 |
| OQ-2/B（现状） | 不改前端 | 无额外改动 | 0行 |
| OQ-3/B（推荐） | 看板展示 enabled 文字 | 已包含在 OQ-2/A 的前端改动中 | 0额外行 |
| OQ-4/A（推荐） | 不加 enable/disable 按钮 | 无额外改动 | 0行 |
| OQ-5/A（推荐） | 先实测 Pi 再推进 | 可能调整服务清单 | 视实测结果 |

**最保守路径（OQ-1/C + OQ-2/B）**：仅改 views.py 3行，重启 backend，零前端改动。看板状态语义未修正，但3个关键服务已可见。

**推荐路径（OQ-1/A + OQ-2/A）**：改 views.py 约20行，改 HomeView.vue 约50行，彻底解决状态误报问题。
