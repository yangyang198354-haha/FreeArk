<!--
file_header:
  project: FreeArk_TempParamFix
  document: test_plan.md
  version: 1.0.0
  status: APPROVED
  author_agent: sub_agent_test_engineer
  created_at: 2026-06-21
  description: 测试计划——温度显示与步进控件修复
-->

# 测试计划
**项目**：FreeArk_TempParamFix  
**版本**：1.0.0  
**日期**：2026-06-21

---

## 一、测试范围

| 层次 | 覆盖内容 |
|------|---------|
| 后端单元测试 | `get_display_value` 对 `_temp_setting` 的换算逻辑；None/非数字兜底；不影响 `_temperature` |
| 后端集成测试（回归） | 原有 1462 个测试全量通过，零回归 |
| 前端单元测试（vitest） | 步进换算、边界禁用、反向换算、初始化、格式化、非温度参数 |

---

## 二、测试用例矩阵

| 测试 ID | 层次 | 关联 AC | 描述 | 运行方式 |
|--------|------|---------|------|---------|
| UT-VL-13 (更新) | 后端单元 | AC-001-01/02/03 | `_temp_setting` 除以10换算 | Django test |
| TC-INIT-01~04 | 前端单元 | US-001 | 初始化展示值（底层整数÷10） | vitest |
| TC-FMT-01~04 | 前端单元 | US-001 | 格式化显示（一位小数+℃） | vitest |
| TC-STEP-01~09 | 前端单元 | US-002/003/004 | 步进逻辑+边界clamp | vitest |
| TC-DISABLE-01~04 | 前端单元 | US-003/004 | 按钮禁用条件 | vitest |
| TC-SUBMIT-01~07 | 前端单元 | US-006 | 反向换算（×10整数字符串） | vitest |
| TC-NTEMP-01~05 | 前端单元 | US-007 | 非温度参数不受影响 | vitest |
| TC-FLOAT-01~02 | 前端单元 | REQ-NFUNC-001 | 浮点精度保证 | vitest |
| TC-BOUNDS-01~03 | 前端单元 | REQ-FUNC-006 | 边界映射完整性 | vitest |

---

## 三、门控标准

| 指标 | 标准 | 实际 |
|------|------|------|
| 后端测试通过率 | 100%（0 FAIL，0 ERROR） | 1462/1462 PASS |
| 前端 vitest 通过率（我们的测试文件） | 100% | 38/38 PASS |
| 后端回归（已有测试） | 0 新增失败 | 确认 0 回归 |
| CRITICAL code review finding | 0 | 0 |
