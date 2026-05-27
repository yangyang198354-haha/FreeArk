# 模块设计文档

```
file_header:
  document_id: MOD-v0.5.3-FCC
  title: 设备列表「故障数量」列 + OpenClaw 故障查询工具 — 模块设计
  author_agent: sub_agent_system_architect (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: v0.5.3-fault-count-column
  created_at: 2026-05-26
  status: DRAFT
  references:
    - docs/architecture/architecture_design_v0.5.3_fault_count_column.md
    - docs/requirements/v0.5.3_fault_count_column/requirements_spec.md
```

---

## 1. 模块清单

| 模块 ID | 文件路径 | 类型 | 操作 |
|---------|---------|------|------|
| MOD-BE-FC-01 | `FreeArkWeb/backend/freearkweb/api/fault_utils.py` | 后端 Python 模块 | 新增 |
| MOD-BE-FC-02 | `FreeArkWeb/backend/freearkweb/api/views.py` | 后端视图 | 修改（追加两个视图函数，修改一个视图函数）|
| MOD-BE-FC-03 | `FreeArkWeb/backend/freearkweb/api/urls.py` | 后端路由 | 修改（追加两条 path）|
| MOD-BE-FC-04 | `FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py` | 后端 MQTT Handler | **不修改**（OQ-01 裁决：废止写入端缓存失效钩子，改用 TTL 刷新）|
| MOD-FE-FC-01 | `FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue` | 前端 Vue 组件 | 修改（template 追加一列，无 script 改动）|
| MOD-SKILL-FC-01 | `agents/freeark-skill/SKILL.md` | OpenClaw Skill 文档 | 修改（追加 2 个工具定义）|
| MOD-SKILL-FC-02 | `agents/freeark-skill/scripts/freeark_tool.py` | OpenClaw 工具 CLI | 修改（追加 2 个工具路由）|

---

## 2. MOD-BE-FC-01：fault_utils.py（新增）

### 2.1 职责

- 集中定义故障字段识别规则（`FAULT_PARAM_NAMES`、`is_fault_param()`）
- 实现故障数量计算逻辑（`count_faults_for_row()`，包含 fresh_air_fault_status 位域 popcount；`compute_fault_count_v2()` 作为包装保留）
- 封装缓存读写操作（`get_fault_count_cached()`、`get_fault_count_batch_cached()`）
- 封装 DB 查询逻辑（`_compute_from_db_batch()`）

> **TODO(AB-001)**：当前缓存后端为 Django LocMemCache（进程内）。未来若扩展为多进程部署或出现第二个跨进程共享缓存需求，需将 `CACHES` 配置迁移至 Redis，本模块所有 `cache.get/set/delete` 调用无需修改（Django cache 框架透明切换）。详见 `architecture_design_v0.5.3_fault_count_column.md` 第 12 节 AB-001。

### 2.2 公共接口定义

