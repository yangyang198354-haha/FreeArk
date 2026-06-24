特性：多模态提问——用户图片输入与豆包视觉模型理解
版本：v1.5.0_multimodal_question
状态：DRAFT
日期：2026-06-24
作者：test-engineer

---

# 单元测试报告 — v1.5.0 多模态提问

## 1. 执行摘要

| 项目 | 值 |
|------|---|
| 执行时间 | 2026-06-24 |
| 执行环境 | Windows 11 / Python 3.11 / Django 5.2.7 / SQLite（跳过，无 DB 依赖） |
| 测试文件 | `api/tests/test_vision_service.py` |
| 执行命令 | `python manage.py test api.tests.test_vision_service --verbosity=2` |
| 实际执行耗时 | 0.702s |

### 统计（算术等式验证）

| 指标 | 值 |
|------|---|
| Total | 25 |
| Pass | 25 |
| Fail | 0 |
| Skip | 0 |
| Blocked | 0 |

**验证**：total = pass + fail + skip + blocked = 25 + 0 + 0 + 0 = **25** ✓

### 通过率

```
通过率 = pass / (pass + fail) × 100%
       = 25 / (25 + 0) × 100%
       = 100.00%
```

### 门控结论

```
门控阈值：80%
实际通过率：100.00%
门控结论：PASSED — 可进行集成测试
```

---

## 2. 按模块分项结果

### 2.1 TestStoreUpload（store_upload 接口）

| TC-ID | 关联 AC | 描述 | 结果 |
|-------|--------|------|------|
| TC-UNIT-001 | AC-MQ-001-01 | store_upload 返回 UUID4 格式字符串 | PASS |
| TC-UNIT-002 | AC-MQ-001-01 | store_upload 后条目在存储中可取回 | PASS |
| TC-UNIT-003 | AC-MQ-007-02 | 总量超限时 raise StorageCapacityError | PASS |
| TC-UNIT-004 | AC-MQ-007-02 | 惰性清理：先存 TTL=0 条目，store_upload 时清理后成功 | PASS |
| TC-UNIT-005 | AC-MQ-001-01 | store_upload 后 _total_size 正确增加 | PASS |

小计：5/5 PASS（100%）

### 2.2 TestGetUpload（get_upload 接口）

| TC-ID | 关联 AC | 描述 | 结果 |
|-------|--------|------|------|
| TC-UNIT-006 | AC-MQ-001-01 | 合法 upload_id 返回正确 bytes | PASS |
| TC-UNIT-007 | AC-MQ-005-03 | 不存在的 upload_id → raise ImageExpiredError | PASS |
| TC-UNIT-008 | AC-MQ-005-03 | TTL 超期（expire_at 在过去）→ raise ImageExpiredError | PASS |
| TC-UNIT-009 | AC-MQ-005-03 | TTL 超期条目被惰性清理，后续不再存在 | PASS |
| TC-UNIT-010 | AC-MQ-010-02 | user_id 不匹配 → raise ImageAccessDeniedError | PASS |
| TC-UNIT-011 | AC-MQ-001-01 | 同一 upload_id 在 TTL 内可多次取回（不删除） | PASS |

小计：6/6 PASS（100%）

### 2.3 TestDeleteUpload（delete_upload 接口）

| TC-ID | 关联 AC | 描述 | 结果 |
|-------|--------|------|------|
| TC-UNIT-012 | AC-MQ-001-01 | 删除后 _total_size 正确减少 | PASS |
| TC-UNIT-013 | AC-MQ-001-01 | 删除后 upload_id 不再可取回 | PASS |
| TC-UNIT-014 | AC-MQ-010-02 | 删除不存在的 id 不抛异常（静默忽略） | PASS |

小计：3/3 PASS（100%）

### 2.4 TestCheckCapacity（check_capacity 接口）

| TC-ID | 关联 AC | 描述 | 结果 |
|-------|--------|------|------|
| TC-UNIT-015 | AC-MQ-007-02 | 空存储返回 True | PASS |
| TC-UNIT-016 | AC-MQ-007-02 | 手动填满 _total_size 后返回 False | PASS |
| TC-UNIT-017 | AC-MQ-007-02 | 清理过期后空间释放，check_capacity 恢复 True | PASS |
| TC-UNIT-018 | AC-MQ-007-02 | check_capacity 会清理过期条目（副作用验证） | PASS |

小计：4/4 PASS（100%）

### 2.5 TestAnalyzeImage（analyze_image VLM 调用，异步）

| TC-ID | 关联 AC | 描述 | 结果 |
|-------|--------|------|------|
| TC-UNIT-019 | AC-MQ-001-01 | Mock AsyncOpenAI 成功 → 返回 description | PASS |
| TC-UNIT-020 | AC-MQ-009-01 | 首次 TimeoutError，第二次成功（重试逻辑） | PASS |
| TC-UNIT-021 | AC-MQ-009-02 | 两次 TimeoutError → raise VisionServiceError | PASS |
| TC-UNIT-022 | AC-MQ-005-02 | 4xx HTTP 错误 → 直接 raise，不重试（调用次数=1） | PASS |
| TC-UNIT-023 | AC-MQ-001-01 | VLM 返回空字符串 → 返回非空占位文案 | PASS |
| TC-UNIT-024 | AC-MQ-008-02 | analyze_image 日志中不含 base64 字符串 | PASS |
| TC-UNIT-025 | AC-MQ-009-02 | 非 4xx 连接错误重试后 VisionServiceError（调用次数=2） | PASS |

小计：7/7 PASS（100%）

---

## 3. US-MQ-* 覆盖矩阵

| US-ID | 关联 TC | 结果 |
|-------|--------|------|
| US-MQ-001 | TC-UNIT-001/002/005/006/011/012/013/019/023 | 全部 PASS |
| US-MQ-002 | （AC-MQ-002 在集成测试 TC-INT-103 覆盖） | — |
| US-MQ-005 | TC-UNIT-007/008/009/021/022/025 | 全部 PASS |
| US-MQ-007 | TC-UNIT-003/004/015/016/017/018 | 全部 PASS |
| US-MQ-008 | TC-UNIT-024 | PASS |
| US-MQ-009 | TC-UNIT-020/021/025 | 全部 PASS |
| US-MQ-010 | TC-UNIT-010/014 | 全部 PASS |

---

## 4. 失败汇总

无失败用例。
