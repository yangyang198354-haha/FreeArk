<!--
  @feature    v1.11.3_miniapp_settings_card_room_name
  @version    1.11.3
  @status     DRAFT
  @author_agent sub_agent_test_engineer
  @created    2026-06-28
-->

# 测试计划 — v1.11.3 参数设置卡片显示具体房间名

## 1. 被测改动范围

**文件**：`miniprogram/subpackages/control/pages/param-settings.vue`

| 改动编号 | 位置（行号） | 描述 |
|----------|------------|------|
| CHANGE-01 | 第 321-364 行，`deviceList` computed | 新增 roomNameMap 构建逻辑；role 字段改为三层优先级（房间名 → roleMap → 兜底） |
| CHANGE-02 | 第 489-491 行，`connectRoom()` 末尾 | 进入房间时主动调用 `_initPartState(sp)` + `loadStructure(sp)` |

已有辅助函数（不改动，仅被依赖）：
- `resolveRoomName(room)`：三层 fallback（room_name → ori_room_name → "未知房间"）
- `loadStructure(sp)`：缓存命中同步读，缓存未命中异步网络请求

---

## 2. 用户故事覆盖范围

| US | 标题 | 包含 AC 数 |
|----|------|-----------|
| US-001 | 末端温控卡片显示具体房间名 | AC-001-01 / 02 / 03 |
| US-002 | 系统设备卡片保持 roleMap 角色名 | AC-002-01 / 02 / 03 |
| US-003 | structure 不可用时兜底 | AC-003-01 / 02 / 03 |
| US-004 | 进入页面及切换房间时触发 loadStructure | AC-004-01 / 02 / 03 |
| US-005 | deviceSn 类型归一化 | AC-005-01 / 02 |

---

## 3. AC 可测性分类

| AC | 描述摘要 | 可测性 | 测试方式 |
|----|---------|--------|---------|
| AC-001-01 | room_name 有值 → role = 房间名 | TESTABLE_BY_VITEST | 纯函数单测 |
| AC-001-02 | room_name 空，ori_room_name 有值 → role = ori_room_name | TESTABLE_BY_VITEST | 纯函数单测 |
| AC-001-03 | 两者均空 → role = "未知房间" | TESTABLE_BY_VITEST | 纯函数单测 |
| AC-002-01 | 设备不在 rooms，roleMap 有值 → role = roleMap 角色名 | TESTABLE_BY_VITEST | 纯函数单测 |
| AC-002-02 | 设备仅在 system_devices，不在 rooms → role = roleMap 角色名 | TESTABLE_BY_VITEST | 纯函数单测 |
| AC-002-03 | 末端温控与系统设备同时存在 → 互不干扰 | TESTABLE_BY_VITEST | 纯函数单测（复合场景） |
| AC-003-01 | structure = null → role = roleMap（不崩溃） | TESTABLE_BY_VITEST | 纯函数单测 |
| AC-003-02 | structure = null，多张卡片 → 全部 fallback，无 TypeError | TESTABLE_BY_VITEST | 纯函数单测 |
| AC-003-03 | structure 从 null 变为有值 → 响应式更新 | NOT_TESTABLE_NEEDS_RUNTIME | 依赖 Vue3 reactive 系统，需 Vue Test Utils 或微信开发者工具 |
| AC-004-01 | 缓存命中 → loadStructure 从缓存读 | NOT_TESTABLE_NEEDS_RUNTIME | loadStructure 内部涉及 uni.getStorageSync + Vue reactive，需完整 SFC 运行时 |
| AC-004-02 | 无缓存 → loadStructure 触发网络请求 | NOT_TESTABLE_NEEDS_RUNTIME | 同上，且涉及 uni.request mock 整体链路 |
| AC-004-03 | 切换 specific_part → 独立 loadStructure 调用 | NOT_TESTABLE_NEEDS_RUNTIME | 需模拟 roomIndex 响应式切换，依赖完整 SFC 运行时 |
| AC-005-01 | MQTT key 字符串 vs structure device_sn 数字 → 匹配成功 | TESTABLE_BY_VITEST | 纯函数单测（String() 归一化验证） |
| AC-005-02 | device_sn 已是字符串 → String() 幂等，匹配成功 | TESTABLE_BY_VITEST | 纯函数单测 |

**可执行 AC 共 10 个；NOT_TESTABLE AC 共 4 个。**

---

## 4. 测试策略

### 4.1 核心策略：纯函数提取 + Vitest 单测

`deviceList` computed 的核心算法可拆分为三个无副作用的纯函数：

| 函数 | 职责 |
|------|------|
| `resolveRoomName(room)` | 从 room 对象解析房间名，三层 fallback |
| `buildRoomNameMap(structure)` | 遍历 structure.rooms，构建 deviceSn(string) → 房间名 Map |
| `computeRole(sn, roomNameMap, productCode, roleMap)` | 三层优先级选取 role |

这三个函数在测试文件内复现，与 SFC 中的实现语义完全一致，可在 Node/Vitest 环境直接执行，不依赖 Vue 运行时。

### 4.2 测试框架

