# 模块设计文档 — v0.5.4 MQTT 采集链路性能优化 P1

```
file_header:
  document_id: MOD-v0.5.4
  title: MQTT 采集链路性能优化 P1 — 模块设计文档
  author_agent: sub_agent_system_architect (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.4
  created_at: 2026-05-21
  status: CONFIRMED
  references:
    - docs/architecture/architecture_design_v0.5.4_mqtt_pipeline_perf_p1.md
    - docs/requirements/v0.5.4_mqtt_pipeline_perf_p1/requirements_spec.md
    - FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py
    - FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-21 | 初始草稿，基于 ADR-001/002/003/004 |
| 0.2.0-CONFIRMED | 2026-05-21 | 用户确认：P1-1 锁定方案 A（§1.3 为最终实现）；模块二 P1-2 随策略 A 归档延后，不进入本期开发 |

---

## 1. 模块一：`mqtt_handlers.py`（P1-1）

### 1.1 变更范围

**文件**：`FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py`

**受影响区域**：
1. 模块级常量区（约第 600-607 行）：新增 `_energy_hist_last_hour` 缓存
2. `PLCLatestDataHandler._write_history()` 方法（约第 751-786 行）：新增 energy 去重分支

**不受影响区域**（明确保持不变）：
- `_ENERGY_PARAM_NAMES`（常量，保持不变）
- `_general_hist_last_hour`（general 去重缓存，保持不变）
- `_write_history()` 中 general 参数的处理分支（保持不变）
- `_bulk_upsert()` 方法（保持不变）
- `PLCDataHandler`、`ConnectionStatusHandler` 类（保持不变）

### 1.2 新增常量：`_energy_hist_last_hour`

**位置**：在 `_general_hist_last_hour` 定义之后，`_TIMESTAMP_FORMATS` 之前。

**设计意图**：与 `_general_hist_last_hour` 完全对称，仅用于 energy 参数的按小时去重。

```python
# [P1-1 新增] Energy 参数历史去重缓存：每小时写入第一条，与 general 去重策略对齐。
# key: (specific_part: str, param_name: str) → hour_key: str ('YYYY-MM-DD-HH')
# 线程安全：依赖 CPython GIL 保证单次 dict get/set 的原子性；
#           极端情况（多 worker 并发写同一 key）同一小时最多多写一条，可接受。
# 内存占用：≈ 568 设备 × 2 参数 = 1136 key，约 100KB 以内，忽略不计。
_energy_hist_last_hour: dict = {}

# [P1-1 新增] energy 历史写入的时间窗口粒度：整点小时（与 general 一致）。
# 如需改为 N 分钟粒度（方案 B），修改此常量并更新 _write_history 逻辑。
_ENERGY_HIST_GRANULARITY = 'hour'  # 当前仅支持 'hour'，预留扩展点
```

> **注意**：`_ENERGY_HIST_GRANULARITY` 为预留扩展点，当前实现仅支持 `'hour'`（整点对齐），如 OQ-2 答复要求 N 分钟粒度，可在此处修改常量并在 `_write_history()` 中增加对应 floor 逻辑，而无需大幅重构。

### 1.3 修改方法：`PLCLatestDataHandler._write_history()`

**修改前（现状）**：

```python
def _write_history(self, records):
    hist_objs = []
    for r in records:
        param_name = r['param_name']
        collected_at = r['collected_at']

        if param_name not in _ENERGY_PARAM_NAMES:
            # General 参数：无时间戳则跳过；否则按小时去重
            if collected_at is None:
                continue
            hour_key = collected_at.strftime('%Y-%m-%d-%H')
            cache_key = (r['specific_part'], param_name)
            if _general_hist_last_hour.get(cache_key) == hour_key:
                continue
            _general_hist_last_hour[cache_key] = hour_key

        hist_objs.append(DeviceParamHistory(...))
    ...
