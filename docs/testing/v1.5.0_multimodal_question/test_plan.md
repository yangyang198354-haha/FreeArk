特性：多模态提问——用户图片输入与豆包视觉模型理解
版本：v1.5.0_multimodal_question
状态：DRAFT
日期：2026-06-24
作者：test-engineer

---

# 测试计划 — v1.5.0 多模态提问

## 1. 测试策略

### 1.1 测试目标

验证 v1.5.0 多模态提问功能的所有验收标准（AC-MQ-*）均通过自动化测试，确保：
- 图片临时存储（vision_service）逻辑正确且线程安全
- REST 预上传端点安全校验完整（MIME、大小、容量、鉴权）
- WS Consumer 多模态扩展路径行为正确（UUID 校验、progress 通知、错误降级、DB 持久化）
- 纯文字聊天路径向后兼容，图片功能故障不影响主聊天流

### 1.2 测试范围（In-Scope）

| 模块 | 测试层级 | 说明 |
|------|---------|------|
| MOD-MQ-03 vision_service（store/get/delete/check/analyze） | 单元测试 | 进程内存储逻辑；VLM 超时/重试/降级（mock AsyncOpenAI） |
| MOD-MQ-02 views_chat_image（POST /api/chat/image-upload/） | 集成测试 | REST 端点校验顺序；与 vision_service 的集成 |
| MOD-MQ-04 consumers（receive/\_handle\_chat/\_pump） | 集成测试 | WS 多模态路径；错误帧；DB 持久化 |

### 1.3 测试范围（Out-of-Scope）

| 项目 | 排除原因 |
|------|---------|
| AC-MQ-001-02（铭牌识别质量） | 人工抽检，非自动化测试 |
| AC-MQ-003-*（前端预览/撤销） | 前端 UI 测试，本期不在后端测试范围 |
| AC-MQ-006-*（历史会话含图标注） | 前端渲染逻辑，需前端 vitest 覆盖 |
| AC-MQ-007-01/03（客户端大小校验/自动压缩） | 前端逻辑 |
| AC-MQ-008-01（uvicorn access log 无 base64） | 运维级验证，手工执行 |
| AC-MQ-004-01（流式输出与纯文字一致性 UX） | 端到端 UX，人工验证 |
| AC-MQ-009-03（超时期间 WS 心跳）| 基础设施级，非应用代码 |
| doubao-vision 真实网络调用 | 所有 VLM 调用均通过 mock 隔离 |

### 1.4 测试环境

| 项目 | 值 |
|------|---|
| Python 版本 | 3.11 |
| Django 版本 | 5.2.7 |
| 数据库 | SQLite（测试自动切换，`_RUNNING_TESTS=True`） |
| Channel Layer | InMemoryChannelLayer（无需 Redis） |
| 外部 API | 全部通过 `unittest.mock` 隔离，不发真实网络请求 |
| 执行命令 | `python manage.py test api.tests.test_vision_service api.tests.test_chat_image_upload api.tests.test_consumers_multimodal --verbosity=2` |

### 1.5 覆盖率目标

| 层级 | 目标 | 门控 |
|------|------|------|
| 单元测试（vision_service 存储+VLM） | ≥ 80% 通过率 | 未达标则停止集成测试 |
| 集成测试（REST + WS Consumer） | ≥ 90% 通过率 | 未达标则停止 E2E |
| 需求覆盖率 | 全部可测 AC-MQ-* 有对应 TC | 每条 US-MQ-* 至少一个 TC |

---

## 2. 测试用例清单

