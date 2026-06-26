# 架构设计说明书（ADR）

**版本**：v1.10.0_miniprogram_param_settings
**日期**：2026-06-26
**状态**：DRAFT — 待评审
**作者**：Claude Code（system-architect 子代理 403 不可用，主控内联产出）
**上游**：已 APPROVED 的 `requirements_spec.md` + `user_stories.md` + 实测证据 `capture_findings_oq03.md`

---

## 1. 架构目标与边界

让**业主（role=user）**在微信小程序内，对**自己已绑定的房间**，通过屏端 MQTT 协议读写设备参数；可设置参数集合与 web 版一致。

**强约束（继承自需求）**
- C-01 web 零回归：不动 `views_device_settings.py` 与 datacollection S7 链路。
- C-02/C-03：业主直连 broker，越权与全租户风险已书面接受（OQ-10）；隔离仅做「后端只下发自己房间」+ UI 限制。
- C-04：可写白名单/标签由后端单一权威下发，客户端不自带。
- C-05：写命令带唯一 request_id。

## 2. 总体架构

```
┌────────────────────────────┐         ┌──────────────────────────────┐
│  微信小程序 (uni-app)        │         │  Django 后端 (ASGI, 现有)      │
│  业主端 / role=user          │         │                               │
│                            │  HTTPS  │  /api/miniapp/device-settings/ │
│  param-settings 页 ────────┼────────▶│   GET config/  (IsOwnerUser)   │
│   - 取配置/绑定房间/凭证      │         │   POST audit/  (IsOwnerUser)   │
│   - 渲染可写项               │         │                               │
│  utils/screenMqtt.js        │         │  screen_param_config.py(白名单)│
│   (mqtt.js + wxs://)        │         │  PLCWriteRecord(+channel)      │
└──────┬─────────────────────┘         └──────────────────────────────┘
       │ wss/wxs (MQTT over WebSocket+TLS)        ▲ 后端【不】连 broker
       │ admin/public                             │ 仅服务配置 + 接收审计上报
       ▼
┌────────────────────────────────────────────────┐
│  厂商共享云 MQTT broker  wss://www.ttqingjiao.site:8084/mqtt │
│   下行 /screen/service/cloud/to/screen/{screenMac}  ← DeviceWrite（本端发） │
│   上行 /screen/upload/screen/to/cloud/{screenMac}   → DeviceStatusUpdate（回显/确认）│
└───────────────────────────┬────────────────────┘
                            ▼
                     屏端设备(screen) → PLC
```

**关键特征**：后端**完全不接触 broker**（无新增后端 MQTT 依赖、不占树莓派出口）。写入与回显全在小程序客户端直连完成；后端只负责①下发配置/凭证/绑定房间，②接收尽力而为的审计上报。

## 3. 端到端数据流

1. **进入页面**：`GET /api/miniapp/device-settings/config/` → 返回 broker 连接参数(host/port/path/protocol/username/password)、业主**已绑定房间列表**(specific_part, location_name, **screenMac=unique_id**)、可写白名单+值 codec+展示标签+productCode 角色名。
2. **连接 broker**：`utils/screenMqtt.js` 用 `wxs://www.ttqingjiao.site:8084/mqtt` + admin/public 连接，订阅所选房间的
   - `/screen/upload/screen/to/cloud/{screenMac}`（设备值推送，回显/确认主源）
   - `/screen/service/cloud/to/screen/{screenMac}`（可选，观测他端下发）
3. **构建设备清单（屏端自描述，ADR-02）**：解析 `DeviceStatusUpdate` 的 `data:{deviceSn, productCode, items:[{attrTag,attrValue}]}`，按 deviceSn 聚合最新值；按配置过滤出**可写 attrTag**渲染控件，只读 attr 可只读展示。
4. **下发**：业主编辑 → `DeviceWrite` 发到 `/screen/service/cloud/to/screen/{screenMac}`，body：
   ```json
   {"header":{"name":"DeviceWrite","messageId":"<epoch-ms>","sn":"<deviceSn>","screenMac":"<mac>"},
    "payload":{"code":200,"message":"","data":{"deviceSn":"<deviceSn>",
      "items":[{"attrTag":"<tag>","attrValue":"<val>"}]}}}
   ```
   - 系统机改 `mode` 时联动追加 `energy_supply_mode`（cold→cold/hot→hot/wind→no/dehumidification→cold，ADR-08）。
   - 同时本地生成全局唯一 request_id（放入自定义字段，见 module_design）。
5. **确认（无独立 ack，ADR-04）**：监听该 deviceSn 的下一条 `DeviceStatusUpdate`，若目标 attrTag 已变为目标值 → 成功；超时(默认 8s)未反映 → 提示"未确认，请重试/刷新"。
6. **审计上报（尽力而为，ADR-06）**：发出后 `POST /api/miniapp/device-settings/audit/`，后端校验 screenMac 属于该业主后写 `PLCWriteRecord(channel='screen-mqtt')`。

