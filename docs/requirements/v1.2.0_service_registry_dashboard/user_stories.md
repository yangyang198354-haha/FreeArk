# 用户故事清单 — v1.2.0 服务注册表与看板完整化

**文档编号**: US-SRD-001
**关联需求**: REQ-SPEC-SRD-001 v1.0.0
**版本**: 1.0.0
**状态**: DRAFT
**创建日期**: 2026-06-16
**作者**: requirement-analyst (via pm-orchestrator)

---

## 用户角色定义

| 角色 | 描述 |
|------|------|
| 运维人员 | 通过 FreeArk Web 界面监控和管理系统服务 |
| 系统管理员 | 同运维人员，同时有 SSH 权限可做深度操作 |

---

## 用户故事总览

| 故事编号 | 优先级 | 依赖 OQ | 说明 |
|---------|-------|--------|------|
| US-SRD-01 | P0（必须） | 无 | 服务管理页面列出漏网的常驻服务 |
| US-SRD-02 | P0（必须） | OQ-1 | 系统看板展示全部 freeark-* 服务 |
| US-SRD-03 | P0（必须） | 无 | 新服务在服务管理页面可查看详情 |
| US-SRD-04 | P0（必须） | 无 | inspection-agent 可见且状态正确 |
| US-SRD-05 | P1（重要） | OQ-2/A | 看板区分"正常待机"和"已停用" |
| US-SRD-06 | P1（重要） | OQ-2/A | 定时服务不被误报为故障 |
| US-SRD-07 | P2（可选） | OQ-1/A | .timer 单元状态在看板可见 |
| US-SRD-08 | P2（可选） | OQ-4/A | 对 disabled 服务执行手动启动 |

---

## 详细用户故事

### US-SRD-01：服务管理页面列出漏网的常驻服务

**角色**：运维人员
**故事**：作为运维人员，我希望在「服务管理」页面能看到 freeark-fault-consumer 和 freeark-condensation-consumer，以便在故障排查时能确认这两个关键消费者的运行状态并在必要时重启。

**背景**：freeark-fault-consumer（故障 MQTT 消费者）和 freeark-condensation-consumer（结露预警消费者）是生产关键服务，已运行于 Pi，但当前不在 MONITORED_SERVICES 白名单，服务管理页面和看板均不可见，运维无法通过 UI 管控。

**Given**：运维人员已登录 FreeArk Web，进入「服务管理」页面；`api/views.py` 的 `MONITORED_SERVICES` 已追加 `freeark-fault-consumer` 和 `freeark-condensation-consumer`
**When**：页面加载完成（或点击「刷新」）
**Then**：
- 服务列表中出现 `freeark-fault-consumer` 行，显示其 active_state、enabled 状态
- 服务列表中出现 `freeark-condensation-consumer` 行，显示其 active_state、enabled 状态
- 两个服务的「详情」、「启动」、「停止」、「重启」按钮可点击
- 响应时间在可接受范围内（见 NFR-01）

**复核方式（人工）**：
1. 在 Pi 上确认服务运行中：`systemctl status freeark-fault-consumer freeark-condensation-consumer`
2. 在 FreeArk Web 服务管理页面截图，确认两服务均在列表中
3. 点击「详情」，确认弹窗显示 active_state=active

---

### US-SRD-02：系统看板「系统运行状态」展示全部 freeark-* 服务

**角色**：运维人员
**故事**：作为运维人员，我希望在系统看板的「系统运行状态」卡片中，看到所有 freeark-* 系统服务的状态，而不是只有白名单里的9个，以便一眼掌握全系统服务健康状况。

**Given**：运维人员已登录，进入系统看板；MONITORED_SERVICES 已更新为包含全部 freeark-* 服务（按 OQ-1 决策）
**When**：看板页面加载完成（或点击「系统运行状态」卡片的「刷新」按钮）
**Then**：
- 「系统运行状态」卡片展示的服务数量 >= 12（原9 + 至少3个新增）
- freeark-fault-consumer 出现在卡片中，状态显示正确
- freeark-condensation-consumer 出现在卡片中，状态显示正确
- freeark-inspection-agent 出现在卡片中，状态显示正确（当前 disabled+stopped）
- 所有原有9个服务仍然正常展示（无回归）