### 2.1 单元测试（UNIT）— test_vision_service.py

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-UNIT-001 | US-MQ-001 | AC-MQ-001-01 | UNIT | store_upload 返回 UUID4 格式字符串 | 空存储 | 调用 store_upload(bytes, user_id) | 返回合法 UUID4 字符串 |
| TC-UNIT-002 | US-MQ-001 | AC-MQ-001-01 | UNIT | store_upload 后条目可取回 | 空存储 | store_upload 后调用 get_upload | 返回原始 bytes |
| TC-UNIT-003 | US-MQ-007 | AC-MQ-007-02 | UNIT | 总量超限时 raise StorageCapacityError | 空存储 | store_upload 51MB 数据 | 抛 StorageCapacityError |
| TC-UNIT-004 | US-MQ-007 | AC-MQ-007-02 | UNIT | 惰性清理：先存 TTL=0 条目再 store 时清理后成功 | 注入45MB过期条目 | store_upload 10MB 数据 | 成功，过期条目已清理 |
| TC-UNIT-005 | US-MQ-001 | AC-MQ-001-01 | UNIT | store_upload 后 _total_size 正确增加 | 空存储 | store_upload 小图 | _total_size 增量等于图片大小 |
| TC-UNIT-006 | US-MQ-001 | AC-MQ-001-01 | UNIT | 合法 upload_id 返回正确 bytes | 已存储 | get_upload(uid, 正确user_id) | 返回原始 bytes |
| TC-UNIT-007 | US-MQ-005 | AC-MQ-005-03 | UNIT | 不存在的 upload_id → ImageExpiredError | 空存储 | get_upload(不存在的uuid) | 抛 ImageExpiredError |
| TC-UNIT-008 | US-MQ-005 | AC-MQ-005-03 | UNIT | TTL 超期 → ImageExpiredError | 已存储但expire_at设为过去 | get_upload | 抛 ImageExpiredError |
| TC-UNIT-009 | US-MQ-005 | AC-MQ-005-03 | UNIT | TTL 超期条目被惰性清理 | 已存储但expire_at设为过去 | get_upload | 抛后条目不再在 _upload_store 中 |
| TC-UNIT-010 | US-MQ-010 | AC-MQ-010-02 | UNIT | user_id 不匹配 → ImageAccessDeniedError | 已存储 | get_upload(uid, 错误user_id) | 抛 ImageAccessDeniedError |
| TC-UNIT-011 | US-MQ-001 | AC-MQ-001-01 | UNIT | 同一 upload_id 在 TTL 内可多次取回 | 已存储 | 循环调用 get_upload 3次 | 每次均返回正确 bytes |
| TC-UNIT-012 | US-MQ-001 | AC-MQ-001-01 | UNIT | 删除后 _total_size 正确减少 | 已存储 | delete_upload | _total_size 减少等于图片大小 |
| TC-UNIT-013 | US-MQ-001 | AC-MQ-001-01 | UNIT | 删除后 upload_id 不再可取回 | 已存储 | delete_upload 后 get_upload | 抛 ImageExpiredError |
| TC-UNIT-014 | US-MQ-010 | AC-MQ-010-02 | UNIT | 删除不存在的 id 不抛异常 | 空存储 | delete_upload("nonexistent") | 无异常，静默忽略 |
| TC-UNIT-015 | US-MQ-007 | AC-MQ-007-02 | UNIT | 空存储 check_capacity 返回 True | 空存储 | check_capacity() | True |
| TC-UNIT-016 | US-MQ-007 | AC-MQ-007-02 | UNIT | 手动填满后 check_capacity 返回 False | _total_size=50MB | check_capacity() | False |
| TC-UNIT-017 | US-MQ-007 | AC-MQ-007-02 | UNIT | 清理过期后 check_capacity 恢复 True | 过期条目占49MB，_total_size设为满 | check_capacity() | True（惰性清理后） |
| TC-UNIT-018 | US-MQ-007 | AC-MQ-007-02 | UNIT | check_capacity 触发过期清理副作用 | 注入过期条目 | check_capacity() | 过期条目从 _upload_store 中消失 |
| TC-UNIT-019 | US-MQ-001 | AC-MQ-001-01 | UNIT | analyze_image mock 成功返回描述 | mock AsyncOpenAI | analyze_image(bytes, text) | 返回 description 字符串 |
| TC-UNIT-020 | US-MQ-009 | AC-MQ-009-01 | UNIT | 首次 TimeoutError 第二次成功（重试） | mock：第1次超时，第2次成功 | analyze_image | 返回描述，调用 2 次 |
| TC-UNIT-021 | US-MQ-009 | AC-MQ-009-02 | UNIT | 两次 TimeoutError → VisionServiceError | mock：始终超时 | analyze_image | 抛 VisionServiceError |
| TC-UNIT-022 | US-MQ-005 | AC-MQ-005-02 | UNIT | 4xx 错误直接 raise 不重试 | mock：status_code=400 | analyze_image | 抛 VisionServiceError，仅调用 1 次 |
| TC-UNIT-023 | US-MQ-001 | AC-MQ-001-01 | UNIT | VLM 返回空字符串 → 占位文案 | mock：返回 "" | analyze_image | 返回非空占位文案 |
| TC-UNIT-024 | US-MQ-008 | AC-MQ-008-02 | UNIT | analyze_image 日志不含 base64 字符串 | mock AsyncOpenAI，捕获 logger | analyze_image | 日志中无 base64 内容 |
| TC-UNIT-025 | US-MQ-009 | AC-MQ-009-02 | UNIT | 非 4xx 连接错误重试后 VisionServiceError | mock：始终 ConnectionError | analyze_image | 抛 VisionServiceError，调用 2 次 |

