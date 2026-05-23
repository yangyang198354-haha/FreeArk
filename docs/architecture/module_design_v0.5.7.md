# 模块详细设计文档增量 — FreeArk v0.5.7 按房型过滤设备面板与采集点裁剪

```
file_header:
  document_id: MOD-v0.5.7
  title: FreeArk v0.5.7 — 按房型过滤设备面板、参数设置与 PLC 采集点裁剪 模块设计
  author_agent: sub_agent_system_architect (via PM Orchestrator, incremental revision)
  project: FreeArk 能耗采集平台
  version: v0.5.7-fix2
  created_at: 2026-05-22
  revised_at: 2026-05-23
  status: APPROVED
  revision_note: |
    PM 决策锁定（2026-05-22）：
    - M6 清理命令：本版本不实施（OQ-v0.5.7-03），模块标记说明
    - 新增 M7：采集侧按需采集裁剪（OQ-v0.5.7-04 纳入本版本）
      M7-A：views.py ondemand_refresh 注入 allowed_params
      M7-B：ondemand_collect_subscriber.py 读取白名单，裁剪 PLC 读取
    - 更新模块依赖关系图（含 M7）
    - 补充 M7 相关测试要点
    fix2 修订（2026-05-23，生产验证 bug 修复）：
    - M1 §1.3 _match_panel_sub_types() 规则 4 更新：
      panel_fourth_children 判定由「含儿童房 AND 房间数≥4」改为「含书房 AND 含儿童房」
    - 更新模块 M1 测试要点：UT-M1-04 场景更新，新增四房/三房生产用例专项测试要点
  references:
    - docs/architecture/architecture_design_v0.5.7.md
    - docs/requirements_spec_v0.5.7.md
    - docs/user_stories_v0.5.7.md
    - FreeArkWeb/backend/freearkweb/api/models.py
    - FreeArkWeb/backend/freearkweb/api/views.py (get_device_realtime_params, L1595)
    - FreeArkWeb/backend/freearkweb/api/views_device_settings.py (device_settings_params, L132)
    - FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py (PLCLatestDataHandler, L695)
    - FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py
    - datacollection/resource/plc_config.json
```

---

## 模块 M1：房型过滤工具模块（新增文件）

**文件**：`FreeArkWeb/backend/freearkweb/api/utils_room_filter.py`
**位置**：新建文件，与 `views.py`、`mqtt_handlers.py` 同目录

### 1.1 常量定义

```python
"""
utils_room_filter.py — FreeArk v0.5.7
房型过滤工具：根据 device_room 表中已同步的房间信息，
确定某专有部分可显示的 DeviceConfig sub_type 集合。
"""
import threading
import time
import logging
from typing import frozenset

logger = logging.getLogger(__name__)

# ── 温控面板 sub_type → 房间关键词映射 ─────────────────────────────
# 关键词来源：seed_device_config.py 注释 + plc_config.json description 字段
# 匹配规则：device_room.ori_room_name 中包含列表中任意一个关键词即命中
#
# 映射语义说明（对照 plc_config.json）：
#   panel_study_room      → 三房次卧 / 四房书房   → ori_room_name 含"次卧"或"书房"
#   panel_bedroom         → 三房主卧 / 四房次卧   → ori_room_name 含"主卧"（四房次卧由 panel_study_room 处理）
#   panel_children_room   → 三房儿童房 / 四房主卧 → ori_room_name 含"儿童房"或"主卧"
#   panel_fourth_children → 四房儿童房（专属）   → ori_room_name 含"儿童房"
#
# 注意：panel_children_room 与 panel_fourth_children 均含"儿童房"关键词。
# get_available_sub_types() 使用以下规则区分：
#   - 若 ori_room_name 含"四"且含"儿童房" → panel_fourth_children 命中
#   - 若 ori_room_name 含"儿童房"但不含"四" → panel_children_room 命中
#   - 若两种儿童房都命中（四房户型）→ 两者均可用

SUB_TYPE_TO_ROOM_KEYWORDS: dict = {
    'panel_study_room':      ['次卧', '书房'],
    'panel_bedroom':         ['主卧'],
    'panel_children_room':   ['儿童房', '主卧'],
    'panel_fourth_children': ['儿童房'],
}

# 不受房型约束的系统级 sub_type（始终可用，无需房间验证）
SYSTEM_LEVEL_SUB_TYPES: frozenset = frozenset({
    'main_thermostat',
    'fresh_air',
    'energy_meter',
    'hydraulic_module',
    'air_quality',
})

# 所有温控面板 sub_type（用于 blocklist 计算）
ALL_PANEL_SUB_TYPES: frozenset = frozenset(SUB_TYPE_TO_ROOM_KEYWORDS.keys())

# 缓存：{specific_part: (available_sub_types: frozenset, cached_at: float)}
_room_filter_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_TTL_SECONDS: int = 300  # 5 分钟
```

