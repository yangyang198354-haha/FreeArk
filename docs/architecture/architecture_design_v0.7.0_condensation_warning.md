# 架构设计文档

```
file_header:
  document_id: ARCH-v0.7.0-CW
  title: 结露预警管理页面 — 架构设计（ADR）
  author_agent: sub_agent_system_architect (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.7.0-condensation-warning
  created_at: 2026-05-30
  status: APPROVED
  references:
    - docs/requirements/v0.7.0_condensation_warning/requirements_spec.md
    - docs/requirements/v0.7.0_condensation_warning/user_stories.md
    - docs/architecture/architecture_design_v0.6.4_fault_mgmt_room_column.md
    - FreeArkWeb/backend/freearkweb/api/fault_consumer/state_machine.py
    - FreeArkWeb/backend/freearkweb/api/fault_consumer/room_lookup.py
    - FreeArkWeb/backend/freearkweb/api/management/commands/fault_consumer.py
    - FreeArkWeb/backend/freearkweb/api/views_fault.py
    - FreeArkWeb/backend/freearkweb/api/models.py (PLCLatestData, ScreenConnectivityStatus, DeviceNode)
    - deployment/systemd/freeark-fault-consumer.service
    - deployment/systemd/freeark-fault-cleanup.service
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 1.0.0-APPROVED | 2026-05-30 | 初始正式版本，含 ADR-CW-01~06、ARCH-PENDING-01 选定方案（方案 A — PLCLatestData 直查）、数据表设计、systemd 服务模板、API 设计、前端路由 |

---

## 1. 架构决策记录（ADR）

### ADR-CW-01：ARCH-PENDING-01 选定方案 — specific_part → 水力模块 system_switch 的取值路径

**背景**

需求规格 §6.3 ARCH-PENDING-01 要求架构设计阶段选定：当温控面板（product_code 120003）触发结露预警时，如何取到同一 `specific_part` 下水力模块（product_code 260001/270001/10016）的最近已知 `system_switch` 值。

候选方案：
- 方案 A：查询 `PLCLatestData` 表（已有），WHERE specific_part=X AND param_name='system_switch'，取 value。
- 方案 B：通过 `DeviceNode` 拓扑反查，找到同 specific_part 下 product_code∈{260001,270001,10016} 的设备，再查其最新 system_switch 状态。
- 方案 C：消费侧监听所有报文，进程内维护 `{specific_part: system_switch_value}` 内存缓存（类似状态机）。

**调研结论（基于现有代码实测）**

`PLCLatestData` 表结构如下（来自 `models.py` L327-346）：

```
specific_part  VARCHAR(20)  indexed
param_name     VARCHAR(100)
value          BigIntegerField (null=True)
collected_at   DateTimeField (null=True)
updated_at     DateTimeField (auto_now)
```

表中已有 `(specific_part, param_name)` 的 UNIQUE 约束（由 `seed_device_config.py` 的 `system_switch` 条目确认，param_name='system_switch' 存在于 main_thermostat 和 hydraulic_module 两种 sub_type 下，两者的水力模块设备均通过 PLC 数采写入此表）。

生产代码 `views.py` L923/L937-941 已有直接查询范例：
```python
PLCLatestData.objects.filter(
    specific_part__in=online_parts_qs,
    param_name='system_switch',
    value__isnull=False,
).exclude(value=0)
```

`PLCLatestData.value` 是 BigIntegerField，PLC 数采侧写入时将 system_switch 作为整数存储（0=关，非0=开）；前端展示时解释为 "on"/"off"。

**决策：采用方案 A（PLCLatestData 直查）**

**理由**：

| 维度 | 方案 A（PLCLatestData 直查）| 方案 B（DeviceNode 拓扑反查）| 方案 C（进程内缓存） |
|------|---------------------------|----------------------------|--------------------|
| 实现复杂度 | 低：单表查询，已有生产范例 | 高：需 JOIN DeviceNode→PLCLatestData，且 DeviceNode 无 specific_part 列（需经 DeviceRoom→DeviceFloor 多跳） | 中：需独立缓存结构，增加消费侧复杂度 |
| 数据新鲜度 | PLC 数采周期约 30s 刷新，对"触发时刻快照"足够 | 同方案 A，数据源相同 | 依赖同进程消费到水力模块报文，MQTT 报文频率不确定 |
| 依赖稳定性 | PLCLatestData 已在生产稳定运行 | DeviceNode→DeviceFloor 路径多表 JOIN，稳定性风险高 | 进程重启时缓存丢失，cold start 窗口 system_switch 均为 "unknown" |
| 与现有代码一致性 | views.py 有完全相同的查询模式 | 无先例 | 增加新的状态管理维度，与需求要求的"最大化复用"方向相反 |
| 生产风险 | 最低 | 较高 | 中 |

方案 A 的唯一弱点：PLCLatestData 仅由 PLC 数采服务写入，若某住户 PLC 离线，specific_part 下无最新值。此场景按需求设计直接兜底为 "unknown"，可接受。

**实现细节**

T1 INSERT 时，`condensation_consumer` 执行如下查询取 system_switch：

```python
def _get_system_switch_for_specific_part(specific_part: str) -> str:
    """
    查 PLCLatestData WHERE specific_part=X AND param_name='system_switch'。
    返回值：'on' / 'off' / 'unknown'
    PLCLatestData.value: BigIntegerField, 0=关, 非0=开。
    """
    from django.db import close_old_connections
    close_old_connections()
    try:
        from api.models import PLCLatestData
        row = PLCLatestData.objects.filter(
            specific_part=specific_part,
            param_name='system_switch',
            value__isnull=False,
        ).order_by('-updated_at').first()
        if row is None:
            logger.debug('_get_system_switch: specific_part=%s 无记录，返回 unknown', specific_part)
            return 'unknown'
        return 'on' if row.value != 0 else 'off'
    except Exception as exc:
        logger.error('_get_system_switch 异常: %s specific_part=%s', exc, specific_part)
        return 'unknown'