### 2.2 集成测试（INT）— test_chat_image_upload.py（REST）

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-INT-001 | US-MQ-001 | AC-MQ-001-01 | INT | 合法 PNG 上传 → 200，含 upload_id 和 expires_in | 已登录用户 | POST /api/chat/image-upload/ + MINIMAL_PNG | 200，upload_id 为 UUID，expires_in 为正整数 |
| TC-INT-002 | US-MQ-001 | AC-MQ-001-01 | INT | 合法 JPEG 上传 → 200 | 已登录用户 | POST + MINIMAL_JPEG | 200 |
| TC-INT-003 | US-MQ-004 | AC-MQ-004-02 | INT | 未认证请求 → 401 | 无 Token | POST 无认证头 | 401 |
| TC-INT-004 | US-MQ-007 | AC-MQ-007-02 | INT | 超过 10MB 文件 → 413 | 已登录用户 | POST + 11MB PNG | 413 |
| TC-INT-005 | US-MQ-007 | AC-MQ-007-02 | INT | 非图片内容（魔数检测失败）→ 400 | 已登录用户 | POST + 文本文件 | 400，含 error 字段 |
| TC-INT-006 | US-MQ-001 | AC-MQ-001-01 | INT | 缺少 image 字段 → 400 | 已登录用户 | POST 无 image 字段 | 400 |
| TC-INT-007 | US-MQ-001 | AC-MQ-001-01 | INT | 上传成功后 upload_id 在 vision_service 中可查 | 已登录用户 | POST + MINIMAL_PNG | 响应 upload_id 在 _upload_store 中 |
| TC-INT-008 | US-MQ-007 | AC-MQ-007-02 | INT | 存储满时 → 503 | mock check_capacity=False | POST | 503 |
| TC-INT-009 | US-MQ-008 | AC-MQ-008-02 | INT | 响应体不含图片 bytes 或 base64 | 已登录用户 | POST + MINIMAL_PNG | 响应中无 base64 编码内容 |
| TC-INT-010 | US-MQ-001 | AC-MQ-001-01 | INT | 多次上传产生不同 upload_id | 已登录用户 | POST × 5 | 5 个唯一 upload_id |