### 1.2 核心函数：`get_available_sub_types()`

```python
def get_available_sub_types(specific_part: str) -> frozenset:
    """
    查询并缓存指定专有部分可用的 DeviceConfig sub_type 集合。

    返回值：
        frozenset[str]，包含该专有部分应显示的所有 sub_type。
        - 系统级 sub_type（SYSTEM_LEVEL_SUB_TYPES）始终包含。
        - 温控面板 sub_type 仅在 device_room 中存在对应房间时包含。
        - 若设备树未同步（device_floor 中无记录），仅返回 SYSTEM_LEVEL_SUB_TYPES。

    缓存：
        TTL = 300s，线程安全（_cache_lock 保护读写）。
        设备树同步后调用 invalidate_room_filter_cache(specific_part) 主动清除。
    """
    # 1. 检查缓存
    now = time.monotonic()
    with _cache_lock:
        cached = _room_filter_cache.get(specific_part)
        if cached is not None:
            available_sub_types, cached_at = cached
            if (now - cached_at) < _CACHE_TTL_SECONDS:
                logger.debug(
                    'utils_room_filter: 命中缓存 specific_part=%s, sub_types=%s',
                    specific_part, available_sub_types
                )
                return available_sub_types

    # 2. 查询 device_room（延迟导入，避免循环依赖）
    from .models import DeviceFloor
    try:
        floors = DeviceFloor.objects.filter(
            owner__specific_part=specific_part
        ).prefetch_related('rooms')
    except Exception as e:
        logger.error(
            'utils_room_filter: 查询 DeviceFloor 失败 specific_part=%s: %s',
            specific_part, e
        )
        return SYSTEM_LEVEL_SUB_TYPES

    # 3. 收集所有 ori_room_name
    all_ori_room_names: list = []
    for floor in floors:
        for room in floor.rooms.all():
            if room.ori_room_name:
                all_ori_room_names.append(room.ori_room_name)

    logger.debug(
        'utils_room_filter: specific_part=%s, 共 %d 个房间: %s',
        specific_part, len(all_ori_room_names), all_ori_room_names
    )

    # 4. 若设备树未同步（floors 为空），降级为仅系统级面板
    if not floors:
        logger.info(
            'utils_room_filter: specific_part=%s 设备树未同步，降级为仅系统级面板',
            specific_part
        )
        result = SYSTEM_LEVEL_SUB_TYPES
        _update_cache(specific_part, result, now)
        return result

    # 5. 通过关键词匹配确定可用的 panel sub_type
    available_panels = _match_panel_sub_types(all_ori_room_names)
    result = SYSTEM_LEVEL_SUB_TYPES | available_panels

    logger.info(
        'utils_room_filter: specific_part=%s → available_sub_types=%s',
        specific_part, result
    )

    _update_cache(specific_part, result, now)
    return result
```

### 1.3 内部函数：`_match_panel_sub_types()`

