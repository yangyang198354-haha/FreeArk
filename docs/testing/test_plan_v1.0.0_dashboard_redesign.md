# 测试计划

```
file_header:
  document_id: TEST-PLAN-v1.0.0-DASHBOARD-REDESIGN
  title: 系统看板重设计 + 设备列表凝露提醒列 — 测试计划
  author_agent: sub_agent_test_engineer
  project: FreeArk 住宅能耗/暖通监控平台
  version: v1.0.0
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: DRAFT
```

---

## 1. 测试范围

| 层级 | 内容 |
|------|------|
| 单元测试（后端） | 2 个新 API 端点逻辑；device-list 凝露字段注入 |
| 集成测试（后端） | API 路由正常响应（含认证）；字段类型正确性 |
| 手工验证项 | 前端页面渲染（需本地 npm run dev）；hover 动效；点击跳转 |

## 2. 测试文件

| 文件 | 位置 |
|------|------|
| `test_v100_dashboard_redesign.py` | `FreeArkWeb/backend/freearkweb/api/tests/` |

## 3. 执行命令（真实可复现命令）

```powershell
# 从项目根目录进入 backend
cd C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend\freearkweb

# 执行本次新增测试（SQLite 内存 DB，不连接生产）
python manage.py test freearkweb.api.tests.test_v100_dashboard_redesign `
    --settings=freearkweb.test_settings --verbosity=2
```

## 4. 测试用例汇总

| 测试 ID | 测试类 | 测试方法 | 验收标准 | 对应需求 |
|---------|-------|---------|---------|---------|
| UT-CL-01 | DeviceListCondensationFieldTest | test_UT_CL_01_has_active_condensation_true | has_active_condensation=True | REQ-FUNC-CL-01 / US-CL-01 AC-CL-01-01 |
| UT-CL-02 | DeviceListCondensationFieldTest | test_UT_CL_02_has_active_condensation_false_no_record | has_active_condensation=False（无记录） | AC-CL-01-02 |
| UT-CL-04 | DeviceListCondensationFieldTest | test_UT_CL_04_recovered_condensation_returns_false | is_active=False 返回 False | AC-CL-01-05 |
| UT-CL-field | DeviceListCondensationFieldTest | test_UT_CL_field_always_present | 所有 result 行含 has_active_condensation | AC-CL-01-03 |
| UT-FS-01 | FaultSummaryAPITest | test_UT_FS_01_active_fault_count | active_fault_count=3（排除已恢复） | US-DC-01 AC-DC-01-01 |
| UT-FS-02 | FaultSummaryAPITest | test_UT_FS_02_affected_unit_count_distinct | affected_unit_count=2（去重） | AC-DC-01-02 |
| UT-FS-03 | FaultSummaryAPITest | test_UT_FS_03_no_fault_returns_zero | 无故障返回 0/0 | REQ-FUNC-DC-01 |
| UT-FS-struct | FaultSummaryAPITest | test_UT_FS_response_structure | success=True + 两个必要键 | REQ-FUNC-DC-01 |
| UT-DFS-01 | DeviceFaultSummaryAPITest | test_UT_DFS_01_returns_four_categories | 4 类键均存在 | US-DC-02~05 |
| UT-DFS-01b | DeviceFaultSummaryAPITest | test_UT_DFS_01b_device_node_total | total >= 1 | REQ-FUNC-DC-06 |
| UT-DFS-02 | DeviceFaultSummaryAPITest | test_UT_DFS_02_thermostat_includes_product_code_260001_and_120003 | thermostat_panels fault_count=2 | US-DC-03 AC-DC-03-02 |
| UT-DFS-02c | DeviceFaultSummaryAPITest | test_UT_DFS_02c_recovered_fault_not_counted | fresh_air fault_count=1（排除已恢复） | US-DC-04 |
| UT-DFS-03 | DeviceFaultSummaryAPITest | test_UT_DFS_03_empty_db_returns_zeros | 所有 fault_count=0 | REQ-FUNC-DC-06 |
| UT-DFS-hm | DeviceFaultSummaryAPITest | test_UT_DFS_hydraulic_module_fault_count | hydraulic_module fault_count=2 | US-DC-05 |
| UT-AUTH-01a | NewAPIAuthTest | test_UT_AUTH_01a_fault_summary_requires_auth | 未认证返回 401 | 安全要求 |
| UT-AUTH-01b | NewAPIAuthTest | test_UT_AUTH_01b_device_fault_summary_requires_auth | 未认证返回 401 | 安全要求 |

## 5. 覆盖率目标

| 指标 | 目标 | 说明 |
|------|------|------|
| 单元测试通过率 | ≥80%（所有测试用例 PASS） | 见上表 16 个用例 |
| 集成测试通过率 | ≥90% | API 端点含认证、路由、响应格式验证 |
| US-* 覆盖 | 全部 9 个 US 有测试 | 后端逻辑覆盖；前端部分手工验证 |

## 6. 手工验证检查清单（需本地运行前端）

- [ ] HomeView 看板页面正常加载，4 组标题行可见（能耗概览/设备状态/故障与子设备/趋势与日志）
- [ ] 5 张新卡片显示数值（故障总数、空气品质传感器、温控面板、新风、水力模块）
- [ ] 故障总数卡片显示「影响 N 户」副信息
- [ ] 鼠标 hover 新卡片时有上移+阴影动效（250ms ease-out）
- [ ] 点击任意新卡片时光标为 pointer
- [ ] 点击故障总数卡片 → 跳转到 /device-management/faults?is_active=true
- [ ] 点击温控面板卡片 → URL 包含 5 个 sub_type 重复参数
- [ ] 故障管理页面通过 URL sub_type 参数自动初始化过滤器
- [ ] 设备列表页面「故障数量」列之后出现「凝露提醒」列
- [ ] 有活跃凝露的住户行显示橙色「有」
- [ ] 无活跃凝露的住户行显示灰色「无」
- [ ] 现有卡片（今日用电量、PLC在线等）仍正常展示，hover 行为不变
