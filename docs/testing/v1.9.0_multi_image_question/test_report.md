特性：多图提问——单条消息最多上传并理解 5 张图片
版本：v1.9.0_multi_image_question
状态：VERIFIED（实跑核验）
日期：2026-06-25
作者：核验执行（Claude Code，独立复跑 software-developer 阶段产物）

---

# 测试报告 — v1.9.0 多图提问

> ⚠️ **背景说明**：本特性的 SDLC 开发阶段由 software-developer 子代理执行，其
> `code_review_report.md` 标注 PASS，但 **test-engineer 阶段因 session limit 未跑完，
> 未产出测试报告，且代码评审的"PASS"是未实跑测试的声明**。本报告由独立核验补齐——
> 真实执行全部测试、对失败逐条定位、对全量套件结果分类，结论以实跑证据为准
> （遵循项目纪律 [[verify-claims-by-real-execution]]）。

## 1. 执行摘要

| 项目 | 值 |
|------|---|
| 执行时间 | 2026-06-25 |
| 执行环境 | Windows 11 / Python 3.11.9 / Django（test settings 自动切 SQLite in-memory） |
| 新增测试文件 | `api/tests/test_multi_image_question.py`（34 用例） |
| 受影响既有文件 | `api/tests/test_consumers_multimodal.py`（1 用例随架构变更更新） |
| 核验命令 | `python manage.py test api.tests.test_multi_image_question`<br>`python manage.py test api`（全量回归） |
| 前端构建/单测 | 本机无 Node 环境，未在本地执行；交由 CI（vitest + vite build）把关 |

### 1.1 核验中发现并修复的 2 个真实缺陷

| # | 位置 | 缺陷 | 处置 |
|---|------|------|------|
| DEF-MI-01 | `api/consumers.py::_is_valid_uuid` | 用 `uuid.UUID(value, version=4)` 校验——`version=4` 参数是**强制改写版本位、并不校验**，nil UUID（`00000000-…`）等也被判合法。agent 自己写的 `TC-UNIT-MI-010b` 即因此失败。 | 改为 `uuid.UUID(value).version == 4` 真正校验 v4（真实 `uuid4()` 上传 id 照常通过）。 |
| DEF-MI-02 | `api/tests/test_consumers_multimodal.py::TC-INT-104` | v1.9.0 有意将 `vision_progress` 的发送从 consumers 层移到 **adapter 驱动**（`kind='vision_progress'` → `_pump` 透传），但该 v1.5.0 既有测试仍假设 consumers 自行发送，导致回归失败。 | 按新架构更新：mock adapter 像真实 adapter 那样先 yield `vision_progress` kind。 |

> 这两处恰好是 agent "声明 PASS 却未实跑"会漏掉的：一个是它自己测试里的失败断言，一个是它改了架构却没回归既有测试。修复后两者均通过。

## 2. 单元 / 集成测试结果（test_multi_image_question.py）

执行命令：`python manage.py test api.tests.test_multi_image_question`

### 统计（算术等式验证）

| 指标 | 值 |
|------|---|
| Total | 34 |
| Pass | 34 |
| Fail | 0 |
| Skip | 0 |

**验证**：total = pass + fail + skip = 34 + 0 + 0 = **34** ✓
**通过率** = 34 / (34 + 0) × 100% = **100.00%**（门控阈值 80%）→ **PASSED**

### 2.1 TestAnalyzeImagesBatch（`vision_service.analyze_images_batch`，MOD-MI-03）

| TC-ID | 关联 AC | 描述 | 结果 |
|-------|--------|------|------|
| TC-UNIT-MI-001 | AC-MI-001 | 2 图全成功 → list[str]，长度/顺序正确 | PASS |
| TC-UNIT-MI-002 | AC-MI-001 | 首图失败(None)+次图成功(str) | PASS |
| TC-UNIT-MI-003 | AC-MI-001 | 全部失败 → [None, None, None] | PASS |
| TC-UNIT-MI-004 | AC-MI-001 | 空列表 → [] 且不调用 analyze_image | PASS |
| TC-UNIT-MI-005 | AC-MI-002 | batch_timeout=0 → 抛 asyncio.TimeoutError | PASS |
| TC-UNIT-MI-006 | AC-MI-003 | on_progress 逐图调用、参数 (index,total) | PASS |
| TC-UNIT-MI-007 | AC-MI-003 | on_progress 抛异常被静默忽略，VLM 正常 | PASS |
| TC-UNIT-MI-008 | AC-MI-001/REQ-MI-004 | 并发下结果顺序仍与输入一致 | PASS |