**复核方式（人工）**：
1. 打开浏览器 DevTools，观察 `/api/dashboard/services/` 返回的 data 数组长度
2. 确认响应中包含新增服务的条目，且 status 字段值合理（active/inactive/failed）

---

### US-SRD-03：新增服务在服务管理页面可查看详情

**角色**：运维人员
**故事**：作为运维人员，当我在服务管理页面点击新增服务（如 freeark-fault-consumer）的「详情」按钮时，能看到该服务的 active_state、sub_state、PID、内存占用和 systemctl status 原始输出，以便深度诊断。

**Given**：US-SRD-01 前提满足；freeark-fault-consumer 已在列表中显示
**When**：点击 freeark-fault-consumer 行的「详情」按钮
**Then**：
- 弹出详情对话框，标题为「服务详情 — freeark-fault-consumer」
- 显示 active_state（如 active）
- 显示 sub_state（如 running）
- 显示 PID（如果服务运行中）
- 显示内存占用（如 12.0 M）
- 显示 systemctl status 原始输出（不超过 4096 字节）
- API 响应来自 `GET /api/services/freeark-fault-consumer/detail/`，返回 HTTP 200

**复核方式（人工）**：
1. 在 Pi 上执行 `systemctl status freeark-fault-consumer --no-pager`，记录 PID 和内存
2. 在 Web 详情弹窗中对比 PID 和内存值与上述命令输出一致
3. 确认原始输出区域显示了 systemctl 输出内容

---

### US-SRD-04：freeark-inspection-agent 在服务管理和看板中可见且状态正确

**角色**：运维人员
**故事**：作为运维人员，我希望看到 freeark-inspection-agent 出现在服务管理和看板中，并且其状态显示为"已停用"或"disabled"（而非"故障"），以便我知道它是主动停用状态、需要用户决策后才能启用。

**背景**：inspection-agent 当前 unit 已装于 /etc/systemd/system/，但 disabled+stopped，是有意为之的待启状态。不应被误判为服务故障。

**Given**：MONITORED_SERVICES 已追加 `freeark-inspection-agent`；OQ-2 决策已做（推荐方案 A：区分4态）
**When**：
- 进入服务管理页面，查看服务列表
- 进入系统看板，查看「系统运行状态」
**Then**：
- 服务管理列表：freeark-inspection-agent 行的 active_state 显示 `inactive`，enabled 显示 `disabled`，字体颜色或标签颜色为灰色（而非红色告警）
- 系统看板（OQ-2/A 方案）：freeark-inspection-agent 状态显示为"已停用"（灰色徽章），而非"已停止"或"异常"
- 如果 OQ-2 维持方案 B（不改前端），则服务管理列表 enabled 列显示 `disabled` 即满足需求（看板仍显示"已停止"，属于已知限制）

**复核方式（人工）**：
1. Pi 上执行：`systemctl is-active freeark-inspection-agent`（预期返回 `inactive`）；`systemctl is-enabled freeark-inspection-agent`（预期返回 `disabled`）
2. 在服务管理页面核对 enabled 列显示值
3. 在看板核对状态徽章颜色和文字

---

### US-SRD-05：看板区分"正常待机（inactive+enabled）"和"已停用（disabled）"

**角色**：运维人员
**故事**：作为运维人员，我希望看板上的定时服务（如 freeark-fault-cleanup.timer）显示为"待机"（蓝色/灰色），而 freeark-inspection-agent 显示为"已停用"（不同颜色），以避免误以为这些服务都发生了故障。

**依赖**：OQ-2 用户决策方案 A；OQ-1 用户决策纳入 .timer 单元