```python
def _match_panel_sub_types(ori_room_names: list) -> frozenset:
    """
    根据房间名称列表，确定哪些 panel sub_type 可用。

    规则：
    1. panel_study_room：任意房间名含"次卧"或"书房"
    2. panel_bedroom：任意房间名含"主卧"（但"主卧"命中的是 panel_bedroom，
       "儿童房"含"主卧"的情况由 panel_children_room 处理，不影响 panel_bedroom）
    3. panel_children_room：任意房间名含"儿童房"或"主卧"
    4. panel_fourth_children（fix2 校正）：同时满足：
       - 任意房间名含"书房"（has_study_room）—— 对应四房户型特征
       - 任意房间名含"儿童房"（has_children_keyword）
       OR（冗余识别）任意房间名同时含"儿童房"且含"四"字

       生产根因说明：原「房间数 ≥ 4」为错误启发式，三房户型（9-1-10-1002）
       房间总数也达到 5（含全屋/客厅等非卧室），导致三房误激活 panel_fourth_children。
       生产全量 40 个专有部分扫描确认「含书房 = 四房」，100% 吻合，无例外。

    简化版本（v0.5.7-fix2）：
    - 遍历所有房间名，对每个 sub_type 检查关键词匹配
    - panel_fourth_children 核心判定改为：has_study_room AND has_children_keyword
      原「含'四'字」分支保留作冗余识别（防御未来显式命名如「四房儿童房」），不删除
    """
    available = set()

    # 建立关键词命中集合
    all_names_joined = ' '.join(ori_room_names)  # 合并为一个字符串方便检索

    for sub_type, keywords in SUB_TYPE_TO_ROOM_KEYWORDS.items():
        if sub_type == 'panel_fourth_children':
            # fix2：核心判定改为「含书房 AND 含儿童房」
            # 冗余识别保留：房间名中含"四"且含"儿童房"（防御未来显式命名）
            has_study_room = any('书房' in name for name in ori_room_names)
            has_children_keyword = any('儿童房' in name for name in ori_room_names)
            has_explicit_fourth = any(
                '儿童房' in name and '四' in name for name in ori_room_names
            )
            if (has_study_room and has_children_keyword) or has_explicit_fourth:
                available.add(sub_type)
        else:
            if any(kw in all_names_joined for kw in keywords):
                available.add(sub_type)

    return frozenset(available)
```

### 1.4 辅助函数

```python
def get_panel_param_blocklist(specific_part: str) -> frozenset:
    """
    获取该专有部分不应写入 DB 的 param_name 集合（不存在房间的参数黑名单）。

    用于 PLCLatestDataHandler 的落库过滤。
    返回 frozenset[str]，包含所有不可用 panel sub_type 下的全部 param_name。
    """
    available_sub_types = get_available_sub_types(specific_part)
    unavailable_panels = ALL_PANEL_SUB_TYPES - available_sub_types

    if not unavailable_panels:
        return frozenset()  # 全部房间存在，无需过滤

    # 延迟导入
    from .models import DeviceConfig
    blocked_params = DeviceConfig.objects.filter(
        sub_type__in=unavailable_panels,
        is_active=True,
    ).values_list('param_name', flat=True)

    result = frozenset(blocked_params)
    logger.debug(
        'utils_room_filter: specific_part=%s, blocklist 共 %d 个参数 (unavailable_panels=%s)',
        specific_part, len(result), unavailable_panels
    )
    return result


def invalidate_room_filter_cache(specific_part: str = None) -> None:
    """
    主动清除房型过滤缓存。

    Args:
        specific_part: 若提供，仅清除该专有部分的缓存；若为 None，清除全部缓存。
    调用时机：设备树同步成功后（views.py 中的 sync_device_tree 接口）。
    """
    with _cache_lock:
        if specific_part is None:
            _room_filter_cache.clear()
            logger.info('utils_room_filter: 已清除全部房型过滤缓存')
        else:
            _room_filter_cache.pop(specific_part, None)
            logger.info('utils_room_filter: 已清除 %s 的房型过滤缓存', specific_part)


def _update_cache(specific_part: str, result: frozenset, timestamp: float) -> None:
    """线程安全地更新缓存。"""
    with _cache_lock:
        _room_filter_cache[specific_part] = (result, timestamp)
```

