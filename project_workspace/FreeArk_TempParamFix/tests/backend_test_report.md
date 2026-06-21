<!--
file_header:
  project: FreeArk_TempParamFix
  document: backend_test_report.md
  version: 1.0.0
  status: APPROVED
  author_agent: sub_agent_test_engineer
  created_at: 2026-06-21
  description: 后端测试报告——温度显示修复
-->

# 后端测试报告
**执行日期**：2026-06-21  
**分支**：fix/device-settings-temp-display

---

## 执行命令

```
cd FreeArkWeb/backend/freearkweb
python manage.py test api.tests --settings=freearkweb.test_settings --verbosity=2
```

## 结果

| 指标 | 数值 |
|------|------|
| 总测试数 | 1462 |
| 通过 | 1448（OK） |
| 跳过 | 14（SQLite 并发锁限制，标注 skip on SQLite） |
| 失败（FAIL） | 0 |
| 错误（ERROR） | 0 |

**结论：PASS**

---

## 关键变更测试说明

### test_UT_VL_13_temp_setting_display_divides_by_ten（原 test_UT_VL_13_temp_setting_display_with_unit）

更新内容：
- 原断言：`assertIn('24', result)` 和 `assertIn('℃', result)`（raw=24 → "2.4 ℃"，但 "24" 不在结果中，原断言与旧代码行为偶然一致，与新逻辑不符）
- 新断言：验证 130→"13.0 ℃"，260→"26.0 ℃"，255→"25.5 ℃"，"100"→"10.0 ℃"，None→"—"，以及 `_temperature` 不被除以10

### 回归验证

1462 个测试全量执行，无回归。其中包含：
- `IsWritableV050Tests`（15项）：全部 PASS
- `ParamValueLabelTests`（13项含更新的VL-13）：全部 PASS
- `ReqFunc001~004` 集成测试：全部 PASS
- `RegressionProtectionTests`：全部 PASS
- `V051ModeEnumAlignmentTests`：全部 PASS
- `HandleWriteAckTests`：全部 PASS
- 其余 model/serializer/e2e 测试：全部 PASS