```

**修改后（P1-1 方案 A）**：

```python
def _write_history(self, records):
    """追加写入 DeviceParamHistory（时序历史，append-only）。

    - Energy 参数（total_hot/cold_quantity）：[P1-1] 每小时写入第一条，通过
      模块级内存缓存 _energy_hist_last_hour 去重（6 分钟采集，写入降约 10 倍）。
    - General 参数：每小时写入第一条，通过 _general_hist_last_hour 去重（不变）。
    """
    hist_objs = []
    for r in records:
        param_name = r['param_name']
        collected_at = r['collected_at']

        if param_name not in _ENERGY_PARAM_NAMES:
            # General 参数：无时间戳则跳过；否则按小时去重（逻辑不变）
            if collected_at is None:
                continue
            hour_key = collected_at.strftime('%Y-%m-%d-%H')
            cache_key = (r['specific_part'], param_name)
            if _general_hist_last_hour.get(cache_key) == hour_key:
                continue
            _general_hist_last_hour[cache_key] = hour_key
        else:
            # [P1-1 新增] Energy 参数：无时间戳则跳过；否则按小时去重
            if collected_at is None:
                continue
            hour_key = collected_at.strftime('%Y-%m-%d-%H')
            cache_key = (r['specific_part'], param_name)
            if _energy_hist_last_hour.get(cache_key) == hour_key:
                continue  # 本小时已有样本，跳过
            _energy_hist_last_hour[cache_key] = hour_key

        hist_objs.append(DeviceParamHistory(
            specific_part=r['specific_part'],
            param_name=param_name,
            value=str(r['value']) if r['value'] is not None else None,
            collected_at=collected_at,
        ))

    if not hist_objs:
        logger.debug("PLCLatestDataHandler: 历史写入跳过（energy/general 均已在本小时记录）")
        return
    try:
        DeviceParamHistory.objects.bulk_create(hist_objs)
        logger.debug(f"PLCLatestDataHandler: 历史追加 {len(hist_objs)} 条")
    except Exception as e:
        logger.error(f"PLCLatestDataHandler: 历史写入失败: {e}", exc_info=True)
```

### 1.4 方案 B（未选用 —— 仅存档，本期不实现）

> 用户已确认 OQ-1 = 方案 A，本节方案 B 不实现，仅作为历史粒度变更的备用参考存档。

若 OQ-2 答复选择"N 分钟时间桶"方案，`_write_history()` 中 energy 分支的 key 生成逻辑修改为：

```python
# 方案 B：N 分钟时间桶对齐（N 由 _ENERGY_HIST_MINUTES 常量控制）
_ENERGY_HIST_MINUTES = 30  # 例：每 30 分钟保留一条

