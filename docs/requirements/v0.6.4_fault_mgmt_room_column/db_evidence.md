# DB 实测证据（v0.6.4 前置调研）

```
document_id: DB-EVIDENCE-v0.6.4
title: 生产 DB 实测 — 房间/设备链路验证
project: FreeArk v0.6.4 fault_mgmt_room_column
created_at: 2026-05-29
status: COMPLETED — 主线已在生产执行 4 条查询并粘贴结果（2026-05-29）
```

本文件记录 v0.6.4 需求规格正式产出前，在生产数据库（192.168.31.98:3306, 库 freeark）上执行的四条验证查询及其原始结果。

PM Orchestrator 无法直接 SSH 执行命令，以下为已备好的查询命令。请将结果粘贴至对应"原始结果"节后回报，PM 将核查是否与假设一致，如有矛盾立即停下报告偏差。

---

## 执行前准备

```bash
# 如公司 DNS 不识别 vicp.fun，先解析 IP：
nslookup et116374mm892.vicp.fun 8.8.8.8
# 记下解析到的 IP，替换下面命令中的 <PROD_IP>

# 以下所有命令在 Bash（非 PowerShell）中执行
PROD_IP=<上面解析到的IP>
WORKDIR=/home/yangyang/Freeark/FreeArk
MANAGE="venv/bin/python FreeArkWeb/backend/freearkweb/manage.py dbshell"
```

---

## 查询 1：3-1-602 完整设备链路

**验证目标**：4 房户型 `specific_part='3-1-6-602'` 应见 5 台设备（1 台 260001 客厅 + 4 台 120003 分布主卧/次卧/儿童房/书房）。

```bash
ssh -p 57279 -o StrictHostKeyChecking=no yangyang@$PROD_IP \
  "cd $WORKDIR && echo \"
SELECT dn.device_sn, dn.product_code, dn.device_name,
       dr.ori_room_name, dr.room_name, df.floor_no
FROM device_node dn
JOIN device_room dr ON dn.room_id = dr.id
JOIN device_floor df ON dr.floor_id = df.id
JOIN owner_info oi ON df.owner_id = oi.id
WHERE oi.specific_part = '3-1-6-602'
  AND dn.product_code IN ('120003','260001')
ORDER BY dn.product_code, dr.ori_room_name;
\" | $MANAGE"
```

### 原始结果

```
device_sn  product_code  device_name  ori_room_name  room_name  floor_no
22554      120003        温控面板      主卧          主卧        1
22552      120003        温控面板      书房          书房        1
22555      120003        温控面板      儿童房        儿童房      1
22553      120003        温控面板      次卧          次卧        1
22158      260001        主温控        客厅          客厅        1
```

**结论**：A-01 ✓ — 3-1-6-602 是 4 房户型，1 台 260001（客厅·主温控）+ 4 台 120003（主卧/次卧/儿童房/书房·温控面板），ori_room_name 一一区分。

---

## 查询 2：3 房户型对照（两步）

**步骤 2a — 找一个 3 房样本**（device_node 中温控设备共 4 台的户型）：

```bash
ssh -p 57279 -o StrictHostKeyChecking=no yangyang@$PROD_IP \
  "cd $WORKDIR && echo \"
SELECT oi.specific_part, COUNT(dn.id) AS device_cnt
FROM owner_info oi
JOIN device_floor df ON df.owner_id = oi.id
JOIN device_room dr ON dr.floor_id = df.id
JOIN device_node dn ON dn.room_id = dr.id
  AND dn.product_code IN ('120003','260001')
GROUP BY oi.specific_part
HAVING COUNT(dn.id) = 4
LIMIT 5;
\" | $MANAGE"
```

### 原始结果（步骤 2a）

```
specific_part  device_cnt
1-1-16-1601    4
1-1-16-1602    4
1-2-16-1601    4
1-2-16-1602    4
10-1-16-1601   4
```

选 `1-1-16-1601` 用于步骤 2b。

**步骤 2b — 用取到的 specific_part 查该户型设备清单**（将 `<THREE_ROOM_SP>` 替换为 2a 结果中的值）：

```bash
ssh -p 57279 -o StrictHostKeyChecking=no yangyang@$PROD_IP \
  "cd $WORKDIR && echo \"
SELECT dn.device_sn, dn.product_code, dn.device_name,
       dr.ori_room_name, dr.room_name, df.floor_no
FROM device_node dn
JOIN device_room dr ON dn.room_id = dr.id
JOIN device_floor df ON dr.floor_id = df.id
JOIN owner_info oi ON df.owner_id = oi.id
WHERE oi.specific_part = '<THREE_ROOM_SP>'
  AND dn.product_code IN ('120003','260001')
ORDER BY dn.product_code, dr.ori_room_name;
\" | $MANAGE"
```

### 原始结果（步骤 2b — specific_part = 1-1-16-1601）

```
device_sn  product_code  device_name  ori_room_name  room_name  floor_no
22550      120003        温控面板      主卧          主卧        1
22549      120003        温控面板      儿童房        儿童房      1
22551      120003        温控面板      次卧          次卧        1
22001      260001        主温控        客厅          客厅        1
```

