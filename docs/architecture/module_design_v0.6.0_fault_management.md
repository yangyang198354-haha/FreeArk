# 模块设计文档

```
file_header:
  document_id: MOD-v0.6.0-FM
  title: MQTT 故障事件持久化 + 故障管理页面 — 模块设计
  author_agent: sub_agent_system_architect (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.6.0-fault-management
  created_at: 2026-05-27
  status: DRAFT
  references:
    - docs/architecture/architecture_design_v0.6.0_fault_management.md
    - docs/requirements/v0.6.0_fault_management/requirements_spec.md
    - FreeArkWeb/backend/freearkweb/api/fault_utils.py
    - FreeArkWeb/backend/freearkweb/api/management/commands/screen_heartbeat_consumer.py
    - FreeArkWeb/backend/freearkweb/api/management/commands/dph_cleanup_service.py
    - FreeArkWeb/backend/freearkweb/api/urls.py
    - FreeArkWeb/frontend/src/router/index.js
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-27 | 初始草稿，模块清单与接口定义 |

---

## 1. 模块清单

| 模块 ID | 文件路径 | 类型 | 操作 | 需求覆盖 |
|---------|---------|------|------|---------|
| MOD-BE-FM-01 | `FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py` | 后端 Python 模块（新增包）| 新增 | FR-FM-06 |
| MOD-BE-FM-02 | `FreeArkWeb/backend/freearkweb/api/fault_consumer/fault_classifier.py` | 后端 Python 模块 | 新增 | FR-FM-06 |
| MOD-BE-FM-03 | `FreeArkWeb/backend/freearkweb/api/fault_consumer/state_machine.py` | 后端 Python 模块 | 新增 | FR-FM-02 |
| MOD-BE-FM-04 | `FreeArkWeb/backend/freearkweb/api/management/commands/fault_consumer.py` | Django Management Command | 新增 | FR-FM-01, US-FM-01, US-FM-06 |
| MOD-BE-FM-05 | `FreeArkWeb/backend/freearkweb/api/management/commands/fault_cleanup.py` | Django Management Command | 新增 | FR-FM-07, US-FM-09 |
| MOD-BE-FM-06 | `FreeArkWeb/backend/freearkweb/api/models.py` | Django Model | 修改（追加 FaultEvent 模型）| FR-FM-03 |
| MOD-BE-FM-07 | `FreeArkWeb/backend/freearkweb/api/migrations/NNNN_add_fault_event.py` | Django Migration | 新增（自动生成）| FR-FM-03 |
| MOD-BE-FM-08 | `FreeArkWeb/backend/freearkweb/api/views_fault.py` | 后端视图（新文件）| 新增 | FR-FM-05 |
| MOD-BE-FM-09 | `FreeArkWeb/backend/freearkweb/api/serializers_fault.py` | DRF Serializer（新文件）| 新增 | FR-FM-05 |
| MOD-BE-FM-10 | `FreeArkWeb/backend/freearkweb/api/urls.py` | 路由 | 修改（追加 2 条 path）| FR-FM-05 |
| MOD-FE-FM-01 | `FreeArkWeb/frontend/src/views/FaultManagementView.vue` | 前端 Vue 组件 | 新增 | FR-FM-04, US-FM-03~08 |
| MOD-FE-FM-02 | `FreeArkWeb/frontend/src/router/index.js` | 前端路由 | 修改（追加 1 条路由）| FR-FM-04 |
| MOD-FE-FM-03 | `FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue` | 前端 Vue 组件 | 修改（追加「故障管理」导航入口）| FR-FM-04 |
| MOD-SYS-FM-01 | `/etc/systemd/system/freeark-fault-consumer.service` | systemd 服务单元 | 新增 | FR-FM-01, US-FM-06 |
| MOD-SYS-FM-02 | `/etc/systemd/system/freeark-fault-cleanup.service` | systemd 服务单元 | 新增 | FR-FM-07 |
| MOD-SYS-FM-03 | `/etc/systemd/system/freeark-fault-cleanup.timer` | systemd 定时器 | 新增 | FR-FM-07 |

**不修改的模块**（满足最小侵入原则）：

| 文件路径 | 原因 |
|---------|------|
| `api/fault_utils.py` | v0.5.3-FCC 模块，fault_consumer 仅复用其常量（FAULT_PARAM_NAMES），不修改接口 |
| `api/mqtt_handlers.py` | v0.5.3-FCC 的 MQTT 处理路径，不调用 invalidate_fault_count_cache（AB-002 待决）|
| `api/views.py` | 已有视图不修改，新接口放在 views_fault.py |
| `management/commands/screen_heartbeat_consumer.py` | 心跳服务独立运行，不改动 |

---

## 2. MOD-BE-FM-01：fault_consumer/constants.py

### 2.1 职责

集中定义 fault_consumer 包内的所有常量：故障类型映射、严重级别映射、sub_type 到 fault_code 的反向映射（供 API 过滤使用）。

### 2.2 包结构

```
FreeArkWeb/backend/freearkweb/api/fault_consumer/
    __init__.py
    constants.py        ← MOD-BE-FM-01
    fault_classifier.py ← MOD-BE-FM-02
    state_machine.py    ← MOD-BE-FM-03
