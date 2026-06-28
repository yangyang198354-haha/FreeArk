<!-- @feature v1.11.3_miniapp_settings_card_room_name @version 1.11.3 @status DRAFT @author_agent sub_agent_system_architect @created 2026-06-28 @description 技术选型说明：本次改动零新依赖，完全基于现有 UniApp + Vue3 + 原生 JS Map -->

# 技术选型说明书 — v1.11.3 参数设置页设备卡片显示房间名

---

## 1. 技术选型表

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 前端框架 | UniApp + Vue3 | 现有生产版本（不变） | 项目既有选型，param-settings.vue 已在此框架中运行；本次改动是框架内局部修改 | REQ-NFUNC-002 | 无 | 不升级、不降级 |
| 响应式原语 | Vue3 `reactive()` | Vue3（现有） | `partState` 已为 `reactive({})`，Vue3 自动追踪嵌套属性访问（ADR-1113-03 核心前提）；`deviceList` 是 `computed()`，structure 赋值时自动失效重算 | REQ-FUNC-004, REQ-NFUNC-001 | 无 | 不新增，已在 script setup 顶部 import |
| 响应式原语 | Vue3 `computed()` | Vue3（现有） | `deviceList` 已是 `computed()`；修改其函数体，追加对 `partState[sp].structure` 的读取；Vue3 自动将其纳入依赖图 | REQ-FUNC-001, REQ-NFUNC-003 | 无 | 不新增 import |
| 数据结构 | 原生 JS `Map<string, string>` | ES6+（现有运行时支持） | 构建 deviceSn → roomName 映射（ADR-1113-01 Option B）；O(1) 查找，优于嵌套循环；不依赖任何第三方库 | REQ-NFUNC-002, REQ-NFUNC-003 | 无 | 微信小程序 JS 运行时完整支持 ES6+ Map |
| 类型转换 | 原生 JS `String()` | ES5+（现有运行时支持） | 将 `room.devices[].device_sn`（number）转为字符串后与 MQTT deviceSn（string）比较，消除类型不匹配（REQ-FUNC-003）；无副作用，幂等 | REQ-FUNC-003 | 无 | 不引入 parseInt/Number 等，String() 最安全（对已是字符串的值无影响） |
| 本地缓存 | `uni.getStorageSync` / `uni.setStorageSync` | UniApp API（现有） | `readStructureCache` / `writeStructureCache` 的底层实现，已在 `loadStructure` 内使用；v1.11.3 不修改缓存层，仅新增 `loadStructure` 调用入口 | REQ-FUNC-005 | 无 | 缓存键 `owner_structure_{sp}`，TTL 24h，逻辑不变 |
| 网络请求 | `api.getOwnerStructure(specificPart)` | 现有 API 封装（不变） | `loadStructure` 内部已使用，v1.11.3 不新增 API 调用类型，仅新增调用时机（connectRoom 末尾） | REQ-NFUNC-002 | 无 | 端点 `/api/miniapp/owner/structure/`，不变 |

---

## 2. 为什么本次不需要任何新库

### 2.1 核心理由

本次改动的本质是：**在 `param-settings.vue` 内，将两个已有功能区域（区域二 deviceList + 区域一 structure）的数据流打通**。所有所需的工具（reactive、computed、Map、String()、loadStructure、resolveRoomName）均已存在于文件内或 JavaScript 运行时。

### 2.2 各备选方案的库需求分析

| ADR | 选定方案 | 若选其他方案的额外 import |
|-----|---------|----------------------|
| ADR-1113-01 | Option B（原生 Map） | Option A 也无需新 import |
| ADR-1113-02 | Option A（connectRoom 末尾追加） | Option C（watch）需 `import { watch } from 'vue'`（当前不确定是否已导入） |
| ADR-1113-03 | Option A（Vue3 reactive 自动追踪） | Option B（手动 watch）需 `watch`，同上 |