**Given**：FR-02a 已实现（/api/dashboard/services/ 追加 enabled 字段）；FR-02b 已实现（HomeView.vue 使用4态状态显示逻辑）
**When**：系统看板「系统运行状态」加载完成，且当前不在 cleanup 的执行时段（03:00-03:30 以外）
**Then**：
- freeark-fault-cleanup.timer：status=active（timer 等待触发为 active），显示绿色"运行中"
- freeark-condensation-cleanup.timer：同上
- freeark-inspection-agent：status=inactive + enabled=disabled，显示灰色"已停用"
- freeark-fault-consumer：status=active + enabled=enabled，显示绿色"运行中"
- 无服务因正常的 inactive 状态而显示红色"异常"

**复核方式（人工）**：
1. Pi 上执行：`systemctl is-active freeark-fault-cleanup.timer`（预期 `active`）；`systemctl is-active freeark-inspection-agent`（预期 `inactive`）；`systemctl is-enabled freeark-inspection-agent`（预期 `disabled`）
2. 在看板上对比各服务的徽章颜色与上述 systemctl 结果是否语义一致
3. 确认没有任何 timer 服务显示红色

---

### US-SRD-06：定时 cleanup 服务在执行期间状态正确展示

**角色**：运维人员
**故事**：作为运维人员，我希望在凌晨 03:00-03:30 cleanup 服务正在执行时，看板显示为"运行中"；执行完毕后恢复"待机"；如果执行失败，显示"异常"——以此区分正常生命周期和真实故障。

**依赖**：OQ-2 用户决策方案 A

**Given**：FR-02a 和 FR-02b 已实现
**When**：看板在 cleanup 执行期间（约 03:00）刷新
**Then**：
- freeark-dph-cleanup：active_state=active，显示绿色"运行中"（此时进程正在运行）
- freeark-fault-cleanup（oneshot）：active_state=active，显示绿色"运行中"
**When**：cleanup 正常完成后，看板刷新（缓存 TTL 30s）
**Then**：
- active_state 回到 inactive，enabled=enabled，显示蓝色"待机"
**When**：cleanup 因故退出码非零（systemd 记录为 failed）
**Then**：
- active_state=failed，显示红色"异常"

**复核方式（人工）**：此故事的"执行期间"状态难以实时捕获，可通过以下方式验证失败态：
1. 临时修改一个 cleanup 服务使其立即失败（如错误的 ExecStart 参数），`systemctl start` 后检查 is-active 返回 `failed`
2. 在看板刷新后确认该服务显示红色"异常"
3. 恢复原 ExecStart 并执行 `systemctl reset-failed`

---

### US-SRD-07：.timer 单元状态在看板可见（OQ-1/A 依赖）

**角色**：运维人员
**故事**：作为运维人员，我希望在看板能直接看到 freeark-fault-cleanup.timer 和 freeark-condensation-cleanup.timer 的状态，以确认定时任务的调度是否正常运行（timer 处于 active 状态意味着调度正在运行）。

**依赖**：OQ-1 用户选择方案 A（纳入 .timer 单元）

**Given**：MONITORED_SERVICES 已追加 `freeark-fault-cleanup.timer` 和 `freeark-condensation-cleanup.timer`
**When**：看板加载
**Then**：
- 两个 .timer 服务在看板可见，status=active（等待触发中），显示为正常状态
- 服务名 `freeark-fault-cleanup.timer` 正确显示（含 .timer 后缀）
- 在非触发时段，两个 timer 的 is_active=true（timer 单元 active 意味着在等待下次触发）

**复核方式（人工）**：
1. Pi 上执行：`systemctl is-active freeark-fault-cleanup.timer`（预期返回 `active`）
2. 在看板确认 `freeark-fault-cleanup.timer` 显示绿色"运行中"
3. 执行 `systemctl list-timers freeark-fault-cleanup.timer`，确认 NEXT 时间为明天凌晨 03:30

---

### US-SRD-08：对 disabled 的 inspection-agent 执行手动 start（OQ-4/A）