```

### 2.3 接口定义

```python
# fault_consumer/constants.py

import re
from api.fault_utils import FAULT_PARAM_NAMES, _ERROR_N_PATTERN

# ---------------------------------------------------------------------------
# 故障类型映射：fault_code 模式 → (fault_type, severity)
# ---------------------------------------------------------------------------

# 精确匹配优先于模式匹配
EXACT_FAULT_MAP: dict[str, tuple[str, str]] = {
    'comm_fault_timeout':                       ('comm',       'error'),
    'fresh_air_unit_stop_error':                ('fresh_air',  'error'),
    'fresh_air_unit_communication_error':       ('comm',       'error'),
    'hydraulic_module_low_temp_error':          ('other_error','error'),
    'energy_meter_status_communication_error':  ('comm',       'error'),
    'air_quality_sensor_communication_error':   ('comm',       'error'),
}

# 后缀模式匹配（按声明顺序，先匹配先生效）
SUFFIX_FAULT_RULES: list[tuple[str, str, str]] = [
    # (后缀, fault_type, severity)
    ('_communication_error', 'comm',    'error'),
    ('_temp_sensor_error',   'sensor',  'error'),
    ('_humidity_sensor_error','sensor', 'error'),
    ('_external_temp_sensor_error','sensor','error'),
]

# 位域故障模式
_FRESH_AIR_BIT_PATTERN = re.compile(r'^fresh_air_fault_bit_\d+$')
_ERROR_N_PATTERN_LOCAL  = re.compile(r'^error_\d+$')  # 与 fault_utils._ERROR_N_PATTERN 一致

# ---------------------------------------------------------------------------
# sub_type → 对应 fault_code 列表（供 API 过滤使用，ADR-FM-05-SUBTYPE）
# ---------------------------------------------------------------------------

SUB_TYPE_TO_FAULT_CODES: dict[str, list[str]] = {
    'living_room_thermostat': [
        'living_room_temp_sensor_error',
        'living_room_humidity_sensor_error',
        'living_room_external_temp_sensor_error',
        'living_room_communication_error',
    ],
    'study_room_thermostat': [
        'study_room_temp_sensor_error',
        'study_room_humidity_sensor_error',
        'study_room_external_temp_sensor_error',
        'study_room_communication_error',
    ],
    'bedroom_thermostat': [
        'bedroom_temp_sensor_error',
        'bedroom_humidity_sensor_error',
        'bedroom_external_temp_sensor_error',
        'bedroom_communication_error',
    ],
    'children_room_thermostat': [
        'children_room_temp_sensor_error',
        'children_room_humidity_sensor_error',
        'children_room_external_temp_sensor_error',
        'children_room_communication_error',
    ],
    'fourth_children_room_thermostat': [
        'fourth_children_room_temp_sensor_error',
        'fourth_children_room_humidity_sensor_error',
        'fourth_children_room_external_temp_sensor_error',
        'fourth_children_room_communication_error',
    ],
    'fresh_air_unit': [
        'fresh_air_unit_stop_error',
        'fresh_air_unit_communication_error',
        # fresh_air_fault_bit_* 用前缀匹配，不在此列举
    ],
    'hydraulic_module': ['hydraulic_module_low_temp_error'],
    'energy_meter':     ['energy_meter_status_communication_error'],
    'air_quality_sensor': ['air_quality_sensor_communication_error'],
}

