# 架构设计文档

```
file_header:
  document_id: ARCH-v0.6.0-FM
  title: MQTT 故障事件持久化 + 故障管理页面 — 架构设计
  author_agent: sub_agent_system_architect (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.6.0-fault-management
  created_at: 2026-05-27
  status: DRAFT
  references:
    - docs/requirements/v0.6.0_fault_management/requirements_spec.md
    - docs/requirements/v0.6.0_fault_management/user_stories.md
    - FreeArkWeb/backend/freearkweb/api/fault_utils.py
    - FreeArkWeb/backend/freearkweb/api/management/commands/screen_heartbeat_consumer.py
    - FreeArkWeb/backend/freearkweb/api/management/commands/dph_cleanup_service.py
    - FreeArkWeb/backend/freearkweb/api/models.py
    - FreeArkWeb/backend/freearkweb/api/urls.py
    - FreeArkWeb/frontend/src/router/index.js
    - docs/architecture/architecture_design_v0.5.3_fault_count_column.md
    - docs/architecture/module_design_v0.5.3_fault_count_column.md
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-27 | 初始草稿，ADR-FM-01~ADR-FM-08，覆盖全部需求 |

---

## 1. 设计目标与约束

### 1.1 核心目标

| 目标 | 具体要求 |
|------|---------|
| 事件驱动持久化 | MQTT 报文驱动写入，仅状态变化时写 DB，不记录每条报文（避免重蹈 device_param_history 36M 行问题） |
| 进程内状态机 | 故障去重与 last_seen_at 更新在进程内完成，DB 写入仅限"首次出现"与"恢复"两种路径 |
| 历史可查询 | fault_event 表支持多维过滤（房号、时间段、类型、设备）+ 分页 REST API |
| 零额外基础设施 | 物理机部署（树莓派），禁 Docker，无 Redis，不新增外部依赖 |
| 最小侵入 | v0.5.3-FCC 的 plc_latest_data 路径完整保留，不修改任何现有 API |

### 1.2 关键约束

- 生产服务器：树莓派 192.168.31.51，物理机，无 Docker
- 生产 DB：MySQL 9.4 @ 192.168.31.98:3306，settings.py read_timeout/write_timeout=60s
- 测试 DB：SQLite（所有 Django migrations 必须 SQLite 兼容）
- 严禁查询 device_param_history（3766 万行/11.3GB）
- MQTT broker：wss://www.ttqingjiao.site:8084/mqtt（EMQX，已有心跳服务在运行）
- paho-mqtt >=1.6.1,<2.0（requirements.txt 已有，不升版本）
- 部署：plink + git pull，禁 pscp

---

## 2. 架构决策记录（ADR）

### ADR-FM-01：MQTT 订阅 systemd 服务架构

**问题**：新增 MQTT 故障消费服务，如何与现有 freeark-screen-heartbeat 服务共存？是否共用进程？

**方案评估**：

| 方案 | 优点 | 缺点 |
|------|------|------|
| A：共用 freeark-screen-heartbeat 进程，在其 on_message 中增加故障处理分支 | 少一个进程 | 职责耦合；心跳服务崩溃会影响故障采集；订阅 topic 逻辑混杂（# vs +）；违反需求 FR-FM-01 "独立服务"要求 |
| B：新增独立 Django Management Command `fault_consumer`，由独立 systemd 服务管理（本方案）| 职责清晰；独立重启互不影响；topic 订阅独立配置；与 screen_heartbeat_consumer 同架构风格，开发者易理解 | 多一个进程（树莓派可承受，A-06 已确认） |
| C：使用 celery beat 或 apscheduler 在 Django 进程内运行 | 复用已有 gunicorn/waitress 进程 | 需新增 celery，引入新的基础设施依赖；长连接 MQTT 不适合 task queue 模型 |

**决策**：采用方案 B。

**服务设计**：
- 服务名：`freeark-fault-consumer`
- Management Command：`python manage.py fault_consumer`
- 文件路径：`FreeArkWeb/backend/freearkweb/api/management/commands/fault_consumer.py`
- systemd 配置（`/etc/systemd/system/freeark-fault-consumer.service`）：

```ini
[Unit]
Description=FreeArk Fault Event MQTT Consumer
After=network.target mysql.service
Wants=network-online.target

[Service]
Type=simple
User=freeark
WorkingDirectory=/home/freeark/FreeArk/FreeArkWeb/backend
ExecStart=/home/freeark/.venv/bin/python manage.py fault_consumer
Restart=on-failure
RestartSec=30s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=freeark-fault-consumer
Environment=DJANGO_SETTINGS_MODULE=freearkweb.settings

