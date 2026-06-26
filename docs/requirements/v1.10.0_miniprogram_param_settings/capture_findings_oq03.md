# OQ-03 抓包实测结论（屏端参数读写协议）

**日期**：2026-06-26
**来源**：`scripts/tmp/sniff_screen_param_rw.py`，10 分钟全量抓包（`oq03_capture_10min.ndjson` / `_mapping.json`）
**触发**：用户在原厂端对房间 **3-1-702**（screenMac `c5d29c52a237ade5`）改了多个参数，抓到 **11 条真实 `DeviceWrite`**。
**报文量**：10 分钟 16,620 条 `DeviceStatusUpdate` + 630 `DeviceStatusRead` + 16 `ScreenSceneSetUpload` + 11 `DeviceWrite`，涉及 ~360 块屏、3600 个 deviceSn。

---

## 1. Broker / 安全事实（影响 OQ-10）

- `wss://www.ttqingjiao.site:8084/mqtt`，**必须 TLS**；凭据 `admin/public` 即可连。
- **这是厂商共享云 broker**：一套 `admin/public` 能 **看到并写入所有客户、所有屏**（抓到 360+ 屏的全量设备数据流）。这把 OQ-10「接受越权风险」的代价放大到了「全租户级」——不仅业主可越权改同项目他人房间，凭证本身就能改任意项目任意屏。**强烈建议在架构/安全评审中复议**（至少不要把 `admin/public` 直接打进小程序包；考虑后端中转或厂商提供受限凭证）。

## 2. 主题（实测）

| 用途 | 方向 | 主题 |
|------|------|------|
| 写命令 `DeviceWrite` | 云→屏 | `/screen/service/cloud/to/screen/{screenMac}` |
| 读请求 `DeviceStatusRead` | 云→屏 | `/screen/service/cloud/to/screen/{screenMac}` |
| **设备值推送** `DeviceStatusUpdate` | 屏→云 | **`/screen/upload/screen/to/cloud/{screenMac}`** ⚠️ |

⚠️ 关键：值推送（回显数据源，OQ-04）走的是 **`/screen/upload/...`**，不是 `/screen/service/screen/to/cloud/...`。客户端订阅回显必须订 upload 主题（本次靠 `--extra-topics` 才抓到，否则会漏）。

## 3. 报文 envelope（实测完整样例）

**DeviceWrite（云→屏，写命令）：**
```json
{
  "header": { "name": "DeviceWrite", "messageId": "1782445674746",
              "sn": "22154", "screenMac": "c5d29c52a237ade5" },
  "payload": { "code": 200, "message": "success",
    "data": { "deviceSn": "22154",
      "items": [ { "attrTag": "mode", "attrValue": "dehumidification" } ] } }
}
```
- `header` **无 ackCode**；`messageId` 是 13 位 epoch-ms 风格字符串；`deviceSn` 为**字符串**。
- 一条 `DeviceWrite` 的 items 实测都是**单属性**（一次改一个 attr），多次改 = 多条报文。

**DeviceStatusUpdate（屏→云，值推送/回显）：**
```json
{
  "header": { "ackCode": 1, "messageId": "2718",
              "name": "DeviceStatusUpdate", "screenMac": "c5d29c52a237ade5" },
  "payload": { "code": 200,
    "data": { "deviceSn": 22158,
      "items": [ {"attrTag":"temp_set","attrValue":"26.0"}, … ],
      "productCode": 260001 } }
}
```
- `header.ackCode=1`（无需回复）；`messageId` 是小整数字符串；`deviceSn` 为**整数**（与 DeviceWrite 的字符串不一致，实现需双向兼容）；`productCode` 在 `data` 内。

## 4. OQ-05 写回执 —— 实测结论：**无独立写回执**

该屏 10 分钟内出现的 header.name 仅 `{DeviceStatusRead, DeviceWrite, DeviceStatusUpdate, ScreenSceneSetUpload}`，**没有任何 DeviceWrite 专用 ack**。
→ 写入成功与否，**只能靠紧随其后的 `DeviceStatusUpdate` 反映新值来确认**（实测：写 `temp_set=26.0` 后，22158 的 DeviceStatusUpdate 即 `temp_set="26.0"`；写 `mode=dehumidification`、`energy_supply_mode=cold` 后 22154 状态同步反映）。这与 OQ-04（订阅值推送）天然吻合：用同一条值推送既做回显又做写确认。

## 5. OQ-07 值编码 —— ✅ 实测全集（2026-06-26 第二轮定向补抓，14 条 DeviceWrite + 全程时间线）

**写命令词表 = 状态推送词表**（同一套 attrValue 串）。web 可写参数集的双向 codec **已 100% 确认**：

