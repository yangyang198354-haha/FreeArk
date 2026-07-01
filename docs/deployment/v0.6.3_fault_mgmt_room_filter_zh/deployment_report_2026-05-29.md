# v0.6.3 故障管理 房间过滤/设备名归一化/故障描述中文化 部署报告

| 项 | 值 |
|---|---|
| 版本 | v0.6.3-FM |
| BUG | BUG-FM-006（房间过滤）/ BUG-FM-007（新风名归一化）/ BUG-FM-008（故障描述中文化） |
| commit | `a825e0d feat(fault-mgmt): v0.6.3 房间过滤/设备名归一化/故障描述中文化 (BUG-FM-006/007/008)` |
| 部署日期 | 2026-05-29 |
| 部署人 | Claude Code (Opus 4.7) |
| 目标 | 生产 — 树莓派 `192.168.31.51` / `et116374mm892.vicp.fun:57279`（部署时本地 DNS 异常，用解析后 IP `115.236.153.170` + `HostKeyAlias` 直连） |
| 方式 | ssh + `git pull` + systemd restart + `manage.py backfill_fault_message_zh` |
| 结果 | ✅ 成功，三个 BUG 在生产 ORM 实测中均验证生效 |

---

## 1. 变更范围（纯后端，无前端、无 migration）

| 文件 | 类型 |
|---|---|
| `FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py` | 新增 `SUB_TYPE_ROOM_FILTER` / `DEVICE_NAME_OVERRIDE` / `ERROR_CODE_LABELS`；删除 v0.6.2 的 `SUB_TYPE_TO_PRODUCT_CODES` |
| `FreeArkWeb/backend/freearkweb/api/views_fault.py` | sub_type 过滤分支重写，加 `DeviceNode JOIN device_room.ori_room_name` Subquery |
| `FreeArkWeb/backend/freearkweb/api/serializers_fault.py` | `get_device_name()` 增加 `DEVICE_NAME_OVERRIDE` 覆盖检查 |
| `FreeArkWeb/backend/freearkweb/api/fault_consumer/fault_classifier.py` | `get_fault_message()` 改为字典查表 → error_N 兜底 → 原 capitalize 逻辑 |
| `FreeArkWeb/backend/freearkweb/api/tests_fault_event.py` | 追加 `TestBugFM006/007/008` 共 23 个用例 |
| `FreeArkWeb/backend/freearkweb/api/management/commands/backfill_fault_message_zh.py` | **新增** 历史回填 management command |
| `docs/troubleshooting/BUG-FM-006_room_filter_by_device_join.md` | RCA |
| `docs/troubleshooting/BUG-FM-007_fresh_air_device_name_normalization.md` | RCA |
| `docs/troubleshooting/BUG-FM-008_fault_message_zh_translation.md` | RCA |
| `docs/troubleshooting/BUG-FM-006-008_implementation_plan.md` | 实施计划 |

---

## 2. 部署前置检查

| 检查项 | 结果 |
|---|---|
| 本地测试 | `python manage.py test api.tests_fault_event` → **170/170 通过**（原 147 + 新增 23） |
| 生产 HEAD（拉取前） | `e6e2b7b` (v0.6.2 BUG-FM-004/005) |
| 本次 commit 范围 vs 本地长期修改 | `.env`、`heartbeat_broker_config.json`、`package-lock.json` 零交集，安全 |
| 本地 DNS 解析 | 异常（公司 DNS 暂时无法解析 `vicp.fun`）→ 用公网 DNS（8.8.8.8）解析得 `115.236.153.170`，IP + `HostKeyAlias` workaround |

---

## 3. 部署步骤执行记录

### Step 1 — 拉代码
```
ssh ... yangyang@115.236.153.170 'cd /home/yangyang/Freeark/FreeArk && git pull origin main'
→ Updating e6e2b7b..a825e0d Fast-forward
  10 files changed, 1183 insertions(+), 90 deletions(-)
```