[Install]
WantedBy=multi-user.target
```

**订阅 topic**：`/screen/upload/screen/to/cloud/+`（通配符 `+`，ACL 已确认允许，ADR-FM-01-R08 记录 fallback 方案）

**broker 配置**：从 `heartbeat_broker_config.json` 读取（与心跳服务同一配置文件格式），但使用独立 `client_id = "freeark-fault-consumer"`，避免 MQTT broker 踢出心跳服务的连接。

**ACL Fallback（R-08 风险对应）**：
- 配置文件中增加可选字段 `"fault_consumer_use_mac_list": false`
- 当设为 true 时，服务从 OwnerInfo 表加载所有 unique_id（screenMAC），逐个订阅 `/screen/upload/screen/to/cloud/<mac>`
- 本期默认 false（通配符模式）；ACL 收紧时运维人员切换此开关并 systemctl restart，无需改代码

---

### ADR-FM-02：进程内状态机数据结构

**问题**：如何在进程内高效维护故障活跃状态以避免每条 MQTT 报文触发 DB 读写？

**方案评估**：

| 方案 | 优点 | 缺点 |
|------|------|------|
| A：Django LocMemCache（与 v0.5.3-FCC 同） | 有 TTL 自动清理；Django 缓存 API 统一 | TTL 到期会丢失状态机上下文；不适合"event_id 引用"的有状态场景；cache miss 后无法区分"真未见过"还是"TTL 过期" |
| B：进程内 Python dict，无 TTL（本方案）| 状态永远在内存中直到进程重启；key 明确对应 DB row；支持"首次 vs 重复"精确判断；内存占用可估算（9 MB@45k 条，A-05 估算） | 进程重启后需从 DB 重建；重启期间短暂窗口可能重复 INSERT（由 DB unique 约束兜底） |
| C：SQLite 内存数据库（进程内 in-memory DB） | SQL 查询灵活 | 引入额外依赖路径；比 dict 重；同进程内无并发优势 |

**决策**：采用方案 B。

**状态机 dict 定义**：

```python
# key: (specific_part: str, device_sn: str, fault_code: str)
# value: FaultState dataclass
@dataclass
class FaultState:
    event_id: int          # fault_event.id，用于 UPDATE 定位行
    is_active: bool        # True=活跃，False=已恢复
    last_seen_at: datetime # 最近一次 MQTT 上报（内存中维护，恢复时写回 DB）
```

**内存占用估算**：
- 典型：100 楼 × 10 屏 × 9 设备 × 5 故障码 = 45,000 条
- 每条：key tuple（3 个字符串约 80 字节）+ FaultState（约 60 字节）+ Python dict overhead（约 80 字节）≈ 220 字节
- 总计：45,000 × 220 B ≈ 9.9 MB（在树莓派 2~4 GB RAM 下完全可接受）
- 突发 10× 场景：约 100 MB，仍可接受（AB-001 Redis 化触发条件：实测超 256 MB）

**进程重启重建策略**：
```python
# 启动时执行一次
def _rebuild_from_db():
    qs = FaultEvent.objects.filter(is_active=True)[:10000]  # LIMIT 10000 保护
    for fe in qs:
        key = (fe.specific_part, fe.device_sn, fe.fault_code)
        _state_machine[key] = FaultState(
            event_id=fe.id,
            is_active=True,
            last_seen_at=fe.last_seen_at,
        )
    logger.info('状态机重建完成，共加载 %d 条活跃故障', len(_state_machine))
```

重建后如收到重复 INSERT（极端竞态）：捕获 `IntegrityError`，改为 UPDATE `last_seen_at`，不崩溃。

---

### ADR-FM-03：故障状态机跳变规则

**问题**：如何定义状态机的转移规则，既保证数据一致性，又最小化 DB 写入频率？

**决策**：采用需求 FR-FM-02 明确的"方案 C 变体"，状态转移规则如下：

```
状态 S1: UNKNOWN（内存表 miss 或 is_active=False）
状态 S2: ACTIVE（内存表 hit，is_active=True）

转移 T1: S1 + 收到故障报文
  → DB: INSERT INTO fault_event (is_active=True, first_seen_at=now(), last_seen_at=now(), ...)
  → 内存: _state_machine[key] = FaultState(event_id=new_id, is_active=True, last_seen_at=now())
  → 如 INSERT 触发 IntegrityError → 捕获，UPDATE fault_event SET last_seen_at=now() WHERE key 匹配
  → 状态进入 S2

转移 T2: S2 + 收到故障报文（重复上报，故障持续中）
  → DB: 无操作
  → 内存: _state_machine[key].last_seen_at = now()
  → 状态保持 S2