---

## 模块 M2：后端 API 修改 — `get_device_realtime_params()`

**文件**：`FreeArkWeb/backend/freearkweb/api/views.py`
**位置**：函数 `get_device_realtime_params()`（约 L1595）
**变更方式**：最小化修改，仅在现有逻辑中插入过滤步骤

### 2.1 导入变更

在文件顶部（约 L16）的 import 区域增加：
```python
from .utils_room_filter import get_available_sub_types, SYSTEM_LEVEL_SUB_TYPES
```

### 2.2 函数修改（diff 描述）

**变更位置**：L1623（`configs_qs` 查询之后）新增以下逻辑：

```python
# ── v0.5.7: 房型过滤 ───────────────────────────────────────────────────
# 查询该专有部分可用的 sub_type 集合（来自 device_room 表）
available_sub_types = get_available_sub_types(specific_part)
# ── end v0.5.7 ─────────────────────────────────────────────────────────
```

**变更位置**：L1635（`for cfg in configs_qs:` 循环体顶部）新增过滤：

```python
for cfg in configs_qs:
    group_key = cfg.group
    sub_key = cfg.sub_type

    # v0.5.7: 跳过不属于该专有部分房型的温控面板 sub_type
    if sub_key not in available_sub_types:
        continue
    # ── end v0.5.7 ────────────────────────────────────────────────────

    # 以下为原有逻辑（不变）
    if group_key not in result:
        ...
```

**完整修改后的函数关键路径（伪代码）**：

```
get_device_realtime_params(request):
    specific_part = ...
    group_filter = ...

    # 原有 Query 1
    latest_data_qs = PLCLatestData.objects.filter(specific_part=specific_part)
    latest_by_param = {record.param_name: record for record in latest_data_qs}

    # 原有 Query 2（DeviceConfig）
    configs_qs = DeviceConfig.objects.filter(is_active=True).order_by('id')
    if group_filter:
        configs_qs = configs_qs.filter(group=group_filter)

    # v0.5.7 新增：查询可用 sub_type（带缓存，不增加 DB 查询次数）
    available_sub_types = get_available_sub_types(specific_part)

    result = {}
    for cfg in configs_qs:
        # v0.5.7 新增：跳过不可用的 panel sub_type
        if cfg.sub_type not in available_sub_types:
            continue

        # 原有逻辑：构建嵌套结构
        ...（不变）

    # 原有逻辑：清理空 sub_types
    ...（不变）

    return Response({'success': True, 'specific_part': specific_part, 'data': result})
```

---

## 模块 M3：后端 API 修改 — `device_settings_params()`

**文件**：`FreeArkWeb/backend/freearkweb/api/views_device_settings.py`
**位置**：函数 `device_settings_params()`（约 L132）
**变更方式**：与 M2 相同的模式

### 3.1 导入变更

```python
from .utils_room_filter import get_available_sub_types
```

### 3.2 函数修改（diff 描述）

**变更位置**：`configs = (DeviceConfig.objects.filter(is_active=True)...)` 之后，`groups = {}` 循环之前：

```python
# v0.5.7: 查询可用 sub_type
available_sub_types = get_available_sub_types(specific_part)
```

**变更位置**：`for cfg in configs:` 循环体顶部：

```python
for cfg in configs:
    # P5 后端过滤：不返回只读参数（原有）
    if not _is_writable(cfg.param_name):
        continue

    # v0.5.7: 跳过不属于该专有部分房型的温控面板 sub_type
    if cfg.sub_type not in available_sub_types:
        continue

    # 以下原有逻辑不变
    key = cfg.sub_type
    ...
```