- 框架：Vitest v2.1.9，Node 环境
- 配置文件：`miniprogram/vitest.config.mjs`
- 测试文件：`miniprogram/tests/param_settings_devicelist.spec.js`
- 运行命令：`cd miniprogram && npm run test`

### 4.3 Build 冒烟

- 命令：`npm run build:mp-weixin`（uni-app 官方构建工具）
- 目的：验证 CHANGE-01/CHANGE-02 改动后 SFC 语法无编译错误
- 输出目录：`dist/build/mp-weixin`
- 说明：若因 appid / 微信服务配置等非代码原因失败，标注 SKIPPED

---

## 5. 测试用例清单

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 |
|-------|--------|---------|------|------|
| TC-UNIT-001 | US-001 | AC-001-01 | UNIT | resolveRoomName：room_name 有值 → 返回 room_name |
| TC-UNIT-002 | US-001 | AC-001-02 | UNIT | resolveRoomName：room_name 为空，ori_room_name 有值 → 返回 ori_room_name |
| TC-UNIT-003 | US-001 | AC-001-03 | UNIT | resolveRoomName：两者均为空字符串 → 返回 "未知房间" |
| TC-UNIT-004 | US-001 | AC-001-03 | UNIT | resolveRoomName：两者均 undefined → 返回 "未知房间" |
| TC-UNIT-005 | US-001 | AC-001-01 | UNIT | buildRoomNameMap：正常 structure → Map 填充正确 |
| TC-UNIT-006 | US-005 | AC-005-01 | UNIT | buildRoomNameMap：device_sn 为数字 → String() 归一化，key 为字符串 |
| TC-UNIT-007 | US-005 | AC-005-02 | UNIT | buildRoomNameMap：device_sn 已是字符串 → String() 幂等，匹配成功 |
| TC-UNIT-008 | US-003 | AC-003-01 | UNIT | buildRoomNameMap：structure = null → Map 为空，不崩溃 |
| TC-UNIT-009 | US-003 | AC-003-01 | UNIT | buildRoomNameMap：structure.rooms 为空数组 → Map 为空 |
| TC-UNIT-010 | US-003 | AC-003-02 | UNIT | buildRoomNameMap：structure = null，多 sn 查询 → 全部 undefined，无 TypeError |
| TC-UNIT-011 | US-003 | AC-003-01 | UNIT | buildRoomNameMap：room.devices 缺失 → 不崩溃，Map 仍为空 |
| TC-UNIT-012 | US-001 / US-002 | AC-001-01 / AC-002-01 | UNIT | computeRole：roomNameMap 命中 → 返回房间名（不返回 roleMap 值） |
| TC-UNIT-013 | US-002 | AC-002-01 | UNIT | computeRole：roomNameMap 未命中，roleMap 有值 → 返回 roleMap 角色名 |
| TC-UNIT-014 | US-002 | AC-002-01 | UNIT | computeRole：两者均未命中 → 返回 `设备 ${productCode}` |
| TC-UNIT-015 | US-002 | AC-002-01 | UNIT | computeRole：两者均未命中且 productCode 为空 → 返回 "设备 " |
| TC-UNIT-016 | US-002 | AC-002-03 | UNIT | 复合：末端温控显示房间名，系统设备显示角色名，互不干扰 |
| TC-UNIT-017 | US-001 | AC-001-01 | UNIT | AC-001-01 完整 Given/When/Then：role = 书房，不等于"末端温控" |
| TC-UNIT-018 | US-001 | AC-001-02 | UNIT | AC-001-02 完整 Given/When/Then：role = ori_room_name |
| TC-UNIT-019 | US-001 | AC-001-03 | UNIT | AC-001-03 完整 Given/When/Then：role = "未知房间" |
| TC-UNIT-020 | US-005 | AC-005-01 | UNIT | AC-005-01：MQTT 字符串 "1001" vs 数字 1001 → 匹配成功 |
| TC-UNIT-021 | US-005 | AC-005-02 | UNIT | AC-005-02：device_sn 已是字符串，String() 幂等 |
| TC-UNIT-022 | US-002 | AC-002-02 | UNIT | system_devices 中的设备不在 rooms → role 走 roleMap |
| TC-SMOKE-001 | 全量 | 全量（构建层） | SMOKE | npm run build:mp-weixin 编译无报错 |

**可执行测试用例共 23 个（22 单测 + 1 冒烟）。**

---

## 6. 不在测试范围的内容

- Vue3 响应式层（ref / reactive / computed 响应链）
- 微信开发者工具 UI 验证（视觉渲染、交互动画）
- E2E 测试（需真机或模拟器环境）
- `connectRoom` 中 `loadStructure` 的异步网络请求链路（NOT_TESTABLE_NEEDS_RUNTIME）
- 集成测试（MQTT 数据流 → deviceList 更新）：依赖 WebSocket + 服务端，超出本层测试范围

---

## 7. 质量门控

| 指标 | 目标 |
|------|------|
| 单元测试通过率（可执行项） | 100%（22/22） |
| AC 可测项覆盖率 | 100%（10/10 TESTABLE AC 各有对应 TC） |
| Build 冒烟 | PASS（无语法错误） |
