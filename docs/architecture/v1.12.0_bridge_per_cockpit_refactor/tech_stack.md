<file_header>
  <project_name>v1.12.0_bridge_per_cockpit_refactor</project_name>
  <file_name>tech_stack.md</file_name>
  <file_type>architecture</file_type>
  <author>sub_agent_system_architect</author>
  <created_at>2026-07-08T12:00:00+08:00</created_at>
  <version>1.0.0</version>
  <status>DRAFT</status>
  <upstream_inputs>
    <input path="docs/requirements/v1.12.0_bridge_per_cockpit_refactor/requirements_spec.md" status="APPROVED"/>
    <input path="docs/requirements/v1.12.0_bridge_per_cockpit_refactor/user_stories.md" status="APPROVED"/>
  </upstream_inputs>
</file_header>

# 技术选型表 — 小程序舰桥 per-座舱重构

**文档编号**: TECH-STACK-v1.12.0-BPCR-001
**项目名称**: FreeArk — 小程序舰桥 per-座舱重构
**版本**: 1.0.0
**状态**: APPROVED
**创建日期**: 2026-07-08
**作者**: sub_agent_system_architect

---

## 技术选型总览

本版本为**纯前端变更**，不新增任何第三方依赖。所有技术选型沿用 FreeArk 微信小程序现有技术栈。以下逐项确认并溯源。

---

## 技术选型表

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 前端框架 | uni-app (Vue 3) | 3.x（现有版本） | 项目已基于 uni-app 构建微信小程序，复用 Composition API（`reactive`, `computed`）、Pinia store、组合式函数模式 | REQ-NFUNC-001, REQ-NFUNC-002 | Low — 成熟稳定，无版本变更 | 不升级框架版本 |
| 编程语言 | JavaScript (ES6+) | ES6+（现有） | 小程序前端使用 JS，兼容微信小程序 JavaScript 引擎。新增 `faultUtils.js` 纯函数模块使用 ES6 Set、RegExp、箭头函数、模板字符串 | REQ-FUNC-012 | Low — 无新增语法特性 | 注意：禁止使用 `\p{}` Unicode 属性正则（华为安卓引擎不支持，已知记忆项） |
| 状态管理 | Pinia（ownerStore） | 现有版本 | 业主数据缓存（bindings, structure, realtime params）已在 ownerStore 中实现。本版本不修改 store，仅消费其现有接口 | REQ-NFUNC-003 | Low — 无变更 | `useBridgeDashboard` 继续通过 `useOwnerStore()` 消费 |
| HTTP 客户端 | 自定义 http.js 封装 | 现有版本 | 基于 `uni.request` 封装，带 Token 注入、自动重试 | — | Low — 无变更 | 所有 API 调用通过 `api.js` 统一管理 |
| 轮询机制 | PagePoller | 现有版本 | 封装 `setInterval` + 页面生命周期感知（onShow/onHide 启停），30s 间隔 | REQ-NFUNC-003 | Low — 无变更 | 轮询间隔 `POLL_INTERVAL_MS = 30000` 不变 |
| 位运算 | JavaScript 原生位运算符 | ES6+ | `fresh_air_fault_status` 位域展开使用 `>>` (右移)、`&` (按位与)；popcount 使用 `value.toString(2).split('1').length - 1` | REQ-FUNC-008 | Low — JS 原生能力，无兼容性问题 | 也可用 `BigInt` + 循环，但当前值域（9 bit）不需要 |
| 数据结构 | JavaScript Set、Array、Object | ES6+ | `FAULT_PARAM_NAMES` 使用 `Set` 实现 O(1) 成员判断；`FRESH_AIR_FAULT_BITS` 使用 `Array` 保持顺序 | REQ-FUNC-012 | Low — 原生数据结构 | 已确认微信小程序 JS 引擎支持 `Set` |
| 正则表达式 | JavaScript RegExp | ES6+ | `error_\d+` 参数名匹配：`/^error_\d+$/` | REQ-FUNC-012 | Low — 标准正则，无 Unicode flag | 禁止使用 `u` flag（Unicode 属性转义），与华为安卓兼容 |
| 后端 API | Django REST Framework（复用） | 现有版本 | 所有数据来源于已有端点：`/api/miniapp/owner/realtime-params/`、`/api/miniapp/owner/structure/`、`/api/miniapp/owner/connectivity/`、`/api/devices/fault-events/` | REQ-FUNC-001~013 | Low — API 已生产验证 | 零后端变更（C-01），API 签名不变 |
| 后端故障判定 | `fault_utils.py`（参考源） | v0.5.3-FCC | 前端等效实现 `FAULT_PARAM_NAMES`（26 字段）、`count_faults_for_row()`（普通字段计 1、位域 popcount）、`_ERROR_N_PATTERN` 正则 | REQ-FUNC-012 | Medium — 前后端规则漂移 | 见风险 R-01 |
| 构建工具 | HBuilderX / uni-app CLI | 现有版本 | 沿用现有构建流水线：`npm run dev:mp-weixin`（watch 模式），产出 `dist/dev/mp-weixin` | — | Low — 无变更 | 已知记忆：改 `.vue` 不生效 = dev 监听没跑，必须确认 watch 运行 |
| 版本控制 | Git（main 分支直接提交） | — | 约束 C-05：代码直接提交 main | — | Low — 无分支策略变更 | — |
| 新依赖 | **无** | — | 本版本不引入任何新的 npm 包或第三方库。所有新增逻辑为纯 JS 函数 | C-01, C-02 | **None** — 零新增依赖，零供应链风险 | 新增文件仅 `miniprogram/utils/faultUtils.js` |

