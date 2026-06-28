<!--
  @feature    v1.11.3_miniapp_settings_card_room_name
  @version    1.11.3
  @status     DRAFT
  @author_agent sub_agent_software_developer
  @created    2026-06-28
  @description 自我代码评审报告
-->

# 代码评审报告 — v1.11.3 设备卡片显示具体房间名

## 评审对象

文件：`miniprogram/subpackages/control/pages/param-settings.vue`
改动范围：改动1（deviceList computed，约 325–337 新增 Map 构建 + 第 360 行 role 赋值）
          + 改动2（connectRoom 函数末尾，约 489–491 追加 2 行调用）

评审时间：2026-06-28

---

## 5 维评分

| 维度 | 分值 | 说明 |
|------|------|------|
| Correctness（正确性） | 9/10 | 三层 `??` 优先级逻辑正确；String() 归一化处理数字/字符串不匹配；structure=null 时 Map 为空，自然 fallback，无 TypeError 风险。扣 1 分：若同一 device_sn 出现在多个 room.devices（数据异常），Map 以最后写入的 room 名为准，此场景无显式警告，但属数据质量问题而非本 PR 引入。 |
| Security（安全性） | 10/10 | 无用户输入直接拼接，无 XSS 风险，无凭证硬编码，无越权操作。Map key 来自 structure API 响应（后端归属校验已在 API 层完成）。 |
| Performance（性能） | 9/10 | Map 构建为 O(N×M)（N=rooms 数，M=每房间设备数），对典型住宅（<10 房间，<5 设备/房间）可忽略不计。computed 的响应式追踪机制确保只在依赖变化时重算，无额外轮询开销。扣 1 分：`loadStructure(sp)` 在 `connectRoom` 每次调用时都触发（即使 structure 已加载），缓存命中时快速返回无实际问题，但可用 `if (!partState[sp]?.structure)` 进一步短路（属 MINOR 优化，不影响正确性）。 |
| Maintainability（可维护性） | 9/10 | 三层优先级注释清晰（`REQ-FUNC-001/002`），Map 构建注释标注设计依据（`ADR-1113-01 Option B`），`_initPartState` 幂等性说明明确。扣 1 分：`loadStructure` 不加 `await` 的设计意图仅在注释中说明，建议后续在 ARCHITECTURE.md 中补充 ADR-1113-02 决策记录，以防后来者误加 `await`。 |
| Test Coverage（可测试性） | 8/10 | Map 构建逻辑纯函数化，输入（structure 对象）和输出（role 字符串）均可在单测中直接断言。`_initPartState` 幂等性可单独测试。扣 2 分：`connectRoom` 末尾追加的两行调用包含副作用（修改 reactive 状态 + 可能发起 HTTP 请求），单测需 mock `loadStructure`，当前无测试覆盖（不属于本 PR 范围，test_engineer 阶段补充）。 |

**5 维总体评分：9.0 / 10**

---

## 评审清单

### CRITICAL（0 项）

无 CRITICAL 问题。

### HIGH（0 项）

无 HIGH 问题。

### MEDIUM（0 项）

无 MEDIUM 问题。

### LOW（1 项）

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-001 | LOW | param-settings.vue:489-491 | `loadStructure(sp)` 在每次 `connectRoom` 调用时均会执行，若 `partState[sp].structure` 已存在且未过期，会触发一次 `readStructureCache` 读取（同步，< 1ms）后立即返回。对性能无实际影响，但可在注释中说明"缓存命中时快速返回"以消除阅读疑虑。该注释已在代码中存在。 | DOCUMENTED |

### INFO（3 项）

| Finding ID | 严重级别 | 文件路径:行号 | 描述 |
|-----------|---------|------------|------|
| INF-001 | INFO | param-settings.vue:325-337 | Map 构建循环使用 `for...of`（可读性好），与文件其他部分使用 `forEach` 的风格略有差异，不影响功能，属风格一致性建议。 |
| INF-002 | INFO | param-settings.vue:360 | `??` 运算符（空值合并）语义精确，与原代码 `||` 不同：若 `roleMap[d.productCode]` 为空字符串 `""`，`??` 会显示空字符串而 `||` 会 fallback 到兜底文本。当前 API 不会返回空字符串 productCode role，此差异无实际影响，但记录以供后续维护参考。 |
| INF-003 | INFO | param-settings.vue:490 | `_initPartState(sp)` 调用在 `connectRoom` 中是防御性调用（sp 来自 `room.specific_part`，room 已在函数开头校验非 null）。若 `initOwnerHome` 已先执行，此处是 noop。若参数设置区比区域一先加载（理论上不可能，但作为防御措施合理），此处确保 `partState[sp]` 存在。 |