ADR-1113-02 与 ADR-1113-03 选择 Option A 的重要副作用之一，是避免了引入 `watch`。这保持了 `param-settings.vue` 当前的 import 语句不变，降低了变更面。

---

## 3. Vue3 reactive/computed 响应式机制说明

### 3.1 核心机制（ADR-1113-03 技术前提）

Vue3 `reactive()` 使用 Proxy 拦截对象属性的 get/set 操作：

- **依赖收集（get 拦截）**：当 `computed()` 函数体执行时，访问 `reactive` 对象的任意属性，Vue3 自动将该属性路径注册为此 `computed` 的依赖。
- **依赖失效（set 拦截）**：当被追踪属性被赋予新值时，Vue3 将所有依赖此属性的 `computed` 标记为 stale（需重算），下次访问时触发重算。

### 3.2 本次应用场景

`partState` 是 `reactive({})` → Vue3 追踪 `partState[sp].structure.rooms` 的读取 → `loadStructure` 执行 `ps.structure = ...` → Vue3 失效 `deviceList` computed → 下次模板访问 `deviceList` 时重算 → 模板更新。

**注意**：`partState[sp]` 的键若在 `deviceList` 求值时不存在（`partState[sp]` 为 `undefined`），可选链 `?.` 保证不抛异常，返回 `null`/`undefined`，Map 构建为空 Map，所有设备 fallback 至 roleMap（REQ-FUNC-004 满足）。

### 3.3 微信小程序运行时约束

| 约束项 | 说明 | 本次影响 |
|-------|------|---------|
| 无 DOM | 微信小程序无 DOM API，Vue3 通过 UniApp 渲染层适配 | 本次改动纯逻辑层（computed 函数体），不涉及 DOM，无影响 |
| `uni.getStorageSync` 可用 | 同步本地存储 API，`readStructureCache` 已在用 | `loadStructure` 新增调用入口不改变存储层，无影响 |
| 无 Node.js 内置模块 | 小程序运行时不支持 `require('path')` 等 | 本次使用原生 JS `Map` 和 `String()`，均在小程序 JS 运行时支持范围内，无影响 |
| `Map` 支持 | 微信小程序基础库 2.x+ 全面支持 ES6 `Map` | [ESTIMATE — 团队已在其他页面使用 ES6 语法，可认为运行时支持] |

---

## 4. 技术风险汇总

| 风险等级 | 风险描述 | 缓解措施 |
|---------|---------|---------|
| Low | Vue3 reactive 对动态新增键（`partState[newSp]`）的追踪：直接给 `reactive` 对象赋值新键在 Vue3 中是响应式的（与 Vue2 的 `Vue.set` 限制不同） | 不需额外处理；`_initPartState(sp)` 通过 `partState[sp] = {...}` 赋值，Vue3 Proxy 天然追踪 |
| Low | `partState[sp].structure` 为 `null` 时可选链保护：若 `?.` 使用不当导致 TypeError | 代码审查时确认 `partState[currentSp]?.structure?.rooms` 全链可选链保护 |
| Low | `String()` 对 `null`/`undefined` 的行为（返回 `"null"` / `"undefined"`）：若 `device.device_sn` 为 `null`，`String(null) === "null"`，与正常 MQTT key 不匹配，静默 miss | 不影响正确性（仅该设备 fallback 至 roleMap），可接受 |

---

## 5. 关于 import 语句的最终结论

**结论：本次改动无需在 `param-settings.vue` 中新增任何 import 语句。**

已使用的语言特性/API 均属于以下类别之一：
1. `param-settings.vue` `<script setup>` 中已声明的函数和变量（`partState`、`currentRoom`、`loadStructure`、`_initPartState`、`resolveRoomName`）
2. JavaScript 原生内置（`Map`、`String()`）— 无需 import
3. 已在顶部 import 的 Vue3 原语（`reactive`、`computed`）— 不新增

---

*文档结束 — 共 6 项技术选型，全部为现有技术，零新依赖，零新 import*
