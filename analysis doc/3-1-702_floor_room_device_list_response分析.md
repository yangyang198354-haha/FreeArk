# 3-1-702 floor-room-device/list 接口响应分析

## 1. 请求信息

| 项 | 值 |
| --- | --- |
| URL | `http://47.117.41.184:10013/homeauto-contact-screen/contact-screen/screen/floor-room-device/list` |
| Method | `POST` |
| 必传 Header | `screenMAC: c5d29c52a237ade5`（3-1-702 屏 MAC） |
| Body | 空 |
| 抓取时间 | 2026-05-15 |
| Raw 响应文件 | [3-1-702_response_raw.json](3-1-702_response_raw.json)（≈ 140 KB / 1497 行） |

服务端使用 `screenMAC` 在云端反查该屏所绑定的 楼栋-楼层-房间-设备 树，并把这台屏可见的全部设备及其可配置/可读 attr 元数据下发回来。

---

## 2. 顶层结构

```jsonc
{
  "code": 200,
  "message": "成功",
  "data": [ Floor, ... ]      // 楼层数组
}
```

- `code` / `message`：固定 200 / "成功"
- `data`：楼层数组，**3-1-702 只有 1 个楼层**（floor=1）

### 层级 Schema（自上而下）

```
Floor
└─ rooms[]: Room
   └─ devices[]: Device
      ├─ attrs[]: Attr
      │   ├─ selectValues[]: SelectValue   (attrValueType=1 时使用)
      │   └─ numValue: NumValue            (attrValueType=2 时使用)
      └─ deviceProtocol: Protocol
```

### Floor

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `floor` | int | 楼层号 |
| `floorName` | string | 楼层名（用于展示） |
| `rooms` | Room[] | 该层房间列表 |

### Room

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `roomName` | string | 当前房间名（用户可改名） |
| `oriRoomName` | string | 房间原始名（出厂/默认） |
| `roomType` | int | 房间类型枚举（见 §4） |
| `devices` | Device[] | 房间内设备列表 |

### Device

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `deviceSn` | int | 设备 SN，本树内唯一 |
| `deviceName` | string | 设备名 |
| `systemFlag` | int | 1=子设备 / 2=主机（自由方舟主机） |
| `relatedDeviceSn` | int / null | 所属主机 SN；主机自身为 null |
| `productCode` | string | 产品编码（如 "10016"、"270001"） |
| `categoryCode` | int | 设备品类编码 |
| `attrs` | Attr[] | 该设备的属性元数据 |
| `deviceProtocol` | Protocol | 通信协议描述 |

### Attr

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `attrTag` | string | 属性标签（程序内 key，如 `mode`、`temp_set`） |
| `attrValueType` | int | **1 = 枚举型**（用 selectValues） / **2 = 数值型**（用 numValue） |
| `attrConstraint` | int | 约束：0 / 1 / 2（推测：0 只读、1 系统级、2 可控；见 §5） |
| `selectValues` | SelectValue[] | 枚举可选项；数值型时为 `[]` |
| `numValue` | NumValue / null | 数值范围；枚举型时为 null |

#### SelectValue

```jsonc
{ "name": "制冷", "code": "cold", "sortNo": 3 }   // sortNo 可为 null
```

#### NumValue

```jsonc
{ "precision": 0, "max": "40", "min": "0", "step": "1" }
// precision: 小数位; max/min/step 注意是字符串
```

#### Protocol

```jsonc
{ "protocol": 2, "addressCode": 1 }   // 主机为 {null,null}；子设备多为 {2,1}（Modbus / 总线地址）
```

---

## 3. 3-1-702 设备树（实际抓取）

> 楼层 1 共 6 个房间、9 台设备。"自由方舟" (sn=22153) 为主机，其它 8 台子设备的 `relatedDeviceSn` 全部指向 22153。

| 房间 | roomType | deviceSn | deviceName | productCode | categoryCode | proto/addr | attr 数 |
| --- | :-: | :-: | --- | :-: | :-: | :-: | :-: |
| 全屋 | 1 | 22153 | 自由方舟（主机） | 10016 | 1 | — / — | 6 |
| 全屋 | 1 | 22154 | 水力模块 | 270001 | 27 | 2 / 1 | 8 |
| 全屋 | 1 | 22155 | 新风 | 130004 | 13 | 2 / 1 | 16 |
| 全屋 | 1 | 22156 | 能耗表 | 250001 | 25 | 2 / 1 | 7 |
| 全屋 | 1 | 22157 | 空气品质 | 100007 | 10 | 2 / 1 | 5 |
| 客厅 | 2 | 22158 | 主温控 | 260001 | 26 | 2 / 1 | 9 |
| 书房 | 6 | 22552 | 温控面板 | 120003 | 12 | 2 / 1 | 8 |
| 次卧 | 5 | 22553 | 温控面板 | 120003 | 12 | 2 / 1 | 8 |
| 主卧 | 4 | 22554 | 温控面板 | 120003 | 12 | 2 / 1 | 8 |
| 儿童房 | 5 | 22555 | 温控面板 | 120003 | 12 | 2 / 1 | 8 |

合计：**83 条 attr 元数据**。

### 各设备的 attrTag 列表

