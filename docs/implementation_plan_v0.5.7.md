# 实现计划 — FreeArk v0.5.7 按房型过滤设备面板与采集点裁剪

```
file_header:
  document_id: IMPL-v0.5.7
  title: FreeArk v0.5.7 — 实现计划
  author_agent: sub_agent_software_developer (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: v0.5.7
  created_at: 2026-05-23
  status: APPROVED
  references:
    - docs/architecture/module_design_v0.5.7.md
    - docs/architecture/architecture_design_v0.5.7.md
    - docs/requirements_spec_v0.5.7.md
```

---

## 1. 实现范围

依据 PM 决策（OQ-v0.5.7-02/03/04 全部锁定）和设计文档（module_design_v0.5.7.md v0.5.7-rev1），
本版本实现以下模块：

| 模块 | 文件 | 变更类型 | FR 覆盖 |
|------|------|---------|--------|
| M1 utils_room_filter | `api/utils_room_filter.py` | 新增 | FR-01~05 基础 |
| M2 设备面板 API 过滤 | `api/views.py::get_device_realtime_params` | 修改 | FR-01 |
| M3 参数设置 API 过滤 | `api/views_device_settings.py::device_settings_params` | 修改 | FR-02 |
| M4 MQTT 落库过滤 | `api/mqtt_handlers.py::PLCLatestDataHandler` | 修改 | FR-03/04 |
| M5 设备树同步清缓存 | `api/views.py::device_tree_sync_one/batch` | 修改 | NFR-01 |
| M6 清理命令 | — | **本版本不实施**（PM OQ-v0.5.7-03）| FR-06 |
| M7-A Django 按需采集白名单 | `api/views.py::device_ondemand_refresh` | 修改 | FR-05 |
| M7-B 采集侧裁剪 | `datacollection/ondemand_collect_subscriber.py` | 修改 | FR-05 |

---

## 2. 变更文件清单

### 2.1 新增文件

- `FreeArkWeb/backend/freearkweb/api/utils_room_filter.py`（M1）
  - `SUB_TYPE_TO_ROOM_KEYWORDS` 映射字典
  - `SYSTEM_LEVEL_SUB_TYPES` 常量
  - `get_available_sub_types(specific_part)` — 查询可用 sub_type，带 300s 缓存
  - `get_panel_param_blocklist(specific_part)` — 获取落库黑名单
  - `get_allowed_param_names(specific_part)` — 获取按需采集白名单
  - `invalidate_room_filter_cache(specific_part=None)` — 主动清缓存
  - `_match_panel_sub_types(ori_room_names)` — 内部关键词匹配
  - `_update_cache(specific_part, result, timestamp)` — 线程安全缓存写入

### 2.2 修改文件

**`FreeArkWeb/backend/freearkweb/api/views.py`**
- 顶部 import 增加：`from .utils_room_filter import get_available_sub_types, get_allowed_param_names, invalidate_room_filter_cache, SYSTEM_LEVEL_SUB_TYPES`
- `get_device_realtime_params()`：在 `configs_qs` 构建后调用 `get_available_sub_types()`，在循环顶部增加 `if sub_key not in available_sub_types: continue`（M2）
- `device_tree_sync_one()`：成功后调用 `invalidate_room_filter_cache(specific_part)`（M5）
- `device_tree_sync_batch()`：启动后调用 `invalidate_room_filter_cache()`（M5）
- `device_ondemand_refresh()`：计算 `_allowed_params = get_allowed_param_names(specific_part)` 并注入 payload（M7-A）

**`FreeArkWeb/backend/freearkweb/api/views_device_settings.py`**
- 顶部 import 增加：`from .utils_room_filter import get_available_sub_types`
- `device_settings_params()`：在 groups 循环前调用 `get_available_sub_types()`，在循环顶部增加 `if cfg.sub_type not in available_sub_types: continue`（M3）

**`FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py`**
- 顶部 import 增加：`from .utils_room_filter import get_panel_param_blocklist`
- `PLCLatestDataHandler.handle()`：在 `data_dict` 解析后调用 `get_panel_param_blocklist()`，在参数循环顶部增加房型过滤跳过逻辑（M4）

**`datacollection/ondemand_collect_subscriber.py`**
- `_on_request()`：解析 `allowed_params = data.get('allowed_params')`，转为 `set`，传入 `_execute_ondemand`（M7-B）
- `_execute_ondemand()`：签名增加 `allowed_params=None` 参数，configs 构建循环中增加白名单过滤（M7-B）

---

## 3. 关键实现决策

### 3.1 M1 缓存设计
- 进程内字典 `_room_filter_cache`，TTL=300s，`threading.Lock` 保护
- 查询异常时返回 `SYSTEM_LEVEL_SUB_TYPES`（安全降级），**不缓存**失败结果（下次重试）

### 3.2 M4 blocklist 优化
- `param_blocklist` 为空（全量房间存在）时，不进入 `in blocklist` 判断，无性能影响

### 3.3 M7-A 空白名单降级
- `get_allowed_param_names()` 返回 `None` 或 `[]` 时，不注入 `allowed_params` 字段
- 采集侧收到无 `allowed_params` 的 payload 时，降级为全量采集（原有行为）

### 3.4 M5 批量同步清缓存时机
- `device_tree_sync_one` 在 `sync_one_specific_part()` 成功返回后立即清除对应 specific_part 缓存
- `device_tree_sync_batch` 在启动批量任务后立即清除全部缓存（批量在后台线程，预清确保同步后首次访问时读到最新数据）

---

## 4. 不实施项

- **M6 清理命令**（`cleanup_invalid_device_params.py`）：PM OQ-v0.5.7-03 决策，本版本不实施。文件不新建。

---

## 5. 测试要点（移交 GROUP_D）

见 module_design_v0.5.7.md §测试要点，重点关注：
1. 三房户型「儿童房」面板不显示、采集不轮询、不落库
2. 四房户型「儿童房」正常显示/采集/落库
3. 设备树未同步降级到方案 B（仅系统级面板）
4. 缓存 TTL 与设备树同步后的失效（invalidate 后重新查 DB）
5. panel_bedroom / panel_children_room 关键词重叠的边界
6. allowed_params=None 时向后兼容（全量采集）
7. 性能：缓存命中下房型过滤开销可接受