---

## 模块 M4：MQTT Handler 修改 — `PLCLatestDataHandler`

**文件**：`FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py`
**位置**：`PLCLatestDataHandler` 类（约 L695）
**变更方式**：在 `handle()` 方法中，构建 `records` 列表前增加 blocklist 过滤

### 4.1 导入变更

```python
from .utils_room_filter import get_panel_param_blocklist
```

### 4.2 `handle()` 方法修改

**变更位置**：L727（`data_dict = device_info['data']` 之后，`for param_name, param_data in data_dict.items():` 之前）：

```python
# v0.5.7: 获取该专有部分不应落库的参数黑名单（带缓存）
param_blocklist = get_panel_param_blocklist(specific_part)
# ── end v0.5.7 ─────────────────────────────────────────────────────────
```

**变更位置**：`for param_name, param_data in data_dict.items():` 循环体顶部（L738 之后），在现有 `_EXCLUDED_PARAMS` 检查之后增加：

```python
for param_name, param_data in data_dict.items():
    # 原有：排除由 PLCDataHandler 处理的参数
    if param_name in _EXCLUDED_PARAMS:
        skipped_excluded += 1
        ...
        continue

    # v0.5.7: 跳过不存在房间的温控面板参数（不落库）
    if param_name in param_blocklist:
        logger.debug(
            'PLCLatestDataHandler: 跳过不存在房间参数 %s/%s (room_filter)',
            specific_part, param_name
        )
        continue
    # ── end v0.5.7 ───────────────────────────────────────────────────

    # 原有逻辑（不变）
    if not isinstance(param_data, dict):
        ...
    if not param_data.get('success', False):
        ...
    ...
    records.append({...})
```

### 4.3 `OndemandPLCLatestDataHandler` 继承影响

`OndemandPLCLatestDataHandler` 继承自 `PLCLatestDataHandler`，只覆盖了 `_write_history()`，`handle()` 方法复用父类。因此 M4 的修改自动适用于按需采集场景，无需额外修改。

---

## 模块 M5：设备树同步后缓存清除

**文件**：`FreeArkWeb/backend/freearkweb/api/views.py`
**位置**：设备树同步接口（需查找现有的 sync_device_tree 或 batch_sync 接口）

**变更位置**：在设备树同步成功写入 `device_room` 后，调用：

```python
from .utils_room_filter import invalidate_room_filter_cache
# 单户同步成功后
invalidate_room_filter_cache(specific_part)
# 批量同步成功后（或同步完成回调中）
invalidate_room_filter_cache()  # 清除全部缓存
```

---

## 模块 M6：清理管理命令【本版本不实施】

**PM 决策**（OQ-v0.5.7-03，2026-05-22）：**本版本不实施**，存量冗余数据保留，后续单独处理。不开发此模块。

**文件**：`FreeArkWeb/backend/freearkweb/api/management/commands/cleanup_invalid_device_params.py`
**位置**：**本版本不新建此文件**

### 6.1 命令设计

```python
"""
Management command: cleanup_invalid_device_params
用途：清理 plc_latest_data 和 device_param_history 中属于不存在房间的冗余数据。

用法：
  python manage.py cleanup_invalid_device_params --dry-run   # 仅统计，不删除
  python manage.py cleanup_invalid_device_params --execute   # 实际执行删除
  python manage.py cleanup_invalid_device_params --specific-part 9-1-10-1002 --execute
"""
```

### 6.2 执行逻辑