```python
# --- 常量 ---
FAULT_PARAM_NAMES: frozenset[str]
# 包含 25 个具名故障字段（见 requirements_spec.md 第 6 节）+ 'comm_fault_timeout'
# 不包含 'fresh_air_fault_status'（由 compute_fault_count_v2 特殊处理）

_FAULT_CACHE_PREFIX: str = 'fault_count:'
_FAULT_CACHE_TTL: int = 60  # 秒（ADR-FC-005 修订：短 TTL 刷新，满足 US-FC-05 ≤60s 延迟要求）
# TODO(AB-001): 若未来切换至 Redis，_FAULT_CACHE_TTL 值不变，仅修改 settings.py CACHES 配置。

# --- 函数 ---

def is_fault_param(param_name: str) -> bool:
    """
    判断参数名是否属于故障字段。
    返回 True 的条件：
    1. param_name in FAULT_PARAM_NAMES（含 comm_fault_timeout）
    2. 匹配正则 ^error_\d+$（PLC 故障码位字段）
    """

def count_faults_for_row(param_name: str, value: Optional[int]) -> int:
    """
    计算单行记录对故障总数的贡献（ADR-FC-006）。
    逻辑：
    - param_name == 'fresh_air_fault_status':
        若 value is None or value == 0 → 返回 0
        否则 → 返回 bin(int(value)).count('1')（popcount，每个置1的bit算1个故障）
        Python 3.10+ 可用 int(value).bit_count()；兼容写法用 bin(int(value)).count('1')
    - is_fault_param(param_name) and value is not None and value != 0 → 返回 1
    - 其他（含 value is None or value == 0）→ 返回 0
    """

def compute_fault_count_v2(records: Iterable[tuple[str, Optional[int]]]) -> int:
    """
    计算一组记录的故障总数（count_faults_for_row 的批量包装，供 _compute_from_db_batch 使用）。
    参数 records：(param_name, value) 的可迭代对象。
    逻辑：sum(count_faults_for_row(pn, v) for pn, v in records)
    返回：故障总数（整数，≥0）
    """

def get_fault_count_cached(specific_part: str) -> Optional[int]:
    """
    获取单个 specific_part 的故障数量（带缓存）。
    缓存未命中时调用 _compute_from_db_batch([specific_part]) 计算并填充。
    返回：
    - int（≥0）：故障数量
    - None：PLCLatestData 无该 specific_part 记录
    """

def get_fault_count_batch_cached(specific_parts: list[str]) -> dict[str, Optional[int]]:
    """
    批量获取多个 specific_part 的故障数量（带缓存）。
    优先从缓存读取，未命中的 specific_part 批量查 DB 后填充缓存。
    返回：{specific_part: fault_count_or_none} 字典
    """

def invalidate_fault_count_cache(specific_part: str) -> None:
    """
    （备用）主动清除指定 specific_part 的故障数量缓存条目。
    OQ-01 裁决后，mqtt_handlers.py 不调用此函数（缓存由 TTL=60s 自动过期）。
    保留供未来切换至写入端钩子（ADR-FC-005 方案 B）时直接启用。
    """

def get_fault_details(specific_part: str) -> list[dict]:
    """
    获取处于故障状态的参数列表（仅当前非正常的字段）。
    返回：[{"param_name": str, "value": int}, ...]，按 param_name 升序
    用于 /api/devices/fault-count/ 响应中的 fault_details 字段。
    """

def get_fault_details_updated_at(specific_part: str) -> Optional[datetime]:
    """
    获取该 specific_part 故障相关字段的最新 updated_at 时间戳。
    用于 /api/devices/fault-count/ 响应中的 updated_at 字段。
    """

# --- 内部函数（不对外暴露）---

def _compute_from_db_batch(specific_parts: list[str]) -> dict[str, Optional[int]]:
    """
    批量从 PLCLatestData DB 查询并计算故障数量。
    使用单条 SQL（Q 对象组合 OR 条件），避免 N+1 查询。
    SQL 核心条件：
    WHERE specific_part IN (...) AND (
        param_name IN (<FAULT_PARAM_NAMES 列表>) OR
        param_name LIKE 'error_%' OR
        param_name = 'fresh_air_fault_status'
    )
    """
```

### 2.3 依赖关系

```
fault_utils.py
  ├── 依赖：django.core.cache（LocMemCache）
  ├── 依赖：api.models.PLCLatestData
  └── 依赖：django.db.models.Q
  
被依赖：
  ├── api.views（views.py）
  └── api.mqtt_handlers（PLCLatestDataHandler）
```

---

## 3. MOD-BE-FC-02：views.py 修改

### 3.1 修改 device_management_device_list()

**现有逻辑**：查询 `PLCConnectionStatus` 分页，JOIN `OwnerInfo`，构建响应列表。

**追加逻辑**：在构建 `results` 列表前，提取本页所有 `specific_part`，调用 `get_fault_count_batch_cached()` 批量获取故障数量，将结果 `fault_count` 写入每条记录。

```python
# 伪代码，追加于现有 device_management_device_list 函数中
from .fault_utils import get_fault_count_batch_cached

# 1. 获取本页 specific_part 列表
page_specific_parts = [row['specific_part'] for row in page_results]

# 2. 批量获取故障数量（缓存 + DB）
fault_counts = get_fault_count_batch_cached(page_specific_parts)

# 3. 将 fault_count 追加到每条结果
for row in page_results:
    row['fault_count'] = fault_counts.get(row['specific_part'])
```

### 3.2 新增 device_fault_count()

```python
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def device_fault_count(request):
    """
    查询指定专有部分的故障数量和故障明细。
    GET /api/devices/fault-count/?specific_part=3-1-7-702[,3-1-7-703,...]
    
    参数：
        specific_part (str): 必须，逗号分隔，最多 50 个
    
    返回：
        200: {success: true, data: [{specific_part, fault_count, fault_details, updated_at}], queried_at}
        400: 参数缺失或超限
        401: 未鉴权（DRF 默认）
        500: 内部错误
    """
```

**参数校验逻辑**：
1. `specific_part` 参数缺失 → 400
2. 按逗号分割并去除空白 → 列表
3. 列表长度 > 50 → 400
4. 调用 `get_fault_count_batch_cached()` 获取故障数量
5. 对每个 `specific_part` 调用 `get_fault_details()` 获取详情（仅对故障数 > 0 的才查详情，减少 DB 查询）
6. 构建响应

