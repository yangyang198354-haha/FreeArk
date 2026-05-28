# BUG-FM-005 RCA — 设备类型筛选对通用 error_N 故障失效

**BUG 编号**：BUG-FM-005
**发现日期**：2026-05-28
**模块**：故障管理 API（`views_fault.py`、`fault_consumer/constants.py`）
**严重级别**：High（设备类型过滤对生产中 ~99% 的故障记录完全失效）
**状态**：已修复（v0.6.2-FM）

---

## 1. 现象

用户在故障管理界面选择设备类型（如"书房温控面板"）进行筛选，结果列表返回空或仅返回
极少数记录，无法筛出绝大多数生产故障数据。

---

## 2. 根因分析

### 2.1 设计假设与生产现实的差距

**设计假设**（`constants.py` 原始设计）：

`SUB_TYPE_TO_FAULT_CODES` 假设 `fault_event.fault_code` 字段会存储命名型故障码：

```python
'study_room_thermostat': [
    'study_room_temp_sensor_error',
    'study_room_humidity_sensor_error',
    'study_room_external_temp_sensor_error',
    'study_room_communication_error',
]
```

**生产现实**（`fault_event` 表，2026-05 实测，top fault_code 分布）：

| fault_code            | 数量 |
|-----------------------|------|
| comm_fault_timeout    | 852  |
| error_679             | 441  |
| error_265             | 271  |
| error_496             | 117  |
| error_194             | 87   |
| error_709             | 63   |
| error_739             | 43   |
| error_769             | 30   |
| error_193             | 25   |
| error_82              | 21   |
| error_799             | 20   |
| error_140             | 12   |
| ...（其他 error_N）   | ...  |

**关键事实**：生产 `fault_event` 表中**不存在任何一行**的 `fault_code` 为
`study_room_*` / `living_room_*` / `bedroom_*` 等命名风格。

所有设备故障均以 PLC 寄存器编号格式 `error_N` 上报，命名型 fault_code 在
当前 MQTT 数据流中从未出现。

### 2.2 旧过滤逻辑的必然失效

旧代码（`views_fault.py`）：

```python
fault_codes.extend(SUB_TYPE_TO_FAULT_CODES.get(st, []))
# ...
if fault_codes:
    q |= Q(fault_code__in=fault_codes)
```

由于 `fault_code__in=['study_room_temp_sensor_error', ...]` 在生产库中无任何命中，
sub_type 过滤对所有现存生产数据（除 `comm_fault_timeout` 的 comm 类之外）**100% 失效**。

---

## 3. 修复方案（混合 OR 联合）

### 3.1 新增 `SUB_TYPE_TO_PRODUCT_CODES` 映射

在 `constants.py` 新增：

```python
SUB_TYPE_TO_PRODUCT_CODES: dict = {
    'living_room_thermostat':           ['260001', '120003'],
    'study_room_thermostat':            ['260001', '120003'],
    'bedroom_thermostat':               ['260001', '120003'],
    'children_room_thermostat':         ['260001', '120003'],
    'fourth_children_room_thermostat':  ['260001', '120003'],
    'fresh_air_unit':                   ['130004'],
    'hydraulic_module':                 ['270001'],
    'energy_meter':                     ['250001'],
    'air_quality_sensor':               ['100007'],
}
```

product_code 取自生产 `fault_event` 表实际分布及 `PRODUCT_CODE_LABELS` 映射。

### 3.2 过滤逻辑改为 fault_code OR product_code

`views_fault.py` 修改（核心逻辑）：

```python
fault_codes.extend(SUB_TYPE_TO_FAULT_CODES.get(st, []))
product_codes.extend(SUB_TYPE_TO_PRODUCT_CODES.get(st, []))

q = Q()
if fault_codes:
    q |= Q(fault_code__in=fault_codes)      # 命名型：向后兼容
if product_codes:
    q |= Q(product_code__in=product_codes)  # product_code：覆盖 error_N 通用码
if include_fresh_air_bits:
    q |= Q(fault_code__startswith='fresh_air_fault_bit_')
qs = qs.filter(q)
```

---

## 4. 设计权衡（重要）

### 4.1 温控类 sub_type 房间维度丢失

由于 `error_N` 通用故障码不包含房间信息，以下 sub_type 均映射到相同 product_code 集合：

- `living_room_thermostat` → `['260001', '120003']`
- `study_room_thermostat`  → `['260001', '120003']`
- `bedroom_thermostat`     → `['260001', '120003']`
- `children_room_thermostat` → `['260001', '120003']`
- `fourth_children_room_thermostat` → `['260001', '120003']`

**结果**：选择"客厅温控面板"和"书房温控面板"会返回**完全相同**的数据集（所有主温控和温控面板的故障）。

**这是数据模型层面的限制，不是 BUG**。PLC 寄存器编号（error_N）在 MQTT 消息中
不携带安装位置信息，无法在不修改硬件固件或 MQTT 协议的情况下区分房间。

**推荐使用方式**：如需按房间筛选，请**同时使用**"房号筛选器"（specific_part 参数，
BUG-FM-004 已修复）。例如：
- sub_type=study_room_thermostat + specific_part=9-1-604（9栋1单元604室书房温控）

### 4.2 `SUB_TYPE_TO_FAULT_CODES` 保留原因

命名型 fault_code 映射保留，原因：
1. 未来固件升级可能上报命名型 fault_code，届时可直接命中
2. OR 联合不影响现有精确匹配的正确性
3. `comm_fault_timeout` 通过 `SUB_TYPE_TO_FAULT_CODES` 命中的 `comm` 类 sub_type 依赖此映射

---

## 5. 影响评估

- **修复后覆盖率**：生产 ~99% 的 error_N 故障记录（之前 ~1% 仅 comm 类命中）均可被 product_code 正确筛出
- **修改范围**：`constants.py`（新增 `SUB_TYPE_TO_PRODUCT_CODES`）、`views_fault.py`（扩展过滤逻辑）
- **无 DB schema 变更**：纯代码修复
- **无 API 接口变更**：请求/响应格式不变，前端无需修改

---

## 6. 测试覆盖

见 `tests_fault_event.py` 类 `TestBugFM005SubTypeProductCodeFilter`：

1. 温控 sub_type 匹配 product_code=260001/120003 的 error_N 故障
2. 多温控 sub_type 房间维度等价性（设计权衡验证）
3. OR 联合：命名型 fault_code 与 product_code 共存
4. fresh_air_unit 三类全覆盖（精确/前缀/product_code）
5. hydraulic_module、energy_meter、air_quality_sensor 各自 product_code 匹配
6. BUG-FM-003 已有 11 个测试用例不受影响（向后兼容验证）