```
1. 枚举 OwnerInfo 中所有已同步设备树的 specific_part
   （即 device_floor 表中存在 owner__specific_part 的记录）

2. 对每个 specific_part：
   a. 调用 get_panel_param_blocklist(specific_part) 获取黑名单
   b. 若黑名单为空，跳过
   c. dry-run 模式：统计 PLCLatestData 和 DeviceParamHistory 中匹配的记录数
   d. execute 模式：事务内批量删除

3. 对未同步设备树的 specific_part：跳过（不删除，输出警告）

4. 输出汇总报告：
   - 处理的专有部分数量
   - 删除（或将删除）的 plc_latest_data 记录数
   - 删除（或将删除）的 device_param_history 记录数
   - 跳过的专有部分列表
```

---

## 模块 M7：采集侧按需采集裁剪（新增，FR-v0.5.7-05）

**PM 决策**（OQ-v0.5.7-04，2026-05-22）：**纳入本版本，必须实现**。

M7 由两个子模块组成：Django 后端侧（M7-A）和 datacollection 采集侧（M7-B）。

---

### M7-A：Django 后端 — `ondemand_refresh` 接口注入 `allowed_params`

**文件**：`FreeArkWeb/backend/freearkweb/api/views.py`
**位置**：按需采集接口（需通过 `grep ondemand_refresh views.py` 定位确切行号）

#### 7A.1 导入变更

```python
from .utils_room_filter import get_available_sub_types
```

（`get_available_sub_types` 在 M2 中已导入，无需重复；此处仅在 `ondemand_refresh` 视图所在区域额外使用）

#### 7A.2 函数修改（diff 描述）

当前 `ondemand_refresh`（或功能等价的按需采集触发接口）构建 MQTT payload 的逻辑大致为：

```python
# 原有逻辑
payload = {
    "specific_part": specific_part,
    "requested_at": current_time_str,
}
mqtt_client.publish(ondemand_topic, payload, qos=1)
```

**修改后**（v0.5.7 新增）：

```python
# v0.5.7: 计算 allowed_params 白名单，注入 ondemand 指令
available_sub_types = get_available_sub_types(specific_part)
# 查询可用 sub_type 下的全部 param_name（包含系统级）
from .models import DeviceConfig
allowed_param_names = list(
    DeviceConfig.objects.filter(
        is_active=True,
        sub_type__in=available_sub_types,
    ).values_list('param_name', flat=True)
)
# 若 allowed_param_names 为空（异常情况），不注入白名单，采集侧降级为全量
payload = {
    "specific_part": specific_part,
    "requested_at": current_time_str,
}
if allowed_param_names:
    payload["allowed_params"] = allowed_param_names
    logger.debug(
        'ondemand_refresh: specific_part=%s, allowed_params 共 %d 个',
        specific_part, len(allowed_param_names)
    )
# ── end v0.5.7 ─────────────────────────────────────────────────────────
mqtt_client.publish(ondemand_topic, payload, qos=1)
```

**说明**：
- `get_available_sub_types()` 已有 300s 缓存，此处无额外 DB 查询（除非缓存 miss）。
- `DeviceConfig` 查询：针对约 50 条配置，极快（< 1ms）。
- 若 `allowed_param_names` 为空（极端情况，如设备树数据异常），不注入 `allowed_params`，采集侧降级为全量采集，保证服务可用性。

---

### M7-B：采集侧 — `OndemandCollectSubscriber` 读取白名单裁剪 PLC 读取

**文件**：`datacollection/ondemand_collect_subscriber.py`
**位置**：`OndemandCollectSubscriber` 类（L97~）

#### 7B.1 `_on_request()` 方法修改

**变更位置**：L183（`specific_part = data.get('specific_part', '')` 之后）：

```python
# 原有
specific_part = data.get('specific_part', '')
# ... 防重入检查 ...
self._executor.submit(self._execute_ondemand, specific_part)
```

**修改后**（v0.5.7 新增）：

