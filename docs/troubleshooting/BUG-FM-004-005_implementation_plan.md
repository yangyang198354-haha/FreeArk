# BUG-FM-004 / BUG-FM-005 实施计划

**版本**：v0.6.2-FM
**日期**：2026-05-28
**作者**：software-developer agent（PARTIAL_FLOW 编排）

---

## 修改文件清单

### 1. `FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py`

| 修改点 | 类型 | 说明 |
|--------|------|------|
| 新增 `SUB_TYPE_TO_PRODUCT_CODES` dict | 新增 | 9 个 sub_type → product_code 列表映射，用于 OR 联合过滤（BUG-FM-005） |
| `SUB_TYPE_TO_FAULT_CODES` 注释增补 | 修改 | 说明保留原因及 OR 联合设计 |
| `PRODUCT_CODE_LABELS` 新增 `'260002'` | 新增 | 生产有 3 条无标签故障记录，暂标"未知设备 260002" |
| 模块文档字符串更新至 v0.6.2-FM | 修改 | 记录变更历史和设计权衡 |

### 2. `FreeArkWeb/backend/freearkweb/api/views_fault.py`

| 修改点 | 类型 | 说明 |
|--------|------|------|
| 新增 `SUB_TYPE_TO_PRODUCT_CODES` 导入 | 修改 | 从 constants 导入新映射 |
| `specific_part` 过滤：新增 3 段格式分支 | 修改 | BUG-FM-004：3 段输入用 startswith+endswith 匹配 4 段 DB 值 |
| `sub_type` 过滤：新增 product_code OR 分支 | 修改 | BUG-FM-005：fault_code OR product_code 联合过滤 |
| 模块文档字符串更新至 v0.6.2-FM | 修改 | 记录版本 |

### 3. 新增文档

| 文件 | 说明 |
|------|------|
| `docs/troubleshooting/BUG-FM-004_room_number_segments_mismatch.md` | RCA 文档 |
| `docs/troubleshooting/BUG-FM-005_sub_type_filter_breaks_on_generic_error_codes.md` | RCA 文档 |
| `docs/troubleshooting/BUG-FM-004-005_implementation_plan.md` | 本文件 |

---

## 不修改的文件

- `api/fault_utils.py` — 禁区，constants.py 注释明确说明
- `api/serializers_fault.py` — `fault-event-categories` 接口只暴露标签，不需要 `SUB_TYPE_TO_PRODUCT_CODES`
- 前端任何文件 — 两个 BUG 的修复均在后端完成，前端零改动

---

## 关键设计决策记录

### BUG-FM-004：为何选方案 B（后端段式解析）而非方案 A（前端改 4 段）

- 方案 A 需要修改 `building_data.js` 中所有房号 value，并同步迁移测试数据，改动面大
- 方案 B 仅修改过滤分支，前端无感知，3 段格式是更自然的用户输入形式（无楼层概念）
- 方案 B 向后兼容：4 段格式输入仍走 icontains，遗留数据不受影响

### BUG-FM-005：为何保留 `SUB_TYPE_TO_FAULT_CODES` 而非替换

- OR 联合策略：两个映射在不同场景互补，不应互相替代
- 命名型 fault_code 未来可能出现（固件升级），保留可直接生效
- `comm_fault_timeout` 的 comm 类 sub_type 依赖此映射仍可正常工作

### `260002` 标签问题

生产实测有 3 条 `product_code=260002` 的故障记录，但该 product_code 未在已知设备清单中出现。
暂标"未知设备 260002"，待硬件团队确认真实设备名称后更新。
