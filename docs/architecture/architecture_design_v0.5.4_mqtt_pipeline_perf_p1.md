# 架构设计文档 — v0.5.4 MQTT 采集链路性能优化 P1

```
file_header:
  document_id: ARCH-v0.5.4
  title: MQTT 采集链路性能优化 P1 — 架构设计文档
  author_agent: sub_agent_system_architect (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.4
  created_at: 2026-05-21
  status: CONFIRMED
  references:
    - docs/requirements/v0.5.4_mqtt_pipeline_perf_p1/requirements_spec.md
    - docs/requirements/v0.5.4_mqtt_pipeline_perf_p1/user_stories.md
    - docs/troubleshooting/data_collection_pipeline_perf_analysis_2026-05-21.md
    - FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py
    - FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-21 | 初始草稿，ADR-001/002/003/004，含待用户拍板项 |
| 0.2.0-CONFIRMED | 2026-05-21 | 用户确认 OQ-1~OQ-4：ADR-001 定方案 A、ADR-003 定策略 A、ADR-004 定分批部署。本期开发范围仅 P1-1 |

---

## 1. 架构总览

### 1.1 本次变更的架构定性

本次 v0.5.4 是**对既有系统的增量内部优化**，不引入任何新的架构层次、外部服务或数据存储。所有变更限定在两个已有 Python 模块内，通过修改模块级常量和函数内去重逻辑实现：

| 变更文件 | 变更性质 | 变更规模 |
|---------|---------|---------|
| `FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py` | 新增模块级 dict 缓存 + `_write_history()` 内增加 energy 去重分支 | 预计 ~15 行 |
| `FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py` | 修改三个模块级整数常量 | 预计 1-3 行 |

**不引入**：新文件、新 Django 模型、数据库 migration、新 API endpoint、新 systemd 服务、新依赖包。

### 1.2 受影响链路示意

```
[采集端 datacollection]
  ↓ MQTT (每 ≈6 分钟，energy；每 ≈10 分钟，general)
[MQTT Broker (EMQX 192.168.31.98:32788)]
  ↓
[paho 网络线程 — on_message() — 纯入队，零 I/O]
  ↓ put_nowait()
┌─────────────────────────────────────────────┐
│ energy_queue (maxsize=2000) ← P1-2 可调整    │
│ general_queue (maxsize=2000)                │
└─────────────────────────────────────────────┘
  ↓ get()
┌─────────────────────────────────────────────┐
│ energy_workers × NUM_ENERGY_WORKERS (=3)    │  ← P1-2 可调整
│   PLCDataHandler → ConnectionStatusHandler  │
│   → PLCLatestDataHandler                    │
│       ├─ _bulk_upsert() → plc_latest_data   │  （不变）
│       └─ _write_history()                   │  ← P1-1 修改
│           ├─ energy 参数：[新增去重缓存]      │
│           └─ general 参数：[现有去重缓存]     │
│                   ↓ bulk_create()            │
│           device_param_history              │
│                                             │
│ general_workers × NUM_GENERAL_WORKERS (=6)  │  ← P1-2 可调整
│   PLCDataHandler → PLCLatestDataHandler     │
│       └─ _write_history() [现有，不变]       │
└─────────────────────────────────────────────┘
          ↓
   MySQL freeark (192.168.31.98:3306)
   innodb_buffer_pool_size = 2GB (P0 已完成)