**角色**：系统管理员
**故事**：作为系统管理员，我希望在服务管理页面能对 freeark-inspection-agent 执行「启动」操作（临时启动，不持久化 enable），以便在用户决策前做验证测试，而不需要每次都 SSH 到 Pi 上手动执行 systemctl start。

**依赖**：OQ-4 用户选择方案 A；FR-01 完成

**Given**：freeark-inspection-agent 在服务管理列表中可见；当前状态 disabled+inactive
**When**：点击 freeark-inspection-agent 行的「启动」按钮，确认弹窗
**Then**：
- 后端执行 `sudo systemctl start freeark-inspection-agent`
- 若 sudoers 已配置且服务正常启动，返回 `{success: true, new_status: "active"}`
- 列表中 freeark-inspection-agent 的 active_state 刷新为 active
- enabled 仍为 disabled（start 操作不改变 enable 状态）
- 页面显示操作成功提示

**反向测试（服务启动失败）**：
**Given**：inspection-agent 依赖的 .env 变量未配置（如 DEEPSEEK_API_KEY 未设置）
**When**：点击「启动」
**Then**：
- 后端返回 HTTP 500，error 字段包含 systemctl 的错误输出
- 页面显示错误提示，不挂起

**复核方式（人工）**：
1. 在 Pi 上确认 sudoers 已配置 `yangyang ALL=(ALL) NOPASSWD: /bin/systemctl start freeark-inspection-agent`（或通配符）
2. 在 Web 上执行启动操作后，立即 SSH 到 Pi 执行 `systemctl status freeark-inspection-agent`，确认状态为 active
3. 约 30 秒后若服务因 .env 缺失而失败，`systemctl status` 应显示 failed，Web 看板在下次刷新后应显示"异常"

---

## 验收条件汇总表（门控评审用）

| 故事 | 验收标准摘要 | 涉及文件 | 测试方式 |
|-----|------------|---------|---------|
| US-SRD-01 | 服务管理列表含 fault-consumer, condensation-consumer | views.py:MONITORED_SERVICES | 人工 + 单元测试（mock systemctl） |
| US-SRD-02 | 看板 /api/dashboard/services/ 返回 >=12 个服务 | views.py:MONITORED_SERVICES | 人工 DevTools 检查 |
| US-SRD-03 | /api/services/freeark-fault-consumer/detail/ 返回 200 | views.py:service_management_detail | 单元测试（mock subprocess） |
| US-SRD-04 | inspection-agent 在列表中 enabled=disabled，颜色非红 | views.py + HomeView.vue（OQ-2/A） | 人工核对 |
| US-SRD-05 | timer 服务不显示红色；inspection-agent 显示灰色 | HomeView.vue:4态逻辑 | 人工核对 |
| US-SRD-06 | failed 状态显示红色；inactive+enabled 显示蓝色 | HomeView.vue | 人工（构造失败态） |
| US-SRD-07 | .timer 单元在看板显示 active | views.py:MONITORED_SERVICES | 人工 Pi 上 systemctl 核对 |
| US-SRD-08 | start 操作返回 success；enabled 仍 disabled | views.py:service_management_action | 人工 + Pi 上 status 核对 |

---

## 故事依赖图

```
FR-01（白名单追加）
    └─→ US-SRD-01（服务管理可见）  ←── P0，无 OQ 依赖
    └─→ US-SRD-02（看板可见）      ←── P0，OQ-1 范围决策
    └─→ US-SRD-03（详情查看）      ←── P0，无 OQ 依赖
    └─→ US-SRD-04（inspection 可见）←── P0，OQ-2 影响显示细节
    └─→ US-SRD-07（timer 可见）    ←── P2，OQ-1/A

FR-02a（后端 enabled 字段）
FR-02b（前端4态逻辑）
    └─→ US-SRD-05（4态区分）      ←── P1，依赖 OQ-2/A
    └─→ US-SRD-06（执行中/失败态）←── P1，依赖 OQ-2/A

FR-01 + OQ-4/A
    └─→ US-SRD-08（手动 start）   ←── P2，可选
```