# sub_type 显示标签（供 /api/devices/fault-event-categories/ 接口使用）
SUB_TYPE_LABELS: dict[str, str] = {
    'living_room_thermostat':           '客厅温控面板',
    'study_room_thermostat':            '书房温控面板',
    'bedroom_thermostat':               '主卧温控面板',
    'children_room_thermostat':         '儿童房温控面板',
    'fourth_children_room_thermostat':  '第四儿童房温控面板',
    'fresh_air_unit':                   '新风机',
    'hydraulic_module':                 '水力模块',
    'energy_meter':                     '能耗表',
    'air_quality_sensor':               '空气品质传感器',
}

FAULT_TYPE_LABELS: dict[str, str] = {
    'comm':        '通信故障',
    'sensor':      '传感器故障',
    'fresh_air':   '新风故障',
    'other_error': '其他故障',
}
```

---

## 3. MOD-BE-FM-02：fault_consumer/fault_classifier.py

### 3.1 职责

提供两个纯函数：`is_fault_candidate(param_name)` 和 `is_fault_active(param_name, value)`，以及 `get_fault_type_and_severity(param_name)` 用于写入 DB 时分类。

### 3.2 接口定义

```python
# fault_consumer/fault_classifier.py

def is_fault_candidate(param_name: str) -> bool:
    """判断参数名是否可能是故障相关字段（需进一步判断值）。
    
    覆盖范围：
    - FAULT_PARAM_NAMES 中所有具名字段（含 comm_fault_timeout）
    - error_<N> 模式字段
    - fresh_air_fault_bit_* 模式字段
    
    不包含 fresh_air_fault_status（该字段是位域整体，由 PLC 拉取路径处理，非 MQTT 直接上报的位字段）
    """
    ...

def is_fault_active(param_name: str, value) -> bool:
    """判断某参数的当前值是否处于故障态。
    
    规则：
    - comm_fault_timeout: value != "normal" 且 value 非 None
    - error_<N>: value 不等于 "0"（字符串）且不等于 0（整数）且非 None
    - 其他具名故障字段: value != 0 且非 None
    - fresh_air_fault_bit_*: value != 0 且非 None
    
    Returns:
        True  → 当前为故障态
        False → 当前为正常态（或 value 无法解析）
    """
    ...

def get_fault_type_and_severity(param_name: str) -> tuple[str, str]:
    """根据参数名返回 (fault_type, severity) 元组。
    
    优先级：精确匹配 > 后缀匹配 > 位域模式 > error_N 模式 > 默认
    
    Returns:
        tuple: (fault_type, severity)
        例如: ('comm', 'error'), ('fresh_air', 'warning'), ('other_error', 'error')
    """
    ...
```

---

## 4. MOD-BE-FM-03：fault_consumer/state_machine.py

### 4.1 职责

维护进程内状态机字典 `_state_machine`，提供 `process_fault_field` 函数作为核心入口，实现 ADR-FM-03 定义的状态转移逻辑。

### 4.2 接口定义

```python
# fault_consumer/state_machine.py

from dataclasses import dataclass
from datetime import datetime

@dataclass
class FaultState:
    event_id: int
    is_active: bool
    last_seen_at: datetime

# 进程内状态机（模块级单例字典）
# key: (specific_part: str, device_sn: str, fault_code: str)
# value: FaultState
_state_machine: dict[tuple[str, str, str], FaultState] = {}

def rebuild_from_db() -> int:
    """进程启动时从 DB 重建状态机。
    
    查询 fault_event WHERE is_active=True LIMIT 10000，
    填充 _state_machine。
    
    Returns:
        int: 加载的记录数
    
    调用时机: fault_consumer Management Command 的 handle() 方法启动时
    调用前提: Django 已完成 setup()（ORM 可用）
    """
    ...

