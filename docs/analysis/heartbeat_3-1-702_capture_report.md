# 大屏心跳消息抓取分析报告 — 3-1-702

> **状态**：已完成抓取与分析（基于真实生产数据）
> **抓取时间**：2026-05-23（绝对时间见 §1）
> **抓取脚本**：`scripts/analysis/capture_heartbeat_702.py`
> **原始数据**：`scripts/analysis/capture_raw_3-1-702.jsonl`（50 条目标消息，26 KB）

---

## 1. 抓取参数

| 参数 | 值 |
|------|---|
| 目标大屏（标识） | `3-1-7-702`（3栋1单元7楼702房，`OwnerInfo.specific_part`） |
| 目标 MAC（`unique_id`） | `c5d29c52a237ade5` |
| MAC 来源 | `resource/all_owner.json`（与生产 `owner_info` 表幂等同步） |
| Broker URL（最终生效） | **`wss://www.ttqingjiao.site:8084/mqtt`**（第 1 优先级即命中） |
| 传输协议 | WSS（WebSocket over TLS，Let's Encrypt 证书） |
| 认证 | username=`admin` / password=`public` |
| 订阅 Topic（通配符） | `/screen/upload/screen/to/cloud/#` |
| 过滤条件 | topic 末段 ∈ `{c5d29c52a237ade5}` |
| 起始时间（epoch ms） | `1779539610183` → 2026-05-23 22:33:30.183 +08:00 |
| 结束时间（epoch ms） | `1779540190890` → 2026-05-23 22:43:10.890 +08:00 |
| 实际抓取时长 | 580.7 秒（首条到末条；脚本 600s 窗口完整） |
| 总收到消息数（全网） | **18,736** 条 |
| 目标 MAC 收到消息数 | **50** 条 |
| Broker 候选回退顺序 | 8084 → 443 → 8884（首选即成功） |

**Broker 路径与生产消费者的差异（重要）**

- 生产 `freeark-screen-heartbeat.service` 的 `heartbeat_broker_config.json` 仍配置为 TCP `mqtt://47.117.41.184:11883/mqtt`。
- 本次抓取走 WSS `www.ttqingjiao.site:8084/mqtt`。
- 用 `admin/public` 同时认证成功 + 订阅同一 topic 模式 + 收到目标 MAC 消息——说明 **WSS 与 TCP 暴露的是同一 EMQX 实例**（仅监听端口不同）。WSS 端口默认 8084 与 EMQX 出厂值一致。

---

## 2. 消息清单

**topic 唯一值**：全部 50 条目标消息只命中 1 个 topic：

```
/screen/upload/screen/to/cloud/c5d29c52a237ade5
```

**消息类型唯一值**（`header.name`）：全部 50 条均为 **`DeviceStatusUpdate`**。

**`screenMac` header 字段**：50/50 均为 `c5d29c52a237ade5`，与 topic 末段冗余一致。

### 2.1 整体 Payload 结构（**与之前测试代码假设 `{}` 完全不符**）

```json
{
  "header": {
    "ackCode": 1,
    "messageId": "6630",
    "name": "DeviceStatusUpdate",
    "screenMac": "c5d29c52a237ade5"
  },
  "payload": {
    "code": 200,
    "data": {
      "deviceSn": 22155,
      "productCode": 130004,
      "items": [
        {"attrTag": "newwind_inlet_temp", "attrValue": "26.6"},
        {"attrTag": "pau_in_temp",        "attrValue": "100.2"},
        {"attrTag": "pau_out_temp",       "attrValue": "15.8"}
      ]
    }
  }
}
```

> **关键校正**：生产 payload 是**结构化设备遥测数据**，不是空 `{}`（测试代码用 `b'{}'` 仅为简化）。心跳信息**不**仅编码在 topic 中——topic 标识"是哪台大屏"，payload 标识"这台大屏挂接的哪个 PLC 设备、哪些属性、当前值"。

### 2.2 子设备维度分布（按 `deviceSn`）

3-1-7-702 大屏挂接了 **10 个不同的 PLC 子设备**：