转移 T3: S2 + 收到"正常"报文（故障字段恢复为 normal/0）
  → DB: UPDATE fault_event SET is_active=False, recovered_at=now(),
         last_seen_at=内存中的 last_seen_at WHERE id=event_id
  → 内存: _state_machine[key].is_active = False
  → 状态进入 S1（下次该 key 出现故障时视为新事件，执行 T1）
```

**recovered_at timeout（R-10 stale active 风险）**：

本期不实现 heartbeat-based timeout（stale 自动标记）。运维人员可通过「只看未恢复」toggle 在故障管理页面观察 `last_seen_at` 来判断故障是否真实活跃。此机制列入 AB-007 后续版本实现。

**故障恢复的判断标准**：在 MQTT `items[]` 中遍历字段时，如果某字段在上一次报文中被识别为故障（is_active=True），而当前报文中同字段的值恢复为正常值，则触发 T3。判定"正常值"的规则：

| 字段类型 | 正常值 |
|----------|--------|
| `comm_fault_timeout` | `"normal"`（字符串） |
| `error_<N>` | `"0"` 或整数 `0` |
| 其他 FAULT_PARAM_NAMES 字段 | 整数 `0` 或空值 |

---

### ADR-FM-04：MySQL 数据表设计（fault_event）

**问题**：如何设计 `fault_event` 表的索引策略，在满足查询性能要求的同时避免过多索引拖累写入性能？

**最终 DDL（Django model 定义）**：

```python
class FaultEvent(models.Model):
    specific_part = models.CharField(max_length=64, verbose_name='房号')
    device_sn = models.CharField(max_length=64, verbose_name='设备序列号')
    product_code = models.CharField(max_length=32, verbose_name='产品编码')
    fault_code = models.CharField(max_length=64, verbose_name='故障码')
    fault_type = models.CharField(
        max_length=16,
        choices=[
            ('comm', '通信故障'),
            ('sensor', '传感器故障'),
            ('fresh_air', '新风故障'),
            ('other_error', '其他故障'),
        ],
        verbose_name='故障大类',
    )
    fault_message = models.CharField(max_length=255, verbose_name='故障描述')
    severity = models.CharField(
        max_length=8,
        choices=[('error', 'Error'), ('warning', 'Warning')],
        verbose_name='严重级别',
    )
    first_seen_at = models.DateTimeField(verbose_name='首次出现时间')
    last_seen_at = models.DateTimeField(verbose_name='最后活跃时间')
    recovered_at = models.DateTimeField(null=True, blank=True, verbose_name='恢复时间')
    is_active = models.BooleanField(default=True, verbose_name='是否活跃')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'fault_event'
        verbose_name = '故障事件'
        verbose_name_plural = '故障事件'
        constraints = [
            models.UniqueConstraint(
                fields=['specific_part', 'device_sn', 'fault_code', 'first_seen_at'],
                name='uq_fault_event_key_time',
            )
        ]
        indexes = [
            models.Index(fields=['specific_part', 'is_active'],
                         name='idx_fault_sp_active'),
            models.Index(fields=['first_seen_at', 'is_active'],
                         name='idx_fault_time_active'),
        ]