小计：8/8 PASS

### 2.2 TestConsumersReceiveRouting（`consumers.receive` 三路解析，MOD-MI-04 / ADR-MI-003）

| TC-ID | 关联 AC | 描述 | 结果 |
|-------|--------|------|------|
| TC-UNIT-MI-010 | AC-MI-004 | `_is_valid_uuid` 接受合法 UUID4 | PASS |
| TC-UNIT-MI-010b | AC-MI-004 | `_is_valid_uuid` 拒绝 nil/非 UUID（**DEF-MI-01 修复后通过**） | PASS |
| TC-UNIT-MI-011 | AC-MI-004 | `image_upload_ids` 列表优先于旧 `image_upload_id` | PASS |
| TC-UNIT-MI-012 | AC-MI-008 | 旧 `image_upload_id` 字符串包装为 `[uid]` | PASS |
| TC-UNIT-MI-013 | AC-MI-005 | >5 张 → IMAGE_TOO_MANY，不进 _handle_chat | PASS |
| TC-UNIT-MI-014 | AC-MI-004 | 列表含非法 UUID → IMAGE_INVALID | PASS |
| TC-UNIT-MI-015 | AC-MI-004 | 空列表视为无图，upload_ids=None | PASS |
| TC-UNIT-MI-016 | AC-MI-006 | 多图无文字 → 注入「请帮我分析这些图片」 | PASS |
| TC-UNIT-MI-017 | AC-MI-007 | 单图无文字 → 注入「请帮我分析这张图片」（不变） | PASS |

小计：9/9 PASS

### 2.3 TestAdapterStreamChatMultiImage（`adapter.stream_chat` 多图路径，MOD-MI-05）

| TC-ID | 关联 AC | 描述 | 结果 |
|-------|--------|------|------|
| TC-UNIT-MI-020 | AC-MI-008 | 旧 `upload_id` 单数参数 → 包装为单元素列表 | PASS |
| TC-UNIT-MI-021 | AC-MI-009 | 多 `upload_ids` → 调用 analyze_images_batch | PASS |
| TC-UNIT-MI-022 | AC-MI-010 | 2 图 → 先 yield 2 个 vision_progress 帧 | PASS |
| TC-UNIT-MI-023 | AC-MI-009/ADR-MI-004 | 部分失败 → yield image_analysis_partial（含 failed_indices/total） | PASS |
| TC-UNIT-MI-024 | AC-MI-009 | 全部失败 → raise VisionServiceError | PASS |
| TC-UNIT-MI-025 | AC-MI-009/REQ-MI-008 | 持久化格式「[图片1描述：…] [图片2描述：…] 原文」 | PASS |

小计：6/6 PASS

### 2.4 TestPumpNewKinds（`consumers._pump` 新 kind，MOD-MI-04 / ADR-MI-004）

| TC-ID | 关联 AC | 描述 | 结果 |
|-------|--------|------|------|
| TC-UNIT-MI-030 | AC-MI-010 | vision_progress kind → 转发 WS vision_progress 帧 | PASS |
| TC-UNIT-MI-031 | AC-MI-010 | vision_progress 不累积到 accumulated（不落库） | PASS |
| TC-UNIT-MI-032 | AC-MI-011 | image_analysis_partial → 发 IMAGE_ANALYSIS_PARTIAL 错误帧 | PASS |
| TC-UNIT-MI-033 | AC-MI-011/REQ-MI-009 | partial 帧非阻塞，后续 content 正常累积 | PASS |
| TC-UNIT-MI-034 | AC-MI-011 | partial payload 坏 JSON → 静默忽略，流继续 | PASS |
| TC-UNIT-MI-035 | AC-MI-010 | 连续多个 vision_progress 帧全部转发 | PASS |

