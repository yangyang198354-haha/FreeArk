<file_header>
  <project_name>FreeArk_BridgeDashboard</project_name>
  <flow_mode>PARTIAL_FLOW</flow_mode>
  <group_id>GROUP_B</group_id>
  <phase_id>PHASE_04</phase_id>
  <author_agent>sub_agent_system_architect</author_agent>
  <inception_timestamp>2026-07-08T00:00:00Z</inception_timestamp>
  <status>DRAFT</status>
  <input_files>
    <file path="docs/requirements/v1.11.0_bridge_dashboard/requirements_spec.md" status="APPROVED" />
    <file path="docs/requirements/v1.11.0_bridge_dashboard/user_stories.md" status="APPROVED" />
  </input_files>
</file_header>

# 技术选型 — v1.11.0 Bridge Dashboard（舰桥仪表盘重写）

**文档编号**：TECH-v1110-BD-001
**项目名称**：FreeArk 微信小程序舰桥仪表盘重写
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-07-08
**配套文档**：`architecture_design.md`、`module_design.md`（同目录）

---

## 1. 技术选型表

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 小程序框架 | uni-app (Vue 3) | 最新 stable（已在使用） | 现有项目框架，C-05 约束不改变其他页面和构建流程；Vue 3 Composition API 支持 composable 模式（ADR-BD-01） | REQ-NFUNC-001, C-05 | 低——已生产运行稳定 | 构建目标 mp-weixin |
| 前端语言 | JavaScript (ES2015+) | — | 现有代码库全部使用 JS（非 TypeScript）；小程序编译链无需额外配置；ArkTabBar/MetricCard 等现有组件均为 JS | — | 低——团队熟悉 | 新代码与现有代码风格一致 |
| 状态管理 | Pinia | 现有安装版 | 现有 `store/auth.js` 和 `store/owner.js` 使用 Pinia；composable 内使用 Vue 3 `reactive()` 作为本地状态（ADR-BD-01），不新增 Store | REQ-FUNC-005, REQ-NFUNC-003 | 低——已在多个版本中验证 | composable 替代全局 Store 用于页面级状态 |
| 响应式方案 | Vue 3 Composition API (`reactive` / `computed` / `ref`) | Vue 3.3+ | 现有页面已使用 Composition API（`<script setup>`）；`reactive()` 用于 composable 内部状态聚合；`computed()` 用于派生状态（隔舱颜色、整体健康度） | REQ-FUNC-001~003, REQ-FUNC-009 | 低——框架内置 | 不引入 Vuex（项目已从 Vuex 迁移至 Pinia） |
| HTTP 客户端 | 现有 `utils/http.js` | 现有 | 统一鉴权（Token 注入）、401 拦截、BASE_URL 管理；所有 API 调用必须通过此模块 | REQ-NFUNC-003, REQ-NFUNC-005 | 低——已在生产使用 | 不做任何修改 |
| API 封装 | 现有 `utils/api.js`（扩展） | 现有 + 新增 1 方法 | 现有 18 个 API 封装方法；新增 `getDashboardDeviceFaultSummary()` 封装已有的后端端点 | REQ-FUNC-002, C-04 | 中——新增端点权限需验证（见风险汇总） | 唯一修改的现有文件 |
| 轮询机制 | 现有 `PagePoller` 类 | 现有 | `setInterval` 封装；现有 `index.vue` 已使用 30s 周期（PM 确认 I-01）；composable 中集成启停逻辑 | REQ-FUNC-009, REQ-NFUNC-002 | 低——已在生产使用 | `onHide` 停止，`onShow` 恢复 |
| CSS 动画 | CSS `@keyframes`（复用现有 6 个） | 现有 | `ownerScan` / `pulseSoft` / `powerFlow` / `fanSpin` / `damageBlink` / `enginePulse`；`animation-play-state` 用于暂停控制 | REQ-NFUNC-001, REQ-NFUNC-002 | 低——`animation-play-state` 在旧微信版本可能不支持（见风险汇总） | 不引入第三方动画库 |
| 布局方案 | CSS Flexbox + 固定定位 | 现有 | 现有 `index.vue` 已使用 `display: flex` + `flex-direction: column` 全页布局；`position: absolute/fixed` 用于背景装饰层；`scroll-view` 纵向滚动 | REQ-NFUNC-004 | 低——在小程序中表现稳定 | 六段式战舰布局通过 flex 列 + 内联块实现 |
| 隔舱造型 | CSS `clip-path` polygon | 现有 | 现有 `ship-shell` 战舰轮廓和 `room-shape-*` 房间异形隔舱均使用 clip-path；扩展隔舱造型复用此方案（ADR-BD-03） | REQ-FUNC-004, REQ-NFUNC-001 | 低——已在微信小程序中验证 | 禁止 Canvas/SVG（与现有模式不兼容） |
| 隔舱图标 | CSS 纯绘制 | 现有 | 现有 `fan-top`（风机圆形扇叶）、`host-top`（主机矩形散热片）、`panel-top`（控制面板）均使用 CSS 伪元素+边框绘制；能耗隔舱新增"能量核心"CSS 图标 | REQ-FUNC-002 | 低——不依赖图标字体或图片资源 | 微信小程序 WXML 不渲染内联 SVG |
| 故障抽屉 | 自定义内联 Popup | 新（自建） | 使用 `v-if` + `position: fixed` + `transform: translateY` + `transition` 实现半屏抽屉（ADR-BD-04）；不引入 uni-ui | REQ-FUNC-006, REQ-NFUNC-001 | 低——小程序中自定义 popup 为成熟模式 | `padding-bottom: env(safe-area-inset-bottom)` 适配 |
| 页面路由 | 现有 `pages.json` | 现有 | 不新增路由；覆盖 `pages/home/index` 页面文件；tabBar 配置不变 | C-05 | 无——完全复用 | 无修改 |
| 底栏组件 | 现有 `ArkTabBar.vue` | 现有 | 沿用现有赛博朋克底栏；4 tab（舰桥/指挥/副官/舰长休息室）；active 态青色发光 pill | REQ-NFUNC-001, C-05 | 无——不修改 | 无修改 |
| 字体 | 系统默认 + Orbitron/Menlo monospace（数据标注） | 现有 | 现有视觉体系使用 `Orbitron, Menlo, monospace` 作为数字字体；房间名/标签使用系统默认（`PingFang SC` 等） | REQ-NFUNC-001 | 低——Orbitron 为 web-safe 回退字体 | 微信小程序不支持 `@font-face` 加载自定义字体（Orbitron 在小程序中降级为 Menlo） |
| 颜色体系 | 现有赛博朋克色板 | 现有 | 背景 `#05070f`、主青 `#2ff4e0`/`#00e5ff`、紫色 `#7c3aed`、状态绿 `#27f5b5`、预警黄 `#ffd400`、告警红 `#ff315d` | REQ-NFUNC-001 | 无——已有精确定义 | 见需求 §2.1 完整色板 |
| 数据缓存 | 现有 `ownerStore` 缓存层 | 现有 | TTL 分级的本地 `uni.storage` 缓存策略：bindings 5min / structure 30day / realtime 60s；首屏使用缓存，轮询直接调 API | REQ-FUNC-011, REQ-NFUNC-005 | 低——已在生产中使用 | 不新增缓存机制 |
| 错误处理 | `Promise.allSettled` + 独立错误状态 | 新（模式） | 6 个 API 使用 `allSettled` 并行请求（ADR-BD-01）；每个隔舱独立错误状态字段；全局错误横幅（全部失败时） | REQ-NFUNC-005 | 低——标准 JS API | 错误消息不含技术敏感信息 |
| 故障判定工具 | 现有 `arkZoneMap.js`（复用 `worseStatus` / `STATUS_RANK`） | 现有 | 仅复用状态聚合工具函数；HTTP FaultEvent 的 severity→status 映射在 composable 中独立实现 | REQ-FUNC-001 | 低——仅读不改 | MQTT attr 判定逻辑（`attrSeverity`/`isFaultActive`）不使用 |
| IDE / 开发工具 | HBuilderX + 微信开发者工具 | 现有 | 现有团队开发环境；uni-app 编译 + mp-weixin 调试 | — | 无 | 无变更 |