### Step 2 — 重启服务（含发现的服务清单缺漏）

⚠️ **过程中发现**：freeark-prod-deploy skill 文档遗漏了 `freeark-fault-consumer.service`（fault_event 写入路径的实际服务）。第一轮只重启 `backend + mqtt-consumer`，新 INSERT 仍是英文 `'Error 265'`。MySQL processlist 排查后定位、补重启 `freeark-fault-consumer`，新 INSERT 才变成中文。

| 服务 | 重启原因 | 结果 |
|---|---|---|
| `freeark-backend` | `views_fault.py` / `serializers_fault.py` / `constants.py` 改动 | `active` ✓ |
| `freeark-mqtt-consumer` | 防御性（constants.py 共享 import） | `active` ✓ |
| **`freeark-fault-consumer`**（第二轮才发现） | **fault_classifier.get_fault_message() 实际由此服务调用写入** | `active` ✓ |

`/api/health/` → `{"status":"ok",...}` ✓

> **教训已写入 memory**：`project_freeark_systemd_services.md`。后续修改 `api/fault_consumer/` 下任何文件必须重启 `freeark-fault-consumer`。

**生产实测验证**（fault-consumer 重启后的新 INSERT）：
```
id=2971 fault_code=error_679 fault_message='通信故障'              created_at=2026-05-29 07:49:12
id=2972 fault_code=error_265 fault_message='设备故障 (错误码 265)' created_at=2026-05-29 07:49:29
```
✅ 写入路径已生效。

### Step 3 — 历史数据回填
```
manage.py backfill_fault_message_zh --dry-run
→ [DRY-RUN] 预计回填行数：2956 行

manage.py backfill_fault_message_zh
→ 全部完成（中途 ssh client 断连但服务端 python 跑完）
```

**回填后覆盖率最终验证**：

| 指标 | 值 |
|---|---|
| fault_event 总行数 | 3094 |
| 英文 `Error N` 格式残留 | **0** |
| 英文其他 capitalize 格式残留 | **0** |
| 中文 fault_message 覆盖 | **3094 (100%)** |

高频映射结果：
- `comm_fault_timeout` → `通信超时` × 1294
- `error_679` → `通信故障` × 721
- `error_265` → `设备故障 (错误码 265)` × 443（兜底）
- `error_194` → `空气品质设备故障` × 115
- `error_82` → `新风机停机故障` × 21
- `error_140` → `低温故障` × 20

### Step 4 — 生产 ORM 验证（关键 — 三 BUG 全部实证）

#### BUG-FM-006：温控面板按房间区分（v0.6.2 等价问题彻底解决）

| sub_type | product_code | room 关键词 | device_sn 集合 | fault 命中数 |
|---|---|---|---|---|
| `living_room_thermostat`（客厅） | `260001` | — | — | **801** |
| `study_room_thermostat`（书房） | `120003` | 书房 \| 次卧 | 1052 | **328** |
| `bedroom_thermostat`（主卧） | `120003` | 主卧 | 634 | **190** |
| `children_room_thermostat`（儿童房） | `120003` | 儿童房 | 634 | **198** |

四个 sub_type **返回不同数据**，房间维度成功区分（修复前 v0.6.2 4 个均返回 1028 同一集合）。

#### BUG-FM-007：新风名归一化

| 来源 | 值 |
|---|---|
| `DeviceNode.device_name`（DB） | `'新风'` |
| `DEVICE_NAME_OVERRIDE['130004']` | `'新风机'` |
| Serializer 输出 | `'新风机'` ✓（override 命中） |

device_tree_sync 周期同步**不会**影响显示（归一化在 serializer 边界）。

#### BUG-FM-008：故障描述中文化

| fault_code | 输出 |
|---|---|
| `error_140` | `'低温故障'` ✓ |
| `error_82` | `'新风机停机故障'` ✓ |
| `error_679` | `'通信故障'` ✓ |
| `comm_fault_timeout` | `'通信超时'` ✓ |
| `error_193` | `'设备故障 (错误码 193)'` ✓（兜底正确） |
| `fresh_air_fault_bit_3` | `'Fresh air fault bit 3'` ✓（保持原 capitalize） |

