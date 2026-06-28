<!--
  @feature    v1.11.3_miniapp_settings_card_room_name
  @version    1.11.3
  @status     DRAFT
  @author_agent sub_agent_test_engineer
  @created    2026-06-28
-->

# 测试报告 — v1.11.3 参数设置卡片显示具体房间名

## 1. 执行摘要

| 指标 | 值 |
|------|----|
| 执行日期 | 2026-06-28 |
| 执行环境 | Windows 11 Pro 10.0.26200，Node（Vitest v2.1.9） |
| 测试文件 | `miniprogram/tests/param_settings_devicelist.spec.js` |
| 可执行 TC 总数 | 22（单测） + 1（冒烟） = 23 |
| 单测 PASS | 22 |
| 单测 FAIL | 0 |
| 单测 SKIP | 0 |
| 单测 BLOCKED | 0 |
| 冒烟 PASS | 1 |
| NOT_TESTABLE | 4 个 AC（AC-003-03 / AC-004-01 / AC-004-02 / AC-004-03） |
| 单元测试通过率 | 22 / (22 + 0) = **100%** |
| 质量门控（≥80%） | **PASSED** |

---

## 2. 真实 vitest 输出

以下为 `npm run test` 的完整控制台输出（2026-06-28 17:43:02，未经修改）：

```
> freeark-miniprogram@1.0.0 test
> vitest run

 RUN  v2.1.9 C:/Users/胖子熊/MyProject/FreeArk/miniprogram

 ✓ tests/param_settings_devicelist.spec.js (22 tests) 6ms
 ✓ tests/poller.spec.js (2 tests) 4ms
 ✓ tests/auth.spec.js (5 tests) 2ms
 ✓ tests/http.spec.js (5 tests) 6ms
 ✓ tests/chat-ws.spec.js (7 tests) 7ms
 ✓ tests/api.spec.js (5 tests) 6ms
 ✓ tests/screenMqtt.spec.js (13 tests) 6ms
 ✓ tests/stores.spec.js (7 tests) 7ms (5 tests) 5ms

 Test Files  8 passed (8)
       Tests  66 passed (66)
    Start at  17:43:02
    Duration  764ms (transform 233ms, setup 111ms, collect 684ms, tests 42ms, environment 1ms, prepare 1.29s)
```

**结论：66 个测试全部通过（其中 param_settings_devicelist.spec.js 贡献 22 个），无失败，无跳过。**

---

## 3. 逐 AC 测试结果

### US-001：末端温控卡片显示具体房间名

| AC | 对应 TC | 结果 | 实际输出 |
|----|---------|------|---------|
| AC-001-01 | TC-UNIT-001, TC-UNIT-005, TC-UNIT-012, TC-UNIT-017 | PASS | resolveRoomName 返回 room_name；Map 命中；role = 房间名，不等于"末端温控" |
| AC-001-02 | TC-UNIT-002, TC-UNIT-018 | PASS | room_name="" → ori_room_name 正确 fallback |
| AC-001-03 | TC-UNIT-003, TC-UNIT-004, TC-UNIT-019 | PASS | 两者均空/undefined → "未知房间" |

### US-002：系统设备卡片保持 roleMap 角色名

| AC | 对应 TC | 结果 | 实际输出 |
|----|---------|------|---------|
| AC-002-01 | TC-UNIT-013, TC-UNIT-014, TC-UNIT-015 | PASS | roomNameMap 未命中 → roleMap 值；两者未命中 → 兜底字符串 |
| AC-002-02 | TC-UNIT-022 | PASS | system_devices 不被加入 roomNameMap，role 走 roleMap |
| AC-002-03 | TC-UNIT-016 | PASS | 末端温控 role = 房间名，系统设备 role = roleMap 值，互不干扰 |

### US-003：structure 不可用时兜底

| AC | 对应 TC | 结果 | 实际输出 |
|----|---------|------|---------|
| AC-003-01 | TC-UNIT-008, TC-UNIT-009, TC-UNIT-011 | PASS | structure=null → Map.size=0，不抛异常；rooms=[] → Map 为空；devices 字段缺失不崩溃 |
| AC-003-02 | TC-UNIT-010 | PASS | null structure 下多 sn 查询全返回 undefined，无 TypeError |
| AC-003-03 | — | NOT_TESTABLE | 依赖 Vue3 reactive 响应式机制，需 Vue Test Utils 或微信开发者工具运行时验证 |

### US-004：进入页面及切换房间时触发 loadStructure

| AC | 对应 TC | 结果 | 说明 |
|----|---------|------|------|
| AC-004-01 | — | NOT_TESTABLE | loadStructure 内部依赖 uni.getStorageSync + Vue reactive partState，需完整 SFC 运行时 |
| AC-004-02 | — | NOT_TESTABLE | 无缓存时触发网络请求，需 uni.request mock 整体链路 |
| AC-004-03 | — | NOT_TESTABLE | 切换 specific_part 依赖 roomIndex reactive 变化，需完整 SFC 运行时 |

### US-005：deviceSn 类型归一化

| AC | 对应 TC | 结果 | 实际输出 |
|----|---------|------|---------|
| AC-005-01 | TC-UNIT-006, TC-UNIT-020 | PASS | device_sn 数字 1001 被 String() 转为 "1001"；MQTT key 字符串 "1001" 命中 Map |
| AC-005-02 | TC-UNIT-007, TC-UNIT-021 | PASS | device_sn 已是字符串 "1002"，String() 幂等，正常命中 |

---

## 4. Build 冒烟结果