| 概念 | web param | web 值 | 屏端 attrTag | 屏端值（实测全集） |
|---|---|---|---|---|
| 开关 | `*_switch` | 0/1 | `switch` / `system_switch` | `off` / `on` |
| 温度设定 | `*_temp_setting` | ×10 整数(260) | `temp_set` / `out_temp_set` | 真实小数串 `"26.0"`（**不 ×10**） |
| 运行模式 | `operation_mode`(`*_mode`) | 1/2/3/4 | `mode` | `cold`(1制冷)/`hot`(2制热)/`wind`(3通风)/`dehumidification`(4除湿) |
| 能源供应 | `central_energy_supply` | 1/2/3 | `energy_supply_mode` | `cold`(1制冷)/`hot`(2制热)/`no`(3无) |
| 离家节能 | `away_energy_saving` | 0/1 | `energy_saving_sign` | `off`(0)/`on`(1) |

补充行为：
- 系统机（deviceSn 22154）切模式时，App **一条交互同时下发 `mode` + `energy_supply_mode`**：cold↔cold、hot↔hot、**wind↔no**（通风时无能源供应）。复刻 App 行为则改 mode 需联动 energy_supply_mode。
- 面板（22153）的 `mode` 跟随系统机镜像变化。
- `temp_set` 写值实测含小数（首轮 `"26.5"`）；wire 为真实物理量，×10 仅 PLC/web 存储细节。
- `wind_speed`(只见 `normal`)、`humidification_enable`(只见 `off`) **不在 web 可写白名单**，未纳入本 codec；未来要开放需另抓其枚举。

## 6. 3-1-702 设备清单（deviceSn → productCode → 角色）

| deviceSn | productCode | 角色（推断） | 可写 attr（实测/推断） |
|---|---|---|---|
| 22158 | 260001 | 主温控器 main_thermostat | `switch`✅、`temp_set`✅、`system_switch` |
| 22552-22555 | 120003 | 末端温控/风机盘管 ×4 | `switch`✅、`temp_set`✅ |
| 22154 | 270001 | 系统/能源主机 | `system_switch`✅、`mode`✅、`energy_supply_mode`✅、`energy_saving_sign` |
| 22155 | 130004 | 新风 PAU fresh_air | `out_temp_set`、`humi_upper/lower_limit`、`fan_speed`、`wind_speed`（待证） |
| 22156 | 250001 | 能量计 energy_meter | 只读 |
| 22157 | 100007 | 空气质量传感器 | 只读 |
| 22153 | 10016 | 面板/控制器 | `mode`、`wind_speed`、`system_switch`、`humidification_enable`（待证） |

只读类 attrTag（屏端）：`temp`、`NTC_temp`、`humidity`、`dew_point_temp`、`condensation_alarm`、`error_*`、`comm_fault_timeout`、能量计累计量、空气质量等——与 web 只读后缀语义一致。

## 7. 对设计的影响（供架构阶段）

1. **deviceSn 是厂商云分配的**，web/PLC 侧当前不掌握 `specific_part ↔ deviceSn` 关系。两条可选路线：
   - **(A 推荐) 屏端自描述**：小程序直连后订阅本屏 `DeviceStatusUpdate`，**实时拿到本房间所有 deviceSn + attrTag + 当前值**，直接用屏端原生词表渲染「可设置项」并写回（`DeviceWrite` 用同样的 attrTag/attrValue）。**无需 specific_part→deviceSn 预置表，也无需翻译成 web 数字码**——天然解决映射难题。
   - (B) 后端维护 `specific_part→deviceSn→attrTag` 映射表（需厂商数据或逐屏抓取，维护成本高）。
2. 若走 (A)，「与 web 保持一致」落在两点：**①可写白名单**（屏端词表下选哪些 attrTag 可改，对齐 web 的 `switch/temp_set/mode/energy_supply_mode/energy_saving_sign`）；**②展示标签**（off/on→关/开，dehumidification→除湿，cold→制冷，等）。这两份都是小配置表，建议由后端下发（OQ-12）。
3. 写确认复用值推送（OQ-05 无独立 ack）；UI：发 `DeviceWrite` → 监听该 deviceSn 的下一条 `DeviceStatusUpdate` 中该 attrTag 是否变为目标值。

## 8. 补抓结果（已完成 2026-06-26 第二轮）

- ✅ mode 四档（cold/hot/wind/dehumidification）、energy_supply_mode 三档（cold/hot/no）、离家节能（off/on）枚举全集已确认，§5 codec 100% 覆盖 web 可写集。
- ✅ 确认 switch/system_switch/temp_set/mode/energy_supply_mode/energy_saving_sign 均可写（DeviceWrite 实测生效，状态回报反映）。
- 待开放项（非本期）：新风 `out_temp_set`/`wind_speed`、面板 `humidification_enable` 若未来纳入可写，需另抓其枚举/范围。