```

---

## 2. 架构决策记录（ADR）

### ADR-001：P1-1 去重策略选型 — 推荐"每小时对齐"，与 general 完全对称

**背景**：`_write_history()` 中 energy 参数当前无去重，每 6 分钟全量写入（568 × 2 = 1136 行/批）。需引入时间窗口控制。

**可选方案：**

| 方案 | 描述 | energy 写入频率 | 实现复杂度 | 对历史查询的影响 |
|------|------|----------------|-----------|----------------|
| A — 每小时整点（推荐） | 新建 `_energy_hist_last_hour` dict，与 `_general_hist_last_hour` 完全对称；以 `collected_at` 的小时字符串（`'%Y-%m-%d-%H'`）为 key | 每小时 1 批（1136 行），降 10 倍 | 最低（~10 行代码，逻辑复制） | 保留每小时一条，支持小时粒度趋势查询 |
| B — 每 N 分钟时间桶 | 新建 `_energy_hist_last_bucket` dict；key = `collected_at` floor 到 N 分钟（如 `collected_at - collected_at % timedelta(minutes=N)`） | 每 N 分钟 1 批，如 N=30 降 5 倍 | 中（需 timedelta 运算，处理 None 时间戳边界） | 保留更细粒度，支持 N 分钟粒度趋势 |
| C — 完全不写入 | energy 参数跳过 `device_param_history` 写入（在 `_write_history()` 中对 energy 直接 continue） | 0（降 100%） | 最低 | 历史表中无 energy 记录，查询只能走 plc_data（天粒度） |

**ADR-001 决策（2026-05-21 用户确认）：方案 A**

**理由：**
1. `total_hot_quantity` / `total_cold_quantity` 是累计量，相邻整点时刻的差值即为该小时实际用量。整点小时对齐保留了计算任意小时用量的能力，与 `plc_data` 日聚合语义对齐。
2. 实现与 `_general_hist_last_hour` 完全对称，代码审查成本最低，引入新 bug 的风险最小。
3. 降幅（10 倍）显著，每天 energy 写入量从 ~240 批 × 1136 行 = **27.3 万行** 降至 ~24 批 × 1136 行 = **2.7 万行**，与 general 每小时 4.7 万行量级相当，不再是异常突出的写入源。

**方案 C 的排除理由**：若 `device_param_history` 中 energy 历史被看板的历史趋势图表或报表依赖（OQ-1 有此可能），方案 C 会破坏现有功能；在 OQ-1 得到明确"无依赖"答复前，不应选择方案 C。

**用户确认结论（OQ-1/OQ-2）**：用户答复 energy 历史"小时粒度趋势够用"，确认采用**方案 A**；OQ-2 采用**整点小时对齐**（与 general 一致）。方案 B、方案 C 均不采用。

---

### ADR-002：P1-1 缓存命名与键结构 — 与 general 保持对称

**背景**：新建 energy 去重缓存需确定命名和 key 结构。

**决策**：

```python
# 新增（仿照 _general_hist_last_hour）
_energy_hist_last_hour: dict = {}
# key: (specific_part: str, param_name: str) → hour_key: str ('YYYY-MM-DD-HH')
```

**理由**：
- key 结构 `(specific_part, param_name)` 与 general 完全一致，568 设备 × 2 参数 = 1136 个 key，内存占用极小（约 100KB 以内）。
- 命名规则 `_energy_hist_last_hour` 与 `_general_hist_last_hour` 形成对称，读者一眼即可理解两者关系。
- 模块级 dict 由 Python 进程内的所有 worker 线程共享，无需传参，与现有 general 缓存的访问方式完全一致。

**线程安全说明**（承接 NFR1-1）：
- CPython GIL 保证 `dict.get()` 和 `dict.__setitem__()` 在字节码层面的原子性。
- 最坏情形：两个 energy worker 并发处理同一设备同一参数，均判断"缓存 miss"，各自追加一条记录 → 同一小时多写一条（共 2 条而非 1 条）。
- 这与 general 的现有设计完全一致，业务上可接受（时序历史略有重复，不影响计费）。

---

### ADR-003：P1-2 worker 数量评估框架 — 推荐"先 P1-1，再观察"策略

**背景**：P0 生效后 energy INSERT 性能预计大幅提升，需重新评估 worker 分配。但调整 worker 数量会直接影响 DB 连接数和系统负载，属于需谨慎操作的运维参数。

**推算依据（P0 生效后）**：

| 参数 | 当前值 | P0 后估算 | 说明 |
|------|--------|----------|------|
| energy 到达速率 | ~1.58 条/秒 | ~1.58 条/秒（不变） | 采集端不变 |
| 单条 energy 处理时间 | ≥2s（瓶颈 1 主导）| ~50-200ms（估算，索引驻留内存） | buffer pool 2GB 后消除随机 I/O |
| P1-1 生效后，energy 中实际触发 INSERT 的比例 | 100% | ~1/10（每小时第一条）| P1-1 去重后绝大多数消息不写 device_param_history |
| P1-1 生效后，energy worker 的实际 DB 写入耗时 | 绝大多数有 INSERT | 绝大多数**跳过 INSERT**，仅更新 plc_latest_data + plc_data | 去重使热路径大幅变短 |

**关键推论**：P1-1 实施后，energy worker 的主要耗时**不再是 device_param_history INSERT**，而是：
1. `PLCDataHandler`（写 `plc_data`，每条约 ≤50ms）
2. `ConnectionStatusHandler`（`select_for_update()` 行锁，约 150ms，**不受 P1-1 影响**）
3. `PLCLatestDataHandler._bulk_upsert()`（写 `plc_latest_data`，约 ≤50ms）

P1-1 生效后，单条 energy 消息的处理时间预计约 **200-400ms**（由 `ConnectionStatusHandler` 行锁主导），3 个 worker 的吞吐约 **7.5-15 条/秒**，远超到达速率 1.58 条/秒，积压将自然消解。

**ADR-003 决策（2026-05-21 用户确认）：策略 A — 先部署 P1-1，观察 1-2 天，再评估是否需要 P1-2**

> 用户确认采用策略 A。**P1-2 本期不开发**：P1-2 的需求与设计归档保留，待 P1-1 上线、生产观察 1-2 天后，依据实测的 energy 入库延迟（`created_at - collected_at`）另行决定是否启动及具体策略。

**理由**：
- P1-1 本身有望使 energy 队列积压完全消解（worker 吞吐远超到达速率）。
- 若 P1-1 后积压已消解，P1-2 调整 worker 数量的价值有限，且调整会增加 DB 连接数，对树莓派内存略有压力。
- 若 1-2 天观察后积压仍存在（可通过查询 `created_at - collected_at` 验证），则按 OQ-3 选定的策略执行 P1-2。

**P1-2 备用方案（若 OQ-3 答复要求同步部署）**：

| 策略 | energy workers | general workers | maxsize | 总 DB 连接增量 |
|------|----------------|-----------------|---------|--------------|
| A: 不变（观察） | 3 | 6 | 2000 | 0 |
| B: 小幅增 energy | 5 | 6 | 2000 | +2 |
| C: 重新平衡 | 6 | 4 | 2000 | 0（总数不变） |
| D: 仅扩 maxsize | 3 | 6 | 4000 | 0 |

**架构建议**：若用户选择同步部署 P1-2，推荐策略 C（重新平衡，总 worker 数不变为 9，仅将 2 个 worker 从 general 调配至 energy），理由是树莓派总 DB 连接数不增加，同时改善 energy 吞吐。

---

### ADR-004：P1-1 与 P1-2 是否合并部署

**背景**：两个优化修改不同文件，但都需要重启同一个 `freeark-mqtt-consumer` 服务。

**可选方案：**

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 分批部署（推荐） | 先部署 P1-1（仅改 `mqtt_handlers.py`），观察后再部署 P1-2（仅改 `mqtt_consumer.py`） | 效果归因清晰，可单独回滚 | 需要两次服务重启 |
| 合并部署 | 同一个 commit 包含两个文件的修改，一次重启 | 简单，运维操作少 | 若出现问题难以判断是 P1-1 还是 P1-2 引起 |

**ADR-004 决策（2026-05-21 用户确认）：分批部署（先 P1-1，后视情况 P1-2）**

**用户确认结论（OQ-4）**：用户确认**分批部署**。本期（v0.5.4）仅开发并部署 P1-1（`mqtt_handlers.py`）；P1-2（`mqtt_consumer.py`）待 P1-1 观察期后另行启动，单独 commit、单独部署。

---

## 3. 组件交互（P1-1 生效后）

### 3.1 energy 消息处理流程（P1-1 后）

```
energy worker 收到消息
  → PLCDataHandler.handle()
       写 plc_data（每条都写，不变）
  → ConnectionStatusHandler.handle()
       select_for_update() 更新 plc_connection_status（不变）
  → PLCLatestDataHandler.handle()
       _bulk_upsert()  → 写 plc_latest_data（不变）
       _write_history(records)
         for r in records:
           param_name = r['param_name']
           if param_name not in _ENERGY_PARAM_NAMES:
             # general 分支（不变）
             ...
           else:
             # [P1-1 新增] energy 去重分支
             collected_at = r['collected_at']
             if collected_at is None:
               continue                        # 无时间戳，跳过（与 general 一致）
             hour_key = collected_at.strftime('%Y-%m-%d-%H')
             cache_key = (r['specific_part'], param_name)
             if _energy_hist_last_hour.get(cache_key) == hour_key:
               continue                        # 本小时已有样本，跳过写入
             _energy_hist_last_hour[cache_key] = hour_key
             # 未跳过：追加到 hist_objs（每小时第一次通过）
         bulk_create(hist_objs)  →  device_param_history
