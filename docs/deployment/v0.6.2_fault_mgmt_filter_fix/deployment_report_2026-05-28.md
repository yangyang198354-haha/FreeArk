# v0.6.2 故障管理筛选修复部署报告（BUG-FM-004 / BUG-FM-005）

| 项 | 值 |
|---|---|
| 版本 | v0.6.2-FM |
| BUG 编号 | BUG-FM-004（房号段数）/ BUG-FM-005（设备类型对 error_N 失效） |
| commit | `e6e2b7b fix(fault-mgmt): v0.6.2 房号段数匹配 + 设备类型 product_code 过滤 (BUG-FM-004/005)` |
| 部署日期 | 2026-05-28 |
| 部署人 | Claude Code (Opus 4.7) |
| 目标 | 生产 — 树莓派 `192.168.31.51` / `et116374mm892.vicp.fun:57279` |
| 方式 | ssh + `git pull` + systemd restart（符合"禁 pscp"硬约束） |
| 结果 | ✅ 成功，生产真实数据验证两 BUG 均已修复 |

---

## 1. 变更范围（后端 + 文档）

| 文件 | 类型 |
|---|---|
| `FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py` | 新增 `SUB_TYPE_TO_PRODUCT_CODES`；补 `PRODUCT_CODE_LABELS['260002']` |
| `FreeArkWeb/backend/freearkweb/api/views_fault.py` | `specific_part` 段式匹配；`sub_type` 改 `fault_code__in OR product_code__in` |
| `FreeArkWeb/backend/freearkweb/api/tests_fault_event.py` | 新增 `TestBugFM004RoomNumberSegments`（10）+ `TestBugFM005SubTypeProductCodeFilter`（14） |
| `docs/troubleshooting/BUG-FM-004_room_number_segments_mismatch.md` | RCA |
| `docs/troubleshooting/BUG-FM-005_sub_type_filter_breaks_on_generic_error_codes.md` | RCA |
| `docs/troubleshooting/BUG-FM-004-005_implementation_plan.md` | 实施计划 |

无前端改动、无 DB migration、无 systemd unit 变更、无 API 接口契约变更。

---

## 2. 部署前置检查

| 检查项 | 结果 |
|---|---|
| 生产 HEAD（拉取前） | `94fb3fd fix(fault-mgmt): 故障类型/设备类型过滤器无效 (BUG-FM-003)` |
| 本地修改文件 | `.env`、`heartbeat_broker_config.json`、`package-lock.json`（既知预期项，与本次拉取零交集） |
| 本次 commit 范围 | `git diff --name-only 94fb3fd..e6e2b7b` → 仅 backend `.py` × 3 + RCA `.md` × 3，无冲突风险 |
| 本地测试 | `python manage.py test api.tests_fault_event` → **147/147 全部通过** |

---

## 3. 部署步骤执行记录

### Step 1 — 拉代码
```
cd /home/yangyang/Freeark/FreeArk && git pull origin main
→ Updating 94fb3fd..e6e2b7b Fast-forward
  6 files changed, 848 insertions(+), 8 deletions(-)
```

### Step 2 — 验证代码落地
- `git log -1` → `e6e2b7b fix(fault-mgmt): v0.6.2 ...` ✅
- `grep SUB_TYPE_TO_PRODUCT_CODES constants.py` → line 82 命中 ✅
- `grep product_code views_fault.py` → 命中新增的 OR 联合分支 ✅

### Step 3 — 重启服务
```
sudo systemctl restart freeark-backend
sudo systemctl restart freeark-mqtt-consumer
```
- `freeark-backend`：`active`，uvicorn 启动正常（`ASGI 'lifespan' protocol appears unsupported` 是文档化无害信息）
- `freeark-mqtt-consumer`：`active`（防御性重启 — `constants.py` 被 `fault_classifier.py` 引用，但本次改动为纯增量字典，不影响 classifier 行为）

> 备注：MQTT 消费者只用到 `EXACT_FAULT_MAP`/`SUFFIX_FAULT_RULES`/正则模式，新增的 `SUB_TYPE_TO_PRODUCT_CODES` 仅被 `views_fault.py` 使用，故 mqtt-consumer 重启并非严格必需，是按 skill §6 "用到该代码的 worker 服务" 防御性执行。

### Step 4 — 烟测
- `curl http://127.0.0.1:8080/api/health/` → `{"status":"ok","message":"FreeArk Web API 服务正常运行"}` ✅
- backend journald 启动序列正常，已接受 health request 并返回 200

### Step 5 — **生产真实数据验证**（关键步骤）

