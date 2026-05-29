# 模块设计文档

```
file_header:
  document_id: MOD-v0.7.0-CW
  title: 结露预警管理页面 — 模块设计
  author_agent: sub_agent_system_architect (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.7.0-condensation-warning
  created_at: 2026-05-30
  status: APPROVED
  references:
    - docs/architecture/architecture_design_v0.7.0_condensation_warning.md
    - docs/requirements/v0.7.0_condensation_warning/requirements_spec.md
    - FreeArkWeb/backend/freearkweb/api/fault_consumer/state_machine.py
    - FreeArkWeb/backend/freearkweb/api/management/commands/fault_consumer.py
    - FreeArkWeb/backend/freearkweb/api/views_fault.py
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 1.0.0-APPROVED | 2026-05-30 | 初始正式版本，MOD-BE-CW-01~07 + MOD-FE-CW-01~03 + MOD-INFRA-CW-01~03 |

---

## 模块总览

本版本新增 13 个模块，其中 7 个后端模块、3 个前端模块、3 个基础设施模块。

| 模块 ID | 文件路径 | 职责 | 对标故障管理模块 |
|---------|---------|------|----------------|
| MOD-BE-CW-01 | `api/condensation_consumer/__init__.py` | 包标记 | `fault_consumer/__init__.py` |
| MOD-BE-CW-02 | `api/condensation_consumer/state_machine.py` | 进程内状态机（T1/T2/T3） | `fault_consumer/state_machine.py` |
| MOD-BE-CW-03 | `api/management/commands/condensation_consumer.py` | Django Management Command，MQTT 消费主循环 | `management/commands/fault_consumer.py` |
| MOD-BE-CW-04 | `api/management/commands/condensation_cleanup.py` | Django Management Command，90 天清理 | `management/commands/fault_cleanup.py` |
| MOD-BE-CW-05 | `api/models.py`（追加 CondensationWarningEvent） | 数据模型 | `models.py` FaultEvent |
| MOD-BE-CW-06 | `api/views_condensation.py`（新文件） | REST API 视图 | `views_fault.py` |
| MOD-BE-CW-07 | `api/serializers_condensation.py`（新文件） | DRF 序列化器（含 is_screen_online） | `serializers_fault.py` |
| MOD-FE-CW-01 | `frontend/src/views/CondensationWarningView.vue`（新文件） | 结露预警列表页 | `FaultManagementView.vue` |
| MOD-FE-CW-02 | `frontend/src/router/index.js`（修改） | 新增路由 | 故障管理路由条目 |
| MOD-FE-CW-03 | `frontend/src/components/Layout.vue`（修改） | 新增导航菜单项 | 故障管理菜单项 |
| MOD-INFRA-CW-01 | `deployment/systemd/freeark-condensation-consumer.service` | 消费者服务 | `freeark-fault-consumer.service` |
| MOD-INFRA-CW-02 | `deployment/systemd/freeark-condensation-cleanup.service` | 清理服务 | `freeark-fault-cleanup.service` |
| MOD-INFRA-CW-03 | `deployment/systemd/freeark-condensation-cleanup.timer` | 清理定时器 | `freeark-fault-cleanup.timer` |
| DB-CW-01 | `api/migrations/0029_add_condensation_warning_event.py` | 数据库迁移（新表 DDL） | `0026_add_fault_event.py` |

**不修改的已有模块（直接复用）**：

| 模块 | 复用路径 |
|------|---------|
| `fault_consumer/room_lookup.py` | condensation_consumer/state_machine.py 直接 import |
| `utils_room_filter.py` | 不需要（结露预警无按房间名过滤需求） |
| `CascadingSelector.vue` | CondensationWarningView.vue 直接引用，无修改 |
| `api/urls.py` | 追加 1 条路由，不重构现有路由 |

---

## 模块详细设计

---

### MOD-BE-CW-02：condensation_consumer/state_machine.py

**文件路径**：`FreeArkWeb/backend/freearkweb/api/condensation_consumer/state_machine.py`

**职责**：进程内结露预警状态机，实现 T1/T2/T3 三条转移规则。

**关键函数签名**：

```python
@dataclass
class CondensationState:
    event_id: int
    is_active: bool
    last_seen_at: datetime