---

## 4. 设计权衡 / 已知限制

### BUG-FM-006 性能
- Subquery 每次请求多查一次 `DeviceNode JOIN device_room`，估算 < 5ms（device_node ≈ 5000 行）
- 第一版不引入缓存（避免过早优化）。未来如发现性能问题，可加 `device_room_cache.py`（参考 `device_name_cache.py` 模式）

### BUG-FM-008 兜底说明
- 用户提供的 3 个示例（error_140/82/193）只有 140 和 82 在 docx 中明确有命名，error_193 docx 未提及
- 实际映射按 docx 内容：error_140 = "低温故障"（属水力模块），error_82 = "新风机停机故障"（同水力模块）
- 未在字典内的 error_N 自动走兜底"设备故障 (错误码 N)"

### 第四儿童房保留
- 按用户决定，`fourth_children_room_thermostat` 下拉项保留，行为与 `children_room_thermostat` 等价（均匹配儿童房）
- 设备面板 PLC 参数统计（`fault_utils.py` 的 `fourth_children_room_*_error`）保持不变，四房户型第二儿童房的故障数继续统计

---

## 5. 风险 / 回滚

### 风险
- ✅ 测试 170/170 通过
- ✅ 三 BUG 生产 ORM 实测验证
- ✅ 无 DB schema 变更，无前端改动
- ✅ backfill 命令幂等，可重复执行

### 回滚
```bash
# 代码回滚
ssh ... yangyang@115.236.153.170 \
  'cd /home/yangyang/Freeark/FreeArk && git reset --hard e6e2b7b && \
   sudo systemctl restart freeark-backend && sudo systemctl restart freeark-mqtt-consumer'

# fault_message 回滚（DB 数据回滚 —— 谨慎使用）
# 注意：回滚后 fault_message 显示英文 "Error 140" 等，但 fault_code 不变
# 若仅代码回滚而不动 fault_message，新数据回到英文格式，但已回填的历史数据仍是中文（数据不一致）
```

---

## 6. 生产验证建议（请用户验证）

浏览器 **Ctrl+F5** 强刷 故障管理页面：

### BUG-FM-006 房间过滤
1. 选"客厅温控面板" → 列出 801 条左右（仅 product_code=260001，无房间过滤）
2. 选"书房温控面板" → 列出 328 条左右（次卧+书房）
3. 选"主卧温控面板" → 列出 190 条左右
4. 选"儿童房温控面板" → 列出 198 条左右
5. 选"第四儿童房温控面板"（已保留）→ 应与"儿童房"等价
6. **关键**：4 个温控 sub_type 应返回**不同**数据（v0.6.2 是同一集合）

### BUG-FM-007 新风机命名
- 看任何新风机故障 → "设备名称"列应显示"新风机"（不再是"新风"）

### BUG-FM-008 故障描述
- "故障描述"列显示中文：低温故障 / 新风机停机故障 / 通信故障 / 通信超时 / 内置温度传感器故障 等
- 未映射的 error_N 显示"设备故障 (错误码 N)"

---

## 7. 关联文档

- RCA: `docs/troubleshooting/BUG-FM-006_room_filter_by_device_join.md`
- RCA: `docs/troubleshooting/BUG-FM-007_fresh_air_device_name_normalization.md`
- RCA: `docs/troubleshooting/BUG-FM-008_fault_message_zh_translation.md`
- 实施计划: `docs/troubleshooting/BUG-FM-006-008_implementation_plan.md`
- 上游修复: `docs/deployment/v0.6.2_fault_mgmt_filter_fix/deployment_report_2026-05-28.md`
- 上游修复: `docs/deployment/v0.6.1_fault_mgmt_ux/BUG-FM-003/deployment_report_2026-05-28.md`