---

## 2. 技术风险汇总

| 风险等级 | 风险描述 | 关联选型 | 影响 | 缓解措施 |
|---------|---------|---------|------|---------|
| **Medium** | `/api/dashboard/device-fault-summary/` 端点的权限策略可能与 owner 角色不兼容——当前后端 `UserRoleApiGuardMiddleware` 拦截 role=user 对 `/api/dashboard/` 前缀的访问 | API 封装 (api.js 扩展) | 若被拦截，子系统隔舱（新风/水力/空气品质）无法获取数据，3 个隔舱显示"数据不可用" | 开发初期先用真实 owner token 测试此端点；若返回 403，协调后端将该端点加入 `/api/miniapp/` 白名单或调整为 IsOwnerUser 鉴权（涉及 C-04 例外，需 PM 决策） |
| **Low** | `animation-play-state: paused` 在微信 < 8.0.0 版本中可能不支持 | CSS 动画 | 页面后台时动画未暂停，轻微增加电量消耗（REQ-NFUNC-002 为非 Must Have） | 降级方案：后台时通过条件 class 移除 `animation` 属性而非暂停；前台时重新添加（动画从头播放） |
| **Low** | 能耗子系统前端过滤（`device_type_label` 文本匹配）可能漏匹配或误匹配 | 能耗子系统数据推导 | 能耗隔舱显示的故障计数可能不准确（多计或少计） | 开发阶段使用 `console.debug` 输出过滤结果；提供可配置的关键词列表；PM 可微调过滤规则无需部署后端 |
| **Low** | 低端设备上多个 clip-path + box-shadow 叠加可能导致滚动帧率下降 | 隔舱造型 (CSS clip-path) | 滚动不流畅，影响用户体验 | 减少 box-shadow 叠加层数（≤2 层）；对非交互元素使用 `will-change: transform`；真机测试时使用微信性能面板监控帧率 |
| **Low** | `fixed` 定位的故障抽屉在 iOS `scroll-view` 嵌套场景中层级异常 | 故障抽屉 | 抽屉无法覆盖 ArkTabBar 或被 scroll-view 裁剪 | 将抽屉渲染在 `scroll-view` 外部（页面根层级）；使用 `z-index: 999`；ArkTabBar 也使用 fixed 定位，需确保抽屉 z-index > 底栏 z-index |
| **Low** | 5 个房间隔舱 + 4 个子系统隔舱在 375px 宽度屏幕上可能过于拥挤 | 布局方案 (Flexbox) | 隔舱过小，文字截断，触控区不足 | 子系统 dock 使用 `gap: 10rpx` 紧凑排列；房间网格使用 `flex-wrap: wrap` 两列布局；每个隔舱确保 `min-width: 150rpx` 以满足 ≥44x44 逻辑像素触控区 |