- **自由方舟 (22153)**：`comm_fault_timeout, humidification_enable, mode, wind_speed, system_switch, energy_saving_sign`
- **水力模块 (22154)**：`mode, system_switch, energy_saving_sign, energy_supply_mode, 2nd_outwater_temp_detect, 2nd_inwater_temp_detect, primary_valve_opening, comm_fault_timeout`
- **新风 (22155)**：`humidification_enable, wind_speed, empty_screen_timing, filter_working_time, filter_max_life, comm_fault_timeout, humi_upper_limit, humi_lower_limit, out_temp_set, one_water_valve_opening, fan_speed, pau_through_temp, newwind_inlet_temp, pau_out_temp, pau_in_temp, speed_level`
- **能耗表 (22156)**：`work_duration, total_hot_quantity, total_cold_quantity, comm_fault_timeout, back_water_temp, total_flow_rate, in_water_temp`
- **空气品质 (22157)**：`hcho, tvoc, pm25, co2, comm_fault_timeout`
- **主温控 (22158, 客厅)**：`switch, humidity, temp, temp_set, system_switch, condensation_alarm, NTC_temp, dew_point_temp, comm_fault_timeout`
- **温控面板 (22552/22553/22554/22555)**：`switch, temp, temp_set, humidity, condensation_alarm, NTC_temp, dew_point_temp, comm_fault_timeout`（4 个房间完全一致）

---

## 4. 枚举类型推断

### roomType（本次出现的取值）

| roomType | 房间 |
| :-: | --- |
| 1 | 全屋 |
| 2 | 客厅 |
| 4 | 主卧 |
| 5 | 次卧 / 儿童房 |
| 6 | 书房 |

### systemFlag

| 值 | 含义 |
| :-: | --- |
| 1 | 子设备 |
| 2 | 主机（自由方舟） |

### categoryCode ↔ productCode 关系

观察到 `categoryCode` 取 `productCode` 的"前 1~2 位 / 万位"——属于品类大类，例：

| categoryCode | productCode | 设备 |
| :-: | :-: | --- |
| 1 | 10016 | 自由方舟主机 |
| 10 | 100007 | 空气品质 |
| 12 | 120003 | 温控面板 |
| 13 | 130004 | 新风 |
| 25 | 250001 | 能耗表 |
| 26 | 260001 | 主温控 |
| 27 | 270001 | 水力模块 |

### deviceProtocol.protocol

主机为 `null`，所有子设备为 `2`（推测 Modbus over RS485），`addressCode=1` 表示子设备总线地址。

---

## 5. Attr 字段语义

### attrValueType

| 值 | 含义 | 配套字段 |
| :-: | --- | --- |
| 1 | 枚举 / 开关 | `selectValues[]` 非空，`numValue=null` |
| 2 | 数值（连续量） | `numValue` 非空，`selectValues=[]` |

整体分布：枚举型 29 条、数值型 54 条。

### attrConstraint

出现取值 `0 / 1 / 2`。从样本看：

- 设备状态量 / 通信故障类（如 `2nd_outwater_temp_detect`、`primary_valve_opening`、`comm_fault_timeout` 数值场景）多为 **0**
- 系统主参数（`mode`、`wind_speed` 在主机上）多为 **1**
- 子机可控参数（`mode`、`system_switch` 在水力模块上）多为 **2**

经验上："0=只读 / 1=系统只读、2=可下发控制"。最终语义建议以服务端文档为准。

### numValue 注意点

`max / min / step` 都是**字符串**，前端需要 `parseFloat` 后再做范围/步进计算；`precision` 为小数位数（0 表示整数）。

---

## 6. 关键设计要点 / 使用建议

1. **以 screenMAC 为唯一索引**：服务端通过它定位屏 → 屋 → 全树；客户端无需传任何 body。
2. **主子设备拓扑**：`systemFlag=2` 是树根，子设备靠 `relatedDeviceSn` 反向挂到主机；同一房间内可能既有主机又有多台子机（如本案"全屋"房）。
3. **协议解析二选一**：渲染 attr 控件时按 `attrValueType` 分支——
   - `1` → 下拉/分段控件，候选取 `selectValues`，提交值用 `code`；
   - `2` → 数值控件，范围/步进取自 `numValue`。
4. **可控性判断走 `attrConstraint`**：值为 0 时仅作展示；1/2 时可写入（具体 1 与 2 的差异建议在服务端确认）。
5. **房间排序 / 重命名**：`oriRoomName` 保留原名，`roomName` 是用户改名后的，配置面里展示用 `roomName`；如果要做"重置"功能则可回写 `oriRoomName`。
6. **温控面板高度同构**：所有房间的"温控面板"(`productCode=120003`) 的 8 条 attr 完全一致，UI 渲染层可复用同一模板。
7. **数据量**：单屏一次返回 ~140 KB JSON，建议本地按 `deviceSn` 做哈希缓存，避免每次都重新解析。

---

## 7. 字段速查 / Type Sketch（TypeScript）

```ts
interface FloorRoomDeviceListResp {
  code: number;            // 200
  message: string;         // "成功"
  data: Floor[];
}

interface Floor {
  floor: number;
  floorName: string;
  rooms: Room[];
}

interface Room {
  roomName: string;
  oriRoomName: string;
  roomType: number;        // 1=全屋,2=客厅,4=主卧,5=次卧/儿童房,6=书房,...
  devices: Device[];
}

interface Device {
  deviceSn: number;
  deviceName: string;
  systemFlag: 1 | 2;       // 1=子设备 2=主机
  relatedDeviceSn: number | null;
  productCode: string;
  categoryCode: number;
  attrs: Attr[];
  deviceProtocol: { protocol: number | null; addressCode: number | null };
}

interface Attr {
  attrTag: string;
  attrValueType: 1 | 2;    // 1=枚举 2=数值
  attrConstraint: 0 | 1 | 2;
  selectValues: SelectValue[];
  numValue: NumValue | null;
}

interface SelectValue { name: string; code: string; sortNo: number | null; }
interface NumValue    { precision: number; max: string; min: string; step: string; }
```