```

**索引策略决策**：

| 索引 | 覆盖查询场景 | 说明 |
|------|------------|------|
| PRIMARY KEY (id) | 所有 UPDATE by event_id | 自增 BigAutoField |
| UNIQUE (specific_part, device_sn, fault_code, first_seen_at) | 防重 INSERT；同一故障重新触发视为新行 | 兼做进程重启 IntegrityError 兜底 |
| INDEX (specific_part, is_active) | 按房号过滤活跃故障；进程重启重建缓存的 WHERE specific_part 辅助 | 复合索引：sp 在前，支持仅按 sp 查询 |
| INDEX (first_seen_at, is_active) | 时间范围过滤（最常见查询模式）；「只看未恢复」组合过滤 | API 的默认查询（last 7 days + is_active 可选）走此索引 |

**不增加以下索引的原因**：
- `INDEX(is_active)` 单列：选择性极低（bool 字段），MySQL 通常不走此索引，增加写入代价无益
- `INDEX(specific_part)` 单列：被复合索引 `(specific_part, is_active)` 的最左前缀覆盖，无需单独建
- `INDEX(fault_type)`、`INDEX(severity)`：查询时作为过滤条件，但 cardinality 低（4 个值），MySQL 倾向全表扫配合 first_seen_at 索引过滤，不值得单独建

**与 device_param_history 并存影响评估**：

fault_event 表的写入模式与 device_param_history 有根本不同：

| 维度 | device_param_history | fault_event |
|------|---------------------|-------------|
| 写入触发 | 每条 MQTT 报文（全量写）| 仅故障首次出现 / 恢复时 |
| 预期写入频率 | 数百条/分钟（历史已 3766 万行）| 几条/天（事件驱动） |
| 行增长速度 | 已证明失控 | 90 天清理保障可控 |
| 对 buffer pool 影响 | 主要占用（11.3 GB 数据）| 可忽略（预估月增 < 1 万行）|

结论：fault_event 表对 MySQL 负载的增量影响极小，不会加剧 device_param_history 的现有性能压力。

---

### ADR-FM-05：REST API 设计

**问题**：故障管理 API 应如何组织路由，与 v0.5.3-FCC 的 `device_fault_count` 是否合并 endpoint？

**v0.5.3-FCC `device_fault_count` 与 v0.6.0 故障管理 API 对比**：

| 维度 | v0.5.3-FCC `/api/devices/fault-count/` | v0.6.0 `/api/devices/fault-events/` |
|------|---------------------------------------|-------------------------------------|
| 数据来源 | `plc_latest_data`（当前快照） | `fault_event`（历史记录） |
| 语义 | "当前有几个故障" | "某故障何时出现、何时恢复" |
| 响应结构 | `{fault_count: int}` per specific_part | 分页列表，每条含时间戳 |
| 前端使用方 | 设备列表页「故障数量」列 | 故障管理页面 |
| 缓存 | LocMemCache TTL=60s | 不缓存（直查 DB） |

**决策**：不合并，保持两套独立 endpoint。

**理由**：
1. 数据源不同（plc_latest_data vs fault_event），合并会破坏 v0.5.3-FCC 的缓存设计。
2. 响应结构完全不同，合并会导致接口语义模糊。
3. 最小侵入原则：v0.5.3-FCC 完整保留，v0.6.0 新增独立接口。

**v0.6.0 新增接口清单**：

```
GET  /api/devices/fault-events/         # 故障事件分页查询（FR-FM-05 主接口）
GET  /api/devices/fault-event-categories/  # 故障类型分类常量（供前端过滤下拉）
```

**`GET /api/devices/fault-events/` 查询参数**：

| 参数 | 类型 | 默认值 | 后端处理 |
|------|------|--------|---------|
| `specific_part` | string | 无 | `LIKE '%value%'`（icontains） |
| `fault_type` | string（多值，`?fault_type=comm&fault_type=sensor`） | 无 | `fault_type__in` |
| `sub_type` | string（多值） | 无 | 通过 `fault_code` 前缀匹配（见 ADR-FM-05-SUBTYPE） |
| `is_active` | `"true"/"false"` | 无（不过滤） | `is_active=True/False` |
| `first_seen_after` | ISO8601 | now() - 7 天 | `first_seen_at__gte` |
| `first_seen_before` | ISO8601 | 无 | `first_seen_at__lte` |
| `page` | int | 1 | DRF Pagination |
| `page_size` | int | 20，最大 100 | DRF Pagination |

**sub_type 过滤的实现（ADR-FM-05-SUBTYPE）**：

`sub_type` 参数指的是设备类型名（如 `living_room_thermostat`、`fresh_air_unit`），而 fault_event 表不存储 sub_type 字段（需求裁决 OQ-01）。过滤逻辑：

- 维护后端常量 `FAULT_CODE_TO_SUB_TYPE` 映射（从 `fault_utils.py` 的 `FAULT_PARAM_NAMES` 推导，集中在 `fault_consumer/constants.py`）
- API 收到 `sub_type` 参数时，将其翻译为对应的 `fault_code` 集合，使用 `fault_code__in` 过滤
- 例：`sub_type=living_room_thermostat` → `fault_code__in=['living_room_temp_sensor_error', 'living_room_humidity_sensor_error', ...]`

**`GET /api/devices/fault-event-categories/` 响应结构**：

```json
{
  "fault_types": [
    {"value": "comm", "label": "通信故障"},
    {"value": "sensor", "label": "传感器故障"},
    {"value": "fresh_air", "label": "新风故障"},
    {"value": "other_error", "label": "其他故障"}
  ],
  "sub_types": [
    {"value": "living_room_thermostat", "label": "客厅温控面板"},
    {"value": "study_room_thermostat", "label": "书房温控面板"},
    {"value": "bedroom_thermostat", "label": "主卧温控面板"},
    {"value": "children_room_thermostat", "label": "儿童房温控面板"},
    {"value": "fourth_children_room_thermostat", "label": "第四儿童房温控面板"},
    {"value": "fresh_air_unit", "label": "新风机"},
    {"value": "hydraulic_module", "label": "水力模块"},
    {"value": "energy_meter", "label": "能耗表"},
    {"value": "air_quality_sensor", "label": "空气品质传感器"}
  ]
}
```

**分页实现**：使用 Django REST Framework `PageNumberPagination`，与现有设备管理接口风格一致。

---

### ADR-FM-06：故障清理 systemd 服务

**问题**：`freeark-fault-cleanup` 服务如何设计，与现有 `freeark-dph-cleanup` 是否可以共用框架？

**决策**：独立实现，参考 `dph_cleanup_service.py` 的分批删除模式，但使用 systemd timer 驱动（不使用 Python schedule 库常驻进程）。

**两者对比**：

| 维度 | freeark-dph-cleanup | freeark-fault-cleanup |
|------|--------------------|-----------------------|
| 运行模式 | 常驻进程（内置 schedule cron）| systemd timer + 一次性执行（--once 模式）|
| 调度方式 | Python `schedule` 库 | systemd `OnCalendar=*-*-* 03:30:00` |
| 执行命令 | `python manage.py dph_cleanup_service --days 7 --cron "0 3 * * *"` | `python manage.py fault_cleanup --days 90 --batch-size 1000` |
| 超时保护 | 需要（60s→600s 放大，大表慢查询） | 不需要（fault_event 表行数远小于 dph，90 天窗口控制规模）|

**理由选择 systemd timer 而非常驻进程**：
- fault_event 表规模远小于 dph，清理任务运行时间短（预估 < 30 秒/次）
- systemd timer 更简洁，不需要常驻进程占内存，符合最小资源占用原则
- systemd timer + one-shot service 是 Linux 清理任务的最佳实践

**清理逻辑**：

```
DELETE FROM fault_event
WHERE first_seen_at < NOW() - INTERVAL {days} DAY
  AND is_active = False