---

## 3. 外部依赖清单

| 依赖 | 提供方 | 用途 | 版本约束 | 降级策略 |
|------|--------|------|---------|---------|
| 后端 API `/api/dashboard/device-fault-summary/` | FreeArk Backend (Django) | 子系统故障汇总 | 已存在（views.py:1563-1606） | API 失败 → 子系统隔舱显示"数据不可用"，其余正常 |
| 后端 API `/api/dashboard/plc-online-rate/` | FreeArk Backend (Django) | PLC 在线率 | 已存在 | API 失败 → PLC 指示器显示"离线" |
| 后端 API `/api/dashboard/fault-summary/` | FreeArk Backend (Django) | 全局故障汇总（本需求不使用，但保留） | 已存在 | N/A |
| 后端 API `/api/devices/fault-events/` | FreeArk Backend (Django) | 活跃故障事件（按 specific_part/room_name 过滤） | 已存在 | API 失败 → 房间隔舱保持上次数据；抽屉显示"数据暂不可用" |
| 后端 API `/api/devices/condensation-warning-events/` | FreeArk Backend (Django) | 结露预警事件 | 已存在 | API 失败 → 结露角标显示"—" |
| 后端 API `/api/miniapp/owner/structure/` | FreeArk Backend (Django) | 房间结构骨架 | 已存在（v1.11.1） | API 失败 → 优先使用 uni.storage 缓存；无缓存时房间隔舱显示"离线"占位 |
| 后端 API `/api/miniapp/owner/realtime-params/` | FreeArk Backend (Django) | 业主实时参数（本需求**不使用**——仅通过 structure + fault-events 判断状态） | 已存在 | N/A（本需求不调用此 API，ADR-BD-02 确定从 FaultEvent 判定而非实时参数） |
| 后端 API `/api/miniapp/bind/status/` | FreeArk Backend (Django) | 业主绑定列表 | 已存在 | API 失败 → 使用 ownerStore 缓存；无缓存时显示"未链接座舱" |
| 微信小程序基础库 | 微信客户端 | 运行环境 | ≥ 2.25.0（uni-app 所需） | 低版本降级：`animation-play-state` 不可用时使用移除 class 方案 |
| uni-app 框架 | DCloud | 跨端框架 | 现有安装版 | 不升级，避免引入兼容性问题 |