```

注意：触发报文同一 deviceSn 的 items[] 中若含 system_switch attrTag，则优先直接取该值（适用于 260001 设备同报文含两字段的场景），PLCLatestData 查询仅作兜底。优先级逻辑在 `_handle_message` 中实现。

**结论：ARCH-PENDING-01 → 选定方案 A（PLCLatestData 直查），已关闭。**

---

### ADR-CW-02：condensation_warning_event 数据表设计（独立新表）

**背景**：需求裁决（OQ-02）：独立新表，不与 fault_event 合并。

**决策**：新增 `condensation_warning_event` 表，依赖 migration 0029（depends: 0028）。

**Django Model 定义**：

```python
class CondensationWarningEvent(models.Model):
    """结露预警事件表（v0.7.0-CW）。

    由 freeark-condensation-consumer 服务写入，记录结露报警事件生命周期。
    写入模式与 FaultEvent 相同（T1/T2/T3 状态机）。

    system_switch 字段来源（ADR-CW-01，ARCH-PENDING-01 选定方案 A）：
      优先取触发报文同 deviceSn 的 system_switch attrTag；
      不存在时查 PLCLatestData(specific_part, param_name='system_switch')；
      均无则写 'unknown'。
    """
    specific_part  = models.CharField(max_length=64, verbose_name='房号', db_index=True)
    device_sn      = models.CharField(max_length=64, verbose_name='设备序列号')
    product_code   = models.CharField(max_length=32, verbose_name='产品编码')
    room_name      = models.CharField(max_length=50, null=True, blank=True, verbose_name='房间名')
    room_id        = models.ForeignKey(
        'DeviceRoom',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        db_column='room_id',
        verbose_name='房间外键',
    )
    warning_type    = models.CharField(max_length=32, default='结露预警', verbose_name='预警类型')
    warning_message = models.CharField(max_length=255, default='结露报警', verbose_name='预警内容')
    condensation_alarm_value = models.CharField(
        max_length=16, null=True, blank=True, verbose_name='触发时 condensation_alarm 原始值'
    )
    dew_point_temp = models.CharField(max_length=16, null=True, blank=True, verbose_name='露点温度快照')
    ntc_temp       = models.CharField(max_length=16, null=True, blank=True, verbose_name='NTC温度快照')
    humidity       = models.CharField(max_length=16, null=True, blank=True, verbose_name='湿度快照')
    system_switch  = models.CharField(
        max_length=8, null=True, blank=True,
        verbose_name='系统开关状态快照（on/off/unknown）'
    )
    first_seen_at  = models.DateTimeField(verbose_name='预警首次出现时间', db_index=True)
    last_seen_at   = models.DateTimeField(verbose_name='最近活跃时间（进程内维护）')
    recovered_at   = models.DateTimeField(null=True, blank=True, verbose_name='恢复时间')
    is_active      = models.BooleanField(default=True, verbose_name='是否活跃', db_index=True)
    created_at     = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at     = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'condensation_warning_event'
        verbose_name = '结露预警事件'
        verbose_name_plural = '结露预警事件'
        constraints = [
            models.UniqueConstraint(
                fields=['specific_part', 'device_sn', 'first_seen_at'],
                name='uniq_cw_sp_sn_first_seen',
            ),
        ]
        indexes = [
            models.Index(fields=['specific_part', 'is_active'], name='idx_cw_sp_active'),
            models.Index(fields=['first_seen_at', 'is_active'], name='idx_cw_time_active'),
        ]

    def __str__(self):
        return f"{self.specific_part} device={self.device_sn} active={self.is_active}"