```python
specific_part = data.get('specific_part', '')

# v0.5.7: 读取 allowed_params 白名单（若无则为 None，触发全量采集）
allowed_params = data.get('allowed_params')  # list[str] or None
if allowed_params is not None:
    allowed_params = set(allowed_params)  # 转为 set，O(1) 查找
    logger.debug(
        '[ondemand] 收到 allowed_params 白名单: specific_part=%s, 参数数=%d',
        specific_part, len(allowed_params)
    )
# ── end v0.5.7 ────────────────────────────────────────────────────────

# ... 防重入检查（不变）...
self._executor.submit(self._execute_ondemand, specific_part, allowed_params)
```

#### 7B.2 `_execute_ondemand()` 签名与配置构建修改

**签名变更**：

```python
def _execute_ondemand(self, specific_part: str, allowed_params=None) -> None:
    """
    在线程池中执行：读取单设备 PLC 数据，发布结果 topic。

    Args:
        specific_part: 目标专有部分标识。
        allowed_params: 参数名白名单（set[str] 或 None）。
                        若为 None，全量采集（向后兼容）。
                        若为 set，仅采集白名单内的参数。
    """
```

**变更位置**：L226-236（`configs` 列表构建，原有遍历 `self._plc_config` 的循环）：

```python
# 原有
configs = []
for param_name, param_info in self._plc_config.items():
    configs.append({
        'ip': plc_ip,
        'db_num': param_info.get('db_num'),
        'offset': param_info.get('offset'),
        'length': param_info.get('length'),
        'data_type': param_info.get('data_type'),
        'device_id': specific_part,
        'param_key': param_name,
    })
```

**修改后**（v0.5.7 新增白名单过滤）：

```python
# v0.5.7: 根据 allowed_params 白名单裁剪 PLC 读取配置
_full_param_count = len(self._plc_config)
configs = []
for param_name, param_info in self._plc_config.items():
    # v0.5.7: 若白名单存在且参数不在白名单内，跳过
    if allowed_params is not None and param_name not in allowed_params:
        continue
    configs.append({
        'ip': plc_ip,
        'db_num': param_info.get('db_num'),
        'offset': param_info.get('offset'),
        'length': param_info.get('length'),
        'data_type': param_info.get('data_type'),
        'device_id': specific_part,
        'param_key': param_name,
    })

if allowed_params is not None:
    logger.info(
        '[ondemand] 采集侧裁剪: specific_part=%s, 实际采集 %d / 总计 %d 个参数',
        specific_part, len(configs), _full_param_count
    )
# ── end v0.5.7 ────────────────────────────────────────────────────────
```

#### 7B.3 向后兼容与降级逻辑

| 场景 | `allowed_params` 值 | 行为 |
|------|---------------------|------|
| 新版 Django，设备树已同步 | `set(["param_a", "param_b", ...])` | 仅读取白名单内的 PLC 地址 |
| 新版 Django，设备树未同步（降级）| `set(["system_switch", ...])` 仅系统级 | 仅读取系统级参数 |
| 旧版 Django（无 `allowed_params`）| `None` | 全量采集（原有行为，不变） |
| Django 异常导致 `allowed_params=[]` 空列表 | `set()` 空集合 | 无参数可采集，`configs=[]`，发布空 data_dict 的 result（不报错，走 L238-241 的空配置处理分支）|

**注意**：空列表情况（`allowed_params=[]`）在 M7-A 中已处理——若 `allowed_param_names` 为空，不注入 `allowed_params` 字段，采集侧收到的是 `allowed_params=None`（全量），不会出现空集合情况。此处作为防御性设计。

---

## 模块整体依赖关系（v0.5.7-rev1）

```
utils_room_filter.py (M1)
    ↑ import
    ├── views.py::get_device_realtime_params() (M2)
    ├── views.py::ondemand_refresh() (M7-A)          ← 新增
    ├── views_device_settings.py::device_settings_params() (M3)
    ├── mqtt_handlers.py::PLCLatestDataHandler (M4)
    └── views.py::sync_device_tree / batch_sync (M5)

models.py (DeviceFloor, DeviceRoom, DeviceConfig)
    ↑ 查询
    └── utils_room_filter.py (M1)

views.py::ondemand_refresh() (M7-A)
    │  通过 MQTT payload["allowed_params"] 传递白名单
    ↓
ondemand_collect_subscriber.py::OndemandCollectSubscriber (M7-B)  ← 新增
    │  读取 allowed_params，裁剪 PLC 读取 configs

cleanup_invalid_device_params.py (M6)
    ── 本版本不实施（PM OQ-v0.5.7-03）
```

