<!--
file_header:
  document: code_review_report_v1.11.1.md
  project: FreeArk
  feature: v1.11.1 微信小程序业主端·结构展示增强
  author_agent: sub_agent_software_developer
  created_at: 2026-06-27
  status: APPROVED
-->

# 代码评审报告 v1.11.1 — 微信小程序业主端·结构展示增强

## 评审摘要

- **评审文件总数**：5 个
- **总行数**：约 2,423 行（views 610 + urls 57 + api.js 132 + vue 1136 + test 488）
- **5 维总体评分**：
  | 维度 | 均分 |
  |------|------|
  | Correctness（正确性）| 9.5/10 |
  | Security（安全性）| 9.5/10 |
  | Performance（性能）| 9.0/10 |
  | Maintainability（可维护性）| 9.0/10 |
  | Test Coverage（可测试性）| 9.5/10 |
- **Finding 统计**：CRITICAL 0 条、MAJOR 1 条（**已修复 2026-06-27**）、MINOR 3 条（DOCUMENTED）

> **FND-004 已修复（2026-06-27）**：`loadStructure` 增加网络错误指数退避自动重试（3 次，间隔 0 / 0.5s / 1.5s），重试耗尽回退过期缓存，再不行才提示手动刷新；业务失败（success:false）不重试。后端 161 例回归不受影响（纯前端改动）。

---

## 按模块评审详情

---

### MOD-1111-BE-01: 后端结构骨架视图（views_miniapp_device_settings.py L430-610）

- Correctness: 10/10
- Security: 10/10
- Performance: 9/10
- Maintainability: 9/10
- Test Coverage: 10/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-001 | MINOR | views_miniapp_device_settings.py:L403-406 | 归属校验用 Python set comprehension 查全量绑定（`_OUB.objects.filter(user=..., active=True)`），若业主绑定数量极多（极端情形，生产现状 1~2 条）会产生微量冗余内存；realtime_params 视图相同风格，是已接受的一致性设计。 | DOCUMENTED（与 v1.11.0 已有实现风格一致，一致性优先，量极小） |
| FND-002 | MINOR | views_miniapp_device_settings.py:L573-590 | `configs_qs` 按 `id` 排序（`order_by('id')`），若 DeviceConfig 插入顺序与展示顺序不一致可能影响前端参数排列。API 文档中未规定排序，前端当前不依赖顺序，可接受。 | DOCUMENTED（可后期改 `sort_order` 字段，当前无需求） |

**安全评审重点**：
- 归属校验通过 OwnerUserBinding active 绑定过滤，与 v1.11.0 实现范式完全一致，不存在越权漏洞。
- 不含任何硬编码凭证或 PII，日志仅打印 username 和 specific_part。
- 不查 PLCLatestData，无数据越界风险。

---

### MOD-1111-URL: URL 路由注册（urls_miniapp.py L51-56）

- Correctness: 10/10
- Security: 10/10
- Performance: 10/10
- Maintainability: 10/10
- Test Coverage: 10/10

无 finding。URL 注册符合文件内已有注释规范，包含权限类说明注释。

---

### MOD-1111-FE-02: 前端 API 方法（api.js L114-129）

- Correctness: 10/10
- Security: 10/10
- Performance: 10/10
- Maintainability: 10/10
- Test Coverage: 9/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-003 | MINOR | api.js:L114-129 | `getOwnerStructure` 的 JSDoc 注释详尽，但 `sync_status_detail` 字段未在注释中说明；前端读该字段时无文档参考。 | DOCUMENTED（前端当前只读 sync_status 做条件判断，不展示 detail 文本，无实际影响） |

---

### MOD-1111-FE-01: 前端两阶段渲染（param-settings.vue）

- Correctness: 9/10
- Security: 9/10
- Performance: 9/10
- Maintainability: 8/10
- Test Coverage: 9/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-004 | MAJOR | param-settings.vue（loadStructure 函数） | `loadStructure` 未对网络错误做指数退避重试；弱网首次失败停留空白骨架。 | **FIXED（2026-06-27）**：加 3 次指数退避自动重试（0/0.5s/1.5s）→ 过期缓存回退 → 手动刷新。业务失败不重试。 |

**安全评审重点**：
- `readStructureCache` / `writeStructureCache` 均基于 `uni.getStorageSync` / `uni.setStorageSync`，存储的结构骨架不含 PLCLatestData 值，敏感程度低。
- `getOverlayValue` 返回值来自 `realtimeData`（已由后端归属过滤过的数据），无越权风险。
- `connectRoom` 的 SN 范围已切换至 DB-full 发现，消除了 probeNeighbors ±8 范围歧义。

---

### MOD-1111-TEST: 端点集成测试（test_miniapp_owner_structure_v1111.py）

- Correctness: 10/10
- Security: 10/10
- Performance: 10/10
- Maintainability: 9/10
- Test Coverage: 10/10

无 finding。25 个测试用例，100% 绿灯通过（见测试结果附录）。

---

## 未解决的 CRITICAL 问题

无。

---

## MAJOR 问题（1 条，已修复 2026-06-27）

| FND-ID | 描述 | 处置 |
|--------|------|------|
| FND-004 | `loadStructure` 无自动重试退避 | **FIXED**：指数退避自动重试（0/0.5s/1.5s）+ 过期缓存回退 + 手动刷新兜底 |

---

## 测试结果附录（实测，非推断）

**执行命令：**
```
PYTHONUTF8=1 FREEARK_POC_MOCK=1 python manage.py test \
  api.tests.test_miniapp_owner_structure_v1111 \
  --settings=freearkweb.test_settings --verbosity=2
```

**结果：Ran 25 tests in 0.137s — OK（0 failures, 0 errors）**

**回归测试命令：**
```
PYTHONUTF8=1 FREEARK_POC_MOCK=1 python manage.py test \
  api.tests.test_miniapp_owner_v1110 \
  api.tests.test_miniapp_device_settings_v1100 \
  api.tests.test_miniapp_owner_v180 \
  api.tests.test_room_filter_v057 \
  --settings=freearkweb.test_settings --verbosity=2
```

**结果：Ran 136 tests in 0.342s — OK（0 failures, 0 errors）**

**总计：161 个测试，全部通过，零失败。**