| TC-ID | 命令 | 结果 | 输出摘要 |
|-------|------|------|---------|
| TC-SMOKE-001 | `npm run build:mp-weixin` | **PASS** | "DONE  Build complete. 运行方式：打开 微信开发者工具, 导入 dist\build\mp-weixin 运行。" |

完整构建输出（2026-06-28 真实执行）：

```
> freeark-miniprogram@1.0.0 build:mp-weixin
> cross-env UNI_INPUT_DIR=. uni build -p mp-weixin

编译器版本：5.13（vue3）
正在编译中...

已开启 uni统计 2.0

DONE  Build complete.
运行方式：打开 微信开发者工具, 导入 dist\build\mp-weixin 运行。
```

**结论：uni-app 编译器正常完成构建，无语法错误，无编译警告。**

---

## 5. 各 TC 详细结果

| TC-ID | 关联 AC | 描述 | 结果 | 备注 |
|-------|---------|------|------|------|
| TC-UNIT-001 | AC-001-01 | resolveRoomName：room_name 有值 | PASS | — |
| TC-UNIT-002 | AC-001-02 | resolveRoomName：room_name 空，ori_room_name 有值 | PASS | — |
| TC-UNIT-003 | AC-001-03 | resolveRoomName：两者均为空字符串 | PASS | — |
| TC-UNIT-004 | AC-001-03 | resolveRoomName：两者均 undefined | PASS | — |
| TC-UNIT-005 | AC-001-01 | buildRoomNameMap：正常 structure → Map 填充正确 | PASS | — |
| TC-UNIT-006 | AC-005-01 | buildRoomNameMap：device_sn 数字 → String() 归一化 | PASS | — |
| TC-UNIT-007 | AC-005-02 | buildRoomNameMap：device_sn 已是字符串 → 幂等 | PASS | — |
| TC-UNIT-008 | AC-003-01 | buildRoomNameMap：structure = null → Map 为空 | PASS | — |
| TC-UNIT-009 | AC-003-01 | buildRoomNameMap：rooms 为空数组 → Map 为空 | PASS | — |
| TC-UNIT-010 | AC-003-02 | buildRoomNameMap：null 下多 sn 查询 → 无 TypeError | PASS | — |
| TC-UNIT-011 | AC-003-01 | buildRoomNameMap：room.devices 缺失 → 不崩溃 | PASS | — |
| TC-UNIT-012 | AC-001-01 / AC-002-01 | computeRole：roomNameMap 命中 → 房间名优先 | PASS | — |
| TC-UNIT-013 | AC-002-01 | computeRole：roomNameMap 未命中 → roleMap 值 | PASS | — |
| TC-UNIT-014 | AC-002-01 | computeRole：两者未命中 → `设备 ${productCode}` | PASS | — |
| TC-UNIT-015 | AC-002-01 | computeRole：两者未命中，productCode 为空 | PASS | — |
| TC-UNIT-016 | AC-002-03 | 复合场景：末端温控与系统设备互不干扰 | PASS | — |
| TC-UNIT-017 | AC-001-01 | 完整 Given/When/Then：role = 书房，不等于"末端温控" | PASS | — |
| TC-UNIT-018 | AC-001-02 | 完整 Given/When/Then：role = ori_room_name | PASS | — |
| TC-UNIT-019 | AC-001-03 | 完整 Given/When/Then：role = "未知房间" | PASS | — |
| TC-UNIT-020 | AC-005-01 | AC-005-01 完整场景：类型不匹配 → 匹配成功 | PASS | — |
| TC-UNIT-021 | AC-005-02 | AC-005-02 完整场景：String() 幂等 | PASS | — |
| TC-UNIT-022 | AC-002-02 | system_devices 不在 rooms → role 走 roleMap | PASS | — |
| TC-SMOKE-001 | 全量（构建层） | npm run build:mp-weixin 无编译错误 | PASS | — |

**total = 23，pass = 23，fail = 0，skip = 0，blocked = 0。**
**算术校验：23 = 23 + 0 + 0 + 0 ✓**

---

## 6. 质量指标

| 指标 | 计算式 | 值 |
|------|-------|----|
| 单元测试通过率 | pass / (pass + fail) = 22 / (22 + 0) | **100%** |
| 可执行 AC 覆盖率 | 10 TESTABLE AC 全有对应 TC | **100%** |
| Build 冒烟 | 无语法/编译错误 | **PASS** |
| 质量门控（单测 ≥ 80%） | 100% ≥ 80% | **PASSED** |

---

## 7. NOT_TESTABLE 项汇总

| AC | 原因 |
|----|------|
| AC-003-03 | structure 从 null 变为有值的响应式更新，依赖 Vue3 reactive + computed 自动重算机制，当前 Node/Vitest 层无法模拟 Vue 运行时 |
| AC-004-01 | loadStructure 缓存命中路径，内部使用 uni.getStorageSync + partState[sp].structure 赋值，需完整 SFC 运行时或 Vue Test Utils 挂载才能验证 |
| AC-004-02 | loadStructure 无缓存时触发网络请求，依赖 uni.request + 异步链路，需 SFC 运行时 |
| AC-004-03 | 切换 specific_part 触发独立 loadStructure 调用，依赖 roomIndex ref 响应式切换 → connectRoom 重新执行，需完整 SFC 运行时 |

**建议**：以上 4 个 AC 可通过微信开发者工具手工测试或后续引入 Vue Test Utils / @uni-helper/vitest-environment-miniprogram 进行补充验证。

---

## 8. 缺陷清单

本次测试未发现任何缺陷。所有可执行测试全部通过，Build 冒烟通过。无需路由至 software_developer。