### 3.3 新增 device_fault_summary()

```python
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def device_fault_summary(request):
    """
    查询有故障的专有部分汇总。
    GET /api/devices/fault-summary/
    
    可选参数：
        building (str): 楼栋过滤
        unit (str): 单元过滤
        min_fault_count (int): 最小故障数，默认 1
    
    返回：
        200: {success: true, total_with_faults, data: [{specific_part, building, unit, room_number, fault_count}], queried_at}
        400: min_fault_count 非法
        401: 未鉴权
        500: 内部错误
    """
```

**实现策略**：
1. 从 `OwnerInfo` 查询所有 specific_part（支持 `building`/`unit` 过滤）
2. 调用 `get_fault_count_batch_cached()` 批量获取所有 specific_part 的故障数量（`OwnerInfo` 记录数量有限，数十到数百，可全量加载）
3. 过滤 `fault_count >= min_fault_count` 且 `fault_count is not None`
4. 按 `fault_count` 降序排序，取前 100 条
5. Join `OwnerInfo` 补充 `building`/`unit`/`room_number`

---

## 4. MOD-BE-FC-03：urls.py 修改

在现有 `urlpatterns` 中追加：

```python
# 故障数量查询（v0.5.3-FCC, REQ-FUNC-FC-05/06）
path('devices/fault-count/', views.device_fault_count, name='device-fault-count'),
path('devices/fault-summary/', views.device_fault_summary, name='device-fault-summary'),
```

插入位置：在 `path('devices/ondemand-refresh/', ...)` 之后。

---

## 5. MOD-BE-FC-04：mqtt_handlers.py——不修改（OQ-01 裁决）

> **OQ-01 裁决（2026-05-26）**：本版本不采用 MQTT 事件驱动缓存失效（原 ADR-FC-005 方案已废止，改为短 TTL 定时刷新）。`PLCLatestDataHandler.handle()` 和 `_bulk_upsert()` **无需任何改动**，故障数缓存通过 TTL=60s 自动过期。

**不修改原因**：
- 缓存失效由 TTL=60s 自动处理（ADR-FC-005 修订方案 A）。
- 不在 MQTT handler 中引入对 `fault_utils.py` 的依赖，保持 MQTT 数据写入链路与业务层解耦。
- 符合"最小侵入"设计目标。

**未来可选升级**（不在本版本执行）：若需要更低延迟（< 60s），可在 `_bulk_upsert` 成功后追加 `invalidate_fault_count_cache(specific_part)` 调用，切换为方案 B（见 ADR-FC-005 方案评估表）。

| Handler | 是否修改 | 原因 |
|---------|---------|------|
| `PLCLatestDataHandler` | **否** | 缓存由 TTL 自动失效；OQ-01 裁决后不做写入端钩子 |
| `PLCDataHandler` | 否 | 能耗 handler，不涉及故障字段 |
| `OndemandPLCLatestDataHandler` | 否 | 按需采集，继承 PLCLatestDataHandler，无额外修改 |
| `ScreenConnectivityHandler` | 否 | 大屏心跳 handler，不涉及故障字段 |

---

## 6. MOD-FE-FC-01：DeviceManagementDeviceListView.vue 修改

### 6.1 Template 改动（精确位置）

在第 129-138 行（`<el-table-column label="运行模式" ...>`）和第 139-166 行（`<el-table-column label="操作" ...>`）之间插入：

```html
<el-table-column label="故障数量" width="100" align="center">
  <template #default="{ row }">
    <span
      v-if="row.fault_count === null || row.fault_count === undefined"
      style="color: #909399;"
    >—</span>
    <span
      v-else
      :style="{
        color: row.fault_count === 0 ? 'var(--color-success)' : 'var(--color-danger)',
        fontWeight: 600
      }"
    >{{ row.fault_count }}</span>
  </template>
</el-table-column>
```

### 6.2 Script 无需修改

- `tableData` ref 已包含 API 返回的所有字段（包括新增的 `fault_count`）
- `fetchList()` 函数已将 `response.results` 赋给 `tableData.value`，新字段自动包含
- 无需新增 data/ref/computed/method

### 6.3 Style 无需修改

颜色使用 CSS 变量 `var(--color-success)` 和 `var(--color-danger)`，这些变量已在 `global.css` 中定义，与 `DeviceCardsView.vue` 中 `.status-ok` 和 `.status-fault` 使用同一变量源。

---

## 7. MOD-SKILL-FC-01：SKILL.md 修改

### 7.1 Tier-1 工具表格追加两行

