# 技术选型表

**版本**：v1.10.0_miniprogram_param_settings
**日期**：2026-06-26
**配套**：`architecture_design.md` / `module_design.md`

---

## 1. 选型总览

| 关注点 | 选型 | 理由 / 备注 |
|--------|------|-------------|
| 小程序 MQTT 客户端 | **mqtt.js** (`mqtt` npm, v4.x) | 内置微信小程序 WebSocket 适配（`wx://`/`wxs://`，底层 `wx.connectSocket`）；社区成熟；uni-app 可用 |
| 传输协议 | `wxs://www.ttqingjiao.site:8084/mqtt` | wxs = 微信小程序 + WebSocket + TLS（对应 wss）；实测 broker 走 TLS |
| broker | 厂商共享云 `www.ttqingjiao.site:8084` | 既有，非自建；凭据 admin/public（env 下发，ADR-07） |
| 前端框架 | uni-app + Vue3 (现有) | 复用现有 miniprogram 工程 |
| 后端 | Django + DRF (现有) | 仅加 2 个 DRF 视图 + 1 配置模块 + 1 字段迁移；**不新增 MQTT 依赖** |
| 审计存储 | 复用 `PLCWriteRecord` + `channel` 字段 | OQ-08；单一写入审计视图 |
| 鉴权 | 现有 Token + `IsOwnerUser` | `/api/miniapp/` 已在中间件白名单 |

## 2. 依赖变更

**前端（miniprogram/package.json）新增**
- `mqtt` ^4.3.x（注意：选用支持微信小程序的版本；v4 起内置 wx 适配。打包后体积约数百 KB，纳入主包或 `subpackages/control` 分包以控主包体积）。

**后端**
- 无新增 pip 依赖（config 接口与 audit 接口均为纯 DRF；后端不连 broker）。

**配置（后端 env / settings）**
- `SCREEN_MQTT_HOST=www.ttqingjiao.site`
- `SCREEN_MQTT_PORT=8084`
- `SCREEN_MQTT_PATH=/mqtt`
- `SCREEN_MQTT_PROTOCOL=wxs`
- `SCREEN_MQTT_USERNAME=admin`
- `SCREEN_MQTT_PASSWORD=public`
> 经 config 接口下发给已登录业主；不硬编码进仓库源码（ADR-07）。生产 `.env` 增这 6 项。

## 3. 微信小程序平台配置（部署前置）

- **合法 socket 域名**：微信公众平台 → 开发设置 → socket 合法域名加入 `wss://www.ttqingjiao.site`（OQ-13 已确认可用）。**未配置则真机连不上 broker**。
- 基础库版本：确认目标基础库支持 `wx.connectSocket` 的多并发与所需 TLS；mqtt.js wxs 适配在常见基础库均可用，**仍需真机验证**（R-3）。
- 分包体积：`mqtt` 打入 `subpackages/control` 分包，避免撑大主包（微信主包 2MB 限制）。

## 4. 验证项（开发期必做）

| ID | 验证 | 方式 |
|----|------|------|
| V-1 | mqtt.js wxs 在目标基础库真机可连/订阅/收发 | 真机连 broker 抓一条 DeviceStatusUpdate |
| V-2 | DeviceWrite 真机下发后值反映 | 真机改 temp_set 看回显变化（对照 `scripts/tmp/sniff_screen_param_rw.py` 旁路验证） |
| V-3 | 温度 min/max/step 与实际设备一致 | 对照 web `DeviceAttrDef.num_value_json`（R-2） |
| V-4 | 多 productCode 房间可写 attr 一致性 | 多房间抽样（R-4） |
| V-5 | PLCWriteRecord.channel 迁移不破坏 web 链路 | test-runner 全量回归 + web device_settings 用例 |

## 5. 旁路工具（已就绪）
- `scripts/tmp/sniff_screen_param_rw.py`：开发/联调期可并行抓包对照真机行为（需 `PYTHONUTF8=1`）。
- 抓包证据与映射：`scripts/tmp/oq03_*` + `capture_findings_oq03.md`。