### 2.3 集成测试（INT）— test_consumers_multimodal.py（WS Consumer）

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-INT-101 | US-MQ-010 | AC-MQ-004-02 | INT | 无 image_upload_id 消息，路径与 v1.4.1 一致 | 已连接 WS，mock adapter | 发送纯文字 chat_message | 收到 stream_token + stream_end，无 vision_progress |
| TC-INT-102 | US-MQ-001 | AC-MQ-001-01 | INT | 非 UUID 格式 image_upload_id → IMAGE_INVALID 错误帧 | 已连接 WS | 发送 image_upload_id="not-a-uuid" | 收到 error code=IMAGE_INVALID |
| TC-INT-103 | US-MQ-002 | AC-MQ-002-01 | INT | message="" + upload_id → adapter 收到默认提问文案 | 已连接 WS，存储有 upload 条目，mock adapter | 发送 message="" + image_upload_id | adapter.stream_chat 调用时 message 含「请帮我分析这张图片」 |
| TC-INT-104 | US-MQ-004 | AC-MQ-004-03 | INT | 含有效 upload_id → 前端收到 vision_progress | 已连接 WS，存储有条目，mock adapter | 发送含 upload_id 消息 | 收到 vision_progress 消息，且在 stream_token 之前 |
| TC-INT-105 | US-MQ-005 | AC-MQ-005-03 | INT | get_upload 抛 ImageExpiredError → IMAGE_EXPIRED 错误帧，WS 保持 | 已连接 WS，patch get_upload 抛 ImageExpiredError | 发送含 upload_id 消息 | 收到 error code=IMAGE_EXPIRED；WS 可继续使用 |
| TC-INT-106 | US-MQ-005 | AC-MQ-005-01/02 | INT | VisionServiceError → IMAGE_ANALYSIS_FAILED，非 INTERNAL_ERROR | 已连接 WS，存储有条目，adapter 抛 VisionServiceError | 发送含 upload_id 消息 | 收到 error code=IMAGE_ANALYSIS_FAILED（非系统错误码） |
| TC-INT-107 | US-MQ-001 | AC-MQ-001-03 | INT | persist_enhanced_message kind → DB 写入增强消息 | 已连接 WS，存储有条目，mock adapter yield persist_enhanced_message | 发送含 upload_id 消息 | chat_memory.append_message 以含 [图片描述：] 的内容调用 |
| TC-INT-108 | US-MQ-010 | AC-MQ-010-02 | INT | ImageAccessDeniedError → IMAGE_INVALID 错误帧 | 已连接 WS，patch get_upload 抛 ImageAccessDeniedError | 发送含 upload_id 消息 | 收到 error code=IMAGE_INVALID |
| TC-INT-109 | US-MQ-010 | AC-MQ-004-02 | INT | 空 message 且无 upload_id → 静默忽略 | 已连接 WS | 发送 message="", 无 upload_id | 无响应消息（receive_nothing=True） |

---

## 3. 不可测试项

以下验收标准标注为 [NOT_TESTABLE] 或手工验证，不纳入自动化测试：

| AC-ID | 原因 | 验证方式 |
|-------|------|---------|
| AC-MQ-001-02（铭牌识别质量） | [NOT_TESTABLE — 需要真实铭牌图片样本和人工判断，无法自动化断言] | 人工抽检 3~5 样本 |
| AC-MQ-003-01/02/03（前端预览/删除/发送后清空） | [NOT_TESTABLE — 前端 UI 行为，需 vitest/Cypress] | 前端 vitest 覆盖 |
| AC-MQ-004-01（流式输出 UX 与纯文字一致） | [NOT_TESTABLE — UX 一致性需人工视觉验证] | 人工端到端测试 |
| AC-MQ-006-01/02（历史消息含图标注渲染） | [NOT_TESTABLE — 前端渲染逻辑] | 前端测试 |
| AC-MQ-007-01/03（客户端大小校验/自动压缩） | [NOT_TESTABLE — 前端 JS 逻辑] | 前端测试 |
| AC-MQ-008-01（uvicorn access log 无 base64） | [NOT_TESTABLE — 需运行时 tail log + grep，非单测] | 手工 tail log 验证 |
| AC-MQ-009-01 timing（≤30s 超时触发） | [NOT_TESTABLE — 等待 30s 超时实际触发不适合自动化测试，通过 mock 验证逻辑路径] | TC-UNIT-020/021 验证逻辑 |
| AC-MQ-009-03（超时期间 WS 心跳不中断） | [NOT_TESTABLE — 基础设施级，channels 框架保证] | 集成环境验证 |

---

## 4. 风险提示

1. TC-UNIT-020/021/025 使用 `asyncio.sleep` mock 跳过等待，测试执行时间正常，但实际超时等待行为须在集成环境验证（AC-MQ-009-01 timing 属性）。
2. TC-INT-101 的"向后兼容"仅验证 WS 消息类型存在，未验证 adapter 调用参数与 v1.4.1 完全一致（深度回归需专门的版本对比测试）。
3. 所有 VLM 相关测试均使用 mock，真实 doubao-vision 效果需在 staging 环境手工验证。
