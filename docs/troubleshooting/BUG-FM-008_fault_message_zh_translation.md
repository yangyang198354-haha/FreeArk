# BUG-FM-008 RCA：故障描述中文化

**版本**：v0.6.3  
**状态**：已修复  
**日期**：2026-05-28

---

## 现象

故障管理列表中，`fault_message` 字段显示英文格式，如：
- `error_140` → "Error 140"
- `error_82` → "Error 82"
- `comm_fault_timeout` → "Comm fault timeout"

用户预期显示中文描述，如"低温故障"、"新风机停机故障"、"通信超时"。

---

## 根因

`fault_classifier.py` 的 `get_fault_message()` 函数采用通用格式化逻辑：

```python
def get_fault_message(param_name: str) -> str:
    msg = param_name.replace('_', ' ').capitalize()
    return msg[:255]
```

该逻辑对所有故障码一律进行"下划线替换+首字母大写"，无中文映射能力。

文档 `监听数据包含的内容.docx` 中已有完整的故障码中文描述，但未被集成到代码中。

---

## 修复方案

### `constants.py` 新增 `ERROR_CODE_LABELS`

将 docx 中整理的故障码中文描述以字典形式集中维护：

```python
ERROR_CODE_LABELS: dict = {
    'comm_fault_timeout': '通信超时',
    'error_140': '低温故障',
    'error_82':  '新风机停机故障',
    # ... 完整列表见 constants.py
}
```

覆盖范围：
- 水力模块（270001）：error_140、error_82
- 主温控（260001）：error_673~679
- 儿童房温控面板（120003 sn=22549）：error_703~709
- 主卧温控面板（120003 sn=22550）：error_733~739
- 次卧温控面板（120003 sn=22551）：error_763~769
- 空气品质（100007）：error_194
- 通用命名型 fault_code：5 个

### `fault_classifier.py` 重写 `get_fault_message()`

优先级：
1. `ERROR_CODE_LABELS` 字典查表
2. `error_N` 通用兜底："设备故障 (错误码 N)"
3. 其他（`fresh_air_fault_bit_N` 等）：保持原 capitalize 逻辑

```python
def get_fault_message(param_name: str) -> str:
    if param_name in ERROR_CODE_LABELS:
        return ERROR_CODE_LABELS[param_name][:255]
    m = _ERROR_N_DIGITS.match(param_name)
    if m:
        return f'设备故障 (错误码 {m.group(1)})'[:255]
    return param_name.replace('_', ' ').capitalize()[:255]
```

### 历史数据回填

新增 Management Command：`backfill_fault_message_zh`

```bash
# 预览影响行数
python manage.py backfill_fault_message_zh --dry-run

# 实际执行
python manage.py backfill_fault_message_zh
```

回填逻辑与 `get_fault_message()` 保持一致，幂等安全，可重复执行。

---

## 影响范围

- `fault_consumer/constants.py`：新增 `ERROR_CODE_LABELS`
- `fault_consumer/fault_classifier.py`：重写 `get_fault_message()`
- `management/commands/backfill_fault_message_zh.py`：新增回填命令
- 不涉及 `fault_utils.py`（禁止修改）、DB schema、前端

---

## 注意事项

1. 未映射的 `error_N` 会显示通用兜底"设备故障 (错误码 N)"，优于原英文格式
2. 命名型 fault_code 未在字典中的，仍走 capitalize 逻辑（保持现有行为）
3. 部署后需执行 `backfill_fault_message_zh` 更新历史记录
