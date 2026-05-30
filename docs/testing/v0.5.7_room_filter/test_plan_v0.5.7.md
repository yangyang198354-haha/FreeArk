# 测试计划 — FreeArk v0.5.7 按房型过滤设备面板与采集点裁剪

```
file_header:
  document_id: TEST-PLAN-v0.5.7
  title: FreeArk v0.5.7 — 测试计划
  author_agent: sub_agent_test_engineer (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: v0.5.7
  created_at: 2026-05-23
  status: APPROVED
  references:
    - docs/requirements/v0.5.7_room_filter/requirements_spec_v0.5.7.md
    - docs/requirements/v0.5.7_room_filter/user_stories_v0.5.7.md
    - docs/architecture/module_design_v0.5.7.md
    - docs/development/v0.5.7_room_filter/code_review_report_v0.5.7.md
```

---

## 1. 测试策略

### 1.1 测试层次

| 层次 | 工具 | 范围 |
|------|------|------|
| 单元测试 | Django TestCase + unittest.mock | utils_room_filter.py（M1）、PLCLatestDataHandler（M4）、ondemand_collect_subscriber.py（M7-B）|
| 集成测试 | Django APIClient + SQLite in-memory | views.py::get_device_realtime_params（M2）、device_tree_sync_one 缓存清除（M5）、views_device_settings::device_settings_params（M3）、device_ondemand_refresh MQTT payload（M7-A）|
| E2E / 端到端 | 不需要：前端无需改动，后端接口行为可通过集成测试充分覆盖 | — |

### 1.2 覆盖率目标

| 指标 | 目标 |
|------|------|
| 单元测试通过率 | ≥ 80% |
| 集成测试通过率 | ≥ 90% |
| 所有 US-v0.5.7-* 用户故事有对应测试 | 100% |

---

## 2. 测试文件

测试代码文件：
`FreeArkWeb/backend/freearkweb/api/tests/test_room_filter_v057.py`

运行方式：
```
cd FreeArkWeb/backend/freearkweb
python manage.py test api.tests.test_room_filter_v057 --settings=freearkweb.test_settings --verbosity=2
```

---

## 3. 测试用例清单

### 3.1 单元测试：`utils_room_filter.py`（M1）

| 测试编号 | 用户故事 | 场景 | 期望结果 |
|---------|---------|------|---------|
| UT-M1-01 | US-01 | 三房户型（含儿童房 ori_room_name="儿童房"，无"四"字） | `get_available_sub_types` 含 `panel_children_room`，不含 `panel_fourth_children` |
| UT-M1-02 | US-01 | 四房户型（含 ori_room_name="四房儿童房"） | 含 `panel_children_room` 且含 `panel_fourth_children` |
| UT-M1-03 | US-01 | 设备树未同步（DeviceFloor 无记录，floors=[]）| 仅返回 `SYSTEM_LEVEL_SUB_TYPES`，不含任何 `panel_*` |
| UT-M1-04 | US-01 | 正常四房户型（含书房、主卧、儿童房、四房儿童房） | 含所有四个 panel sub_type |
| UT-M1-05 | — | 缓存命中：连续两次调用同一 specific_part，缓存有效期内 | 第二次不查 DB（DeviceFloor.objects.filter 只调用一次）|
| UT-M1-06 | — | 缓存失效：invalidate_room_filter_cache(sp) 后再次调用 | 重新查 DB（DeviceFloor.objects.filter 调用第二次）|
| UT-M1-07 | — | 全量清缓存：invalidate_room_filter_cache(None) | 所有 specific_part 的缓存被清除 |
| UT-M1-08 | US-03 | `get_panel_param_blocklist()` 对无儿童房专有部分 | 返回 `fourth_children_room_*` 系列 param_name 集合（非空）|
| UT-M1-09 | US-03 | `get_panel_param_blocklist()` 对全量房间存在的专有部分 | 返回空 frozenset |
| UT-M1-10 | — | DeviceFloor 查询异常时降级 | 返回 `SYSTEM_LEVEL_SUB_TYPES`，不缓存错误结果 |

### 3.2 单元测试：`PLCLatestDataHandler`（M4）