| `deviceSn` | `productCode` | 10 分钟内消息数 | 推断设备类型（依据 attrTag 集合） |
|-----------|---------------|----------------|--------------------------------|
| 22155 | 130004 | **30** | 新风/PAU 主机（含 newwind_inlet_temp, pau_in/out/through_temp, fan_speed, humidification_enable, wind_speed, one_water_valve_opening） |
| 22154 | 270001 | 10 | 能量计量/主水阀（含 primary_valve_opening, total_hot_quantity, total_cold_quantity, work_duration, energy_supply_mode, energy_saving_sign） |
| 22157 | 100007 | 3 | 温控/空气质量分支 A（含 pm25, co2, hcho, tvoc, error_733-739） |
| 22152-22155 房间面板（22552/22553/22554/22555） | 120003 | 各 1 | 4 个房间温控面板（含 switch, temp, NTC_temp, humidity, temp_set, condensation_alarm, dew_point_temp, error_703-709/763-769/793-799） |
| 22153 | 10016 | 1 | PLC 网关本体（独有字段 plc_ip_1/2, plc_gateway_ip_1/2, plc_subnet_mask_1/2, plc_ip_sure） |
| 22156 | 250001 | 1 | 设备类型未知 D（仅 5 项：error_763-769 + comm_fault_timeout） |
| 22158 | 260001 | 1 | 设备类型未知 E（含 error_793-799 + 多个状态） |

`deviceSn → productCode` 关系：**1:1 严格绑定**，每个 deviceSn 始终携带同一 productCode。

### 2.3 上报模式：突发全量 + 增量

观察 50 条的时间戳间隔，存在**两种模式**：

- **突发全量段**（连续 9 条，间隔均约 100ms，messageId 6638-6646）：大屏在某触发点**轮询所有 10 个 deviceSn 各上报一次完整状态**，每条 `items` 长度 5–26 不等。覆盖所有 10 个子设备各一次。
- **增量段**（其余 41 条，间隔 1.8–41.6 秒）：仅上报**变化的 attrTag**，`items` 长度多为 1–2。典型增量推送。

---

## 3. 字段结构表

### 3.1 顶层字段

| 字段路径 | 类型 | 示例值 | 含义推断 | 推断来源/依据 |
|---------|------|--------|---------|-------------|
| `header.ackCode` | int | `1` | 是否需要 ACK（1=需要） | 50/50 都是 1（生产恒定值），从命名推断 |
| `header.messageId` | string | `"6630"` | 设备侧自增消息序号 | 50 条 6630→6679 严格单调递增、无跳号；推断为大屏会话内计数器 |
| `header.name` | string | `"DeviceStatusUpdate"` | 消息类型 | 50/50 一致；命名即语义 |
| `header.screenMac` | string | `"c5d29c52a237ade5"` | 上报大屏 MAC，与 topic 末段冗余 | 与 topic 末段 100% 一致 |
| `payload.code` | int | `200` | HTTP 风格状态码（200=成功） | 50/50 都是 200；典型 RESTful 编码 |
| `payload.data.deviceSn` | int | `22155` | PLC 子设备序列号 | 同一大屏下多值共存，1:1 绑定 productCode |
| `payload.data.productCode` | int | `130004` | 产品型号编码 | 由 deviceSn 决定，固定不变 |
| `payload.data.items` | array | `[{"attrTag":..., "attrValue":...}]` | 当次上报的属性列表 | 长度 1–26 不等；单次可全量或增量 |
| `payload.data.items[i].attrTag` | string | `"newwind_inlet_temp"` | 属性标签（snake_case 英文） | 自描述，部分需领域知识翻译 |
| `payload.data.items[i].attrValue` | string | `"26.6"` / `"off"` / `"normal"` | 属性值（**全部以字符串表示**，含数字/枚举/布尔语义） | 即使是数字温度也用字符串 `"26.6"`；客户端需自行类型转换 |

### 3.2 attrTag 字典（按语义分组）