Django shell 直查生产 DB（fault-events API 需认证，故走 ORM 验证）：

#### BUG-FM-004 房号段数修复
```
input='9-1-604' (3 段) → match count=3
  sp=9-1-6-604 code=error_140 prod=270001
  sp=9-1-6-604 code=error_194 prod=130004
  sp=9-1-6-604 code=error_265 prod=100007
```
✅ 3 段输入正确命中 4 段 DB 数据（修复前 0 命中）

#### BUG-FM-005 设备类型修复
```
sub_type='study_room_thermostat'
  fault_codes mapping: [study_room_*_error × 4]
  product_codes mapping: ['260001', '120003']
→ match count=1028
  sp=5-1-13-1301 code=comm_fault_timeout prod=120003
  sp=5-1-13-1301 code=comm_fault_timeout prod=120003
  ...
```
✅ 1028 条命中（修复前 0 命中）。全部通过 `product_code__in=['260001','120003']` 命中 `comm_fault_timeout` 等通用故障码

#### 组合验证（无误报）
```
specific_part='9-1-604' + sub_type='study_room_thermostat' → match count=0
```
✅ 行为正确 — 9-1-6-604 房间只有水力/新风/空气品质设备故障，无温控故障

---

## 4. 设计权衡 / 已知限制

### BUG-FM-005 房间维度信息丢失
- 生产 fault_code 99% 是通用 `error_N` 编号，**不携带房间维度**
- 选 `客厅温控面板` 和 `书房温控面板` 会返回相同的 product_code 命中数据
- 这是数据模型层面的限制，不是 BUG
- **用户区分房间需结合"房号筛选器"组合使用**（修复后的 BUG-FM-004 已支持）

### `260002` 标签
- 生产中有 3 条 product_code=260002 的故障无标签，已暂标 `'未知设备 260002'`
- 若开发知道该 product_code 对应何种设备，仅需更新 `PRODUCT_CODE_LABELS['260002']` 一行即可

---

## 5. 风险与回滚

### 风险评估
- ✅ 改动为查询过滤逻辑增强（OR 扩大命中集），不影响数据写入路径
- ✅ 测试覆盖：147 个单元/集成用例全部通过
- ✅ 生产真实数据 ORM 验证：两 BUG 修复均符合预期
- ✅ `SUB_TYPE_TO_FAULT_CODES` 保留兼容，未来若上报命名型 fault_code 仍可工作

### 回滚方案
```bash
ssh -p 57279 yangyang@et116374mm892.vicp.fun \
  'cd /home/yangyang/Freeark/FreeArk && git reset --hard 94fb3fd && \
   sudo systemctl restart freeark-backend && sudo systemctl restart freeark-mqtt-consumer'
```
（无 DB migration，无静态资源备份需求。）

---

## 6. 用户生产验证建议

请用户在浏览器（**Ctrl+F5 强刷**确保拉到最新 backend 行为，前端代码本次未变）依次验证：

### BUG-FM-004 房号
1. 房号选择器选 `9-1-604`，列表应能列出该房间所有故障（DB 中实际为 `9-1-6-604`）
2. 选其他存在的房号，确认能正常命中
3. 不选房号时显示近 7 天全量

### BUG-FM-005 设备类型
1. 选"书房温控面板" → 应能列出大量故障（约 1028 条；含 `comm_fault_timeout` 和各种 `error_N`）
2. 选"客厅温控面板" → 与"书房"返回同等结果集（数据模型限制，符合 v0.6.2 设计）
3. 选"新风机" → 应命中 `product_code=130004` 的所有故障 + `fresh_air_fault_bit_*` 前缀故障
4. 选"水力模块" → 仅命中 `product_code=270001`
5. 选"能耗表" / "空气品质传感器" / 等 → 各自命中对应 product_code
6. **组合**：房号 `9-1-604` + 设备类型"水力模块" → 应能列出 `error_140 prod=270001` 那条

如果发现"客厅温控面板"和"书房温控面板"返回相同数据，这是预期行为（见 §4 设计权衡），不是 BUG。

---

## 7. 关联文档

- RCA：`docs/troubleshooting/BUG-FM-004_room_number_segments_mismatch.md`
- RCA：`docs/troubleshooting/BUG-FM-005_sub_type_filter_breaks_on_generic_error_codes.md`
- 实施计划：`docs/troubleshooting/BUG-FM-004-005_implementation_plan.md`
- 上游修复：`docs/deployment/v0.6.1_fault_mgmt_ux/BUG-FM-003/deployment_report_2026-05-28.md`（BUG-FM-003 axios 数组序列化）