def process_fault_field(
    specific_part: str,
    device_sn: str,
    product_code: str,
    fault_code: str,
    fault_type: str,
    severity: str,
    is_active_now: bool,
    received_at: datetime,
) -> None:
    """处理单个故障字段的状态变化（状态机核心入口）。
    
    实现 ADR-FM-03 的 T1/T2/T3 转移逻辑：
    - T1: 状态机 miss 或 is_active=False，且 is_active_now=True → INSERT + 更新内存
    - T2: 状态机 hit，is_active=True，且 is_active_now=True → 仅更新内存 last_seen_at
    - T3: 状态机 hit，is_active=True，且 is_active_now=False → UPDATE DB + 更新内存
    
    此函数在 on_message 回调中被调用，应尽量快。DB 操作前调用 close_old_connections()。
    
    异常处理:
    - IntegrityError on INSERT: 捕获，改为 UPDATE last_seen_at，内存状态置 is_active=True
    - OperationalError: 记录 ERROR 日志，不崩溃（进程由 systemd 托管）
    """
    ...

def get_state(key: tuple[str, str, str]) -> FaultState | None:
    """获取指定 key 的当前状态（仅供测试/日志使用）。"""
    return _state_machine.get(key)

def get_state_machine_size() -> int:
    """返回当前状态机条目数（仅供日志/监控使用）。"""
    return len(_state_machine)
```

---

## 5. MOD-BE-FM-04：management/commands/fault_consumer.py

### 5.1 职责

Django Management Command 入口，负责：
1. 加载 broker 配置
2. 初始化 MacCache（复用 screen_heartbeat_consumer 中的类，但不引入共享模块，直接复制实现，保持独立性）
3. 调用 `rebuild_from_db()` 初始化状态机
4. 建立 paho-mqtt 连接，注册 on_connect / on_message / on_disconnect 回调
5. 执行 `loop_forever(retry_first_connection=True)` 持续运行

### 5.2 关键实现约束

```python
class Command(BaseCommand):
    help = '故障事件 MQTT 消费者（freeark-fault-consumer）'

    def handle(self, *args, **options):
        # 1. 加载 broker 配置（复用 heartbeat_broker_config.json，独立 client_id）
        cfg = _load_fault_consumer_config()
        # client_id 固定为 'freeark-fault-consumer'（不从配置文件读取，避免误用心跳 client_id）
        client_id = 'freeark-fault-consumer'
        topic = cfg.get('fault_consumer_topic', '/screen/upload/screen/to/cloud/+')

        # 2. 进程启动时重建状态机
        import django
        from api.fault_consumer.state_machine import rebuild_from_db
        count = rebuild_from_db()
        logger.info('fault_consumer 启动，状态机重建完成，活跃故障 %d 条', count)

        # 3. 初始化 MacCache（与心跳服务独立的实例）
        mac_cache = _MacCache()

        # 4. paho-mqtt 1.x API（与 screen_heartbeat_consumer 相同模式）
        ...

        def on_message(client, userdata, msg):
            try:
                _handle_message(msg, mac_cache)
            except Exception as exc:
                logger.exception('on_message 未处理异常: %s', exc)

        # 5. loop_forever
        client.loop_forever(retry_first_connection=True)

def _handle_message(msg, mac_cache) -> None:
    """解析单条 MQTT 消息并驱动状态机。
    
    1. JSON 解析，验证 header.name == "DeviceStatusUpdate"
    2. MAC → specific_part 映射
    3. 提取 deviceSn, productCode
    4. 遍历 items[]，对每个 item 调用 fault_classifier + state_machine
    """
    ...
