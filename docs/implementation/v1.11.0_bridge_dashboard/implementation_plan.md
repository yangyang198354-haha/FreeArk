<file_header>
  <project_name>FreeArk_BridgeDashboard</project_name>
  <flow_mode>PARTIAL_FLOW</flow_mode>
  <group_id>GROUP_C</group_id>
  <phase_id>PHASE_05</phase_id>
  <author_agent>sub_agent_software_developer</author_agent>
  <inception_timestamp>2026-07-08T00:00:00Z</inception_timestamp>
  <status>DRAFT</status>
  <input_files>
    <file path="docs/architecture/v1.11.0_bridge_dashboard/architecture_design.md" status="APPROVED" />
    <file path="docs/architecture/v1.11.0_bridge_dashboard/module_design.md" status="APPROVED" />
    <file path="docs/architecture/v1.11.0_bridge_dashboard/tech_stack.md" status="APPROVED" />
    <file path="docs/requirements/v1.11.0_bridge_dashboard/requirements_spec.md" status="APPROVED" />
  </input_files>
</file_header>

# 实现计划 — v1.11.0 Bridge Dashboard（舰桥仪表盘重写）

**文档编号**：IMPL-PLAN-v1110-BD-001
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-07-08

---

## 1. 实现概览

- **总模块数**：11 个 MOD（9 新建 + 2 修改）
- **总文件数**：11 个（9 新建 + 2 修改）
- **预估总行数**：~910 行新增 + ~600 行重写 + ~5 行微改
- **实现顺序**：拓扑排序——先实现无依赖的底层模块（API 封装、composables、独立组件），最后实现页面编排层（index.vue）

## 2. 模块实现计划（按拓扑顺序）

| 序号 | MOD-ID | 模块名 | 文件路径 | 依赖前置模块 | 复杂度 | 状态 |
|------|--------|--------|---------|------------|--------|------|
| 1 | MOD-BD-011 | api.js 扩展 | miniprogram/utils/api.js | http.js（现有） | L | PLANNED |
| 2 | MOD-BD-003 | useAnimationControl | miniprogram/composables/useAnimationControl.js | 无 | L | PLANNED |
| 3 | MOD-BD-002 | useBridgeDashboard | miniprogram/composables/useBridgeDashboard.js | MOD-BD-011, ownerStore, authStore, PagePoller, arkZoneMap | H | PLANNED |
| 4 | MOD-BD-008 | HealthIndicator | miniprogram/components/HealthIndicator.vue | 无 | L | PLANNED |
| 5 | MOD-BD-009 | PlcIndicator | miniprogram/components/PlcIndicator.vue | 无 | L | PLANNED |
| 6 | MOD-BD-010 | CabinSwitcher | miniprogram/components/CabinSwitcher.vue | 无 | L | PLANNED |
| 7 | MOD-BD-004 | ShipHull | miniprogram/components/ShipHull.vue | 无 | M | PLANNED |
| 8 | MOD-BD-005 | SubsystemCompartment | miniprogram/components/SubsystemCompartment.vue | 无 | M | PLANNED |
| 9 | MOD-BD-006 | RoomCompartment | miniprogram/components/RoomCompartment.vue | 无 | M | PLANNED |
| 10 | MOD-BD-007 | FaultDrawer | miniprogram/components/FaultDrawer.vue | 无 | M | PLANNED |
| 11 | MOD-BD-001 | pages/home/index.vue | miniprogram/pages/home/index.vue | MOD-BD-002~010, ArkTabBar, MetricCard, authStore | H | PLANNED |

## 3. 依赖关系图

```
MOD-BD-011 (api.js 扩展) ──► http.js (现有)
MOD-BD-003 (useAnimationControl) ──► (独立)
MOD-BD-002 (useBridgeDashboard) ──► MOD-BD-011, ownerStore, authStore, PagePoller, arkZoneMap
MOD-BD-004~010 (组件) ──► (独立，纯展示，通过 props 接收数据)
MOD-BD-001 (index.vue) ──► MOD-BD-002, MOD-BD-003, MOD-BD-004~010, ArkTabBar, MetricCard, authStore
```

**循环依赖检查**：无。所有箭头单向。

## 4. 风险与缓解

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| `/api/dashboard/device-fault-summary/` 权限不兼容 owner 角色 | Medium | 已在 composable 中实现容错——API 失败时子系统隔舱显示"数据不可用"，不阻塞其他隔舱 |
| 能耗前端关键词过滤漏匹配 | Low | 关键词列表包含中英文常见能效术语；开发阶段 console.debug 输出过滤结果 |
| `animation-play-state: paused` 在旧微信版本不支持 | Low | 降级方案：暂停时移除 animation class，恢复时重新添加 |
| 多个 clip-path + box-shadow 叠加性能 | Low | 每个元素最多 2 层 box-shadow；非交互元素使用 will-change: transform |
| FaultDrawer fixed 定位在 iOS scroll-view 嵌套中层级异常 | Low | 抽屉渲染在 scroll-view 外部（页面根层级），z-index: 999 |
| 5 个房间 + 4 个子系统在 375px 屏幕拥挤 | Low | 房间使用 flex-wrap 两列布局；子系统使用 gap: 10rpx 紧凑排列 |

## 5. 架构偏差记录

无架构偏差。所有实现严格遵循 module_design.md 接口契约和 architecture_design.md ADR 决策。

## 6. 实现备注

- **INDEX.VUE REWRITE CRITICAL CONSTRAINT**：admin/operator 路径的模板（lines 167-260）、所有 admin 脚本逻辑、所有 admin 样式（lines 1348-1451）必须原样保留，不做任何修改。
- **API.JS MODIFICATION CONSTRAINT**：仅新增 `getDashboardDeviceFaultSummary()` 方法，不修改任何现有方法。
- **ZERO BACKEND CHANGES**：所有 API 端点均已存在于后端，仅前端新增封装调用。
- **CSS KEYFRAME REUSE**：全部复用现有 6 个 @keyframes（ownerScan、pulseSoft、powerFlow、fanSpin、damageBlink、enginePulse），不新增 keyframe 定义。
- **TESTING NOTE**：测试属于 test_engineer 子代理职责，不在本实现产出范围内。
</file_content>