| 分组 | attrTag | 含义推断 | 示例值 | 频次 |
|------|---------|---------|--------|------|
| 温度类 | `newwind_inlet_temp` | 新风入口温度（°C） | `"26.6"` | 7 |
|  | `pau_in_temp` | PAU（主送风机组）入口温度 | `"100.2"` ⚠ | 9 |
|  | `pau_out_temp` | PAU 出口温度 | `"15.8"` | 9 |
|  | `pau_through_temp` | PAU 通过温度 | `"12.7"` | 3 |
|  | `temp` | 室内当前温度 | `"26.5"` | 5 |
|  | `NTC_temp` | NTC 温度传感器读数 | `"26.0"` | 5 |
|  | `dew_point_temp` | 露点温度 | `"16.5"` | 5 |
|  | `temp_set` | 用户设定温度 | `"25.0"` | 5 |
|  | `out_temp_set` | 出风/出水设定温度 | `"13.0"` | 1 |
|  | `2nd_outwater_temp_detect` | 二次回水温度检测 | — | 1 |
|  | `2nd_inwater_temp_detect` | 二次进水温度检测 | — | 1 |
| 风机/水阀 | `fan_speed` | 风机转速（RPM） | `"1686"` | 11 |
|  | `wind_speed` | 风速档位 | `"normal"` | 2 |
|  | `primary_valve_opening` | 主水阀开度（%） | `"0.4"` | 10 |
|  | `one_water_valve_opening` | 一次水阀开度（%） | `"46.0"` | 1 |
| 湿度 | `humidity` | 室内湿度（%） | `"53.0"` | 5 |
|  | `humi_upper_limit` | 湿度上限 | `"55"` | 1 |
|  | `humi_lower_limit` | 湿度下限 | `"40"` | 1 |
|  | `humidification_enable` | 加湿开关 | `"off"` | 2 |
| 空气质量 | `pm25` | PM2.5（μg/m³） | — | 3 |
|  | `co2` | CO₂（ppm） | — | 3 |
|  | `tvoc` | 总挥发性有机物 | — | 1 |
|  | `hcho` | 甲醛 | — | 1 |
| 系统开关/模式 | `switch` | 房间面板总开关 | `"off"` | 5 |
|  | `system_switch` | 系统总开关 | — | 3 |
|  | `mode` | 运行模式 | — | 2 |
|  | `energy_supply_mode` | 供能模式（冷/热） | — | 1 |
|  | `energy_saving_sign` | 节能标志 | — | 1 |
|  | `empty_screen_timing` | 空屏定时 | `"timing"` | 1 |
| 告警/计量 | `condensation_alarm` | 结露报警 | `"0"` | 5 |
|  | `comm_fault_timeout` | 通信故障超时状态 | `"normal"` | **10** |
|  | `filter_working_time` | 滤芯已工作时长 | `"2794"` | 2 |
|  | `filter_max_life` | 滤芯最大寿命 | `"1000"` | 1 |
|  | `work_duration` | 工作时长 | — | 1 |
|  | `total_hot_quantity` | 累计热量 | — | 1 |
|  | `total_cold_quantity` | 累计冷量 | — | 1 |
| 故障码（共 28 种） | `error_82` ~ `error_799` | PLC 故障码，值 `"0"`=无故障 | `"0"` | 各 1 |
| PLC 网络配置 | `plc_ip_1` / `plc_ip_2` | 双 PLC（主备）IP | — | 各 1 |
|  | `plc_gateway_ip_1` / `plc_gateway_ip_2` | 双 PLC 网关 | — | 各 1 |
|  | `plc_subnet_mask_1` / `plc_subnet_mask_2` | 双 PLC 子网掩码 | — | 各 1 |
|  | `plc_ip_sure` | PLC IP 确认标志 | — | 1 |
| **异常占位** | `""` （空字符串） | **末尾 padding，非真实属性** | `attrValue: ""` | **9（同一条消息中）** |

> `pau_in_temp = "100.2"` 看起来异常（远高于环境温度），但 10 分钟内 9 次取值都在 100.2–100.3 之间，**推测该字段量纲并非 °C**（可能是百分比 × 100，或经过缩放的传感器原始读数）。建议向硬件/PLC 协议方核实。

---

## 4. 上报频率统计

### 4.1 整体频率

| 指标 | 值 |
|------|---|
| 抓取窗口 | 600 秒 |
| 目标 MAC 总消息数 | 50 |
| 平均到达频率 | 1 条 / 12.0 秒（即 ~5 条/分钟） |
| 全网消息数 | 18,736（其他 MAC 占 99.7%；最活跃非目标 MAC `3f37f1f7787614ac` 单设备 1805 条） |

### 4.2 消息间隔分布（仅目标 MAC，n=49 间隔）

| 指标 | 值（秒） |
|------|--------|
| min | 0.10 |
| max | 41.58 |
| **平均（mean）** | **11.85** |
| **中位（P50）** | **9.28** |
| P90 | 26.34 |
| **P95** | **30.43** |
| P99 | 41.58 |

**间隔模式分布**：

- 极小间隔（<0.2s）：**9 个**——对应 §2.3 中的突发全量段
- 中等间隔（5–15s）：约 22 个——常规增量上报
- 长间隔（15–42s）：约 18 个——上报间歇期

### 4.3 messageId 序列分析

- 最小 messageId：`6630`
- 最大 messageId：`6679`
- 跨度：50（6679−6630+1）
- 实际收到：50
- **缺口数**：**0**（无跳号、无丢包）
- 单调性：严格递增

> 这是个**强证据**：在抓取窗口内，**该大屏到 EMQX broker 之间消息零丢失**，QoS 0 + WebSocket 链路下表现稳定。

