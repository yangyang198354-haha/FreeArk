# v0.5.1 测试报告

**版本**：v0.5.1 | **日期**：2026-05-20  
**测试环境**：SQLite（in-memory）| PLC 写入：mock MQTT，不连接真实 PLC

---

## 单元测试结果

### 更新用例（原 v0.5.0，已同步修正）

| ID | 描述 | 结论 |
|----|------|------|
| test_UT_W_13 | central_energy_supply 可写 | PASS |
| test_IT_REG_06 | central_energy_supply 可写 | PASS |
| test_UT_VL_01 | operation_mode 枚举键 1-4 | PASS |
| test_UT_VL_06 | 历史值 0 兼容展示制冷 | PASS |
| test_UT_VL_07 | operation_mode=1 → 制冷 | PASS |

### 新增 v0.5.1 单元测试（V051ModeEnumAlignmentTests — 13 用例）

| ID | 描述 | 结论 |
|----|------|------|
| test_UT_V051_01 | operation_mode=1 → 制冷 | PASS |
| test_UT_V051_02 | operation_mode=2 → 制热 | PASS |
| test_UT_V051_03 | operation_mode=3 → 通风 | PASS |
| test_UT_V051_04 | operation_mode=4 → 除湿 | PASS |
| test_UT_V051_05 | key=0 不在选项中 | PASS |
| test_UT_V051_06 | 历史值 0 兼容展示制冷 | PASS |
| test_UT_V051_07 | central_energy_supply 可写 | PASS |
| test_UT_V051_08 | central_energy_supply 三值选项 | PASS |
| test_UT_V051_09 | central_energy_supply=1 → 制冷 | PASS |
| test_UT_V051_10 | central_energy_supply=2 → 制热 | PASS |
| test_UT_V051_11 | central_energy_supply=3 → 无 | PASS |
| test_UT_V051_12 | 历史值 0 不崩溃 | PASS |
| test_UT_V051_13 | 除湿不降级验证（key=4 ≠ 制冷） | PASS |

### 新增 v0.5.1 集成测试（V051CentralEnergySupplyWriteTests — 7 用例）[MOCK-ANNOTATED]

| ID | 描述 | 结论 |
|----|------|------|
| test_IT_V051_01 | 写入值=1（制冷）返回 202 | PASS [MOCK] |
| test_IT_V051_02 | 写入值=2（制热）返回 202 | PASS [MOCK] |
| test_IT_V051_03 | 写入值=3（无，主动关阀）返回 202 | PASS [MOCK] |
| test_IT_V051_04 | _is_writable 确认 | PASS |
| test_IT_V051_05 | operation_mode 仍可写（回归） | PASS |
| test_IT_V051_06 | 写入值=0 返回 400（枚举越界） | PASS |
| test_IT_V051_07 | 写入值=4 返回 400（枚举越界） | PASS |

---

## 汇总

| 项目 | 值 |
|------|---|
| 总用例数 | 25（更新 5 + 新增单元 13 + 新增集成 7）|
| 通过率 | 100%（25/25）|
| mock 标注项 | 3 项（test_IT_V051_01/02/03，PLC 写入通过 mock MQTT）|
| 实连 PLC 测试 | 0（无真实 PLC 可连接，均使用 mock，已明确标注）|

---

## 声明

**未执行生产部署。** 本次测试在 SQLite 环境完成，所有 PLC 写入通过 mock MQTT client 模拟。生产部署（plink + git pull → 树莓派 192.168.31.51）需用户另行 CONFIRM 后由 devops-engineer 执行。