```

**索引设计说明**：

| 索引 | 字段 | 用途 |
|------|------|------|
| PRIMARY KEY | id | 行定位（T3 UPDATE by id） |
| UNIQUE | (specific_part, device_sn, first_seen_at) | T1 IntegrityError 兜底防重复 |
| idx_cw_sp_active | (specific_part, is_active) | 房号+状态过滤（最常见查询路径） |
| idx_cw_time_active | (first_seen_at, is_active) | 时间段+状态过滤（默认 7 天范围） |
| db_index on specific_part | specific_part | 房号单列过滤 |
| db_index on first_seen_at | first_seen_at | 时间单列过滤 |
| db_index on is_active | is_active | 状态单列过滤（进程重启重建用） |

**Migration 策略**：

- migration 0029（depends: ['0028_fault_event_backfill_room']）：
  - 操作：`CreateModel CondensationWarningEvent`（DDL only）
  - 无历史数据回填（新表）
  - MySQL/SQLite 双兼容：Django ORM 迁移自动适配；VARCHAR/DATETIME 在两者均支持
  - 生产执行：可在服务运行期间执行（新表 DDL，不锁现有表），推荐停 condensation-consumer 后再 migrate（此时 consumer 尚未部署，无需顾虑）

**MySQL 与 SQLite 兼容性说明**：

| 特性 | MySQL（生产） | SQLite（测试） | 处理方式 |
|------|-------------|--------------|---------|
| UNIQUE 约束 | 原生支持 | 原生支持 | Django ORM，无差异 |
| DATETIME | 原生支持 | TEXT 存储（Django 透明处理） | 无需特殊处理 |
| ForeignKey ON DELETE SET NULL | 原生支持 | 原生支持 | 无差异 |
| BigAutoField PK | 原生支持（BIGINT AUTO_INCREMENT）| 原生支持 | 无差异 |

---

### ADR-CW-03：condensation_consumer 状态机 key 设计（二元 key）

**背景**：故障管理状态机 key 为 `(specific_part, device_sn, fault_code)`，但结露预警触发源只有单一字段 `condensation_alarm`，无 fault_code 维度。

**决策**：状态机 key 使用 `(specific_part, device_sn)`（二元组），每台设备同一时刻只存在一条活跃结露预警记录。

**理由**：
- 触发字段唯一性：`condensation_alarm` 是布尔/整数场，非多值枚举，无多 fault_code 并发可能。
- 防止同一设备产生多条并发活跃记录（UNIQUE 约束 `(specific_part, device_sn, first_seen_at)` 依赖 first_seen_at 区分不同时间段的预警周期，不依赖 fault_code）。
- 简化状态机内存结构，与需求 FR-CW-02 规格一致。

**实现**：

```python
# condensation_consumer/state_machine.py