# 在 _write_history() energy 分支中：
from datetime import timedelta
bucket = collected_at.replace(
    minute=(collected_at.minute // _ENERGY_HIST_MINUTES) * _ENERGY_HIST_MINUTES,
    second=0, microsecond=0
)
bucket_key = bucket.strftime('%Y-%m-%d-%H-%M')
cache_key = (r['specific_part'], param_name)
if _energy_hist_last_hour.get(cache_key) == bucket_key:
    continue
_energy_hist_last_hour[cache_key] = bucket_key
```

> 默认实现方案 A（整点小时），仅在用户通过 OQ-2 明确选择方案 B 后切换。

### 1.5 变更影响矩阵

| 调用路径 | 变更影响 | 说明 |
|---------|---------|------|
| `PLCLatestDataHandler.handle()` | 无变更 | 不修改调用方式 |
| `_bulk_upsert()` | 无变更 | energy 每条消息仍全量 upsert `plc_latest_data` |
| `PLCDataHandler.handle()` | 无变更 | energy 每条消息仍写 `plc_data`（日聚合） |
| `ConnectionStatusHandler.handle()` | 无变更 | 行锁路径不受 P1-1 影响 |
| `DeviceParamHistory.objects.bulk_create()` | 调用频率降低 | energy 从每 6 分钟调用 → 每小时调用（方案 A），调用时传入的记录数不变 |

---

## 2. 模块二：`mqtt_consumer.py`（P1-2）

> **⚠ 本模块（P1-2）本期不开发** —— OQ-3 用户决策为策略 A（先观察）。本节设计归档保留，待 P1-1 上线、生产观察 1-2 天后依据实测数据另行启动。本期（v0.5.4）开发仅涉及模块一（`mqtt_handlers.py`，P1-1）。

### 2.1 变更范围

**文件**：`FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py`

**受影响区域**：模块顶部常量（第 46-57 行），修改三个整数值。

**不受影响区域**：
- `_ENERGY_PAYLOAD_MAX_SIZE = 2000`（路由阈值，保持不变）
- `_CLOSE_CONN_EVERY_N = 50`（连接维护参数，保持不变）
- `MQTTConsumer` 类的所有方法（保持不变）
- `_worker_loop()`、`_dispatch()`、`on_message()` 等（保持不变）

### 2.2 常量修改（方案待 OQ-3 用户答复确定）

**当前值（基线）**：

```python
NUM_ENERGY_WORKERS = 3
NUM_GENERAL_WORKERS = 6
# queue_maxsize = 2000  （在 MQTTConsumer.__init__ 默认参数中）
```

**P1-2 各策略的修改值**：

| 策略 | NUM_ENERGY_WORKERS | NUM_GENERAL_WORKERS | queue_maxsize | 备注 |
|------|--------------------|---------------------|---------------|------|
| A: 不变（观察）| 3 | 6 | 2000 | 等待 P1-1 效果验证 |
| B: 小幅增 energy | 5 | 6 | 2000 | 总 worker +2，DB 连接 +2 |
| C: 重新平衡（推荐）| 6 | 4 | 2000 | 总 worker 数不变（9→9），DB 连接不增 |
| D: 仅扩 maxsize | 3 | 6 | 4000 | 扩大缓冲，减少丢消息风险 |

**[待 OQ-3 答复]** 架构师推荐：若同步部署 P1-2，选策略 C（重新平衡），代码改动为：

```python
NUM_ENERGY_WORKERS = 6   # 由 3 → 6
NUM_GENERAL_WORKERS = 4  # 由 6 → 4
# queue_maxsize 保持 2000，不变
```

### 2.3 MQTTConsumer 类的初始化路径（不变）

```python
class MQTTConsumer:
    def __init__(self, num_energy_workers=NUM_ENERGY_WORKERS,
                 num_general_workers=NUM_GENERAL_WORKERS,
                 queue_maxsize=2000):
        ...
        self._energy_queue = queue.Queue(maxsize=queue_maxsize)
        self._general_queue = queue.Queue(maxsize=queue_maxsize)
        self._num_energy_workers = num_energy_workers
        self._num_general_workers = num_general_workers
```

P1-2 仅修改模块级常量，`__init__` 方法及以下实现代码**全部不变**。常量修改后，`manage.py mqtt_consumer_service` 重启时自动生效（传入新的默认值）。

### 2.4 服务重启影响

| 重启阶段 | 影响 |
|---------|------|
| 重启前 | 两个队列中未处理的消息将丢失（与 P0 前的现有行为一致，队列不做持久化） |
| 重启中（约 1-3 秒）| MQTT 消息由 broker 按 QoS=1 保留，重连后补发未确认消息 |
| 重启后 | 以新的 worker 数量和 maxsize 启动，旧缓存（`_energy_hist_last_hour` 等）清空，首批消息全量写入 |

---

## 3. 测试要点（供测试工程师参考）

### 3.1 P1-1 单元测试关键用例

| 用例 | 测试方法 | 预期结果 |
|------|---------|---------|
| energy 去重：同小时同设备第二次调用 `_write_history` | 模拟两批记录，`collected_at` 同一小时 | `DeviceParamHistory.objects.count()` 第二次不增加（SQLite 测试库） |
| energy 去重：跨小时边界后首条写入 | 模拟 `collected_at` 跨越整点 | 第二小时首条正常写入 |
| energy 去重不影响 general | 混合 energy + general 记录 | general 仍按每小时去重写入，energy 按每小时去重写入 |
| `_energy_hist_last_hour` 初始为空时全量写入 | 清空缓存后调用 | 1136 条全量写入（或按测试数据比例） |
| `plc_latest_data` 不受影响 | 调用后验证 PLCLatestData 记录 | `_bulk_upsert()` 正常执行，每条记录均 upsert |

### 3.2 P1-2 集成验证

P1-2 无逻辑变更，主要验证：
- 服务以正确的 worker 数量启动（查日志"Worker 线程启动"条数）
- 队列初始化正常（无异常日志）

---

## 4. 部署步骤（概要，供 devops 参考）

### 4.1 P1-1 部署

```bash
# 1. 生产服务器拉取代码
plink yangyang@192.168.31.51 -pw <password> "cd /home/yangyang/Freeark/FreeArk && git pull"

# 2. 重启 MQTT 消费服务
plink yangyang@192.168.31.51 -pw <password> "sudo systemctl restart freeark-mqtt-consumer"

# 3. 验证服务状态
plink yangyang@192.168.31.51 -pw <password> "sudo systemctl status freeark-mqtt-consumer"

# 4. 验证效果（1小时后查询，替换 <specific_part> 为任意设备ID）
# 在生产 MySQL 执行：
# SELECT collected_at FROM device_param_history
# WHERE param_name = 'total_hot_quantity'
#   AND specific_part = '<specific_part>'
# ORDER BY collected_at DESC LIMIT 10;
# 预期：相邻两条间隔 ≥ 1小时
```

### 4.2 P1-2 部署（若 OQ-3 答复要求）

```bash
# P1-2 与 P1-1 的部署步骤相同（git pull + systemctl restart）
# 修改的是不同文件（mqtt_consumer.py），可单独 commit 和部署
```

### 4.3 回滚

```bash
# 定位到 P1-1 的前一个 commit hash
git log --oneline -5

# 回滚（在生产执行）
plink yangyang@192.168.31.51 -pw <password> \
  "cd /home/yangyang/Freeark/FreeArk && git revert <commit_hash> --no-edit && git push"
# 或：PM 在本地 revert 后 push，生产 git pull 拉取

plink yangyang@192.168.31.51 -pw <password> "sudo systemctl restart freeark-mqtt-consumer"
```

**回滚后数据影响**：回滚后 energy 恢复每 6 分钟全量写入；`_energy_hist_last_hour` 缓存随进程重启清空；`device_param_history` 中已写入的优化后历史记录保留（不删除），无数据损失。