# 模块级单例
_cw_state_machine: dict = {}  # key: (specific_part, device_sn)

def rebuild_from_db() -> int:
    """进程启动时从 DB 重建（IS_ACTIVE=True LIMIT 10000）。"""

def process_condensation_alarm(
    specific_part: str,
    device_sn: str,
    product_code: str,
    is_active_now: bool,
    received_at: datetime,
    # T1 快照字段
    condensation_alarm_value: str | None,
    dew_point_temp: str | None,
    ntc_temp: str | None,
    humidity: str | None,
    system_switch: str | None,
) -> None:
    """状态机核心入口，处理单个设备的 condensation_alarm 状态变化。"""

def get_state(key: tuple) -> CondensationState | None:
    """获取指定 key 的当前状态（仅供测试/日志）。"""

def get_state_machine_size() -> int:
    """返回当前状态机条目数。"""
```

**内部函数**：

```python
def _t1_insert(key, specific_part, device_sn, product_code,
               received_at, condensation_alarm_value,
               dew_point_temp, ntc_temp, humidity, system_switch) -> None:
    """T1 转移：INSERT condensation_warning_event + 填充 room_name/room_id。
    IntegrityError 兜底：fallback to UPDATE last_seen_at。
    """
    # 调用 fault_consumer.room_lookup.get_room_for_device(device_sn)
    # 调用 _get_system_switch_for_specific_part 已在 caller 侧完成，直接接收

def _t1_fallback_update(key, specific_part, device_sn, received_at) -> None:
    """T1 IntegrityError 兜底：更新最新活跃行的 last_seen_at。"""

def _t3_recover(key, state, received_at) -> None:
    """T3 转移：UPDATE SET is_active=False, recovered_at, last_seen_at。"""

def _get_system_switch_for_specific_part(specific_part: str) -> str:
    """ADR-CW-01 方案 A：查 PLCLatestData(specific_part, param_name='system_switch')。
    返回 'on' / 'off' / 'unknown'。
    """
```

**依赖**：
- `api.models.CondensationWarningEvent`（T1 INSERT / T3 UPDATE）
- `api.models.PLCLatestData`（system_switch 兜底查询）
- `api.fault_consumer.room_lookup.get_room_for_device`（直接 import，无需改动）
- `django.db.close_old_connections`（每次 DB 操作前调用）
- `django.db.IntegrityError`, `OperationalError`

**与 fault_consumer/state_machine.py 的差异对照表**：

| 项目 | fault_consumer | condensation_consumer |
|------|---------------|----------------------|
| 状态字典名 | `_state_machine` | `_cw_state_machine` |
| key 维度 | `(specific_part, device_sn, fault_code)` | `(specific_part, device_sn)` |
| T1 额外字段 | 无快照字段 | dew_point_temp/ntc_temp/humidity/system_switch/condensation_alarm_value |
| T1 额外逻辑 | 无 | 调用 _get_system_switch_for_specific_part（ADR-CW-01） |
| 重建查询 | `FaultEvent.objects.filter(is_active=True)[:10000]` | `CondensationWarningEvent.objects.filter(is_active=True)[:10000]` |
| 模型 | FaultEvent | CondensationWarningEvent |

---

### MOD-BE-CW-03：management/commands/condensation_consumer.py

**文件路径**：`FreeArkWeb/backend/freearkweb/api/management/commands/condensation_consumer.py`

**职责**：Django Management Command，MQTT 消费主循环，驱动结露预警状态机。

**关键函数签名**：

```python
class Command(BaseCommand):
    help = '结露预警 MQTT 消费者（freeark-condensation-consumer）'

    def handle(self, *args, **options):
        """启动流程：加载配置 → 重建状态机 → 初始化 MacCache → paho 回调 → loop_forever。"""