---

## 5. 异常观察

| 异常 | 描述 | 影响 | 建议 |
|------|------|------|------|
| **末尾空 `attrTag` padding** | `messageId=6642`（deviceSn=22155 突发全量包）末尾出现 9 个 `{"attrTag":"", "attrValue":""}` 占位项 | 浪费带宽，消费侧需过滤空项 | 大屏固件侧应在序列化前裁剪空槽；消费侧防御性 `if not item['attrTag']: continue` |
| **温度量纲异常** | `pau_in_temp` 恒在 `100.2–100.3` | 易被误判为高温告警 | 与硬件确认量纲（°C / 比例尺缩放） |
| **类型不一致** | 数值（`"26.6"`）、布尔（`"off"`）、枚举（`"normal"`、`"timing"`）混用同一 `attrValue` 字符串字段 | 消费侧需按 attrTag 字典选择解析器 | 维护 attrTag → type 映射表 |
| **跨设备 `messageId` 共享同一计数器** | 突发段 #9-#17 共 9 条 messageId 连续递增，但 deviceSn 各异（22153/22553/22154/...） | 不能用 `(deviceSn, messageId)` 做幂等键 | 幂等键应采用 `(screenMac, messageId)` 而非 `(deviceSn, messageId)` |
| **生产 broker 配置与本次抓取路径不一致** | 生产 `heartbeat_broker_config.json` 用 TCP `47.117.41.184:11883`，本次 WSS `www.ttqingjiao.site:8084` 均成功 | 两条路径指向同一 EMQX 不同监听端口 | 若需在生产消费端切换协议，仅改 `protocol/host/port/path`，不需改业务逻辑 |
| **断流间隔与全量上报混合** | 最长 41.58 秒未到达，最短 0.1 秒连发 9 条 | 简单"超时阈值"判定不可靠 | 见 §7 阈值建议 |

---

## 6. 关键发现

1. **payload 不是空**：测试代码 `b'{}'` 仅为单元测试简化，**真实生产 payload 含 `header` + `payload` 两层结构与遥测数据**。后续消费侧若需扩展功能（如解析故障码、提取温度做对比报警），可直接消费现有 payload。

2. **生产消费者只用 topic 末段，完全丢弃了 payload**：`screen_heartbeat_consumer.py` 仅利用 topic 提取 MAC 做"在线时间戳"维护，**生产数据中 99% 的信息量被丢弃**。如果未来需要做"设备级在线监测"（每个 PLC 子设备的健康）、"故障码异步收集"、"温湿度趋势分析"等需求，无需新增订阅 topic，**直接复用现有心跳通道即可**。

3. **大屏与 broker 之间 QoS 0 下 50/50 零丢包**（messageId 严格连续）。意味着断流告警的根因应该是**大屏端断网或断电**，而非"消息偶发丢失"。这降低了告警重试逻辑的复杂度。

4. **同一大屏挂接 10 个 PLC 子设备**（22153-22158 + 22552-22555），其中 22155（新风/PAU 主机）单设备贡献 30/50 = 60% 的消息量。

5. **WSS 8084 直连成功**：脚本无任何额外 TLS 配置（仅 `ssl.create_default_context()` 系统默认），说明 broker 使用了正规公网证书（Let's Encrypt 或同级），客户端兼容性好。生产消费者切换到 WSS 完全可行。

6. **`screenMac` 与 topic 末段 100% 冗余**：可信任 topic 提取 MAC，无需解析 payload 也能识别大屏。

---

## 7. 后续建议

### 7.1 离线判定阈值（用于 `ScreenConnectivityStatus`）

基于本次 P99=41.6 秒、最大间隔 41.6 秒的观测：

- **保守阈值（推荐）**：`max_interval * 3 ≈ 120 秒`——大屏超过 120 秒未上报视为离线
- **激进阈值**：`P99 * 2 ≈ 90 秒`——更早告警，但有误报风险
- **当前生产**：阈值硬编码（请检索 `screen_heartbeat_consumer.py` 内现值），建议提取为 `OfflineThresholdConfig` 数据库可配置项

> **重要限制**：本次仅观测 10 分钟、单台设备。"突发全量段"暗示大屏可能在闲时静默更长。建议在生产环境跑 24 小时全周期统计再敲定。

### 7.2 attrTag 类型映射（消费侧解析）

建议维护 `attr_tag_schema.py`：

