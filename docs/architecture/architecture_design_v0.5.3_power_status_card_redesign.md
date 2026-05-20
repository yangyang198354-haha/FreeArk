# 架构设计文档

```
file_header:
  document_id: ARCH-v0.5.3-r1
  title: 系统看板「开机情况」卡片重设计 — 前端架构设计
  author_agent: sub_agent_software_developer (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: v0.5.3-r1
  created_at: 2026-05-21
  status: APPROVED
  references:
    - docs/requirements/v0.5.3_dashboard_power_status_card/requirements_spec.md
    - docs/requirements/v0.5.3_dashboard_power_status_card/user_stories.md
    - FreeArkWeb/frontend/src/views/HomeView.vue
```

---

## 1. 设计目标

将 `HomeView.vue` 中 `.power-status-wrapper` 内的「系统开机状况」卡片重设计为与
看板下方 `.stat-card` 视觉规范完全统一的布局，同时使两张顶部卡片（「总电量查询」
和「开机情况」）底边严格齐平。

---

## 2. 改动范围

**唯一修改文件**：`FreeArkWeb/frontend/src/views/HomeView.vue`

改动分两部分：
- **template** 区域：`.power-status-wrapper` 内的 HTML 结构（第 49-93 行）
- **style scoped** 区域：`.total-energy-wrapper`、`.power-status-wrapper` 及新 `.ps-*` 类（第 555-660 行）

**不改动**：
- `<script>` 区块（数据状态、API 调用、onMounted 均不变）
- 后端 API、路由、`global.css`、其他视图文件

---

## 3. 卡片标题

由「系统开机状况」改为「**开机情况**」（需求 REQ-02）。

---

## 4. 高度对齐方案（REQ-01）

采用 CSS flex 高度传递链，使两个 wrapper 内的 `el-card` 随 `.top-cards-row`
的 `align-items: stretch` 自动撑满相同高度。

### 4.1 传递链说明

```
.top-cards-row  [display: flex; align-items: stretch]
  └── .total-energy-wrapper  [flex: 2; display: flex; flex-direction: column]
  │     └── .el-card          [:deep, flex: 1; display: flex; flex-direction: column]
  │           └── .el-card__body  [:deep, flex: 1; display: flex; flex-direction: column]
  │
  └── .power-status-wrapper  [flex: 1; display: flex; flex-direction: column]
        └── .el-card          [:deep, flex: 1; display: flex; flex-direction: column]
              └── .el-card__body  [:deep, flex: 1; display: flex; flex-direction: column]
                    └── .power-status-content  [display: flex; flex-direction: column; flex: 1]
```

**关键点**：使用 Vue `scoped` 样式的 `:deep()` 选择器穿透 Element Plus 组件的
Shadow DOM 边界，对 `.el-card` 和 `.el-card__body` 施加 flex 布局。

---

## 5. 卡片正文结构（REQ-03 / REQ-04 / REQ-05）

### 5.1 主信息行（`.ps-main-row`）

```
[ 图标圆圈 50x50 ]  [ 大数字 XX.X% ]
                    [ 「开机率」标签 ]
```

| 元素 | 规格 |
|------|------|
| 图标圆圈 `.ps-icon-circle` | 50x50px，border-radius:50%，background: rgba(103,194,58,0.1) |
| 图标 | `<el-icon>` 内嵌 `<Cpu />`，font-size:24px，color:#67c23a |
| 开机率数值 `.ps-rate-value` | `power_on_rate.toFixed(1)%`，font-size:24px，font-weight:600，color:#303133 |
| 标签 `.ps-rate-label` | 「开机率」，font-size:14px，color:#909399 |

**不显示**：设备总台数、开机台数的文字叙述（REQ-03）。

### 5.2 模式合计行（`.ps-mode-chips`）

水平排布 4 个（或 5 个）chip，`justify-content: space-between`。

| Chip | 数字颜色 | 数据字段 |
|------|---------|---------|
| 制冷 | #409eff | `mode_distribution.cooling` |
| 制热 | #f56c6c | `mode_distribution.heating` |
| 通风 | #e6a23c | `mode_distribution.ventilation` |
| 除湿 | #13c2c2 | `mode_distribution.dehumidification` |
| 未知 | #909399 | `mode_distribution.unknown`（v-if: > 0） |

每个 chip 的结构：
```
.ps-chip
  └── .ps-chip-num   font-size:22px; font-weight:600; color:<各自专属色>
  └── .ps-chip-name  font-size:12px; color:#909399
```

---

## 6. 数据绑定（不变）

`powerStatus` reactive 对象结构不变，由 `fetchPowerStatus()` 在 `onMounted` 中填充：

```json
{
  "powered_on_count": 0,
  "total_count": 0,
  "power_on_rate": 0.0,
  "mode_distribution": {
    "cooling": 0,
    "heating": 0,
    "ventilation": 0,
    "dehumidification": 0,
    "unknown": 0
  }
}
```

初始值均为 0，渲染时不会产生 NaN（`(0).toFixed(1)` = "0.0"）。

---

## 7. 验收标准对照

| REQ-ID | 标准描述 | 实现方式 |
|--------|---------|---------|
| REQ-01 | 两张顶部卡片底边齐平 | flex 高度传递链 + :deep(.el-card) flex:1 |
| REQ-02 | 卡片标题「开机情况」 | template `<span>开机情况</span>` |
| REQ-03 | 仅显示开机率%，无台数叙述 | 废弃 `.ps-on-section`，仅保留 `.ps-rate-value` |
| REQ-04 | 4 模式一行彩色数字+灰色名称 | `.ps-mode-chips` + `.ps-chip` 水平 flex |
| REQ-05 | 图标圆圈+大数字+标签结构 | `.ps-icon-circle` + `.ps-rate-value` + `.ps-rate-label` |

---

## 8. 代码自评审（Code Review）

### 8.1 CRITICAL 检查项

| 检查点 | 结论 |
|--------|------|
| `Cpu` 图标是否已在 script 中 import | PASS — `import { ..., Cpu, ... } from '@element-plus/icons-vue'` 第 224 行，且在 `components` 第 232 行注册 |
| `powerStatus.power_on_rate` 初始为 0.0（数值），`.toFixed(1)` 不报错 | PASS — reactive 初始值 `power_on_rate: 0.0` 第 286 行 |
| `mode_distribution.unknown` 在初始 reactive 中存在 | PASS — 第 293 行 `unknown: 0` |
| `:deep()` 选择器语法正确（Vue 3 scoped） | PASS — `.wrapper :deep(.el-card)` 是 Vue 3 官方 deep 语法 |
| `v-loading` 指令绑定保持不变 | PASS — `v-loading="loading.powerStatus"` 保留 |
| 不引入任何新 import | PASS — 无新增 import |
| `.top-cards-row` 已有 `align-items: stretch` | PASS — 第 560 行原有样式，无需修改 |

### 8.2 MINOR 检查项

| 检查点 | 结论 |
|--------|------|
| 移除旧 `.ps-on-section`、`.ps-mode-section`、`.ps-mode-item`、`.ps-mode-label`、`.ps-mode-value` CSS — 无孤立选择器 | PASS — 这些类在 template 中已同步删除 |
| `power-status-content` 旧有 `min-height: 120px` 改为 `min-height: 100px` + `flex: 1` | PASS — 更合理，不再需要固定最小高度 |
| `ps-mode-chips` 的 `margin-top: 20px` 提供足够的视觉间距 | PASS — 与设计方案一致 |

### 8.3 结论

无 CRITICAL finding，无 BLOCKER。本次改动为纯前端样式/结构调整，不涉及数据层或
API，风险极低。