---

## 4. 新增文件清单

| 文件路径 | 类型 | 预估行数 | 说明 |
|---------|------|---------|------|
| `miniprogram/composables/useBridgeDashboard.js` | Composable | ~200 | 仪表盘数据获取、状态聚合、轮询管理（MOD-BD-002） |
| `miniprogram/composables/useAnimationControl.js` | Composable | ~40 | CSS 动画暂停/恢复控制（MOD-BD-003） |
| `miniprogram/components/ShipHull.vue` | Component | ~80 | 战舰外壳容器（MOD-BD-004） |
| `miniprogram/components/SubsystemCompartment.vue` | Component | ~120 | 子系统隔舱（MOD-BD-005） |
| `miniprogram/components/RoomCompartment.vue` | Component | ~100 | 房间隔舱（MOD-BD-006） |
| `miniprogram/components/FaultDrawer.vue` | Component | ~180 | 故障抽屉（MOD-BD-007） |
| `miniprogram/components/HealthIndicator.vue` | Component | ~60 | 健康指示器（MOD-BD-008） |
| `miniprogram/components/PlcIndicator.vue` | Component | ~80 | PLC 指示器（MOD-BD-009） |
| `miniprogram/components/CabinSwitcher.vue` | Component | ~50 | 座舱切换器（MOD-BD-010） |

**合计新增**: 9 个文件，~910 行。全部在主包 `miniprogram/` 下，不涉及分包。

## 5. 修改文件清单

| 文件路径 | 修改类型 | 预估变更 | 说明 |
|---------|---------|---------|------|
| `miniprogram/pages/home/index.vue` | 完全重写 owner 路径 | ~600 行（替换现有 ~460 行） | admin 路径完整保留不动；owner 模板全部重写 |
| `miniprogram/utils/api.js` | 新增 1 个方法 | +5 行 | 新增 `getDashboardDeviceFaultSummary()` |

**合计修改**: 1 个重写 + 1 个微改。不新增后端端点、不修改 `pages.json`、不修改 ArkTabBar、不修改任何 Store 文件。

## 6. 不需要的技术（明确排除）

以下技术虽然常见于仪表盘类项目，但**明确不引入**本版本：

| 排除技术 | 排除原因 |
|---------|---------|
| Canvas / WebGL | 违反 ADR-BD-03 决策（Vue 模板 + CSS）；微信小程序中 Canvas API 与 Web 标准差异大；无法复用现有 CSS 动画 |
| SVG 内联 / D3.js | 微信小程序 WXML 不渲染内联 SVG；间接引用无法动态着色 |
| Three.js / 3D 渲染 | REQ-FUNC-004 明确禁止 3D 渲染 |
| uni-ui / uView / Vant Weapp | 引入不必要的 npm 依赖；默认样式与赛博朋克主题冲突，覆盖成本高 |
| ECharts / F2 图表库 | 本需求不涉及数据图表——仅故障计数和颜色编码 |
| WebSocket (MQTT) | REQ-FUNC-009 使用 HTTP 周期性轮询，与现有模式一致 |
| TypeScript | 现有代码库使用 JavaScript，引入 TS 需改造构建链 |
| Vuex | 项目已从 Vuex 迁移至 Pinia |
| 新后端端点 | C-04 强制零后端改动 |