@dataclass
class CondensationState:
    event_id: int
    is_active: bool
    last_seen_at: datetime

# key: (specific_part: str, device_sn: str)
_cw_state_machine: dict = {}
```

---

### ADR-CW-04：system_switch 快照字段类型选择（VARCHAR 存储，"on"/"off"/"unknown" 字符串）

**背景**：PLCLatestData.value 是 BigIntegerField（0=关，非0=开），但结露预警表的 system_switch 字段需要语义清晰，并兼容 "unknown" 兜底值。

**决策**：`condensation_warning_event.system_switch` 使用 `VARCHAR(8)` 存储语义字符串（"on"/"off"/"unknown"/NULL）。

**理由**：
- PLCLatestData.value=0 → "off"，非0 → "on"，转换在消费侧完成（一次性）。
- "unknown" 兜底无法用整数表达。
- 前端展示直接读字符串，无需二次解释。
- NULL 值语义等同于 "unknown"（需求 §2.3），序列化层统一处理。

**系统开关优先级实现**（消费侧 `_handle_message` 中）：

```
1. 扫描触发报文同一 deviceSn 的 items[]，找 attrTag='system_switch' → 直接取 attrValue 字符串
   （适用 260001 同报文含两字段的场景）
2. 若 items[] 中无 system_switch →
   调用 _get_system_switch_for_specific_part(specific_part)
   → PLCLatestData WHERE specific_part=X AND param_name='system_switch'
   → value != 0 → 'on'; value == 0 → 'off'; 无记录 → 'unknown'
3. 均无 → 写 'unknown'，记录 DEBUG 日志
```

注意事项：从 MQTT items[] 取到的 attrValue 是字符串，可能为 "0"/"1"/"on"/"off" 等；消费侧需做标准化（非 "0" 且非空 → "on"；"0" 或空 → "off"）。

---

### ADR-CW-05：is_screen_online 字段的计算注入策略（后端查询时实时计算）

**背景**：前端列表每行需展示大屏是否在线，但此值不存储到 condensation_warning_event 表。

**决策**：后端 `condensation_warning_event_list` 视图在分页后，对当前页所有 specific_part 执行一次 IN 查询 `ScreenConnectivityStatus`，计算 now()-last_seen_at ≤ 15min，将结果以 `is_screen_online: bool` 注入每条序列化结果。

**理由**：
- 完全复用故障管理页"无大屏在线字段"的对比参照（故障管理无此字段），但查询模式参照 views.py 的 ScreenConnectivityStatus 使用方式。
- ScreenConnectivityStatus 表为小表（每户一行，约 634 行），IN 查询最多 100 条，预计 < 50ms，无性能问题。
- 不存储到 DB：大屏在线状态是瞬时状态，存储无意义，每次查询时计算是正确语义。

**实现**：

```python
# views_condensation.py 中的后端注入逻辑
from django.utils import timezone
from datetime import timedelta

def _inject_screen_online(results: list[dict]) -> list[dict]:
    """对结果集注入 is_screen_online 字段。"""
    specific_parts = [r['specific_part'] for r in results]
    if not specific_parts:
        return results
    threshold = timezone.now() - timedelta(minutes=15)
    online_set = set(
        ScreenConnectivityStatus.objects
        .filter(specific_part__in=specific_parts, last_seen_at__gte=threshold)
        .values_list('specific_part', flat=True)
    )
    for r in results:
        r['is_screen_online'] = r['specific_part'] in online_set
    return results