LIMIT {batch_size}
```

重复执行直到 affected rows = 0，批次间 sleep 100ms（fault_event 表小，不需要 200ms）。

**服务配置**（两个文件）：

```ini
# /etc/systemd/system/freeark-fault-cleanup.service
[Unit]
Description=FreeArk Fault Event Cleanup (one-shot)
After=network.target mysql.service

[Service]
Type=oneshot
User=freeark
WorkingDirectory=/home/freeark/FreeArk/FreeArkWeb/backend
ExecStart=/home/freeark/.venv/bin/python manage.py fault_cleanup --days=90 --batch-size=1000
StandardOutput=journal
StandardError=journal
SyslogIdentifier=freeark-fault-cleanup
Environment=DJANGO_SETTINGS_MODULE=freearkweb.settings
```

```ini
# /etc/systemd/system/freeark-fault-cleanup.timer
[Unit]
Description=FreeArk Fault Event Cleanup Timer
Requires=freeark-fault-cleanup.service

[Timer]
OnCalendar=*-*-* 03:30:00
AccuracySec=5min
Persistent=true

[Install]
WantedBy=timers.target
```

**与其他服务的并发协调**：

fault_cleanup 执行时间（03:30）与以下服务存在潜在并发：
- `freeark-fault-consumer`（常驻，持续写入）：并发风险极低。清理删除 `is_active=False` 且 90 天前的记录，fault-consumer 只写/更新活跃故障（is_active=True）或更新近期记录，不存在行级冲突。
- `freeark-dph-cleanup`（常驻，内置 schedule 03:00 执行）：操作不同的表（device_param_history vs fault_event），无冲突。
- OpenClaw（loopback 127.0.0.1:18789）：不直接操作 fault_event 表，无冲突。

结论：无需额外协调机制，并发风险可接受。

---

### ADR-FM-07：与 v0.5.3-FCC 的关系与数据对齐

**问题**：v0.5.3-FCC 从 `plc_latest_data` 实时计算故障数，v0.6.0 从 `fault_event.is_active=True` 查历史活跃故障，两者同一时刻的结果是否一致？

**分析**：

| 数据来源 | 刷新机制 | 语义 |
|----------|---------|------|
| v0.5.3 `plc_latest_data` | 每条 MQTT 报文（PLCLatestDataHandler）全量 upsert | "大屏上一次上报时的 PLC 快照" |
| v0.6.0 `fault_event.is_active=True` | MQTT 驱动，首次出现时 INSERT，恢复时 UPDATE | "已知活跃的历史故障事件集合" |

**两者可能不一致的原因**：
1. `plc_latest_data` 每条 MQTT 都更新（最新快照）；`fault_event` 仅在状态跳变时更新
2. fault-consumer 服务重启期间，进程内状态机丢失，重建期间有短暂窗口
3. `plc_latest_data` 包含所有参数（非仅故障字段），而 `fault_event` 仅记录故障事件
4. v0.5.3 按 `sub_type` 可见性过滤（BUG-FCC-001 hotfix）；v0.6.0 不过滤 sub_type（记录全部上报的故障）

**决策**：两者语义不同，不强求一致，各自服务于不同功能。

**明确的分工边界**：
- **v0.5.3-FCC**：提供"当前实时故障数量"（设备列表页的摘要列），数据来源 plc_latest_data，60s TTL 缓存
- **v0.6.0-FM**：提供"故障历史记录与管理"（故障管理页面），数据来源 fault_event 表

**文档化的不一致风险**：
- 运维人员可能发现"设备列表显示 3 个故障"但"故障管理页面只显示 2 个活跃故障"（或反之）
- 原因：sub_type 可见性过滤差异、状态机重建窗口、报文解析逻辑差异
- 缓解：在故障管理页面 UI 上方增加说明文字："故障历史数据来自 MQTT 驱动写入，与设备列表页的实时故障数量统计独立；如需实时快照，请查看设备面板。"

**AB-002 钩子状态**：本期 fault_consumer 写入 fault_event 时，**不调用** `invalidate_fault_count_cache`。AB-002 仍为待决状态，保持 v0.5.3-FCC 设计不变。

---

### ADR-FM-08：内存占用与扩展性边界

**问题**：进程内状态机何时需要迁移至 Redis（AB-001）？

**当前估算**：

| 场景 | 条目数 | 内存占用 |
|------|--------|---------|
| 典型运行（5 故障/设备） | 45,000 | ~10 MB |
| 突发 10× 故障爆发 | 450,000 | ~100 MB |
| Redis 迁移触发阈值 | — | 实测 > 256 MB |

**决策**：本期（v0.6.0）不触发 AB-001，维持进程内 Python dict 方案。

**触发 AB-001 迁移的条件（记录为架构约束，供后续版本参考）**：
1. 实测进程内存超过 256 MB，且通过 `ps aux` 确认 fault-consumer 是主要占用方
2. 或出现第二个需要跨进程共享故障状态的需求（如多进程 fault-consumer）
3. 迁移步骤：settings.py CACHES 切换至 Redis backend；dict 改为 redis-py 操作；无需修改 FaultEvent model 或 API

**OOS-01（Redis 化）**：本期确认不在范围内，v0.6.0 不引入 Redis。

---

## 3. 系统整体架构图

```
MQTT Broker (EMQX wss://ttqingjiao.site:8084)
    │
    │ /screen/upload/screen/to/cloud/+  (DeviceStatusUpdate 报文, 2s/条/子设备)
    │
    ├──────────────────────────────────────────────────────────────────┐
    │                                                                  │
    ▼                                                                  ▼
┌─────────────────────────────────────┐          ┌───────────────────────────────────┐
│  freeark-screen-heartbeat (已有)    │          │  freeark-fault-consumer (新增)    │
│  screen_heartbeat_consumer.py       │          │  fault_consumer.py                │
│  topic: /screen/.../+               │          │  topic: /screen/.../+             │
│  → ScreenConnectivityStatus upsert  │          │  → 进程内状态机 (Python dict)      │
│  (心跳最后在线时间)                  │          │  → fault_event INSERT/UPDATE      │
└─────────────────────────────────────┘          └───────────────────────────────────┘
                                                              │
                                                              ▼
    ┌──────────────────────────────── MySQL 192.168.31.98:3306 ─────────────────────────┐
    │                                                                                    │
    │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   │
    │  │ plc_latest   │   │ fault_event  │   │OwnerInfo     │   │ScreenConnectivity│   │
    │  │ _data        │   │(新增)         │   │(已有，MAC→sp  │   │Status (已有)     │   │
    │  │(已有，快照)   │   │              │   │映射)          │   │                  │   │
    │  └──────────────┘   └──────────────┘   └──────────────┘   └──────────────────┘   │
    └────────────────────────────────────────────────────────────────────────────────────┘
              │                    │
              │                    │
    ┌─────────┴────────────────────┴──────────────────────────────────┐
    │  freeark-backend (waitress, Django, 单进程多线程)                │
    │                                                                  │
    │  GET /api/devices/fault-count/     ← v0.5.3-FCC (已有，不改)    │
    │  GET /api/device-management/...    ← 已有接口                    │
    │  GET /api/devices/fault-events/    ← v0.6.0 新增                │
    │  GET /api/devices/fault-event-categories/  ← v0.6.0 新增        │
    └──────────────────────────────────────────────────────────────────┘
              │
              │ HTTP REST API
              ▼
    ┌──────────────────────────────────────────────────────┐
    │  前端 Vue 3 (Vite)                                    │
    │                                                       │
    │  /device-management/device-list  ← 已有（故障数量列） │
    │  /device-management/faults       ← v0.6.0 新增       │
    │    FaultManagementView.vue                            │
    └──────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────┐
    │  freeark-fault-cleanup.timer (新增，03:30 每日)          │
    │  fault_cleanup.py (Management Command)                  │
    │  → DELETE fault_event WHERE first_seen_at < 90d         │
    │     AND is_active=False, 分批 1000 行                   │
    └─────────────────────────────────────────────────────────┘
```

---

## 4. 报文解析架构

### 4.1 DeviceStatusUpdate 报文处理流程

```
on_message(topic, payload)
    │
    ├── 1. 解析 JSON，验证 header.name == "DeviceStatusUpdate"
    │      失败 → WARNING 日志，return（不崩溃）
    │
    ├── 2. 提取 MAC = topic.split('/')[-1]
    │      通过 MacCache.get_specific_part(mac) 获取 specific_part
    │      映射缺失 → WARNING 日志，return（已知风险 A-06 降级处理）
    │
    ├── 3. 提取 deviceSn, productCode
    │
    ├── 4. 遍历 payload.data.items[]
    │      对每个 item，提取 paramName, value
    │
    │      对每个参数：
    │      ├── is_fault_candidate(paramName) ?
    │      │   否 → skip（不是故障相关字段）
    │      │   是 → 继续
    │      │
    │      ├── is_fault_active(paramName, value) ?
    │      │   → True: 故障态（值不为 normal/0）
    │      │   → False: 正常态
    │      │
    │      └── process_fault_state(specific_part, deviceSn, productCode, paramName, value)
    │              调用 ADR-FM-03 状态机处理
    │
    └── 5. 每次 DB 操作前调用 close_old_connections()
```

### 4.2 故障字段识别（is_fault_candidate）

复用 `fault_utils.py` 的判定规则，在 `fault_consumer/fault_classifier.py` 中封装：

```python
from api.fault_utils import FAULT_PARAM_NAMES, _ERROR_N_PATTERN

# 补充 fresh_air_fault_bit_* 位域字段（fault_utils 未处理，v0.6.0 新增支持）
_FRESH_AIR_BIT_PATTERN = re.compile(r'^fresh_air_fault_bit_\d+$')

def is_fault_candidate(param_name: str) -> bool:
    """判断 param_name 是否可能是故障字段（须进一步判断值是否为故障态）"""
    return (
        param_name in FAULT_PARAM_NAMES
        or bool(_ERROR_N_PATTERN.match(param_name))
        or bool(_FRESH_AIR_BIT_PATTERN.match(param_name))
    )
```

**注意**：`fresh_air_fault_status`（位域整体字段，v0.5.3-FCC 用于 popcount 统计）与 `fresh_air_fault_bit_*`（单个位字段，v0.6.0 MQTT 直接上报）的关系：
- 根据 MQTT 抓包分析，上报的是 `fresh_air_fault_bit_4` 等单个位字段，不是 `fresh_air_fault_status` 整体
- `fresh_air_fault_bit_*` 单个非零值 → `fault_type=fresh_air, severity=warning`
- `fresh_air_fault_status` 不在 fault_consumer 的处理范围内（其值由 PLC 拉取路径提供，非 MQTT 上报）

---

## 5. 数据流时序图

```
大屏 MQTT 上报                fault-consumer 进程              MySQL
       │                           │                              │
       │──DeviceStatusUpdate──────>│                              │
       │  (deviceSn=21997,         │                              │
       │   error_82=1)             │                              │
       │                           ├──is_fault_active()──────────>│ (内存判断，无 DB)
       │                           │  → True                     │
       │                           ├──_state_machine 查找 key─────│ (内存查找，无 DB)
       │                           │  → miss (首次)               │
       │                           ├──INSERT fault_event──────────>│
       │                           │  (is_active=True, ...)       │
       │                           ├──_state_machine[key]=State───│ (内存写入)
       │                           │                              │
       │──DeviceStatusUpdate──────>│                              │
       │  (error_82=1, 10s 后)     │                              │
       │                           ├──_state_machine 查找 key─────│ (内存查找，无 DB)
       │                           │  → hit, is_active=True       │
       │                           ├──state.last_seen_at=now()────│ (仅内存更新)
       │                           │  (不写 DB)                   │
       │                           │                              │
       │──DeviceStatusUpdate──────>│                              │
       │  (error_82=0, 故障恢复)   │                              │
       │                           ├──_state_machine 查找 key─────│ (内存查找，无 DB)
       │                           │  → hit, is_active=True       │
       │                           ├──UPDATE fault_event──────────>│
       │                           │  SET is_active=False,        │
       │                           │  recovered_at=now(),         │
       │                           │  last_seen_at=state.lsa      │
       │                           ├──state.is_active=False───────│ (内存更新)
       │                           │                              │
                                                                  │
Web 请求                      freeark-backend                     │
       │                           │                              │
       │──GET /api/devices/────────>│                             │
       │     fault-events/?...     │                              │
       │                           ├──FaultEvent.objects.filter───>│
       │                           │  (.filter().order_by())      │
       │                           │<──QuerySet─────────────────── │
       │<──200 OK (paginated)──────│                              │
```

---

## 6. 安全性设计

| 方面 | 设计 |
|------|------|
| MQTT 连接 | WSS（TLS），broker 凭证存储在 heartbeat_broker_config.json，不硬编码 |
| broker 密码 | 日志中不输出密码（仅记录 host/port/protocol） |
| API 鉴权 | `IsAuthenticated`（与现有接口一致），所有 fault-events 接口要求登录 |
| DB 凭证 | Django settings.py 环境变量，不在本文档中出现 |
| 日志脱敏 | on_message 中若需记录报文内容，截断前 256 字节，不输出完整 payload |

---

## 7. 可靠性设计

| 机制 | 实现 |
|------|------|
| systemd 自动重启 | `Restart=on-failure, RestartSec=30s` |
| MQTT 自动重连 | `loop_forever(retry_first_connection=True)` |
| 进程重启状态恢复 | 启动时从 DB 加载 is_active=True 记录重建状态机（LIMIT 10000） |
| DB 连接复用保护 | 每次 DB 操作前调用 `close_old_connections()` |
| DB unique 约束兜底 | IntegrityError 捕获 → 改为 UPDATE，不崩溃 |
| MAC 映射缺失容错 | WARNING 日志 + skip，不崩溃 |
| 报文解析失败容错 | 捕获所有解析异常，ERROR 日志 + skip，不影响后续报文 |
| 大事务保护（清理服务） | 分批 1000 行删除，批次间 sleep 100ms |

---

## 8. 测试策略

| 测试类型 | 覆盖范围 | 工具 |
|----------|---------|------|
| 单元测试 | `is_fault_candidate()`、`is_fault_active()`、`get_fault_type_severity()` | pytest + SQLite |
| 单元测试 | 状态机转移 T1/T2/T3（直接调用 `process_fault_state`，不依赖 MQTT） | pytest + SQLite |
| 集成测试 | 状态机 + DB 写入（首次出现 INSERT、重复上报无写 DB、恢复 UPDATE） | pytest + Django TestCase + SQLite |
| 集成测试 | REST API 分页过滤（房号、时间段、类型、is_active） | pytest + DRF APIClient + SQLite |
| 集成测试 | 清理服务（fault_cleanup --days 90 --batch-size 1000 --once） | pytest + SQLite |
| 手工验收 | 生产 systemd 服务启动、journald 日志可查、前端页面过滤功能 | 人工执行 |

**测试与生产 DB 隔离**：所有自动化测试使用 SQLite（Django settings.py 中 `USE_SQLITE=True` 模式，已有 dph_cleanup 测试先例），不依赖生产 MySQL @ 192.168.31.98。

---

## 9. 生产部署步骤（概要）

详细部署计划见 DevOps 阶段输出，此处记录架构约束：

1. `git pull`（在生产服务器 192.168.31.51 通过 plink 执行）
2. `python manage.py migrate`（创建 fault_event 表，新表 migration 不影响现有表）
3. `sudo systemctl daemon-reload`
4. `sudo systemctl enable --now freeark-fault-consumer`
5. `sudo systemctl enable --now freeark-fault-cleanup.timer`
6. 验证：`journalctl -u freeark-fault-consumer -n 20`，检查启动日志和 MQTT 连接成功消息

**rollback**：
- 如需回滚，`sudo systemctl stop freeark-fault-consumer && sudo systemctl disable freeark-fault-consumer`
- `sudo systemctl stop freeark-fault-cleanup.timer && sudo systemctl disable freeark-fault-cleanup.timer`
- `git revert` + `python manage.py migrate`（Django 支持 migration 回滚）
- fault_event 表数据可保留或手动 DROP（不影响其他表）

---

## 10. 架构待办（Architecture Backlog）

| 编号 | 标题 | 优先级 | 触发条件 |
|------|------|--------|---------|
| AB-001 | Redis 化状态机 | 低 | 实测内存 > 256 MB 或需要多进程 |
| AB-002 | MQTT 驱动 fault_count_cache 失效 | 低 | 当 60s TTL 延迟不可接受时 |
| AB-004 | 故障码中文描述字典表 | 中 | 业务方提供字典数据后 |
| AB-005 | 故障告警通知 | 中 | 运维需要实时告警时 |
| AB-006 | 故障趋势统计（周/月聚合） | 低 | 有统计分析需求时 |
| AB-007 | MQTT 漏消息 stale active 自动标记 | 中 | R-10 风险实际发生时 |
| AB-008 | broker ACL fallback 逐 MAC 订阅 | 低 | R-08 风险实际发生时（已预留配置开关）|