在 `## Tier-1 只读工具（14 个，无需确认）` 小节的表格末尾追加：

```markdown
| `freeark_get_fault_count` | 查询指定专有部分的当前故障数量和故障参数明细 | `specific_part`（必须，逗号分隔最多 50 个，如 `"3-1-7-702"` 或 `"3-1-7-702,3-1-8-802"`）|
| `freeark_get_fault_summary` | 查询全系统/楼栋/单元中有故障的专有部分汇总（按故障数降序，最多 100 条）| 可选：`building`（楼栋，如 `"3"`），`unit`（单元，如 `"1"`），`min_fault_count`（最小故障数，默认 1）|
```

### 7.2 版本号更新

将文件末尾版本号从 `v2.1.0` 改为 `v2.2.0`，并追加变更说明：

```markdown
## 版本

v2.2.0（新增 freeark_get_fault_count 和 freeark_get_fault_summary 工具 — v0.5.3-FCC）
```

---

## 8. MOD-SKILL-FC-02：freeark_tool.py 修改

### 8.1 工具路由追加

在工具路由映射字典（或 if-elif 链）中追加：

```python
elif tool == 'freeark_get_fault_count':
    # 参数：specific_part（必须）
    specific_part = params.get('specific_part')
    if not specific_part:
        return {'success': False, 'error': '参数 specific_part 不能为空'}
    resp = _api_get(f'/api/devices/fault-count/?specific_part={requests.utils.quote(specific_part)}')
    # 生成 summary（用于 OpenClaw 快速理解）
    if resp.get('success') and resp.get('data'):
        parts = resp['data']
        total_faults = sum(p.get('fault_count') or 0 for p in parts)
        summary = f"查询了 {len(parts)} 个专有部分，共 {total_faults} 个故障"
    else:
        summary = "查询完成"
    return {**resp, 'summary': summary}

elif tool == 'freeark_get_fault_summary':
    # 参数：building（可选）、unit（可选）、min_fault_count（可选，默认 1）
    query_params = {}
    if params.get('building'):
        query_params['building'] = params['building']
    if params.get('unit'):
        query_params['unit'] = params['unit']
    if params.get('min_fault_count') is not None:
        query_params['min_fault_count'] = str(params['min_fault_count'])
    query_string = '&'.join(f'{k}={v}' for k, v in query_params.items())
    url = f'/api/devices/fault-summary/{"?" + query_string if query_string else ""}'
    resp = _api_get(url)
    if resp.get('success'):
        total = resp.get('total_with_faults', 0)
        summary = f"共 {total} 个专有部分有故障"
    else:
        summary = "查询完成"
    return {**resp, 'summary': summary}
```

---

## 9. 接口依赖矩阵

| 消费方 | 依赖接口 | 接口位置 |
|--------|---------|---------|
| `views.device_management_device_list()` | `get_fault_count_batch_cached(list[str])` | `fault_utils.py` |
| `views.device_fault_count()` | `get_fault_count_batch_cached()`, `get_fault_details()`, `get_fault_details_updated_at()` | `fault_utils.py` |
| `views.device_fault_summary()` | `get_fault_count_batch_cached()` | `fault_utils.py` |
| `PLCLatestDataHandler.handle()` | （不依赖 fault_utils，OQ-01 裁决废止写入端钩子）| — |
| `fault_utils._compute_from_db_batch()` | `PLCLatestData.objects.filter()` | `models.py`（不修改）|
| `fault_utils.get_*_cached()` | `django.core.cache.cache` | Django 框架（不修改）|
| `freeark_tool.py` | `GET /api/devices/fault-count/`, `GET /api/devices/fault-summary/` | Django REST API |

---

## 10. 测试要点（供测试阶段参考）

| 测试类型 | 测试场景 |
|---------|---------|
| 单元测试 | `is_fault_param()` 对各类 param_name 的判定（正例/负例）|
| 单元测试 | `compute_fault_count_v2()` 对普通故障、位域故障、混合场景的计算 |
| 单元测试 | 缓存命中/未命中逻辑（mock Django cache）|
| 集成测试 | `GET /api/devices/fault-count/` 返回正确 fault_count 和 fault_details |
| 集成测试 | `GET /api/device-management/device-list/` 响应包含 `fault_count` 字段 |
| 集成测试 | `PLCLatestDataHandler` 写入后缓存失效、再次查询返回更新值 |
| 集成测试 | `GET /api/devices/fault-summary/?building=3` 过滤正确 |
| 端到端测试 | 前端设备列表「故障数量」列正确显示并着色（绿/红）|
| 性能测试 | 20 条分页列表 P95 响应时间（缓存热/冷状态各测）|