```

---

### ADR-CW-06：condensation_consumer 与 fault_consumer 的代码隔离策略

**背景**：需求明确"独立实现，不与 fault_consumer 共享代码文件"，但同时要求"最大化复用"。

**决策**：代码文件完全独立，但设计结构完全镜像 fault_consumer。共享设计模式，不共享代码文件。

**理由**：
- 运行时隔离：两个 systemd 服务独立运行，任一服务崩溃不影响另一个。
- 进程内状态机独立：fault_consumer 的状态机内存与 condensation_consumer 的状态机内存不共享，分属不同 Python 进程。
- 单测隔离：独立文件使单测边界清晰，无需 mock 跨模块状态。
- 维护独立性：未来结露预警逻辑演化（如增加防抖、多级告警）不影响故障管理。

**目录结构**：

```
FreeArkWeb/backend/freearkweb/api/
├── condensation_consumer/          # 新建包（镜像 fault_consumer/）
│   ├── __init__.py
│   └── state_machine.py            # CondensationState + T1/T2/T3 实现
│
management/commands/
├── condensation_consumer.py        # Management Command（镜像 fault_consumer.py）
└── condensation_cleanup.py         # Management Command（镜像 fault_cleanup.py）
```

---

## 2. 模块影响矩阵（与故障管理的复用对照）

| 新模块/文件 | 对应故障管理模块 | 复用程度 | 关键差异 |
|------------|----------------|---------|---------|
| `condensation_consumer/state_machine.py` | `fault_consumer/state_machine.py` | 高度镜像 | key 无 fault_code；T1 增加快照字段逻辑（dew_point/ntc/humidity/system_switch）；T1 调用 ADR-CW-01 的 _get_system_switch_for_specific_part |
| `condensation_consumer/__init__.py` | `fault_consumer/__init__.py` | 完全复用 | 无差异 |
| `management/commands/condensation_consumer.py` | `management/commands/fault_consumer.py` | 高度镜像 | client_id='freeark-condensation-consumer'；_handle_message 只检查 condensation_alarm；不调用 fault_classifier |
| `management/commands/condensation_cleanup.py` | `management/commands/fault_cleanup.py` | 完全镜像 | 模型名 CondensationWarningEvent；command 名 condensation_cleanup |
| `models.py` → `CondensationWarningEvent` | `models.py` → `FaultEvent` | 结构复用 | 无 fault_code/fault_type/severity；新增 dew_point_temp/ntc_temp/humidity/system_switch/condensation_alarm_value；state machine key 二元 |
| `views_condensation.py`（新文件） | `views_fault.py` | 结构复用 | 无 sub_type/fault_type/room_name 过滤（暂不需要）；新增 _inject_screen_online；specific_part 段数映射逻辑完全复用 |
| `serializers_condensation.py`（新文件） | `serializers_fault.py` | 结构复用 | 字段不同；新增 is_screen_online（SerializerMethodField） |
| `fault_consumer/room_lookup.py` | — | 直接复用 | 无需改动；condensation_consumer/state_machine.py 中直接 import 使用 |
| `utils_room_filter.py` | — | 直接复用（views 层） | 无需改动；specific_part 段数映射逻辑复用自 views_fault.py |
| `deployment/systemd/freeark-condensation-consumer.service` | `freeark-fault-consumer.service` | 完全镜像 | command=condensation_consumer；SyslogIdentifier 不同 |
| `deployment/systemd/freeark-condensation-cleanup.service` | `freeark-fault-cleanup.service` | 完全镜像 | command=condensation_cleanup |
| `deployment/systemd/freeark-condensation-cleanup.timer` | `freeark-fault-cleanup.timer` | 完全镜像 | OnCalendar=*-*-* 03:30:00（故障清理为 03:00，结露为 03:30，错开） |
| `FreeArkWeb/frontend/src/views/CondensationWarningView.vue` | `FaultManagementView.vue` | 高度镜像 | 过滤器三件套（少故障类型/设备类型/房间过滤器）；表格 12 列（新增大屏在线/系统开关/露点/NTC/湿度，移除故障相关列）；is_active UI 标签"未回复/已回复" |
| `FreeArkWeb/frontend/src/router/index.js` | 故障管理路由条目 | 直接参照 | 新增 /device-management/condensation-warnings |
| `FreeArkWeb/frontend/src/components/Layout.vue` | Layout.vue 故障管理菜单项 | 直接参照 | 在「故障管理」之后新增「结露预警」子菜单项 |

---

## 3. 系统架构图（文字描述）

```
[MQTT Broker (wss)]
        │  /screen/upload/screen/to/cloud/+
        ▼