def _load_condensation_consumer_config() -> dict:
    """复用 heartbeat_broker_config.json，独立 client_id='freeark-condensation-consumer'。"""

class _MacCache:
    """与 fault_consumer 相同实现：OwnerInfo → specific_part，5min 刷新。"""

def _handle_message(msg, mac_cache: _MacCache) -> None:
    """解析 DeviceStatusUpdate 报文，提取 condensation_alarm 及快照字段，驱动状态机。"""
```

**_handle_message 核心逻辑**：

```
1. JSON 解析 → 验证 header.name == "DeviceStatusUpdate"
2. topic 末段取 MAC → mac_cache.get_specific_part(mac) → specific_part
3. 提取 payload.data: deviceSn, productCode, items[]
4. 从 items[] 收集：
   - condensation_alarm 值（attrTag='condensation_alarm'）
   - 同 deviceSn 的 dew_point_temp, NTC_temp, humidity（attrTag 匹配）
   - 同 deviceSn 的 system_switch（attrTag 匹配，优先直取）
5. 若未找到 condensation_alarm → 跳过本报文（非预警设备/报文）
6. is_active_now = int(condensation_alarm_value) != 0（解析失败→ False + WARNING 日志）
7. 若 items[] 中无 system_switch → 调用 _get_system_switch_for_specific_part（在 state_machine 内）
8. process_condensation_alarm(specific_part, device_sn, product_code, is_active_now, ...)
```

**配置参数**（来自 heartbeat_broker_config.json）：

| 参数 | 说明 |
|------|------|
| client_id | 固定 'freeark-condensation-consumer'（不从配置文件读，防误用） |
| topic | 复用 fault_consumer_topic（'/screen/upload/screen/to/cloud/+'） |
| protocol/host/port/path/username/password | 从配置文件读，fallback 使用默认值 |

---

### MOD-BE-CW-04：management/commands/condensation_cleanup.py

**文件路径**：`FreeArkWeb/backend/freearkweb/api/management/commands/condensation_cleanup.py`

**职责**：分批硬删除 90 天以上已恢复的结露预警记录，活跃记录豁免。

**命令行参数**（镜像 fault_cleanup.py）：

```
--days      保留天数，默认 90
--batch-size 每批删除行数，默认 1000
--once      执行一次后退出（由 systemd oneshot 驱动）
```

**核心逻辑**：

```python
from django.utils import timezone
from datetime import timedelta

def _run_cleanup(days: int, batch_size: int) -> int:
    """执行一次清理，返回删除总行数。"""
    cutoff = timezone.now() - timedelta(days=days)
    total = 0
    while True:
        # 分批查出待删 id（活跃记录豁免）
        ids = list(
            CondensationWarningEvent.objects
            .filter(is_active=False, first_seen_at__lt=cutoff)
            .values_list('id', flat=True)[:batch_size]
        )
        if not ids:
            break
        deleted, _ = CondensationWarningEvent.objects.filter(id__in=ids).delete()
        total += deleted
        logger.info('condensation_cleanup: 本批删除 %d 行，累计 %d 行', deleted, total)
        if deleted < batch_size:
            break
    return total
```

---

### MOD-BE-CW-06：views_condensation.py

**文件路径**：`FreeArkWeb/backend/freearkweb/api/views_condensation.py`

**职责**：提供 GET /api/devices/condensation-warning-events/ 接口。

**视图函数签名**：

```python
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def condensation_warning_event_list(request) -> Response:
    """分页查询结露预警事件，支持 specific_part/is_active/时间段过滤，
    注入 is_screen_online 字段。"""
```

**过滤逻辑（复用 views_fault.py 相同段数映射）**：

```python
# specific_part 段数映射（完整复用，无修改）
sp = request.query_params.get('specific_part', '').strip()
if sp:
    parts = sp.split('-')
    if len(parts) == 3:
        prefix = f"{parts[0]}-{parts[1]}-"
        suffix = f"-{parts[2]}"
        qs = qs.filter(specific_part__startswith=prefix, specific_part__endswith=suffix)
    else:
        qs = qs.filter(specific_part__icontains=sp)