---

## 测试要点（v0.5.7-rev1）

### 原有模块（M1~M5）

| 测试场景 | 期望结果 |
|---------|---------|
| 专有部分已同步设备树，存在 4 个房间（无儿童房） | `get_available_sub_types()` 不含 `panel_fourth_children` |
| 专有部分已同步设备树，存在 5 个房间（含儿童房） | `get_available_sub_types()` 含 `panel_fourth_children` |
| **fix2 新增**：`9-1-10-1001`（含书房 + 含儿童房，6 间） | `get_available_sub_types()` **含** `panel_fourth_children` |
| **fix2 新增**：`9-1-10-1002`（含儿童房但无书房，5 间） | `get_available_sub_types()` **不含** `panel_fourth_children` |
| **fix2 新增**：三房（5 间，含儿童房，无书房）—— 验证修复有效 | `_match_panel_sub_types()` 不含 `panel_fourth_children` |
| **fix2 新增**：四房（6 间，含书房 + 含儿童房）—— 验证正向激活 | `_match_panel_sub_types()` 含 `panel_fourth_children` |
| 专有部分未同步设备树（device_floor 无记录）**（OQ-02 方案 B 锁定）** | `get_available_sub_types()` 仅含 `SYSTEM_LEVEL_SUB_TYPES`，所有 `panel_*` 不可用 |
| 缓存命中：连续两次调用同一 specific_part | 第二次不查 DB（通过 mock 验证） |
| 缓存失效：invalidate 后再次调用 | 重新查 DB |
| `get_panel_param_blocklist()` 对不存在的房间 | 返回对应 panel_* sub_type 下所有 param_name |
| `PLCLatestDataHandler` 处理含不存在房间参数的消息 | blocklist 内参数不写入 plc_latest_data |
| `device_settings_params()` 对无儿童房的专有部分 | 响应中不含 panel_fourth_children 的参数分组 |
| `get_device_realtime_params()` 对无书房的专有部分 | 响应中不含 panel_study_room 的 sub_type |

### M7 采集侧裁剪（新增，FR-v0.5.7-05，PM OQ-04 锁定）

| 测试场景 | 期望结果 |
|---------|---------|
| `ondemand_refresh()` 对已同步设备树的专有部分 | MQTT payload 中 `allowed_params` 列表仅含可用 sub_type 下的 param_name |
| `ondemand_refresh()` 对未同步设备树的专有部分（降级） | `allowed_params` 仅含系统级参数的 param_name |
| `OndemandCollectSubscriber._on_request()` 收到含 `allowed_params` 的 payload | `allowed_params` 正确解析为 set，传入 `_execute_ondemand()` |
| `_execute_ondemand()` 收到 `allowed_params={"param_a", "param_b"}` | `configs` 列表仅含白名单内参数的读取配置；PLC 读取次数 = `len(allowed_params)` |
| `_execute_ondemand()` 收到 `allowed_params=None`（向后兼容） | `configs` 列表含 plc_config.json 全量参数（原有行为） |
| 采集侧完成采集后，result MQTT 消息不含 `fourth_children_room_*` 参数（白名单已过滤） | `data_dict` 中无 `fourth_children_room_*` 键；DB 不新增这些参数记录 |
| 采集侧日志验证 | 存在「采集侧裁剪: specific_part=X, 实际采集 N / 总计 50 个参数」级别的 INFO 日志 |

### M6 清理命令（本版本不测试）

M6 本版本不实施，无需测试场景。