[freeark-condensation-consumer (systemd)]
  ├─ _MacCache（OwnerInfo → specific_part，5min TTL）
  ├─ condensation_consumer/state_machine.py（进程内内存表）
  │     key=(specific_part, device_sn)
  │     T1 → INSERT condensation_warning_event + _get_system_switch_for_specific_part
  │     T2 → 仅更新内存 last_seen_at
  │     T3 → UPDATE is_active=False, recovered_at
  └─ Django ORM → MySQL 192.168.31.98:3306

[MySQL]
  ├─ condensation_warning_event（新表，migration 0029）
  ├─ PLCLatestData（已有，system_switch 查询用，ADR-CW-01）
  ├─ ScreenConnectivityStatus（已有，is_screen_online 计算用）
  ├─ DeviceNode / DeviceRoom（已有，room_lookup 用）
  └─ OwnerInfo（已有，MAC→specific_part 用）

[freeark-condensation-cleanup.timer → freeark-condensation-cleanup.service]
  每天 03:30 → condensation_cleanup --days=90 --batch-size=1000
  DELETE WHERE is_active=False AND first_seen_at < now()-90d（分批，每批≤1000）

[freeark-backend (Django REST)]
  GET /api/devices/condensation-warning-events/
  ├─ views_condensation.condensation_warning_event_list
  ├─ 过滤：specific_part（段数映射）、is_active、first_seen_after/before
  ├─ 分页：PageNumberPagination（20/页，最大100）
  ├─ _inject_screen_online（IN 查 ScreenConnectivityStatus）
  └─ serializers_condensation.CondensationWarningEventSerializer

[Vue Frontend]
  /device-management/condensation-warnings
  ├─ CondensationWarningView.vue（12 列表格 + 过滤器三件套）
  ├─ CascadingSelector.vue（复用，无修改）
  └─ Layout.vue（新增「结露预警」菜单项）
```

---

## 4. 数据流详述（T1 INSERT 路径）

以温控面板（120003, deviceSn=22549）触发 condensation_alarm=1 为例：

```
1. MQTT on_message 回调接收报文
2. JSON 解析，验证 header.name == "DeviceStatusUpdate"
3. topic 末段取 screenMAC → _MacCache.get_specific_part(mac) → specific_part="1-1-16-1601"
4. 提取 payload.data: deviceSn="22549", productCode="120003", items=[...]
5. 遍历 items[]:
   - 发现 attrTag="condensation_alarm", attrValue="1" → int("1") != 0 → 预警态
   - 提取同 deviceSn items 中的 dew_point_temp, NTC_temp, humidity（若有）
   - 检查同 deviceSn items 中有无 system_switch attrTag：
     - 120003 通常无 → fallback
     - 调用 _get_system_switch_for_specific_part("1-1-16-1601")
       → PLCLatestData WHERE specific_part="1-1-16-1601" AND param_name="system_switch"
       → 找到 value=1 → system_switch="on"
6. process_condensation_field(specific_part, device_sn, product_code, is_active=True, ...)
7. 状态机查 key=("1-1-16-1601", "22549")：内存 miss
8. T1: _t1_insert() → FaultEvent（错，应为 CondensationWarningEvent）.objects.create(
       specific_part="1-1-16-1601", device_sn="22549", product_code="120003",
       warning_type="结露预警", warning_message="结露报警",
       condensation_alarm_value="1",
       dew_point_temp="20.5", ntc_temp="18.0", humidity="65",
       system_switch="on",
       room_name="儿童房", room_id=<id>,  ← get_room_for_device("22549")
       first_seen_at=now(), last_seen_at=now(), is_active=True
   )
9. 内存表写入: key → CondensationState(event_id=N, is_active=True, last_seen_at=now())
```

---

## 5. 新增 systemd 服务规格

### 5.1 freeark-condensation-consumer.service

```ini
[Unit]
Description=FreeArk Condensation Warning MQTT Consumer (v0.7.0-CW)
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=yangyang
WorkingDirectory=/home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb
ExecStart=/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py condensation_consumer
Restart=on-failure
RestartSec=30s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=freeark-condensation-consumer
Environment=DJANGO_SETTINGS_MODULE=freearkweb.settings