# is_active 过滤（同 views_fault.py）
# first_seen_at 时间范围过滤（默认 7 天，同 views_fault.py）
# 排序：-first_seen_at
# 分页：FaultEventPagination（复用同一分页类，或新建 CondensationWarningPagination）
```

**is_screen_online 注入（分页后执行）**：

```python
page = paginator.paginate_queryset(qs, request)
serializer = CondensationWarningEventSerializer(page, many=True)
data = serializer.data
# 注入 is_screen_online
data = _inject_screen_online(list(data))
return paginator.get_paginated_response(data)
```

---

### MOD-BE-CW-07：serializers_condensation.py

**文件路径**：`FreeArkWeb/backend/freearkweb/api/serializers_condensation.py`

**职责**：DRF 序列化器，将 CondensationWarningEvent 转为 JSON，is_screen_online 在视图层注入。

```python
from rest_framework import serializers
from .models import CondensationWarningEvent

class CondensationWarningEventSerializer(serializers.ModelSerializer):
    """只读序列化器。is_screen_online 由视图层 _inject_screen_online 注入到 dict 中，
    不在序列化器中声明（避免 N+1 查询）。"""

    class Meta:
        model = CondensationWarningEvent
        fields = [
            'id', 'specific_part', 'room_name', 'device_sn', 'product_code',
            'warning_type', 'warning_message', 'condensation_alarm_value',
            'dew_point_temp', 'ntc_temp', 'humidity', 'system_switch',
            'first_seen_at', 'last_seen_at', 'recovered_at', 'is_active',
        ]
        read_only_fields = fields
```

**时区处理**：`first_seen_at`/`last_seen_at`/`recovered_at` 均为 DateTimeField，USE_TZ=True 时序列化为 ISO8601 含时区字符串；与故障管理序列化器行为一致。

---

### MOD-FE-CW-01：CondensationWarningView.vue

**文件路径**：`FreeArkWeb/frontend/src/views/CondensationWarningView.vue`

**职责**：结露预警列表页，12 列表格 + 过滤器三件套 + 分页。

**关键状态变量**：

```javascript
// 与 FaultManagementView 对应关系
filterIsActive: 'true'            // 默认"未回复"（对应 is_active=true）
filters: {
  dateRange: [startDate, endDate] // 默认最近 7 天
}
// ref: cwCascadingSelectorRef    // 房号三级联动

warningList: []                   // 当前页数据
totalCount: 0
currentPage: 1
pageSize: 20
loading: false
```

**fetchWarnings() 关键实现**：

```javascript
async fetchWarnings() {
  this.loading = true;
  const params = new URLSearchParams();

  if (this.filterIsActive !== 'all') {
    params.append('is_active', this.filterIsActive);
  }

  // 房号（CascadingSelector 输出 3 段格式）
  const sp = this._getCascadingValue();
  if (sp) params.append('specific_part', sp);

  // 时间段
  if (this.filters.dateRange && this.filters.dateRange.length === 2) {
    params.append('first_seen_after', this.filters.dateRange[0]);
    params.append('first_seen_before', this.filters.dateRange[1]);
  } else {
    // 默认最近 7 天
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
    params.append('first_seen_after', sevenDaysAgo.toISOString().split('T')[0]);
  }

  params.append('page', this.currentPage);
  params.append('page_size', this.pageSize);

  try {
    const res = await api.get(`/api/devices/condensation-warning-events/?${params.toString()}`);
    this.warningList = res.data.results;
    this.totalCount = res.data.count;
  } catch (e) {
    ElMessage.error('获取结露预警列表失败');
  } finally {
    this.loading = false;
  }
}
```

**表格渲染要点**：

| 列 | 渲染逻辑 |
|---|---------|
| 大屏是否在线 | `is_screen_online ? '在线' : '离线'`，在线绿色（`color:#67C23A`），离线灰色（`color:#909399`） |
| 系统开关 | `system_switch === 'on' ? '开启' : system_switch === 'off' ? '关闭' : '-'`（null/"unknown" → "-"） |
| 露点温度/NTC温度 | `value ? value + ' °C' : '-'` |
| 湿度 | `value ? value + ' %' : '-'` |
| 时间列 | 格式化为 `YYYY-MM-DD HH:mm:ss`，复用故障管理的格式化函数 |
| 恢复时间 | `recovered_at || '-'` |

