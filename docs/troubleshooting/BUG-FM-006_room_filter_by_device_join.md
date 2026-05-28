# BUG-FM-006 RCA：温控面板按房间无法区分

**版本**：v0.6.3  
**状态**：已修复  
**日期**：2026-05-28

---

## 现象

用户在故障管理页面选择"书房温控面板"、"主卧温控面板"、"儿童房温控面板"等 sub_type 过滤器时，
返回结果与"客厅温控面板"完全相同——所有温控类 sub_type 均展示了相同的故障列表，无法按房间区分。

---

## 根因

### v0.6.2 临时方案的局限

BUG-FM-005（v0.6.2）修复了 sub_type 过滤对 `error_N` 通用故障码失效的问题，
引入了 `SUB_TYPE_TO_PRODUCT_CODES` 字典，通过 `product_code__in` 过滤。

但该方案的设计权衡（已在 v0.6.2 文档中记录）：
- `error_N` 通用故障码本身**不携带房间维度信息**
- 温控相关 product_code 只有两个：260001（主温控）和 120003（温控面板）
- 所有温控类 sub_type（living_room/study_room/bedroom/children_room 等）均映射到相同的
  `product_code` 集合，导致过滤结果集完全相同

### 数据模型中的房间信息

生产数据库中，房间维度存储在 `device_node JOIN device_room` 的关联中：

```
device_node.device_sn  →  唯一标识设备实例
device_node.room_id    →  关联 device_room
device_room.ori_room_name  →  '客厅' / '书房' / '次卧' / '主卧' / '儿童房'
```

生产分布（2026-05 实测）：
| product_code | ori_room_name | 户数 |
|---|---|---|
| 260001 (主温控) | 客厅 | 634 |
| 120003 (温控面板) | 次卧 | 634 |
| 120003 (温控面板) | 主卧 | 634 |
| 120003 (温控面板) | 儿童房 | 634 |
| 120003 (温控面板) | 书房 | 418 |

`fault_event.device_sn` 是 VARCHAR，`DeviceNode.device_sn` 是 IntegerField，
需要做类型转换 `[str(s) for s in sn_qs]`。

---

## 修复方案

### 核心思路

在过滤时，通过 `device_node JOIN device_room` 的子查询，根据 `ori_room_name` 关键词
取得该房间内设备的 `device_sn` 集合，再用 `Q(device_sn__in=sns)` 过滤故障事件。

### 新增常量：`SUB_TYPE_ROOM_FILTER`

`fault_consumer/constants.py` 新增字典，替代旧的 `SUB_TYPE_TO_PRODUCT_CODES`：

```python
SUB_TYPE_ROOM_FILTER: dict = {
    # (product_codes, room_keywords)；room_keywords 为空表示不过滤房间
    'living_room_thermostat':           (['260001'], []),          # 主温控天然=客厅
    'study_room_thermostat':            (['120003'], ['书房', '次卧']),
    'bedroom_thermostat':               (['120003'], ['主卧']),
    'children_room_thermostat':         (['120003'], ['儿童房']),
    'fourth_children_room_thermostat':  (['120003'], ['儿童房']),   # 与 children_room 等价
    'fresh_air_unit':                   (['130004'], []),
    'hydraulic_module':                 (['270001'], []),
    'energy_meter':                     (['250001'], []),
    'air_quality_sensor':               (['100007'], []),
}
```

### views_fault.py 过滤逻辑

```python
room_filter = SUB_TYPE_ROOM_FILTER.get(st)
if room_filter:
    product_codes, room_keywords = room_filter
    if room_keywords:
        regex_pattern = '|'.join(map(re.escape, room_keywords))
        sn_qs = DeviceNode.objects.filter(
            product_code__in=product_codes,
            room__ori_room_name__regex=regex_pattern,
        ).values_list('device_sn', flat=True)
        device_sns.extend(str(s) for s in sn_qs)
    else:
        direct_product_codes.extend(product_codes)
```

### 设计决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 缓存 | 不引入（第一版） | device_node ~5000 行，子查询 <5ms；过早优化无必要 |
| fourth_children_room | 保留，映射到"儿童房"关键词 | 用户决定不删、不改名；device_room 无独立分组 |
| living_room | 直接 product_code=260001，无房间过滤 | 260001 天然只在客厅，无需 JOIN |
| study_room | 映射书房+次卧 | 沿用 utils_room_filter v0.5.7 历史语义 |

---

## 影响范围

- `fault_consumer/constants.py`：新增 `SUB_TYPE_ROOM_FILTER`，删除 `SUB_TYPE_TO_PRODUCT_CODES`
- `views_fault.py`：sub_type 过滤逻辑重写
- 不涉及前端、DB schema、device_tree_sync

---

## 向后兼容性

- 命名型 fault_code（`Q(fault_code__in=fault_codes)`）路径保留
- `fresh_air_unit` 的 `fault_code__startswith='fresh_air_fault_bit_'` 前缀分支保留
- 非温控类 sub_type（hydraulic_module/energy_meter/air_quality_sensor/fresh_air_unit）
  均使用 `room_keywords=[]`，行为与 v0.6.2 一致