[Install]
WantedBy=multi-user.target
```

### 5.2 freeark-condensation-cleanup.service

```ini
[Unit]
Description=FreeArk Condensation Warning Cleanup (one-shot, v0.7.0-CW)
After=network.target

[Service]
Type=oneshot
User=yangyang
WorkingDirectory=/home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb
ExecStart=/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py condensation_cleanup --days=90 --batch-size=1000
StandardOutput=journal
StandardError=journal
SyslogIdentifier=freeark-condensation-cleanup
Environment=DJANGO_SETTINGS_MODULE=freearkweb.settings
```

### 5.3 freeark-condensation-cleanup.timer

```ini
[Unit]
Description=FreeArk Condensation Warning Cleanup Timer
Requires=freeark-condensation-cleanup.service

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true
Unit=freeark-condensation-cleanup.service

[Install]
WantedBy=timers.target
```

**选择 03:30 而非 03:00 的原因**：故障清理 (freeark-fault-cleanup) 在 03:00 执行，错开 30 分钟减少 MySQL 同时写入压力。

---

## 6. REST API 设计

### 6.1 新增接口

**GET /api/devices/condensation-warning-events/**

路由注册（`urls.py` 追加）：
```python
path('condensation-warning-events/', views_condensation.condensation_warning_event_list, name='condensation_warning_event_list'),
```

查询参数与故障管理接口对照：

| 参数 | 类型 | 处理逻辑 | 来自故障管理 |
|------|------|---------|------------|
| specific_part | string | 段数映射（3段→startswith+endswith，4段→icontains），完全复用 views_fault.py 逻辑 | 复用 |
| is_active | "true"/"false" | 严格转布尔，不传=全部 | 复用 |
| first_seen_after | ISO8601 | 默认 now()-7d，_parse_dt 处理 USE_TZ | 复用 |
| first_seen_before | ISO8601 | 同上 | 复用 |
| page | integer | PageNumberPagination | 复用 |
| page_size | integer | 默认20，最大100 | 复用 |

注意：结露预警无 fault_type / sub_type / room_name 过滤参数（需求未要求，不过度实现）。

### 6.2 响应格式

```json
{
  "count": 42,
  "next": "http://host/api/devices/condensation-warning-events/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "specific_part": "1-1-16-1601",
      "room_name": "儿童房",
      "device_sn": "22549",
      "product_code": "120003",
      "warning_type": "结露预警",
      "warning_message": "结露报警",
      "condensation_alarm_value": "1",
      "dew_point_temp": "20.5",
      "ntc_temp": "18.0",
      "humidity": "65",
      "system_switch": "on",
      "is_screen_online": true,
      "first_seen_at": "2026-05-30T10:00:00+08:00",
      "last_seen_at": "2026-05-30T10:05:00+08:00",
      "recovered_at": null,
      "is_active": true
    }
  ]
}
```

---

## 7. 前端路由与导航变更

### 7.1 router/index.js 新增条目

```javascript
{
  path: '/device-management/condensation-warnings',
  name: 'CondensationWarnings',
  component: () => import('../views/CondensationWarningView.vue'),
  meta: { requiresAuth: true }
}
```

### 7.2 Layout.vue 菜单变更

在「故障管理」菜单项之后新增：

```html
<el-menu-item index="/device-management/condensation-warnings">
  结露预警
