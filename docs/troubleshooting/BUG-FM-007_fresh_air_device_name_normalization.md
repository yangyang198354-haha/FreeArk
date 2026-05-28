# BUG-FM-007 RCA：新风机设备名称归一化

**版本**：v0.6.3  
**状态**：已修复  
**日期**：2026-05-28

---

## 现象

故障管理列表中，`product_code=130004` 的设备（新风机）显示的 `device_name` 为"新风"，
而非预期的"新风机"。用户预期与设备卡片、产品标签保持一致（均显示"新风机"）。

---

## 根因

### DB 数据现状

生产 `device_node` 表中，`product_code=130004` 的设备 `device_name` 字段**全部为"新风"**（634 条统一）。

这是屏侧设备名称的原始值，通过 `device_tree_sync.py:248` 的同步逻辑写入：
```python
# device_tree_sync.py:248（只读引用）
node.device_name = item.get('deviceName', '')  # 直接覆盖，用屏侧原始名
```

### 为何不直接改 DB 或 sync 逻辑

1. **直接 UPDATE DB**：下次 `device_tree_sync` 同步后会被屏侧原始值覆盖，改动无效。
2. **修改 device_tree_sync.py**：是核心同步逻辑，风险大，影响面广，需要专项测试。

### 选择 serializer 层归一化

在 `serializers_fault.py` 的 `get_device_name()` 方法中，在返回前查询 `DEVICE_NAME_OVERRIDE` 字典。
该方案：
- 影响范围最小：只影响故障事件 API 的 `device_name` 字段
- 可逆：只需删除 `DEVICE_NAME_OVERRIDE` 条目即可回退
- 不影响 DB 数据、设备树同步、其他模块

---

## 修复方案

### `constants.py` 新增 `DEVICE_NAME_OVERRIDE`

```python
DEVICE_NAME_OVERRIDE: dict = {
    '130004': '新风机',
}
```

### `serializers_fault.py` 修改 `get_device_name()`

```python
def get_device_name(self, obj):
    try:
        sn = int(obj.device_sn)
    except (ValueError, TypeError):
        return None
    raw = get_device_name_by_sn(sn)
    if raw is not None:
        override = DEVICE_NAME_OVERRIDE.get(str(obj.product_code))
        if override:
            return override
    return raw
```

关键逻辑：
- 仅在 `raw is not None`（缓存命中）时应用覆盖
- cache miss 时返回 `None`，前端走 `device_type_label` 兜底（`PRODUCT_CODE_LABELS['130004']='新风机'`）

---

## 影响范围

- `fault_consumer/constants.py`：新增 `DEVICE_NAME_OVERRIDE`
- `serializers_fault.py`：`get_device_name()` 增加 override 检查
- 不涉及 `device_name_cache.py`、`device_tree_sync.py`、DB schema、前端

---

## 未来扩展

如需归一化更多设备名称，只需在 `DEVICE_NAME_OVERRIDE` 中添加 `product_code → 显示名` 映射，
无需修改其他代码。