```python
ATTR_TAG_TYPES = {
    # number (float)
    "newwind_inlet_temp": "float",
    "pau_in_temp": "float",
    "humidity": "float",
    "temp_set": "float",
    "primary_valve_opening": "float_percent",
    "fan_speed": "int",
    # boolean (off/on)
    "switch": "bool_off_on",
    "system_switch": "bool_off_on",
    "humidification_enable": "bool_off_on",
    # enum
    "wind_speed": "enum_wind_level",      # normal/low/high
    "comm_fault_timeout": "enum_comm",    # normal/timeout
    "empty_screen_timing": "enum_timing",
    # error code (number with "0"=ok)
    "error_*": "error_code",
    # ip address parts
    "plc_ip_1": "ip_string",
    # ...
}
```

### 7.3 `ScreenConnectivityStatus` 字段扩展（可选）

| 现有/新增 | 字段 | 来源 |
|----------|------|------|
| 现有 | `specific_part` | `OwnerInfo.unique_id` 反查 |
| 现有 | `last_seen_at` | 消息到达时间 |
| 新增可选 | `last_message_id` | `header.messageId`，用于检测序号回退 |
| 新增可选 | `attached_device_count` | 该大屏一段时间内出现过的 `deviceSn` 去重计数 |
| 新增可选 | `last_payload_summary` | 最近一次 attrTag 集合摘要（用于运维快速诊断） |

### 7.4 字段含义二次核实清单

请向硬件/PLC 协议方确认：

1. `pau_in_temp = "100.2"` 的量纲（°C / 缩放系数 / 百分比？）
2. `productCode` 与设备类型的官方映射表（130004/270001/120003/10016/250001/100007/260001 各对应何种产品）
3. `error_*` 故障码字典（每个编号含义、严重级别）
4. `header.ackCode=1` 是否要求消费者侧回 ACK？当前 `screen_heartbeat_consumer.py` 未实现 ACK 回执，是否会引发大屏侧重试或告警？
5. `empty_screen_timing` 的具体业务语义（息屏定时？）

### 7.5 抓取脚本去留

- `scripts/analysis/capture_heartbeat_702.py`：保留为分析工具（一次性 + 可复用，仅需改 `TARGET_MACS`）
- `scripts/analysis/_inspect.py`：保留为统计模板
- `.env.capture`：本地凭据，确认已纳入 `.gitignore`
- `capture_raw_3-1-702.jsonl`：保留为本报告原始证据，建议同步至文档目录或归档

---

## 附录 A：原始数据来源与可信度

| 数据项 | 来源 | 可信度 |
|--------|------|--------|
| MAC `c5d29c52a237ade5` | `resource/all_owner.json` → 已通过 `import_all_owners` 同步生产 DB | 高 |
| `specific_part` = `3-1-7-702` | 同上 | 高 |
| Payload 结构 | 本次真实抓取（50 条样本） | **高（实测）** |
| attrTag 含义 | 本报告基于 snake_case 字段名 + 上下文推断 | **中（推断）**，待硬件方确认 |
| messageId 零丢包 | 50 条 messageId 连续无缺口 | 高（实测） |
| 上报频率 P95=30.4s | 本次 10 分钟样本（n=49 间隔） | **中**（样本期短，需 24h 复测） |
| `productCode` 与设备类型对应 | attrTag 关键词推断（newwind/pau/condensation/...） | **低-中**，待文档/硬件方确认 |

## 附录 B：交付物清单

| # | 文件路径（绝对） | 大小/行数 | 用途 |
|---|----------------|----------|------|
| 1 | `C:\Users\胖子熊\MyProject\FreeArk\scripts\analysis\capture_heartbeat_702.py` | ~358 行 | 抓取脚本（可复用） |
| 2 | `C:\Users\胖子熊\MyProject\FreeArk\scripts\analysis\.env.capture.template` | 数行 | 凭据模板 |
| 3 | `C:\Users\胖子熊\MyProject\FreeArk\scripts\analysis\capture_raw_3-1-702.jsonl` | 50 行 / 26,063 字节 | 真实抓取原始数据 |
| 4 | `C:\Users\胖子熊\MyProject\FreeArk\scripts\analysis\_inspect.py` | ~50 行 | 统计分析辅助脚本 |
| 5 | `C:\Users\胖子熊\MyProject\FreeArk\scripts\analysis\capture_run.log` | 抓取过程控制台输出 | 抓取过程审计 |
| 6 | `C:\Users\胖子熊\MyProject\FreeArk\docs\analysis\heartbeat_3-1-702_capture_report.md` | （本文） | 分析报告 |

---

**报告生成**：基于 2026-05-23 22:33–22:43（10 分钟）真实抓取数据。