</el-menu-item>
```

### 7.3 CondensationWarningView.vue 结构概要

```
<template>
  <div class="condensation-warning">
    <div class="page-header">
      <h2>结露预警</h2>
      ...
    </div>

    <!-- 过滤器三件套（仅三项，无故障类型/设备类型/房间） -->
    <el-form :inline="true" class="filter-bar">
      <el-form-item label="状态">
        <el-radio-group v-model="filterIsActive" @change="handleSearch">
          <el-radio-button value="true">未回复</el-radio-button>
          <el-radio-button value="false">已回复</el-radio-button>
          <el-radio-button value="all">全部</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="房号">
        <CascadingSelector ref="cwCascadingSelectorRef" ... />
      </el-form-item>

      <el-form-item label="时间段">
        <el-date-picker v-model="filters.dateRange" type="daterange" ... />
      </el-form-item>
    </el-form>

    <!-- 12 列表格 -->
    <el-table :data="warningList" ...>
      <el-table-column prop="specific_part"   label="房号" />
      <el-table-column prop="room_name"        label="房间" />
      <el-table-column label="大屏是否在线">
        <!-- 绿色/灰色标签，基于 is_screen_online -->
      </el-table-column>
      <el-table-column label="系统开关">
        <!-- on→开启，off→关闭，其他→"-" -->
      </el-table-column>
      <el-table-column prop="warning_type"     label="预警类型" />
      <el-table-column prop="warning_message"  label="预警内容" />
      <el-table-column prop="dew_point_temp"   label="露点温度" />
      <el-table-column prop="ntc_temp"         label="NTC温度" />
      <el-table-column prop="humidity"         label="湿度" />
      <el-table-column prop="first_seen_at"    label="预警发生时间" />
      <el-table-column prop="last_seen_at"     label="最后活跃" />
      <el-table-column prop="recovered_at"     label="恢复时间" />
    </el-table>

    <!-- 分页（与 FaultManagementView 完全一致） -->
    <el-pagination ... />
  </div>
</template>
```

**URLSearchParams 数组参数序列化**：参照 BUG-FM-003 修复经验（KE-PM-011），所有多值参数使用 URLSearchParams append 而非 axios 默认序列化。（本版本无多值过滤参数，但 fetchWarnings() 需保持一致编码风格以防未来扩展。）

---

## 8. 部署顺序

v0.7.0 部署不需要停止现有服务（新增独立模块），建议顺序：

```
1. git pull（在生产服务器执行）
2. python manage.py migrate          # 执行 migration 0029（新表 DDL）
3. sudo cp deployment/systemd/freeark-condensation-*.service /etc/systemd/system/
   sudo cp deployment/systemd/freeark-condensation-cleanup.timer /etc/systemd/system/
4. sudo systemctl daemon-reload
5. sudo systemctl enable --now freeark-condensation-consumer
6. sudo systemctl enable --now freeark-condensation-cleanup.timer
7. npm run build（前端构建，在生产服务器 frontend/ 目录）
8. cp dist/* <nginx-root>/           # 覆盖前端静态文件
9. （freeark-backend 无需重启，路由变更由前端 JS 处理）
10. sudo systemctl reload nginx
```

---

## 9. 架构风险与遗留问题

| 风险/遗留项 | 描述 | 严重级别 | 处置 |
|------------|------|---------|------|
| RISK-CW-ARCH-01 | PLCLatestData.value 存储 system_switch 为整数（0/非0），而 MQTT 的 system_switch attrValue 可能是字符串 "on"/"off"/"0"/"1"。消费侧需处理两种来源的格式差异。 | MINOR | 开发阶段：在 _handle_message 中对 MQTT 直取的 attrValue 做规范化（"0"/""→"off"，非"0"非空→"on"），与 PLCLatestData 路径统一转为 "on"/"off"/"unknown"。 |
| RISK-CW-ARCH-02 | condensation_consumer 进程重启时，cold start 窗口（状态机重建完成前）收到的预警可能走 T1（重复 INSERT）。IntegrityError 兜底逻辑（与 fault_consumer 相同）可防止数据重复，但会记录 WARNING 日志。 | MINOR | 与故障管理相同策略，已接受。重建在启动后立即执行，窗口通常 < 1s（活跃记录约 0~数百条）。 |
| RISK-CW-ARCH-03 | PLCLatestData 表可能无 specific_part 下的 system_switch 记录（若该住户 PLC 从未上线或数采服务未采集到 system_switch）。结果为 "unknown"，符合需求设计。 | INFO | 无需处置，"unknown" 已是正式支持的兜底值。 |
| OD-CW-ARCH-01（遗留开发确认项）| system_switch 从 MQTT items[] 取到的 attrValue 的实际格式（是 "0"/"1" 整数串还是 "on"/"off" 文字串），需开发阶段核对抓包文件 sniff_2860fae9a34ab8a9_20260525_235217.ndjson 后确认规范化逻辑。 | MINOR | 开发前确认；不影响架构，仅影响消费侧的字符串规范化分支。 |