```

### 5.3 broker 配置文件扩展（heartbeat_broker_config.json）

在现有 JSON 格式基础上，为 fault_consumer 增加可选扩展字段（不影响现有心跳服务读取）：

```json
{
  "protocol": "wss",
  "host": "www.ttqingjiao.site",
  "port": 8084,
  "path": "/mqtt",
  "username": "...",
  "password": "...",
  "topic": "/screen/upload/screen/to/cloud/#",
  "client_id": "freeark-screen-heartbeat",
  "keepalive": 60,

  "fault_consumer_topic": "/screen/upload/screen/to/cloud/+",
  "fault_consumer_use_mac_list": false
}
```

`fault_consumer.py` 读取 `fault_consumer_topic` 和 `fault_consumer_use_mac_list` 字段；心跳服务（`screen_heartbeat_consumer.py`）完全忽略这两个字段（不修改心跳服务代码）。

---

## 6. MOD-BE-FM-05：management/commands/fault_cleanup.py

### 6.1 职责

一次性执行的清理 Management Command，由 systemd timer 在每天 03:30 触发。

### 6.2 命令参数接口

```
python manage.py fault_cleanup
  --days=90         保留天数（默认 90）
  --batch-size=1000 每批删除行数（默认 1000）
  --sleep-ms=100    批次间 sleep 毫秒（默认 100）
  --dry-run         演练模式（不删除，输出预计删除行数）
```

### 6.3 清理逻辑约束

```python
# 清理条件：超过 N 天 AND 已恢复（is_active=False）
# 活跃故障永远不删（is_active=True 的行不受清理影响）
DELETE FROM fault_event
WHERE first_seen_at < %s
  AND is_active = FALSE
LIMIT %s

# 循环执行直到 affected_rows == 0
# 批次间 sleep sleep_ms 毫秒
# 使用 Django ORM QuerySet.delete() 或 connection.cursor() 原生 SQL
# 优先使用 ORM（可读性），fault_event 表不会达到 dph 的量级，无需特殊优化
```

**不需要放大 DB 超时**：fault_cleanup 操作的 fault_event 表行数远小于 dph，单批删除 1000 行在 MySQL 上不会超过 60s 超时，无需像 dph_cleanup_service.py 那样放大超时。

---

## 7. MOD-BE-FM-06：models.py（修改）

### 7.1 追加内容

在现有 `models.py` 末尾追加 `FaultEvent` 模型（完整定义见 ADR-FM-04）。

追加位置：文件末尾，保持现有模型定义不变。

### 7.2 Migration 生成命令

```bash
python manage.py makemigrations api --name add_fault_event
# 生成文件: FreeArkWeb/backend/freearkweb/api/migrations/NNNN_add_fault_event.py
```

**SQLite 兼容性**：`UniqueConstraint` 和 `Index` 在 SQLite 和 MySQL 均支持，测试环境兼容。

---

## 8. MOD-BE-FM-07：serializers_fault.py（新增）

### 8.1 职责

DRF Serializer，将 `FaultEvent` ORM 对象序列化为 JSON 响应。

### 8.2 接口定义

```python
# serializers_fault.py

from rest_framework import serializers
from .models import FaultEvent