```

### 3.2 缓存初始化行为（服务重启后）

```
freeark-mqtt-consumer 重启
  → Python 进程启动，导入 mqtt_handlers 模块
  → _energy_hist_last_hour = {}  （空 dict，无任何缓存）
  → 第一批 energy 消息到达时：
       cache_key miss → 所有 1136 条均通过 → bulk_create 写入 1136 行
  → 后续同小时消息到达时：
       cache_key hit → 全部跳过 → bulk_create 写入 0 行
```

**影响评估**：服务重启后首批写入量与优化前相同（1136 行），此后恢复去重效果。服务重启频率极低（按需），影响可忽略。

---

## 4. 数据流对比

### 4.1 device_param_history 写入量对比

| 数据组 | 优化前（每天）| 优化后（每天）| 降幅 |
|--------|-------------|-------------|------|
| energy | ≈240批 × 1136行 = **27.3万行** | ≈24批 × 1136行 = **2.7万行** | **-90%** |
| general | ≈24批 × ~4.7万行 = **112.8万行** | 不变 | — |
| 合计 | ≈**140万行/天** | ≈**115万行/天** | **-17.6%** |

> 注：general 每批实际行数取决于 596 设备 × 约 80 参数 = 47,680 行，24 批 = 1,144,320 行/天。优化后 energy 贡献降至 ~2.7 万行，总量减少约 24.6 万行/天。

**长期影响**：P1-1 生效后，device_param_history 每月新增量从约 **4200 万行** 降至约 **3450 万行**（已含 P0 清理的 1060 万行基准之上）。

### 4.2 写入链路延迟预测（P0 + P1-1 联合效果）

| 链路 | 调查时基线 | P0 后预测 | P0+P1-1 后预测 |
|------|----------|----------|--------------|
| energy 入库延迟（均值） | 20.5 分钟 | 2-5 分钟（INSERT 加速）| < 1 分钟（队列基本不积压）|
| energy 队列满载率 | ~97% | 降至 50% 以下 | 降至 10% 以下（去重后大多消息不触发慢 INSERT）|

> 注：以上预测值基于性能调查报告的推算，实际效果须部署后实测确认。

---

## 5. 非功能性约束（架构层面）

| 约束 | 实现说明 |
|------|---------|
| 物理机，禁止 Docker | 无新增 systemd 服务，不涉及容器化 |
| 部署方式 | `plink + git pull`，后端代码变更重启 `freeark-mqtt-consumer`；无 migration，无前端发版 |
| 线程安全 | 依赖 CPython GIL，与现有 `_general_hist_last_hour` 安全模型一致 |
| 内存占用 | `_energy_hist_last_hour`：1136 key × (tuple + str) ≈ 100KB 以内，忽略不计 |
| 回滚方案 | `git revert` 对应 commit + `sudo systemctl restart freeark-mqtt-consumer`；回滚后 energy 恢复每 6 分钟全量写入，无数据损失 |
| 测试环境 | SQLite（现有配置），测试可直接断言 `_energy_hist_last_hour` 的状态和 `DeviceParamHistory.objects.count()` 的变化 |

---

## 6. 与既有架构的关系

本次变更完全在 `mqtt_handlers.py` 和 `mqtt_consumer.py` 两个模块的内部实现层面，不改变任何：
- API endpoint（无新增、无变更）
- 数据库 Schema（无新增表/列/索引，无 migration）
- systemd 服务配置（无新增服务，仅需重启已有 `freeark-mqtt-consumer`）
- 前端代码（无任何变更）
- MQTT 消息格式（无变更）

本次是对现有 `_general_hist_last_hour` 模式的**标准复制与应用**，架构上无引入新模式。