---

### DB-CW-01：migration 0029

**文件路径**：`FreeArkWeb/backend/freearkweb/api/migrations/0029_add_condensation_warning_event.py`

**依赖**：`['api', '0028_fault_event_backfill_room']`

**操作**：单一 `migrations.CreateModel`（DDL only，无数据回填）

**生成方式**：由 `python manage.py makemigrations` 自动生成（基于 CondensationWarningEvent Model 定义）；开发者无需手写，但需验证：
1. 依赖关系为 `0028_fault_event_backfill_room`
2. 三个 Index 和一个 UniqueConstraint 均出现在迁移中
3. ForeignKey to DeviceRoom 使用 `on_delete=SET_NULL`

---

## 模块间依赖关系

```
condensation_consumer.py (MOD-BE-CW-03)
  ├─→ condensation_consumer/state_machine.py (MOD-BE-CW-02)
  │     ├─→ api.models.CondensationWarningEvent (MOD-BE-CW-05)
  │     ├─→ api.models.PLCLatestData (已有)
  │     └─→ api.fault_consumer.room_lookup (已有，直接复用)
  └─→ api.models.OwnerInfo (已有)

views_condensation.py (MOD-BE-CW-06)
  ├─→ api.models.CondensationWarningEvent (MOD-BE-CW-05)
  ├─→ api.models.ScreenConnectivityStatus (已有)
  └─→ serializers_condensation.py (MOD-BE-CW-07)

CondensationWarningView.vue (MOD-FE-CW-01)
  ├─→ CascadingSelector.vue (已有，无修改)
  └─→ api.get('/api/devices/condensation-warning-events/')

urls.py (追加)
  └─→ views_condensation.condensation_warning_event_list
```

---

## 代码量估算

| 模块 | 估算代码行数 | 说明 |
|------|------------|------|
| MOD-BE-CW-02 state_machine.py | ~180 行 | 镜像 fault_consumer/state_machine.py（~235 行），无 fault_classifier 依赖，但增加快照字段逻辑和 _get_system_switch |
| MOD-BE-CW-03 condensation_consumer.py | ~200 行 | 镜像 fault_consumer.py（~304 行），_handle_message 简化（单字段检测） |
| MOD-BE-CW-04 condensation_cleanup.py | ~80 行 | 镜像 fault_cleanup.py |
| MOD-BE-CW-05 models.py 追加 | ~50 行 | CondensationWarningEvent 模型 |
| MOD-BE-CW-06 views_condensation.py | ~120 行 | 镜像 views_fault.py 主视图函数（去掉 sub_type/fault_type/room_name 过滤，加 _inject_screen_online） |
| MOD-BE-CW-07 serializers_condensation.py | ~30 行 | 简单 ModelSerializer |
| MOD-FE-CW-01 CondensationWarningView.vue | ~350 行 | 镜像 FaultManagementView.vue，过滤器简化，列定义不同 |
| MOD-FE-CW-02 router/index.js 修改 | ~5 行 | 新增 1 条路由 |
| MOD-FE-CW-03 Layout.vue 修改 | ~5 行 | 新增 1 个菜单项 |
| DB-CW-01 migration 0029 | ~60 行 | Django 自动生成 |
| INFRA 3 个 service/timer 文件 | ~90 行 | 镜像故障管理 service/timer |
| **合计** | **~1170 行** | |