class FaultEventSerializer(serializers.ModelSerializer):
    """FaultEvent 序列化器。
    
    时间字段以 ISO8601 格式输出，时区为 Asia/Shanghai（由 Django TIME_ZONE 设置控制）。
    null 的 recovered_at 序列化为 null（JSON），前端显示为 "-"。
    """

    class Meta:
        model = FaultEvent
        fields = [
            'id',
            'specific_part',
            'device_sn',
            'product_code',
            'fault_code',
            'fault_type',
            'fault_message',
            'severity',
            'first_seen_at',
            'last_seen_at',
            'recovered_at',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields  # 此接口为只读，不支持写入
```

---

## 9. MOD-BE-FM-08：views_fault.py（新增）

### 9.1 职责

提供两个 API 视图：故障事件分页查询 + 故障分类常量接口。

### 9.2 接口定义

```python
# views_fault.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from datetime import timedelta

from .models import FaultEvent
from .serializers_fault import FaultEventSerializer
from .fault_consumer.constants import SUB_TYPE_TO_FAULT_CODES, SUB_TYPE_LABELS, FAULT_TYPE_LABELS


class FaultEventPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fault_event_list(request):
    """GET /api/devices/fault-events/
    
    查询参数过滤逻辑：
    - specific_part: icontains（LIKE '%value%'）
    - fault_type: __in（多值，逗号分隔或重复参数）
    - sub_type: 通过 SUB_TYPE_TO_FAULT_CODES 翻译为 fault_code__in
    - is_active: True/False（字符串 "true"/"false"）
    - first_seen_after: first_seen_at__gte（默认 now() - 7d）
    - first_seen_before: first_seen_at__lte
    
    排序: -first_seen_at（最新在前）
    """
    qs = FaultEvent.objects.all()

    # specific_part 模糊匹配
    sp = request.query_params.get('specific_part')
    if sp:
        qs = qs.filter(specific_part__icontains=sp)

    # fault_type 多值过滤
    fault_types = request.query_params.getlist('fault_type')
    if fault_types:
        qs = qs.filter(fault_type__in=fault_types)

    # sub_type 过滤（翻译为 fault_code__in）
    sub_types = request.query_params.getlist('sub_type')
    if sub_types:
        fault_codes = []
        for st in sub_types:
            fault_codes.extend(SUB_TYPE_TO_FAULT_CODES.get(st, []))
            # fresh_air_unit 的 bit_* 字段用前缀处理
        # TODO(impl): fresh_air_fault_bit_* 前缀匹配需要 Q(fault_code__startswith='fresh_air_fault_bit_')
        if fault_codes:
            qs = qs.filter(fault_code__in=fault_codes)

    # is_active 过滤
    is_active_param = request.query_params.get('is_active')
    if is_active_param is not None:
        qs = qs.filter(is_active=(is_active_param.lower() == 'true'))

    # 时间范围过滤（默认最近 7 天）
    default_after = timezone.now() - timedelta(days=7)
    first_seen_after = request.query_params.get('first_seen_after')
    first_seen_before = request.query_params.get('first_seen_before')

    if first_seen_after:
        qs = qs.filter(first_seen_at__gte=first_seen_after)
    else:
        qs = qs.filter(first_seen_at__gte=default_after)

    if first_seen_before:
        qs = qs.filter(first_seen_at__lte=first_seen_before)

    qs = qs.order_by('-first_seen_at')

    paginator = FaultEventPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = FaultEventSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fault_event_categories(request):
    """GET /api/devices/fault-event-categories/
    
    返回故障类型和设备子类型的分类常量，供前端过滤下拉使用。
    """
    return Response({
        'fault_types': [
            {'value': k, 'label': v}
            for k, v in FAULT_TYPE_LABELS.items()
        ],
        'sub_types': [
            {'value': k, 'label': v}
            for k, v in SUB_TYPE_LABELS.items()
        ],
    })
```

---

## 10. MOD-BE-FM-10：urls.py（修改）

### 10.1 追加内容

在现有 `urls.py` 的 `urlpatterns` 列表末尾追加：

```python
from . import views_fault

# 故障管理接口（v0.6.0-FM）
path('devices/fault-events/', views_fault.fault_event_list, name='fault-event-list'),
path('devices/fault-event-categories/', views_fault.fault_event_categories, name='fault-event-categories'),
```

**路由命名规范**：与现有 `devices/fault-count/` 路由风格一致，使用连字符。

---

## 11. MOD-FE-FM-01：FaultManagementView.vue（新增）

### 11.1 职责

故障管理页面主组件，提供多维过滤 + 分页表格 + 查看设备面板功能。

### 11.2 组件结构

```
FaultManagementView.vue
├── <template>
│   ├── 页面标题区：「故障管理」
│   ├── 筛选区上方：「只看未恢复」ElSwitch（默认 OFF）
│   ├── 过滤条件区（ElForm）
│   │   ├── 房号输入框（ElInput，placeholder="输入房号模糊搜索"）
│   │   ├── 故障时间段（ElDatePicker, type="daterange"，默认最近 7 天）
│   │   ├── 故障类型多选下拉（ElSelect multiple，options 来自 fault-event-categories API）
│   │   ├── 故障设备多选下拉（ElSelect multiple，options 来自 fault-event-categories API）
│   │   └── 查询/重置按钮
│   └── 数据表格区（ElTable + ElPagination）
│       ├── 列：房号、设备标识（device_sn）、故障码、故障描述、故障类型、
│       │       严重级别（带颜色 Tag）、首次发生时间、最后活跃时间、
│       │       恢复时间（null→"-"）、状态（活跃/已恢复）
│       └── 操作列：「查看设备面板」ElButton（type="text"）
│
├── <script setup>
│   ├── import: ref, reactive, onMounted, computed
│   ├── import: useRouter from 'vue-router'
│   ├── import: axios
│   ├── state: filters{specific_part, fault_types, sub_types, is_active_only,
│   │          first_seen_after, first_seen_before}
│   ├── state: tableData, total, currentPage, pageSize, loading
│   ├── state: faultTypeOptions, subTypeOptions（来自 categories API）
│   ├── onMounted: fetchCategories() + fetchFaultEvents()
│   ├── fetchCategories(): GET /api/devices/fault-event-categories/
│   ├── fetchFaultEvents(): GET /api/devices/fault-events/ with params
│   ├── handleSearch(): 重置 currentPage=1，执行 fetchFaultEvents()
│   ├── handleReset(): 重置 filters 到默认值，执行 fetchFaultEvents()
│   ├── handleViewDevicePanel(row): 新标签页打开设备面板
│   │   window.open(router.resolve({
│   │     name: 'DeviceCards',
│   │     query: { specific_part: row.specific_part }
│   │   }).href)
│   └── severityTagType(severity, is_active):
│       → active + error → 'danger'（红色）
│       → active + warning → 'warning'（橙色）
│       → inactive → '' （灰色）
│
└── <style scoped>
    └── 基本布局 + 表格样式
```

### 11.3 默认参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 时间段 | 最近 7 天 | `first_seen_after = new Date() - 7d`，`first_seen_before = null` |
| is_active_only | false（OFF）| toggle 默认 OFF |
| page_size | 20 | 可选 10/20/50 |
| 房号 | 空 | 不过滤 |
| fault_types | [] | 不过滤 |
| sub_types | [] | 不过滤 |

### 11.4 「查看设备面板」跳转（新标签页）

```javascript
// 用户裁决 OQ-12：不附加子设备高亮参数
// AC-FM-05-02：新标签页打开，不离开故障管理页面
const handleViewDevicePanel = (row) => {
  const route = router.resolve({
    name: 'DeviceCards',
    query: { specific_part: row.specific_part }
  })
  window.open(route.href, '_blank')
}
```

---

## 12. MOD-FE-FM-02：router/index.js（修改）

### 12.1 追加内容

在现有路由数组中，在 `DeviceManagementDeviceList` 路由之后追加：

```javascript
{
  // 故障管理页面（v0.6.0-FM）
  path: '/device-management/faults',
  name: 'FaultManagement',
  component: () => import('../views/FaultManagementView.vue'),
  meta: { requiresAuth: true }
},
```

---

## 13. MOD-FE-FM-03：DeviceManagementDeviceListView.vue（修改）

### 13.1 修改范围

在现有设备列表页面，增加「故障管理」导航入口。修改仅限于追加导航链接，不改动现有功能。

**修改方式**：在页面顶部操作栏或侧边栏（视现有布局决定）添加一个按钮或链接：

```html
<!-- 追加在现有操作按钮区域 -->
<el-button @click="$router.push({ name: 'FaultManagement' })">
  故障管理
</el-button>
```

**最小侵入**：仅追加导航按钮，不改动任何现有逻辑、数据请求或表格列。

---

## 14. 模块依赖关系图

```
fault_consumer (Management Command)
    ├── depends: api/fault_consumer/fault_classifier.py
    │       └── depends: api/fault_utils.py (FAULT_PARAM_NAMES) [READ-ONLY]
    ├── depends: api/fault_consumer/state_machine.py
    │       └── depends: api/models.py (FaultEvent) [READ/WRITE]
    ├── depends: api/fault_consumer/constants.py
    └── depends: api/models.py (OwnerInfo) [READ-ONLY]

fault_cleanup (Management Command)
    └── depends: api/models.py (FaultEvent) [DELETE]

views_fault.py
    ├── depends: api/models.py (FaultEvent) [READ-ONLY]
    ├── depends: api/serializers_fault.py
    └── depends: api/fault_consumer/constants.py [READ-ONLY]

FaultManagementView.vue
    └── calls: GET /api/devices/fault-events/      (views_fault)
    └── calls: GET /api/devices/fault-event-categories/ (views_fault)
    └── navigates to: DeviceCards (已有路由，不修改)
```

**与 v0.5.3-FCC 的依赖关系**：
- `fault_classifier.py` 通过 `import` 读取 `fault_utils.FAULT_PARAM_NAMES` 和 `_ERROR_N_PATTERN`（只读），不修改 fault_utils
- `views_fault.py` 不依赖 `fault_utils.py`（fault 管理 API 查 fault_event 表，不查 plc_latest_data）
- `fault_consumer` 不调用 `invalidate_fault_count_cache`（AB-002 待决，保持不变）

---

## 15. 配置项清单

| 配置项 | 位置 | 默认值 | 说明 |
|--------|------|--------|------|
| `fault_consumer_topic` | `heartbeat_broker_config.json` | `/screen/upload/screen/to/cloud/+` | MQTT 订阅 topic（R-08 fallback 时可切换）|
| `fault_consumer_use_mac_list` | `heartbeat_broker_config.json` | `false` | ACL fallback 开关（AB-008 前置配置）|
| `--days` | `fault_cleanup` 命令参数 | `90` | 清理保留天数 |
| `--batch-size` | `fault_cleanup` 命令参数 | `1000` | 每批删除行数 |
| `--sleep-ms` | `fault_cleanup` 命令参数 | `100` | 批次间 sleep 毫秒 |
| `OnCalendar` | `freeark-fault-cleanup.timer` | `*-*-* 03:30:00` | 清理执行时间 |
| `CACHE_REFRESH_INTERVAL` | `fault_consumer.py` 内模块常量 | `300`（秒）| MacCache 刷新间隔（与心跳服务一致）|

---

## 16. 需求覆盖矩阵

| 需求 ID | 描述 | 覆盖模块 |
|---------|------|---------|
| FR-FM-01 | MQTT 故障订阅服务 | MOD-BE-FM-04, MOD-SYS-FM-01 |
| FR-FM-02 | 进程内状态机 | MOD-BE-FM-03 |
| FR-FM-03 | fault_event 数据模型 | MOD-BE-FM-06, MOD-BE-FM-07 |
| FR-FM-04 | 故障管理页面（前端）| MOD-FE-FM-01, MOD-FE-FM-02, MOD-FE-FM-03 |
| FR-FM-05 | 故障事件查询 REST API | MOD-BE-FM-08, MOD-BE-FM-09, MOD-BE-FM-10 |
| FR-FM-06 | 故障类型与严重级别判定规则 | MOD-BE-FM-01, MOD-BE-FM-02 |
| FR-FM-07 | 故障事件清理服务 | MOD-BE-FM-05, MOD-SYS-FM-02, MOD-SYS-FM-03 |
| US-FM-01 | MQTT 故障事件自动持久化 | MOD-BE-FM-04 (AC-FM-01-01~07) |
| US-FM-02 | 进程内状态机避免频繁 DB 读写 | MOD-BE-FM-03 (AC-FM-02-01~04) |
| US-FM-03 | 多维过滤查询 | MOD-FE-FM-01, MOD-BE-FM-08 (AC-FM-03-01~07) |
| US-FM-04 | 分页表格显示 | MOD-FE-FM-01 (AC-FM-04-01~03) |
| US-FM-05 | 查看设备面板 | MOD-FE-FM-01 (AC-FM-05-01~02) |
| US-FM-06 | systemd 服务可靠运行 | MOD-SYS-FM-01 (AC-FM-06-01~03) |
| US-FM-07 | 生产部署通过 git pull | 部署阶段，架构层不涉及代码模块 |
| US-FM-08 | 只看未恢复 toggle | MOD-FE-FM-01 (AC-FM-08-01) |
| US-FM-09 | 故障事件数据清理服务 | MOD-BE-FM-05, MOD-SYS-FM-02~03 (AC-FM-09-01~03) |