---

## 逐项审查记录

### 1. 空指针/TypeError 风险（structure 为 null 时的保护）

**审查结果：通过**

`structure?.rooms` 使用可选链操作符，`structure` 为 `null` 或 `undefined` 时整个 `if` 块
不执行，`roomNameMap` 保持空 Map。后续 `roomNameMap.get(sn)` 对空 Map 返回 `undefined`，
`??` 触发 fallback 到 `roleMap[d.productCode]`。全链路无 TypeError 风险。

### 2. Vue3 响应式追踪是否正确

**审查结果：通过**

`deviceList` 是 `computed()`，在其内部访问：
- `currentRoom.value`（computed ref，访问 `.value` 建立追踪）
- `partState[currentSp]?.structure`（partState 是 `reactive({})`，属性访问建立追踪）

当 `loadStructure(sp)` 异步完成后写入 `partState[sp].structure`，Vue3 响应式系统检测到
依赖变化，自动重新求值 `deviceList`，UI 自动更新。此设计是标准的 Vue3 reactive + computed 用法。

### 3. `??` vs `||` 的选择是否正确

**审查结果：通过（有 INF-002 备注）**

`??` 仅对 `null`/`undefined` 触发 fallback，不对 `0`、`false`、`""` 触发。
在本场景中：
- `roomNameMap.get(sn)` 未命中时返回 `undefined` → `??` 触发 ✓
- `roleMap[d.productCode]` 若该 productCode 不存在则为 `undefined` → `??` 触发 ✓
- `roleMap[d.productCode]` 若为空字符串 `""` → `??` 不触发（显示空字符串），`||` 会触发

当前 API 返回的 `product_code_role` 值均为非空字符串（如 "末端温控"、"全屋新风"），
此差异无实际影响。选择 `??` 语义更精确，符合现代 JS 最佳实践。

### 4. `loadStructure(sp)` 不加 await 是否正确

**审查结果：正确**

不加 `await` 是有意设计，原因：
1. `connectRoom` 的主要职责（MQTT acquire/subscribe/publishRead）已在 try 块内完成，
   structure 加载是独立 HTTP I/O，两者无依赖关系。
2. Vue3 响应式确保 structure 加载完成后 `deviceList` 自动重算，不需要调用方等待。
3. 加上 `await` 会在 MQTT 通道建立后额外等待 HTTP 请求，延迟设备数据的首次呈现。

**副作用分析**：`loadStructure` 的副作用是写入 `partState[sp].structure`（reactive），
这是有意为之的。若 `loadStructure` 抛出异常，内部已通过 `try/catch` 处理
（写入 `ps.errorMsg`），不会向 `connectRoom` 冒泡，无静默失败风险。

### 5. `_initPartState(sp)` 的幂等性保证

**审查结果：通过**

`_initPartState` 实现为：
```javascript
function _initPartState(specificPart) {
  if (!partState[specificPart]) {   // 仅当不存在时初始化
    partState[specificPart] = { ... }
  }
}
```
若 `partState[sp]` 已存在（由 `initOwnerHome` 或 `toggleExpand` 初始化），
本次调用为 noop，不会覆盖已有的 `structure`、`expanded` 状态或任何其他字段。
幂等性完全保证。

### 6. 与 v1.11.2 的兼容性

**审查结果：完全兼容**

系统级设备（productCode 260001/130004/270001 等）不在 `structure.rooms` 的任何
`room.devices` 中，`roomNameMap.get(sn)` 返回 `undefined`，`??` fallback 到
`roleMap[d.productCode]`，显示结果与 v1.11.2 完全一致（如 "全屋新风"、"主机" 等）。

区域一"我的房产"展开逻辑完全不受影响（`toggleExpand → loadStructure` 路径不变）。

### 7. 改动是否在规定范围内

**审查结果：通过**

仅修改了 `param-settings.vue` 的两处：
- deviceList computed（Map 构建 + role 赋值修改）
- connectRoom 函数末尾（追加 2 行）

未修改任何其他前端文件、后端文件、样式文件、import 语句或模板部分。
改动严格限定在规定范围内。

---

## 总结

CRITICAL finding 数：0
MAJOR finding 数：0
MEDIUM finding 数：0
LOW finding 数：1（FND-001，已 DOCUMENTED）
INFO finding 数：3（设计备注，无需修复）

评审结论：**APPROVED（可进入测试阶段）**

所有硬性约束均满足：
- 零新 import
- 零后端改动
- 系统级设备卡片行为不变
- String() 归一化确保 key 类型一致
- structure=null 时 Map 为空，三层 `??` 兜底不崩溃不空白
- 改动仅限 param-settings.vue，未越界
