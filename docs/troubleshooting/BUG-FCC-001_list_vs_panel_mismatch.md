# BUG-FCC-001 — 设备列表故障数与设备面板可见故障数不一致

| 字段 | 值 |
|---|---|
| Bug ID | BUG-FCC-001 |
| 报告日期 | 2026-05-27 |
| 上线版本 | v0.5.3-FCC（commit `1aff9c7`） |
| 修复版本 | hotfix（commit `0b726c9`） |
| 严重程度 | Medium — 数字错算，无数据损坏，无服务中断 |
| 影响面 | 凡是户型不含 `panel_fourth_children`、`panel_children_room` 等 sub_type 但 PLC 仍占位上报对应 `*_communication_error` 字段的专有部分 |
| 状态 | ✅ 已修复并验证 |

---

## 1. 现象

用户报告 v0.5.3-FCC 上线后：

> "感觉设备列表显示的故障数和设备面板的详细并不一致，比如 `10-1-1601`，列表里边是 2，里边其实是 1。"

进一步交互确认：

> "进水温度传感器故障 这个有。但是这个房间确实没有儿童房，前端没有这个选项卡。这个户型没有儿童房。不存在的房型的这个值不应该计算。"

真实 `specific_part` 推断为 `10-1-16-1601`（用户写法少了一段层号）。

---

## 2. 数据快照（生产 DB）

### 2.1 `10-1-16-1601` 在 `plc_latest_data` 表中的故障字段

通过 `compute_fault_count_for_sections + count_faults_for_row` 拆解：

| param_name | value | 后端故障贡献 | 面板可见 |
|---|---|---|---|
| `fourth_children_room_communication_error` | 1 | +1 | **否**（户型无第四儿童房卡片） |
| `fresh_air_fault_status` | 16 (=0b10000, popcount=1) | +1 | 是（"新风"卡片 → bit 4 "进水温度传感器故障"） |
| **修复前合计** | — | **2** | 1 |

### 2.2 该专有部分的 `available_sub_types`

```python
>>> get_available_sub_types("10-1-16-1601")
frozenset({'air_quality', 'energy_meter', 'fresh_air', 'hydraulic_module',
           'main_thermostat', 'panel_bedroom', 'panel_children_room', 'panel_study_room'})
```

**没有 `panel_fourth_children`**——该户型确实不含第四儿童房。

### 2.3 同楼层其他房间对比

| specific_part | 修复前 | 修复后 | 真实故障明细 |
|---|---|---|---|
| `1-1-16-1601` | 1 | 0 | 仅 `fourth_children_room_communication_error=1`（占位） |
| `5-1-16-1601` | 1 | 0 | 同上 |
| `10-1-16-1601` | 2 | 1 | 同上 + `fresh_air_fault_status=16` |

---

## 3. 根因

### 3.1 两侧逻辑对比

| | 后端 `fault_utils._compute_from_db_batch` | 前端面板 `views.get_device_realtime_params` |
|---|---|---|
| 数据源 | `plc_latest_data` | `plc_latest_data` + `DeviceConfig` |
| sub_type 过滤 | **无** | `get_available_sub_types(sp)` |
| 结果 | 包含户型不存在的房间字段 | 仅显示户型实际存在的 sub_type 卡片 |

后端 `_compute_from_db_batch` 查询 `plc_latest_data` 时只按 `param_name` 过滤（FAULT_PARAM_NAMES + LIKE `error_%`），**没有按 `available_sub_types` 过滤**；前端面板视图按 `get_available_sub_types(specific_part)` 把户型不存在的 sub_type 卡片整张移除（views.py:1638 + 1646–1652）。两侧口径不一致。

### 3.2 PLC 为什么会占位上报"不存在房型"的故障

`plc_latest_data` 是 PLC 设备模板批量上报的——同型号 PLC 会注册所有可能字段（包括"第四儿童房"对应的传感器、面板通讯通道）。在户型实际没有该房间时，对应通讯通道未连接 → PLC 把 `fourth_children_room_communication_error` 置为 `1`（通讯故障）→ 上报到 `plc_latest_data`。

业务侧的"事实"：此字段值 `=1` 不代表"该房间通讯故障"，而是"该房间根本不存在"。需要在应用层屏蔽。

### 3.3 走过的弯路（首版 RCA 误判）

调度 PM 子代理做静态分析时，曾推测两个错误根因：

| 怀疑 | 假设 | 证伪 |
|---|---|---|
| A — `comm_fault_timeout` 字符串/整数类型不匹配 | DB 存整数但代码用 `"normal"` 字符串比较 | 实际 `count_faults_for_row` 只用 `value is None or value == 0` 判断 |
| D — `comm_fault_timeout` 因 DeviceConfig 无条目被面板屏蔽，但后端计入 | DB value=1 时面板隐藏、后端 +1 | 实测 `10-1-16-1601` 的 `comm_fault_timeout` 没有非 0 上报 |