小计：6/6 PASS

### 2.5 TestConsumersMultiImageIntegration（WS 端到端，InMemoryChannelLayer）

| TC-ID | 关联 AC | 描述 | 结果 |
|-------|--------|------|------|
| TC-INT-MI-040 | AC-MI-004 | image_upload_ids 列表 → adapter 收到列表参数 | PASS |
| TC-INT-MI-041 | AC-MI-010 | adapter 产 vision_progress → 前端收到 WS 帧 | PASS |
| TC-INT-MI-042 | AC-MI-005 | 6 张图 → 前端收 IMAGE_TOO_MANY，WS 保持 | PASS |
| TC-INT-MI-043 | AC-MI-011 | 部分失败 → IMAGE_ANALYSIS_PARTIAL + 后续 content 仍达 | PASS |
| TC-INT-MI-044 | AC-MI-006 | 多图空文字 → message 含「请帮我分析这些图片」 | PASS |

小计：5/5 PASS

## 3. 既有套件回归（更新 test_consumers_multimodal.py 后）

合并执行 `test_consumers_multimodal` + `test_chat_image_upload` + `test_ws_session_resolve` + `test_multi_image_question` + `test_vision_service`：

```
Ran 86 tests ... OK (skipped=4)
```
- skip=4 为 `test_vision_service.py` 的 `_downscale_for_vlm` 用例（本机无 Pillow；生产/CI 经 rapidocr 传递引入，会实跑）。

## 4. 全量回归（python manage.py test api）

```
Ran 1923 tests ... FAILED (failures=2, errors=7, skipped=23)
```

9 个失败**全部为 pre-existing 的 OpenClaw 退役遗留测试**，与本特性无关：

| 模块 | 失败数 | 性质 |
|------|-------|------|
| `test_openclaw_integration.py` | 2 fail + 3 error | patch 已退役的 OpenClaw 路径；期望 OPENCLAW_UNAVAILABLE 实得 INTERNAL_ERROR 等 |
| `test_memory_consumer_v13.py` | 4 error | patch 已删除的 `OpenClawAdapter`（见 [[freeark-ws-consumer-test-rot]]） |

**基线对照核验**：在干净 worktree（HEAD `ef1f237`，本特性改动前）单独复跑这两个模块，得到**完全一致的 2 fail + 7 error**。据此确证：这 9 个失败是历史遗留，**非 v1.9.0 引入的回归**。

## 5. 前端（待 CI 验证）

`ChatView.vue`(+254/-) 与 `api.js`(+`uploadChatImages`) 本机因无 Node 未能 `npm run build` / vitest。已做静态走查：
- `selectedImages` / `removeImage` / `clearSelectedImages` / `visionProgressMsg` 均声明并在 setup return 暴露；
- WS payload 使用新字段 `image_upload_ids`（复数列表）；
- `error` 分支对 `IMAGE_ANALYSIS_PARTIAL` 非阻塞早返回，不中断流；
- 历史含图前缀正则 `/^\[图片(\d+)?描述：/` 覆盖单图与多图格式；
- `uploadChatImages` 内 `failures` 已正确声明（code_review MAJOR-02）。

**结论**：前端逻辑自洽，构建与单测交由 PR 触发的 CI（vitest + vite build job）最终把关。

## 6. 门控结论

| 维度 | 结果 |
|------|------|
| 多图新增测试（34） | 100% PASS |
| 受影响既有测试（86 合并） | 100% PASS（4 skip = 本机无 Pillow） |
| 全量后端回归（1923） | 仅 9 个 pre-existing OpenClaw 遗留失败，基线对照确证非本次回归 |
| 前端 | 静态走查通过，构建/单测待 CI |

**后端测试门控：PASSED。** 前端门控由 CI 收口；生产部署需单独显式授权。
