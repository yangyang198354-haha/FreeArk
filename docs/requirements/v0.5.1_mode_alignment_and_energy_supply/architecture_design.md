# v0.5.1 架构设计文档

**项目**：FreeArk  
**版本**：v0.5.1  
**需求包**：mode 枚举对齐 + 集中能源供给字段设置  
**状态**：APPROVED  
**日期**：2026-05-20

---

## 1. 架构决策摘要

v0.5.1 不引入新服务、不变更 DB Schema、不新增依赖库。所有变更为现有模块内的局部修正与扩展。

### ADR-01：operation_mode 枚举统一为 1-4（不做数据迁移）

**决策**：展示层适配历史值 0 → 显示"制冷"；写入层严格校验 1-4；不执行数据库迁移脚本。

**影响模块**：`param_value_label.py`、`plc_write_manager.py`、`plc_data_viewer_gui.py`、`DeviceCardsView.vue`、`plc_config.json`

### ADR-02：central_energy_supply 独立写入路径

**决策**：`central_energy_supply` 加入 `WRITABLE_PARAM_NAMES` 精确名白名单（与 v0.5.0 `away_energy_saving` 同机制）；值域 1/2/3；PLC 地址 DB14 offset=103 独立写入，不与 `operation_mode` 共用值。

### ADR-03：write_mode_for_building 重构

**决策**：拆分为 `write_operation_mode_for_building(mode: int)` 和独立的 `write_central_energy_supply_for_device(device_id, value)` 两个路径。`write_mode_for_building` 保留签名但仅写 `operation_mode`（DB14 offset=89），不再联动写 `central_energy_supply`。

---

## 2. 受影响文件清单

| 层次 | 文件 | 变更类型 |
|------|------|---------|
| 后端 — 标签映射 | `api/param_value_label.py` | 枚举键 0→1-4；新增 central_energy_supply 精确名 |
| 后端 — 可写白名单 | `api/views_device_settings.py` | WRITABLE_PARAM_NAMES 追加 central_energy_supply |
| 后端 — 测试 | `api/tests/test_device_settings_v050.py` | 更新 UT_W_13、IT_REG_06，新增 v0.5.1 测试用例 |
| 数据采集 — 写管理器 | `datacollection/plc_write_manager.py` | 新增 MODE_DEHUMIDIFICATION=4，重构 write_mode_for_building |
| 数据采集 — GUI | `datacollection/plc_data_viewer_gui.py` | 删除除湿静默降级逻辑 |
| 前端 — 卡片视图 | `FreeArkWeb/frontend/src/views/DeviceCardsView.vue` | central_energy_supply 三值展示 |
| 配置 | `plc_config.json` | operation_mode 新增 enum_values 注释 |

---

## 3. 技术栈（无变更）

- 后端：Django REST Framework + SQLite（测试）/ MySQL（生产）
- 前端：Vue 3 + Element Plus
- PLC 通信：snap7，DB14 数据块
- 部署：物理机，plink + git pull（本次不涉及）