**真正应当先做的事**：SSH 直接 dump 该 specific_part 在 `plc_latest_data` 表的所有故障字段值，而不是基于"代码层面可能性"做静态推断。本次教训记入 §7。

---

## 4. 修复方案

### 4.1 决策矩阵

| 方案 | 描述 | 选择 |
|---|---|---|
| X — 后端口径向面板对齐 | 后端 `_compute_from_db_batch` 加 sub_type 过滤 | ✅ 选用 |
| Y — 面板口径向后端扩展（展示所有字段） | 在 seed_device_config 中为 `comm_fault_timeout`、`error_<N>` 等加 DeviceConfig 条目 + 前端组件适配 | ❌ 改动面大 |
| Z — 统一权威源（前后端共享） | 后端新增 API 把 FAULT_PARAMS 集合暴露给前端 | ❌ 长期规划，本次时间不允许 |

### 4.2 实现细节（commit `0b726c9`）

**`FreeArkWeb/backend/freearkweb/api/fault_utils.py`** 新增两个内部工具：

```python
def _get_param_to_subtypes() -> dict:
    """获取 {param_name: frozenset[sub_type]} 映射，缓存 60s。

    同一 param 可能在多个 sub_type 下激活（DeviceConfig unique_together=param+sub_type）。
    """
    cached = cache.get(_PARAM_SUBTYPE_CACHE_KEY)
    if cached is not None:
        return cached

    from .models import DeviceConfig
    mapping: dict = defaultdict(set)
    for pn, st in DeviceConfig.objects.filter(is_active=True).values_list('param_name', 'sub_type'):
        mapping[pn].add(st)
    result = {k: frozenset(v) for k, v in mapping.items()}
    cache.set(_PARAM_SUBTYPE_CACHE_KEY, result, _PARAM_SUBTYPE_CACHE_TTL)
    return result


def _is_param_visible_for_section(param_name, specific_part, param_to_subtypes):
    """与 views.get_device_realtime_params 口径一致的可见性判定。

    - DeviceConfig 中无条目 → 系统级/PLC 级字段，保留原行为视为可见
    - sub_type 与 available_sub_types 有交集 → 可见
    """
    sub_types_of_param = param_to_subtypes.get(param_name)
    if sub_types_of_param is None:
        return True
    from .utils_room_filter import get_available_sub_types
    available = get_available_sub_types(specific_part)
    return bool(sub_types_of_param & available)
```

`_compute_from_db_batch` 与 `get_fault_details` 在 pivot 阶段调用 `_is_param_visible_for_section`，跳过不可见字段。

### 4.3 关键设计决策

**为什么"DeviceConfig 无条目"保留原行为而非过滤**：

- `comm_fault_timeout`、`error_<N>` 是 PLC 系统级字段，不归属任何房间/sub_type
- 这些字段反映的是 PLC 通信本身或固件故障码，与户型无关
- 如果一刀切按"无 DeviceConfig 即过滤"会丢失 PLC 通信故障告警信号
- 折中：维持现状，未来若需要进一步对齐面板可见性，再走单独流程

**`get_available_sub_types` 复用而非新增**：

- `utils_room_filter.get_available_sub_types` 已有 300s 线程安全缓存
- 直接调用一致性最好，性能开销可忽略

---

## 5. 验证

### 5.1 本地单元测试

新增 `SubTypeFilterTest` 测试类（3 个用例）：

| 测试用例 | 场景 | 期望 |
|---|---|---|
| `test_filter_out_subtype_not_in_available_set` | available = `{fresh_air, panel_bedroom}` | 跳过 fourth_children，结果 = 2 |
| `test_all_subtypes_available_counts_all` | available 含全部 sub_type | 计入全部 = 3 |
| `test_param_without_device_config_still_counts` | `comm_fault_timeout` 无 DeviceConfig | 保留原行为，仍计入 |

完整测试结果：

```
Found 69 test(s).
Ran 69 tests in 18.146s
OK
```

原 66 个用例全部仍通过（hotfix 未破坏既有行为，因测试库默认无 DeviceConfig 条目时所有 param 走"保留原行为"分支）。

### 5.2 生产真实数据验证

部署后 (commit `0b726c9` on Pi)：

```python
>>> compute_fault_count_for_sections(['10-1-16-1601', '1-1-16-1601', '5-1-16-1601'])
{'10-1-16-1601': 1, '1-1-16-1601': 0, '5-1-16-1601': 0}

>>> get_fault_details('10-1-16-1601')
[{'param_name': 'fresh_air_fault_status', 'value': 16}]
```

与用户面板观察一致（"进水温度传感器故障" = bit 4 of 16）。

---

## 6. 副作用与影响

### 6.1 数字变化

修复后，凡是户型不含某些 sub_type 但 PLC 仍占位上报对应 `*_communication_error`（或其他归属字段）的专有部分，故障数都会减少。已观察到的实例：

| specific_part | 楼栋户型 | 修复前 | 修复后 |
|---|---|---|---|
| `1-1-16-1601` | 无 panel_fourth_children | 1 | 0 |
| `5-1-16-1601` | 同上 | 1 | 0 |
| `10-1-16-1601` | 同上 | 2 | 1 |