| 测试编号 | 用户故事 | 场景 | 期望结果 |
|---------|---------|------|---------|
| UT-M4-01 | US-03 | MQTT 消息含无儿童房参数，该专有部分无儿童房 | `plc_latest_data` 中不写入 `fourth_children_room_*` |
| UT-M4-02 | US-04 | 同上，触发 `_write_history()` | `device_param_history` 中不追加 `fourth_children_room_*` |
| UT-M4-03 | US-03 | 同一消息中含实际存在房间的参数 | 实际存在的参数正常写入 |
| UT-M4-04 | US-03 | 系统级参数（无房型约束） | 不被过滤，照常写入 |
| UT-M4-05 | — | `param_blocklist` 为空（全量房间存在）| 无参数被过滤，原有行为不变 |

### 3.3 单元测试：`OndemandCollectSubscriber`（M7-B）

| 测试编号 | 用户故事 | 场景 | 期望结果 |
|---------|---------|------|---------|
| UT-M7B-01 | US-06 | `_execute_ondemand()` 收到 `allowed_params={"param_a"}` | `configs` 仅含 `param_a` 的读取配置，其他参数不在 configs 中 |
| UT-M7B-02 | US-06 | `_execute_ondemand()` 收到 `allowed_params=None` | `configs` 含 plc_config 全量参数（向后兼容）|
| UT-M7B-03 | US-06 | `_execute_ondemand()` 收到 `allowed_params=set()`（空集合）| `configs=[]`，触发「plc_config 为空」逻辑，不崩溃 |
| UT-M7B-04 | US-06 | `_on_request()` 收到含 `allowed_params` 的 payload | `allowed_params` 被转为 set 并传入 `_execute_ondemand()` |
| UT-M7B-05 | US-06 | `_on_request()` 收到无 `allowed_params` 的 payload | `allowed_params=None` 传入 `_execute_ondemand()` |

### 3.4 集成测试：API 层（M2、M3、M5、M7-A）

| 测试编号 | 用户故事 | 场景 | 期望结果 |
|---------|---------|------|---------|
| IT-M2-01 | US-01 | `GET /api/devices/realtime-params/`，三房户型无儿童房 | 响应中不含 `panel_fourth_children` sub_type |
| IT-M2-02 | US-01 | 同上，含主温控等系统级面板 | 系统级面板正常显示 |
| IT-M2-03 | US-01 | `GET /api/devices/realtime-params/`，设备树未同步 | 响应中不含任何 `panel_*` sub_type，系统级面板正常 |
| IT-M2-04 | US-01 | 四房户型含儿童房 | 响应中含 `panel_fourth_children` sub_type |
| IT-M3-01 | US-02 | `GET /api/device-settings/params/{sp}/`，无儿童房 | 响应 groups 中不含 `panel_fourth_children` |
| IT-M3-02 | US-02 | 系统级可写参数不受过滤影响 | 系统级参数分组正常出现 |
| IT-M5-01 | — | `POST /api/device-management/screen-device-tree/sync/` 成功后调用缓存清除 | `invalidate_room_filter_cache(specific_part)` 被调用（mock 验证）|
| IT-M7A-01 | US-06 | `POST /api/devices/ondemand-refresh/`，设备树已同步 | MQTT publish 的 payload 中含 `allowed_params` 字段，不含 `fourth_children_room_*` |
| IT-M7A-02 | US-06 | 同上，设备树未同步（降级）| `allowed_params` 仅含系统级参数的 param_name |

---

## 4. 边界测试

| 测试编号 | 场景 | 期望结果 |
|---------|------|---------|
| EDGE-01 | `panel_bedroom`（三房主卧）与 `panel_children_room`（三房儿童房）同时存在时，`panel_bedroom` 不因「主卧」关键词被错误地触发 `panel_children_room` 独占 | 两者均应可用 |
| EDGE-02 | 同一户型有「主卧」和「儿童房」（三房）：`panel_bedroom` 和 `panel_children_room` 均可用 | 两者均出现在 available_sub_types |
| EDGE-03 | 房间数量 >= 4 但无「儿童房」房间名 | `panel_fourth_children` 不可用（需要「儿童房」关键词）|
| EDGE-04 | `ori_room_name` 为空字符串 | 跳过该房间（不参与匹配），不崩溃 |
| PERF-01 | 缓存命中时 `get_available_sub_types()` 开销 | < 1ms（无 DB 查询，纯内存操作）|