## 4. 架构决策记录（ADR）

**ADR-01 直连 broker（不经后端中转）** — 依据 OQ-02。后端不在写入路径上。后果：隔离/审计能力受限（见 ADR-06、安全节）。备选「后端中转」被否，残余风险已接受。

**ADR-02 屏端自描述，免预置映射** — 依据 OQ-03 实测：deviceSn 由厂商云分配、web 不掌握。客户端订阅 `DeviceStatusUpdate` 实时获得本房间 deviceSn+attrTag+当前值，直接用屏端原生词表渲染与写回。**不需要 specific_part→deviceSn 映射表，也不需要把屏端值翻译成 web 数字码**。"与 web 一致"收敛为「可写白名单 + 中文标签」两份后端配置。

**ADR-03 MQTT 库 = mqtt.js + 微信 `wxs://` 传输** — 微信小程序不能用 paho/原生 TCP；mqtt.js 内置微信小程序 WebSocket 适配（`wx`/`wxs` 协议，底层走 `wx.connectSocket`）。需将 `wss://www.ttqingjiao.site:8084` 加入小程序「合法 socket 域名」（OQ-13 已确认可用）。

**ADR-04 写确认靠值推送反映（无独立 ack）** — 依据 OQ-05 实测：屏端对 DeviceWrite 无专用回执。用 `DeviceStatusUpdate` 反映新值作确认，与回显复用同一条流。

**ADR-05 wire 用屏端语义串；codec 仅在需要与 web 数字对照时使用** — 依据 OQ-07 实测全集。客户端在屏端词表内闭环（off/on、cold/hot/wind/dehumidification、真实小数温度），展示层套中文标签。`_temp_setting` 的 ×10 是 PLC/web 存储细节，本链路 wire 用真实小数，不做 ×10。

**ADR-06 审计 = 客户端尽力上报（替代被动订阅）** — OQ-11 原推荐"后端被动订阅"，但共享 broker 上 DeviceWrite 洪流**无法归属到具体业主**，故改为：客户端发出后调后端审计接口记录（operator=业主、screenMac、items、request_id）。后端校验 screenMac 归属该业主后入库。**已知局限**：可被改造客户端绕过（与 OQ-10 接受风险一致）。复用 `PLCWriteRecord`+新增 `channel` 字段（OQ-08）。

**ADR-07 broker 凭证经后端 config 下发，不硬编码进仓库** — admin/public 放后端 env(`SCREEN_MQTT_*`)，由 config 接口下发给已登录业主。便于轮换；避免明文入 git。仍属客户端可见（接受 OQ-10 风险）。

**ADR-08 系统机 mode↔energy_supply_mode 联动** — 复刻原厂 App 实测行为（改 mode 同时下发 energy_supply_mode）。映射表由后端 config 下发。

**ADR-09 新增 owner 专用分包 `subpackages/control`** — 懒加载、与运维 monitor 分包隔离；入口仅在业主首页 `pages/home` 展示。

## 5. 安全性设计（重点）

- **残余风险（已接受，OQ-10）**：客户端持有 admin/public，可读写厂商**全租户所有屏**。后端层面能做且本版本会做的最小缓解：
  - config/audit 接口 `IsOwnerUser` + 校验 screenMac 必须属于**请求业主的 active 绑定**，否则 403；后端**只**下发业主自己房间的 screenMac（不泄露他人）。
  - 凭证经 env 下发可轮换（ADR-07）。
- **非安全边界**：客户端 UI 只暴露自己房间——但因直连，技术上可越权，已书面接受。
- **登记**：本风险在 requirements §C-02/OQ-10 与本节双重登记；后续收敛路径=后端中转或厂商受限凭证。

## 6. 对现有系统的影响（C-01 零回归核对）

| 触点 | 影响 |
|------|------|
| `views_device_settings.py` / S7 链路 | **不改动** |
| `PLCWriteRecord` 模型 | 仅**新增**可空 `channel` 字段（默认 's7' 兼容旧数据），迁移 scoped 手写（见 [[project-migration-drift-handwrite-scoped]]） |
| `UserRoleApiGuardMiddleware` | **不改**（`/api/miniapp/` 前缀已整体放行） |
| miniprogram 现有页面 | 仅 `pages/home` 增一个入口、`pages.json` 增分包；其余不动 |
| 后端 broker 连接 | **无**（不新增 consumer/依赖） |

## 7. 风险与待确认

- R-1（已接受）：全租户凭证风险。
- R-2：温度设定范围（min/max/step）需取自 web `DeviceAttrDef.num_value_json` 或厂商规格，config 暂用保守默认，开发期校准。
- R-3：mqtt.js 在目标微信基础库版本的 `wxs` 兼容性，开发期需真机验证（tech_stack 列为验证项）。
- R-4：同一房间多设备的可写 attr 在不同 productCode 下是否完全一致，开发期用更多房间抽样确认（当前以 3-1-702 为准）。