可能还有数十个相似 section（楼栋 `2`、`6`、`7`、`8`、`9` 的同层房间），具体数量取决于 PLC 配置。

### 6.2 用户感知

- 设备列表"故障数量"列数字普遍下降（正确方向）
- 之前因占位故障变红的列将变绿
- 与设备面板看到的红色故障行数一致

### 6.3 监控/告警

未引入新的监控告警——按 `AskUserQuestion` 中的裁决"这些不存在房型的故障本就不应报，隐藏即可"。

### 6.4 已知遗留事项（不在本次修复范围）

- `comm_fault_timeout` 在 DeviceConfig 中无条目 → 后端计入但面板不显示。若未来发现该字段非 0 数据导致新的不一致，需要单独决策（参考方案 Y）
- `error_<N>` 同上

---

## 7. 经验教训

### 7.1 RCA 路径教训：先实测，再静态分析

PM 子代理的首版 RCA 完全基于静态代码审计，给出两个"高置信度"根因（A 和 D），全部证伪。真正定位根因花了一次 SSH 数据 dump + 用户反馈"户型没儿童房"两条信息。

**下次类似问题应当**：

1. 先 SSH dump 实际数据，看哪些字段贡献了故障
2. 再对照前端代码看面板会展示哪些
3. 差异定位到具体字段后再做静态推断

静态代码审计能列出"可能不一致的点"，但很难告诉你"实际哪个点出了问题"——除非有具体数据样本。

### 7.2 设计教训：前后端"可见性"规则需统一权威源

本次 bug 的根本结构性原因是：前端面板和后端故障数有**两套各自实现的"哪些字段可见"判定逻辑**——

- 前端：`FAULT_PARAMS` set + `FRESH_AIR_FAULT_BITS` 数组 + `available_sub_types` 过滤
- 后端：`FAULT_PARAM_NAMES` set + `_ERROR_N_PATTERN` 正则 + （hotfix 前）无 sub_type 过滤

只要两者实现独立，长期看一定会漂移。

**长期改进方向**（架构 backlog 建议）：

- **AB-003（新提案）**：把"故障字段可见性"的权威源统一到后端 Python，前端通过单一 API（如 `/api/devices/fault-spec/`）拉取，构建时 codegen 或运行时获取
- 优先级：中（每次新增故障字段都要同步两边的痛点）

### 7.3 测试教训：sub_type 过滤场景应纳入测试金字塔

之前的 66 个测试全部基于"测试库 DeviceConfig 为空时的默认行为"——这恰好是 hotfix 不破坏既有测试的原因，但也意味着**真实生产场景下的 sub_type 过滤行为本就在测试盲区**。

本次新增的 `SubTypeFilterTest` 弥补了这一盲点。未来涉及 `available_sub_types` 的功能开发，测试金字塔应当包含：

- 户型存在该 sub_type → 字段计入
- 户型不存在 → 字段不计入
- DeviceConfig 无条目 → 保留原行为

---

## 8. 时间线

| 时间（CST） | 事件 |
|---|---|
| 2026-05-27 15:53 | v0.5.3-FCC 部署到生产 |
| 2026-05-27 ~16:00 | 用户发现列表 vs 面板数字不一致并反馈 |
| 2026-05-27 ~16:10 | PM 子代理首版 RCA（静态分析，误判） |
| 2026-05-27 ~16:25 | SSH 实测 `10-1-16-1601` 数据，定位真凶字段 |
| 2026-05-27 ~16:30 | 用户反馈"户型没儿童房" → 锁定根因 |
| 2026-05-27 ~16:40 | hotfix 代码 + 测试 + 本地 69/69 通过 |
| 2026-05-27 ~16:50 | commit `0b726c9` → push → 生产 git pull + restart |
| 2026-05-27 ~16:55 | 生产真实数据验证通过 |

总响应时间：约 1 小时（报告 → 修复 → 验证）。

---

## 9. 相关链接

- 上线 commit：`1aff9c7 feat(fault-count): 设备列表故障数量列 + OpenClaw 工具 (v0.5.3-FCC)`
- 修复 commit：`0b726c9 fix(fault-count): 按 available_sub_types 过滤户型不存在的故障字段 (BUG-FCC-001)`
- 架构文档：`docs/architecture/architecture_design_v0.5.3_fault_count_column.md`
- 模块设计：`docs/architecture/module_design_v0.5.3_fault_count_column.md`
- 实现计划：`docs/development/v0.5.3_fault_count_column/implementation_plan.md`
- 相关代码：
  - `FreeArkWeb/backend/freearkweb/api/fault_utils.py`
  - `FreeArkWeb/backend/freearkweb/api/utils_room_filter.py`
  - `FreeArkWeb/backend/freearkweb/api/views.py::get_device_realtime_params`
  - `FreeArkWeb/frontend/src/views/DeviceCardsView.vue`