**结论**：A-02 ✓ — 3 房户型只有 4 台设备（客厅 + 主卧 + 次卧 + 儿童房），**无书房**，验证 plc_config.json 中 `study_room_*` 在 3 房无对应物理面板（PLC 寄存器存在但无设备实体）。

---

## 查询 3：fault_event 故障码分布（四房/儿童房相关）

```bash
ssh -p 57279 -o StrictHostKeyChecking=no yangyang@$PROD_IP \
  "cd $WORKDIR && echo \"
SELECT fault_code, COUNT(*) AS cnt FROM fault_event
WHERE fault_code REGEXP '(children_room|fourth_children_room|study_room|bedroom)'
GROUP BY fault_code ORDER BY cnt DESC;
\" | $MANAGE"
```

### 原始结果（故障码分布）

```
（fault_code REGEXP 'children_room|fourth_children_room|study_room|bedroom' 返回零行）
```

**重大发现**：fault_event 表中 **不存在任何字面 PLC 前缀格式** 的 fault_code。constants.py L125-126 注释原文已说明：
> 生产数据库中命名型 fault_code 实际上不存在（见 BUG-FM-005 RCA），本映射保留用于兼容未来可能出现的命名型故障码。

实际 fault_event 中 fault_code 分布（全表 top 20）：

```
fault_code          cnt
comm_fault_timeout  1294
error_679           767
error_265           477
error_496           199
error_194           123
error_709           95
error_739           70
error_769           48
error_193           44
error_799           40
error_82            21
error_140           20
error_733           7
error_734           3
error_673           1
error_674           1
error_675           1
error_764           1
error_765           1
```

也就是说 fault_code 是 `comm_fault_timeout`（通信超时统一码）+ `error_NNN`（数字编码，对应 PLC 故障位的 register × 16 + bit 之类的映射）。

**A-03 修正**：不能通过 fault_code 文本匹配反推 PLC 前缀；必须通过 device_sn → device_node.room → device_room.ori_room_name 反查。这恰好就是方案 Y 的过滤路径，无需依赖 fault_code 命名。

**反向验证（通过 3-1-602 各设备 device_sn 查 fault_event）**：

```bash
ssh -p 57279 -o StrictHostKeyChecking=no yangyang@$PROD_IP \
  "cd $WORKDIR && echo \"
SELECT fe.fault_code, fe.device_sn, fe.specific_part,
       dr.ori_room_name AS device_room_name
FROM fault_event fe
LEFT JOIN device_node dn ON CAST(dn.device_sn AS CHAR) = fe.device_sn
LEFT JOIN device_room dr ON dn.room_id = dr.id
WHERE fe.fault_code LIKE 'fourth_children_room_%'
GROUP BY fe.fault_code, fe.device_sn, fe.specific_part, dr.ori_room_name
LIMIT 20;
\" | $MANAGE"
```

### 原始结果（fourth_children_room 追踪）

文本前缀查询无记录（见上一节），改为按 device_sn 反查：

```sql
SELECT fe.device_sn, fe.fault_code, COUNT(*) AS cnt
FROM fault_event fe
WHERE fe.device_sn IN ('22552','22553','22554','22555','22158')
GROUP BY fe.device_sn, fe.fault_code
ORDER BY fe.device_sn, cnt DESC;
```

结果：

```
device_sn  fault_code           cnt   设备角色（来自查询1）
22158      comm_fault_timeout    82   客厅 · 主温控 (260001)
22158      error_679             18
22552      comm_fault_timeout    82   书房 · 温控面板 (120003)
22552      error_709             60
22553      comm_fault_timeout    82   次卧 · 温控面板 (120003)
22553      error_739             52
22554      comm_fault_timeout    82   主卧 · 温控面板 (120003)
22554      error_769             33
22554      error_709              1   ← 主卧异常出现 1 条 error_709（书房 code），疑似单次跨房间误报或硬件交叉，需关注
22555      comm_fault_timeout    82   儿童房 · 温控面板 (120003)
22555      error_799             40
```

**error_code → PLC 前缀 → 4 房物理房间 反推表**：

| error_code | 主要 device_sn | ori_room_name | 推断 PLC 前缀 |
|------------|----------------|---------------|---------------|
| error_679 | 22158 | 客厅 | `living_room_*` |
| error_709 | 22552 | 书房 | `study_room_*` |
| error_739 | 22553 | 次卧 | `bedroom_*` |
| error_769 | 22554 | 主卧 | `children_room_*` |
| error_799 | 22555 | 儿童房 | `fourth_children_room_*` |

**完美吻合 plc_config.json description 的双户型映射**（`children_room_*` 在 4 房就是主卧、`bedroom_*` 在 4 房就是次卧、`study_room_*` 在 4 房就是书房、`fourth_children_room_*` 在 4 房就是儿童房）。

**A-04 ✓ 修正版**：fourth_children_room_* 故障在 fault_event 中对应 device_sn=22555，反查 ori_room_name="儿童房"，假设成立。