---

## 技术风险汇总

| 风险编号 | 风险 | 等级 | 影响 | 缓解措施 |
|---------|------|------|------|---------|
| R-01 | **前后端故障判定规则漂移**: `FAULT_PARAM_NAMES` 或 `FRESH_AIR_FAULT_BITS` 在后端更新后，前端未同步，导致子系统状态与 Web 设备面板不一致 | Medium | 业主看到的故障状态与运维人员在 Web 上看到的不同（US-07 对不齐）；但差异仅影响展示，不影响实际故障记录 | (1) 在 `faultUtils.js` 和 `fault_utils.py` 中互相标注同步来源注释；(2) 未来可在 CI 中加入 `FAULT_PARAM_NAMES` 一致性检查脚本；(3) 代码审查时关注两处常量改动 |
| R-02 | **structure 数据同步延迟**: `getOwnerStructure(sp)` 返回 `sync_status: 'pending'` 时 `system_devices` 为空数组，导致所有子系统不显示 | Medium | 业主看到空白舰桥，误以为系统故障 | (1) `sync_status === 'pending'` 时回退到 SYSTEM_SUB_KEYS 全量显示（REQ-NFUNC-004 降级规则）；(2) 显示提示"正在同步设备结构"；(3) 已有 `STRUCTURE_PENDING_TTL_MS = 5min`，pending 状态会自动过期重试 |
| R-03 | **realtime params 返回数据不含某些设备字段**: 某些座舱的 PLC 参数中缺少特定故障字段（如新风设备仅返回温度值未返回故障标志），导致故障漏判 | Low | 有故障但显示正常——真阴性（用户无感知，但掩盖问题） | (1) 故障判定的逻辑是"有故障字段且非零 → 故障"，"无故障字段 → 正常"（与 Web 一致）；(2) 若某设备真的有故障，PLC 必然会推送对应故障字段（这是 PLC 协议保证的）；(3) 与 Web 端行为一致——Web 也依赖 PLC 参数完整性 |
| R-04 | **`_doFetch()` 移除两个 API 后，索引重新编号导致 bugs**: `Promise.allSettled` 结果数组索引从 8 项变为 6 项，结果处理代码的索引引用须全部更新 | Low | 类型错位导致 `structure` 被当成 `faultEvents` 处理，状态异常 | (1) 使用明确的结果解构替代索引访问（推荐重构方式）；(2) 若保留索引方式，必须逐行核对所有 `results[N]` 引用；(3) 测试覆盖座舱切换、轮询刷新场景 |
| R-05 | **`faultUtils.js` 中的 Set 在旧版微信基础库不兼容** | Low | 极低概率——华为安卓机已知问题是 `\p{}` 正则而非 `Set` | (1) 微信小程序基础库 2.x+ 均支持 `Set`；(2) 若真遇到兼容性问题，可降级为 `Array.includes()`（O(n) 替代 O(1)，数据量仅 26 个元素，性能差异可忽略） |
| R-06 | **uni-app 编译缓存导致 `.vue` 和 `.js` 变更不生效** | Low | 开发者工具显示旧版 UI | 已知记忆项：改源码后必须确认 `npm run dev:mp-weixin` watch 在运行；通过比对产物时间戳验证 |

---

## 技术决策总结

1. **零新增依赖**: 本版本为纯逻辑重构，所有技术选型沿袭现有技术栈。唯一新增文件 `faultUtils.js` 使用 ES6 原生能力（Set、RegExp、位运算），无需任何第三方库。
2. **前端等效实现后端故障逻辑**: 选择在 JS 层复刻 `fault_utils.py` 的判定规则而非新增后端 API，满足 C-01 约束（ADR-002）。
3. **数据源从全局 API 迁移至 per-座舱 API**: 移除 `getDashboardDeviceFaultSummary()` 和 `getDashboardPlcOnlineRate()` 两个全局 API 调用，完全依赖已有的 `getOwnerRealtimeParams(sp)` + `getOwnerStructure(sp)`（ADR-001, ADR-008）。
4. **sub_type 白名单驱动的子系统可见性**: 采用与 Web 端 `SYSTEM_SUB_KEYS` 一致的策略，从 structure 数据动态决策子系统显示（ADR-003）。
