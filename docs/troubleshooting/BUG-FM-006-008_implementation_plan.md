# v0.6.3 实施计划：BUG-FM-006 / BUG-FM-007 / BUG-FM-008

**版本**：v0.6.3  
**日期**：2026-05-28

---

## 变更文件清单

### 修改的文件

| 文件 | 变更内容 |
|---|---|
| `api/fault_consumer/constants.py` | 版本号更新为 v0.6.3；新增 `SUB_TYPE_ROOM_FILTER`（替代 `SUB_TYPE_TO_PRODUCT_CODES`）；新增 `DEVICE_NAME_OVERRIDE`；新增 `ERROR_CODE_LABELS` |
| `api/views_fault.py` | sub_type 过滤逻辑重写，使用 `SUB_TYPE_ROOM_FILTER` + `DeviceNode` 子查询 |
| `api/serializers_fault.py` | `get_device_name()` 增加 `DEVICE_NAME_OVERRIDE` 覆盖逻辑 |
| `api/fault_consumer/fault_classifier.py` | `get_fault_message()` 重写：字典查表 + error_N 兜底 + 原逻辑保留 |

### 新增的文件

| 文件 | 说明 |
|---|---|
| `api/management/commands/backfill_fault_message_zh.py` | 历史 fault_message 回填命令（支持 --dry-run） |
| `docs/troubleshooting/BUG-FM-006_room_filter_by_device_join.md` | RCA 文档 |
| `docs/troubleshooting/BUG-FM-007_fresh_air_device_name_normalization.md` | RCA 文档 |
| `docs/troubleshooting/BUG-FM-008_fault_message_zh_translation.md` | RCA 文档 |

---

## 部署步骤

### 1. 代码更新

```bash
git pull
```

### 2. 验证测试通过

```bash
cd FreeArkWeb/backend/freearkweb
python manage.py test api.tests_fault_event --settings=freearkweb.settings
```

### 3. 历史数据回填（先 dry-run 确认影响行数）

```bash
python manage.py backfill_fault_message_zh --dry-run
# 确认行数后执行实际回填
python manage.py backfill_fault_message_zh
```

### 4. 验证生产效果

```bash
# 检查新风机故障的 device_name（应显示"新风机"）
# 检查 error_140 的 fault_message（应显示"低温故障"）
# 检查各 sub_type 过滤按房间区分
```

---

## 回滚方案

如需回滚：
1. `git revert` 本次提交
2. 重新运行测试验证
3. 无需回填（DB 的 fault_message 字段已通过历史回填更新，但旧格式不影响功能）

---

## 不在本次范围的工作

- 删除"第四儿童房温控面板"选项（用户决定保留现状）
- 前端修改（无需变更）
- DB schema 变更（无）
- device_tree_sync 修改（有意避免，风险大）