**异常 ⚠**：22554（主卧）出现 1 条 error_709（书房 code），孤例（vs 主码 error_769 的 33 条），可能是单次硬件交叉或日志误标，**v0.6.4 方案不依赖 error_code → 房间的直接映射**（仍走 device_sn 反查 room），所以此异常不影响重构方案，但建议留档观察。

---

## 查询 4：device_name 分布（product_code × ori_room_name）

```bash
ssh -p 57279 -o StrictHostKeyChecking=no yangyang@$PROD_IP \
  "cd $WORKDIR && echo \"
SELECT dn.product_code, dr.ori_room_name, dn.device_name, COUNT(*) AS cnt
FROM device_node dn
JOIN device_room dr ON dn.room_id = dr.id
WHERE dn.product_code IN ('120003','260001')
GROUP BY dn.product_code, dr.ori_room_name, dn.device_name
ORDER BY cnt DESC;
\" | $MANAGE"
```

### 原始结果

```
product_code  ori_room_name  device_name  cnt
260001        客厅           主温控        634
120003        次卧           温控面板      634
120003        主卧           温控面板      634
120003        儿童房         温控面板      634
120003        书房           温控面板      418
```

**结论**：A-05/A-06 ✓ — ori_room_name 取值集合 = {客厅, 主卧, 次卧, 儿童房, 书房}，与 plc_config.json 物理房间映射一致。device_name 不能用于 1:1 区分（120003 设备全叫"温控面板"），方案 Y 必须用 `(product_code, ori_room_name)` 复合键。

全小区户数：260001×客厅 = 634 户总数；120003×书房 = 418 户 4 房；推断 216 户 3 房（v0.6.1 OQ-01 实测的复核一致）。

---

## 已知事实（来自本地仓库文件，无需 DB 验证）

**来自 `datacollection/resource/plc_config.json` description 字段（权威）**：

| PLC 参数前缀 | description | 3 房语义 | 4 房语义 |
|------------|-------------|---------|---------|
| `living_room_*` | 客厅 | 客厅 | 客厅 |
| `bedroom_*` | 三房主卧四房次卧 | 主卧 | 次卧 |
| `children_room_*` | 三房儿童房四房主卧 | 儿童房 | 主卧 |
| `study_room_*` | 三房次卧四房书房 | 次卧 | 书房 |
| `fourth_children_room_*` | 四房儿童房 | 不适用 | 儿童房 |

**来自 v0.6.1 OQ-01 实测（2026-05-28，已确认）**：

| product_code | ori_room_name | 行数 | 户型推断 |
|-------------|--------------|------|---------|
| 260001 | 客厅 | 634 | 全部 |
| 120003 | 次卧 | 634 | 全部 |
| 120003 | 主卧 | 634 | 全部 |
| 120003 | 儿童房 | 634 | 全部 |
| 120003 | 书房 | 418 | 仅 4 房 |

推断：216 户 3 房（无书房）；418 户 4 房（有书房）。

---

## 假设验证汇总（实测完成）

| 假设编号 | 假设内容 | 状态 | 证据来源 |
|---------|---------|------|---------|
| A-01 | 3-1-6-602 有 1 台 260001(客厅) + 4 台 120003(主卧/次卧/儿童房/书房) | ✓ 成立 | 查询 1 |
| A-02 | 3 房户型只有 3 台 120003（主卧/次卧/儿童房）+ 1 台 260001 客厅，无书房面板 | ✓ 成立 | 查询 2（1-1-16-1601） |
| A-03 | fault_code 中包含字面 PLC 前缀（fourth_children_room_*_error 等） | ✗ 不成立（修正） | 查询 3 — 生产中只有 `error_NNN` 与 `comm_fault_timeout`，无命名型；constants.py L125-126 注释已说明 |
| A-04 | fourth_children_room 系故障对应 device 的 ori_room_name = "儿童房" | ✓ 成立（反查证明） | 查询 3 反向 — device_sn=22555 (儿童房) 主码 error_799 = fourth_children_room_* 区段 |
| A-05 | ori_room_name 取值集合 = {客厅, 主卧, 次卧, 儿童房, 书房} | ✓ 成立 | 查询 4 |
| A-06 | PLC 参数前缀 description 与 device_room.ori_room_name 语义一致 | ✓ 成立 | 查询 1+3反查+4 三方交叉 |

## 关键架构含义（DB 实测后更新）

1. **fault_event 的 fault_code 是 `error_NNN` 数字码 + `comm_fault_timeout`**，不是字面 PLC 前缀。因此 v0.6.4 sub_type 过滤**不能依赖 fault_code 文本匹配**，必须走「device_sn → device_node → device_room.ori_room_name + product_code」复合过滤（方案 Y 的实际实现路径，与 constants.py 现状已一致，重构后保留这条主路径）。

2. **SUB_TYPE_TO_FAULT_CODES 的字面值在重构后仍可保留**（兼容未来命名型码、OR 联合过滤的精确匹配），但不应是过滤主路径。

3. **error_code → 房间反推表（4 房）已用 3-1-602 数据闭环验证**，可作为 v0.6.4 测试用例的 oracle。

4. **零异常 1 条**：device_sn 22554 (主卧) 出现 1 条 error_709 (书房 code)，孤例不影响重构方案，留档观察。
