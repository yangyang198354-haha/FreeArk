# 需求规格说明书

**版本**：v1.10.0_miniprogram_param_settings
**日期**：2026-06-26
**状态**：✅ APPROVED（2026-06-26 用户确认需求与用户故事）— 全部 OQ 已闭环，协议/映射经抓包实测落定
**作者**：Claude Code（pm-orchestrator 子代理因 403 鉴权失败，需求由主控直接产出）
**上游任务**：微信小程序通过 MQTT 实现「设备参数配置」，可配置参数集合与 web 版对齐

### 已决策（2026-06-26 用户确认）
- **OQ-01 = 仅业主自助**：本页面面向 role=user 业主（小程序 `/api/miniapp/` 体系），**不**面向运维/管理员。运维仍用 web 参数设置页。
- **OQ-02 = 小程序前端直连 wss**：业主小程序**直接**连接 `wss://www.ttqingjiao.site:8084` 收发屏端 MQTT，**不**经 Django 后端中转 publish。

> ⚠️ 这两项组合产生重大架构影响：**后端无法在写入时强制「业主只能写自己房间」**。隔离与审计必须改由 **broker 侧 ACL + 后端下发的受限凭证 + 被动观察消费者** 承担。详见 §1.3 修订后的约束与 §8 新派生 OQ-10~OQ-13。

---

## 1. 背景与范围

### 1.1 背景

FreeArk web 版已上线「参数设置」能力：运维/管理员在 `DeviceSettingsPanelView.vue` 页面按房间（specific_part）查看并下发可写参数，链路为
**前端 → 后端 `/api/device-settings/write` → 发 MQTT 到 `/datacollection/plc/write/command/{specific_part}` → `datacollection/plc_write_subscriber.py` 用 snap7（S7 协议）写 PLC → 回执到 `/datacollection/plc/write/ack/{specific_part}`**。

现需在【微信小程序】上实现**同一个参数配置功能**，但走**另一条传输通道**：通过屏端（screen 设备）的 MQTT 协议下发写指令，由屏端自身落到 PLC，而不经过 datacollection 的 S7 直写。

- MQTT 接入点（WebSocket Secure）：`wss://www.ttqingjiao.site:8084`
- 屏端参数读写主题：
  - 上行（屏→云）：`/screen/service/screen/to/cloud/{screenMac}`
  - 下行（云→屏）：`/screen/service/cloud/to/screen/{screenMac}`
- 可配置的参数集合与 web 版**保持一致**。

### 1.2 范围

**本版本包含：**
- 小程序**业主端**新增「参数设置」页：业主对**自己已绑定**房间拉取可写参数（含当前值、可选项、单位/缩放），编辑后下发。
- **业主小程序直连 `wss://...:8084`**，通过屏端 MQTT 协议（`DeviceWrite` 报文）下发写指令到自己绑定房间对应的屏设备。
- 后端为客户端提供：业主绑定房间的 screenMac、可写参数清单 + 参数映射（attrTag/deviceSn）、当前值快照，以及（推荐）broker 受限连接凭证。
- 写入结果反馈：pending → 成功/失败 的状态呈现。
- 可写参数白名单、枚举值域、单位与 ×10 缩放规则**完全沿用 web 版**（由后端下发，保持单一权威来源）。
- 写操作审计留痕（推荐由后端被动订阅屏端主题观察，见 OQ-11）。

**本版本明确不包含（除非 OQ 确认纳入）：**
- 运维/管理员在小程序调参（OQ-01 已定为仅业主；运维继续用 web）。
- 屏端协议中除参数写/读以外的能力（场景、安防、OTA、日志上传控制等）。
- web 端任何行为变更（C-01）。
- 屏端固件/APP 侧改动（假定屏端已实现 `DeviceWrite`/`DeviceStatusRead`，见 OQ-05、OQ-06）。

### 1.3 关键约束（通贯约束）

- **C-01 不改变现有 web 行为**：web 版 `/api/device-settings/*`、datacollection S7 写链路必须零回归。
- **C-02 业主数据隔离（直连模型，已接受残余风险）**：OQ-02 选了客户端直连，**后端无法在写入时拦截越权**；OQ-10 已决定**不强制 broker ACL、接受越权风险**。本版本隔离仅做到：① 后端只向业主下发其**已绑定**的 specific_part 参数与 screenMac；② 客户端 UI 限制（非安全边界）。**已知残余风险**：被篡改的客户端可向他人 screenMac 主题 publish，用户已知悉并接受。
- **C-03 屏端 broker 凭证**：客户端使用的连接凭证（默认 `admin/public` 或用户提供）不具备按屏隔离能力——这是 C-02 残余风险的来源；本版本不追加凭证最小化改造（可作后续加固项）。
- **C-04 可配置参数集合与 web 一致**：以 web 版 `views_device_settings.py` 的可写白名单为唯一权威来源，且**由后端下发给客户端**，客户端不得自带白名单（防双份漂移）。
- **C-05 幂等与防重复下发**：下发须带唯一 request_id，屏端按 request_id 去重（对齐现有 S7 链路做法）。

---

## 2. 现有系统关键事实（需求依据，已 Read/Grep 核实）

### 2.1 web 版「可配置参数」权威定义（`views_device_settings.py`）
- 可写后缀：`_temp_setting`、`_switch`、`_mode`
- 可写精确名白名单：`away_energy_saving`、`central_energy_supply`
- 只读后缀（明确不可写）：`_temperature`、`_humidity`、`_dew_point_setting`、`_error`、`_alert`、`_fault`
- 枚举值域校验：`central_energy_supply` ∈ {1,2,3}
- 可写性判定：只读后缀优先否决；再判精确名白名单或可写后缀命中。

### 2.2 值标签 / 单位 / 缩放规则（`param_value_label.py`）
- `_switch` → {0:关, 1:开}
- `_mode` → {1:制冷, 2:制热, 3:通风, 4:除湿}（历史旧值 0 → 制冷）
- `away_energy_saving` → {0:未启用离家节能, 1:启用离家节能}
- `central_energy_supply` → {1:制冷, 2:制热, 3:无}
- `_temp_setting`：存储为**放大 10 倍的整数**，展示需 ÷10 保留 1 位小数，单位 ℃
- 单位：`_temp_setting`/`_temperature` = ℃，`_humidity` = %RH

### 2.3 web 写链路（`device_settings_write`）
- 入参：`specific_part` + `items:[{param_name, new_value}]`
- 校验可写性 + 枚举值域 → 由 `OwnerInfo.plc_ip_address` 取 PLC IP → 建 `PLCWriteRecord`(status=pending) → publish 到 `/datacollection/plc/write/command/{specific_part}` → 返回 202 pending。
- `PLCWriteRecord` 字段：request_id、batch_request_id、specific_part、param_name、old_value、new_value、operator、status、error_message、created_at。

### 2.4 屏端 MQTT 协议（来自逆向分析 `analysis doc/MQTT消息机制完整分析.md`）
- 报文结构：`{header:{ackCode, messageId, name, screenMac}, payload:{code, message, data}}`
- **下行写控制 `name=DeviceWrite`**：`payload.data = {deviceSn, items:[{attrTag, attrValue}]}` → 屏端 `HardwareCtrlImpl.writeDeviceState()` 执行。
- **下行读状态 `name=DeviceStatusRead`**：`payload.data={deviceSn}` → 屏端回 `DeviceStatusUpdate` 到 `screen/to/cloud`。
- **上行状态 `name=DeviceStatusUpdate`**：`payload.data={deviceSn, productCode, items:[{attrTag, attrValue, nonActiveUpload}]}`。
- `ackCode`：0=需回复，1=无需回复；`messageId` 自增 1~65500。
- 订阅主题（屏侧）：`/screen/service/cloud/to/screen/{mac}`；上行主题：`/screen/service/screen/to/cloud/{mac}`。

### 2.5 身份与设备标识
- **screenMac = `OwnerInfo.unique_id`**（v1.8.0 已确立并上线）。
- `OwnerInfo`：含 `specific_part`（"楼-单-层-户"，unique）、`unique_id`（screenMAC）、`plc_ip_address`。
- 屏端协议的 `deviceSn` / `productCode` / `attrTag` 与 web 的 `param_name`、`specific_part` 的映射关系**尚未在本仓库内确认**（见 OQ-03）。

### 2.6 小程序现状（uni-app，`miniprogram/`）
- 两类受众共存：
  - **运维/管理员**：`subpackages/monitor`（device-list、device-panel、param-history、room-history、plc-status）、`subpackages/ops`、`subpackages/energy`，走常规 `/api/...`。
  - **业主（role=user）**：`pages/home`、`pages/chat`、`pages/bind`，走 `/api/miniapp/` + IsOwnerUser。
- 现有设备面板 `subpackages/monitor/pages/device-panel.vue` 已用 `GET /api/devices/realtime-params/` 读实时参数、`POST /api/devices/ondemand-refresh/` 触发按需采集——**但目前是只读，无写能力**。
- 鉴权：Pinia `store/auth.js` + Token（isAdmin 判 role==='admin'）。API 走 `utils/api.js` → `utils/http.js`。

---

## 3. 干系人与目标用户

| 角色 | 关注点 |
|------|--------|
| 运维工程师（operator） | 现场/远程通过小程序快速调参，能力对齐 web |
| 管理员（admin） | 同上 + 审计可追溯 |
| 业主（user，待定） | 仅在 OQ-01 确认纳入时，自助调自己房间参数 |
| 屏端设备（screen） | 接收 `DeviceWrite`，落 PLC，回状态/回执 |

---

## 4. 功能性需求

> 标注「(对齐 web)」者，行为须与 web 版一致；标注「(新)」者为本通道特有。

### REQ-FUNC-001 参数列表加载（对齐 web）
小程序参数设置页按 `specific_part` 展示**可写参数**，按 sub_type 分组，每项含：display_name、当前值、display_value（按 §2.2 规则格式化）、value_options（枚举可选项）、值类型/数值域元数据。可写白名单与 web 完全一致（§2.1）。只读参数不出现在可编辑列表中。

### REQ-FUNC-002 当前值回显
进入页面与下发后，能显示参数「当前值」。
- 默认实现（推荐）：复用后端实时快照（`PLCLatestData` / `/api/devices/realtime-params/`），与 web 一致。
- 可选增强：通过屏端 `DeviceStatusRead` 实时读（见 OQ-04）。

### REQ-FUNC-003 参数编辑与校验（对齐 web）
- 开关/枚举类用选择控件，温度设定用数值输入。
- 前端做基本校验，**后端做权威校验**：可写性、枚举值域（如 `central_energy_supply` ∈ {1,2,3}）、`_temp_setting` 的 ×10 缩放与范围。
- 仅提交发生变化的项。

### REQ-FUNC-004 下发（新，业主小程序直连屏端 MQTT）
用户确认后，**由业主小程序直接** publish 到 `/screen/service/cloud/to/screen/{screenMac}`：
- screenMac 取自业主绑定关系（= 该 specific_part 的 `OwnerInfo.unique_id`），由后端下发，客户端不可自选任意 screenMac。
- 客户端用后端下发的映射（OQ-12）把 `param_name/new_value` 转为屏端 `DeviceWrite` 报文：`data:{deviceSn, items:[{attrTag, attrValue}]}`。
- 报文带唯一 request_id（见 OQ-06），用于幂等。
- 越权防护依赖 broker ACL + 受限凭证（C-02/C-03/OQ-10），非客户端自律。

### REQ-FUNC-005 参数模型映射（新）
建立 web 参数模型（`param_name` + `specific_part`）→ 屏端协议（`attrTag` + `deviceSn` + `productCode`）的映射。映射来源与维护方式见 OQ-03。下发前后的值表示需一致（尤其 `_temp_setting` 的 ×10 在哪侧处理须明确，见 OQ-07）。

### REQ-FUNC-006 写入结果反馈（新）
- 提交后立即进入 pending 态。
- 客户端订阅 `/screen/service/screen/to/cloud/{screenMac}`，按 request_id 关联屏端回执，更新为成功/失败（前提：屏端对写操作有回执，见 OQ-05）。
- 若屏端无可靠写回执：降级为「乐观提交 + 延时重读当前值比对」（参考现有 device-panel 按需刷新 5s 重读模式）。
- UI 呈现：每项成功/失败、失败原因、整体结果。

### REQ-FUNC-007 写操作审计（新）
下发须可追溯。直连模型下后端不在写入路径上，推荐由**后端被动订阅消费者**观察屏端主题落审计（OQ-11=A）：operator(业主)、specific_part/screenMac、param_name、old_value、new_value、通道（screen-mqtt）、request_id、结果、时间。推荐复用 `PLCWriteRecord` + 增「channel」字段（OQ-08）。

### REQ-FUNC-008 鉴权与隔离（业主自助 + 直连）
- 业主登录复用 `/api/miniapp/` + IsOwnerUser；后端只向业主返回其**已绑定** specific_part 的参数与 screenMac。
- 后端接口（参数拉取）对未绑定 specific_part 返回 403。
- **已知残余风险（OQ-10 接受）**：直连模型下越权写无法由后端在写入时拦截，且本版本不加 broker ACL；隔离止于「后端只下发自己房间信息 + 客户端 UI 限制」。

### REQ-FUNC-009 失败与异常处理
- broker/屏端不可达：返回明确错误，不产生「假成功」（对齐 web 对 PUBACK/假 success 的加固经验）。
- 屏端离线：提示设备离线，可选择是否仍下发（缓存/重试策略见 OQ-09）。

---

## 5. 非功能性需求

- **NFR-01 安全**：屏端 broker 凭证不下发客户端（C-03）；写入路径鉴权与 web 同级。
- **NFR-02 一致性**：可配置参数集合、枚举、单位、缩放与 web 单一权威来源一致，避免双份漂移（理想做法是后端共享同一份白名单/标签逻辑）。
- **NFR-03 可靠性**：幂等去重（request_id）；publish 须确认真正发出（PUBACK），不接受入队即成功。
- **NFR-04 可观测性**：下发与回执有结构化日志，便于排查（对齐现有 datacollection 日志风格）。
- **NFR-05 性能**：单次批量下发交互在合理时延内给出 pending 反馈（≤2s 给出已提交），最终态依赖屏端回执时延。
- **NFR-06 零 web 回归**：不得影响 web `/api/device-settings/*` 与 datacollection S7 链路。

---

## 6. 假设

- A-01：屏端设备已实现并正确处理 `DeviceWrite`（能把 attrTag/attrValue 落到对应 PLC 点位）。
- A-02：`wss://www.ttqingjiao.site:8084` 为屏端使用的 MQTT broker（WebSocket+TLS），**微信小程序可直连**（需把该域名加入小程序合法域名 socket 白名单；凭证由用户提供）。
- A-03：screenMac = `OwnerInfo.unique_id` 对所有目标房间均有有效值。
- A-04：本通道与 datacollection S7 通道是并行的两条写路径；本版本不要求二者互斥或同步（同一参数两条路都能写，须避免并发冲突——见 OQ-09）。
- A-05：broker 支持按主题 ACL 与受限凭证（OQ-10=A）；若不成立则需回退后端中转（OQ-13）。

---

## 7. 验收标准（汇总，详见 user_stories.md）

- AC-总-01：可写参数集合、枚举、单位、缩放与 web 版逐一对齐（同一 specific_part 下两端可写项一致）。
- AC-总-02：在小程序对某 specific_part 修改 `*_temp_setting` / `*_switch` / `*_mode` / `away_energy_saving` / `central_energy_supply` 并下发，屏端实际收到正确的 `DeviceWrite` 报文，且参数生效。
- AC-总-03：下发后页面能反映 pending → 成功/失败。
- AC-总-04：越权/非法值/不可写参数被后端拒绝。
- AC-总-05：web 端参数设置与 datacollection S7 链路功能零回归。

---

## 8. OPEN QUESTIONS（需用户确认后才进入架构/开发）

> 每条给出推荐答案；用户可逐条确认或修改。

**OQ-01 目标用户范围 —— ✅ 已定：仅业主自助（role=user）**
运维/管理员继续用 web；小程序参数设置仅给业主，挂在 `/api/miniapp/` + IsOwnerUser 体系，业主只能操作自己绑定的房间。

**OQ-02 写入路径架构 —— ✅ 已定：小程序前端直连 wss**
业主小程序直接连 `wss://www.ttqingjiao.site:8084` 收发，不经后端中转 publish。
→ 该决策派生 OQ-10/OQ-11/OQ-12/OQ-13（隔离凭证、审计、白名单下发、回退条件），见下。

---
### 由 OQ-01+OQ-02 组合派生的新 OPEN QUESTION（关键，需确认）

**OQ-10 broker 鉴权与按主题 ACL（C-02/C-03 的落点，最高优先级）**
直连模型下，越权防护完全依赖 broker。需确认：
- (A，推荐) broker 支持**按客户端身份的主题 ACL**：后端为业主每个绑定签发受限凭证（只能 pub/sub 自己的 `{screenMac}` 主题），凭证短时效可吊销。
- (B) broker 仅有一套共享账号 `admin/public`（参考逆向文档），无按主题隔离 → **越权写风险**，此时建议回退 OQ-02 为后端中转。
**需用户确认 broker 是否支持 ACL，以及凭证签发方式。** 这是直连模型能否安全成立的前提。

**OQ-11 直连模型下的审计如何留痕**
后端不在写入路径上，无法天然记录。
- (A，推荐) 后端起一个**被动订阅消费者**，订阅 `/screen/service/cloud/to/screen/#`（或具体 screenMac）观察下发与回执，落审计表。
- (B) 客户端下发后再调一个后端「上报审计」接口（可被绕过，仅尽力而为）。
- (C) 本版本不做后端审计，仅客户端本地展示。
**推荐：A**。

**OQ-12 可写白名单 + 参数映射的下发方式**
为保持与 web 单一权威来源（C-04），客户端不应自带白名单/映射。
- (A，推荐) 后端新增 `/api/miniapp/device-settings/params/?...` 返回：可写参数清单 + 当前值 + value_options + 单位/缩放 + 屏端映射（attrTag/deviceSn/productCode）。客户端据此构造 `DeviceWrite`。
**推荐：A**（依赖 OQ-03 的映射数据）。

**OQ-13 直连失败/不可用时的回退**
微信小程序对 `wss://` 自定义域名有合法域名校验等限制，且无 ACL 时存在安全问题。
- 若 OQ-10=B 或小程序无法直连该 broker → 是否接受**回退为后端中转**（即 OQ-02 改 A）？
**建议预留回退方案**，避免直连不可行时整条需求作废。

**OQ-03 参数模型映射 —— ✅ 已实测（2026-06-26，详见 `capture_findings_oq03.md`）**
抓到 3-1-702（screenMac `c5d29c52a237ade5`）11 条真实 `DeviceWrite` + 全量 `DeviceStatusUpdate`。结论：
- 屏端用 `deviceSn`+`attrTag`，attrTag 名与 web `param_name` **不同**（`switch`/`system_switch`/`temp_set`/`mode`/`energy_supply_mode`/`energy_saving_sign`），值是**语义字符串**（见 OQ-07）。
- **deviceSn 由厂商云分配**，web 侧不掌握；故推荐**屏端自描述方案**：小程序订阅本屏 `DeviceStatusUpdate` 实时拿到本房间 deviceSn+attrTag+当前值，直接用屏端词表渲染与写回，**免去 specific_part→deviceSn 预置表与 web 数字码翻译**。「与 web 一致」收敛为「可写白名单 + 展示标签」两份小配置（后端下发，OQ-12）。
- 建议再做一次定向补抓（`--mac c5d29c52a237ade5`）把 mode/energy_supply_mode 枚举全集补齐。

**OQ-04 当前值回显方式 —— ✅ 已定：订阅 screen→cloud 主动推送**
屏端会在 `/screen/service/screen/to/cloud/{screenMac}` **主动推送**设备值（`DeviceStatusUpdate`），小程序直连后订阅该主题即可实时回显，**不**走后端快照、**不**必主动 `DeviceStatusRead`。

**OQ-05 屏端写回执 —— ✅ 已实测：无独立写回执**
该屏只出现 `DeviceStatusRead/DeviceWrite/DeviceStatusUpdate/ScreenSceneSetUpload`，**没有 DeviceWrite 专用 ack**。写确认 = 监听紧随的 `DeviceStatusUpdate` 中该 attrTag 是否变为目标值（实测可靠：写 temp_set/mode/energy_supply_mode 后状态即反映）。与 OQ-04 同一条值推送复用。

**OQ-06 request_id / 幂等承载 —— 推荐：客户端自管全局唯一 request_id**
`header.messageId`（1~65500 自增）只作屏端协议字段；另在 payload 放一个全局唯一 request_id 供幂等/审计关联（需抓包确认屏端是否原样回带该字段）。

**OQ-07 值编码 —— ✅ 已实测全集（codec 100% 确认，详见 `capture_findings_oq03.md` §5）**
wire 用语义串：`switch`=off/on、`temp_set`="26.0"(真实小数不×10)、`mode`=cold/hot/wind/dehumidification(=制冷/制热/通风/除湿=web 1/2/3/4)、`energy_supply_mode`=cold/hot/no(=制冷/制热/无=web 1/2/3)、`energy_saving_sign`=off/on(=web away_energy_saving 0/1)。**写词表=读词表**。若走 OQ-03 屏端自描述方案，直接用屏端词表 + 展示层中文标签即可，连 web 数字码翻译都省（仅 web↔屏双栈并存时才需 codec）。系统机改 mode 需联动下发 energy_supply_mode（wind→no）。

**OQ-08 审计存储 —— 推荐：复用 `PLCWriteRecord` + channel 字段**
增「channel」区分 screen-mqtt / s7，保持单一写入审计视图。

**OQ-09 与 S7 通道并发 —— 推荐：不强约束**
本版本不加锁；审计区分通道，UI 提示「以最后一次下发为准」。

---
### 派生 OQ 的最终决策

**OQ-10 broker ACL —— ✅ 已定（实测复议后）：直连 + 内嵌 `admin/public`，书面接受全租户级风险**
2026-06-26 抓包确认 `www.ttqingjiao.site:8084` 是**厂商共享云**，`admin/public` 可看/写**所有客户所有屏**（实测 360+ 屏全量数据流）。用户在知悉该现实后，**仍选择小程序直连 + 客户端内嵌 `admin/public`**，并**书面接受**「任何持有小程序者可读写全厂商所有屏」的全租户级风险。
- 故本版本不做 broker ACL、不做凭证最小化、不回退后端中转。
- 隔离止于「后端只下发业主自己房间 screenMac/可写清单」+ 客户端 UI 限制（均非安全边界）。
- ⚠️ 该风险登记为已接受的产品级残余风险；后续如要收敛，路径是「后端中转」或「厂商受限凭证」。

**OQ-11 直连下审计 —— 推荐：后端被动订阅消费者**
后端起被动订阅消费者观察屏端主题落审计（与现有 fault/heartbeat consumer 同构）。

**OQ-12 白名单/映射下发 —— 推荐：后端接口下发**
新增 `/api/miniapp/device-settings/params/` 下发可写清单 + 映射 + 单位/缩放，客户端不自带白名单（C-04）。

**OQ-13 微信合法域名 —— ✅ 已定：`www.ttqingjiao.site` 可用**
该域名可加入小程序合法 socket 域名，直连方案可行，无需为域名限制回退。

---

## 9. 待用户提供 / 待抓包确认的输入（开发前置）

1. **抓包结果**（运行 `scripts/tmp/sniff_screen_param_rw.py`）：真实 `DeviceWrite`（写命令）+ `DeviceStatusUpdate`（值推送）样例 → 锁定 OQ-03 映射、OQ-05 回执、OQ-06 字段回带、OQ-07 缩放。
2. `wss://www.ttqingjiao.site:8084` 的连接凭证（默认试 `admin/public`；TLS 默认开，可 `--no-tls` 回退）。
3. 抓包须在运行期**触发一次真实写**（用原厂云/App 或屏端原生途径改一个参数）才能采到 `DeviceWrite`——FreeArk web 改参走 S7 不经此 broker。

---

## 10. 备注

- 本需求由主控直接产出：pm-orchestrator 子代理在本次会话因 `403 Please run /login` 鉴权错误未能运行（`subagent_tokens=0`），故未走标准 requirement-analyst 流水线。文档结构对齐既有 `docs/requirements/v1.8.0_*` 规范。
- 用户已确认：OQ-01=仅业主、OQ-02=直连 wss、OQ-03=抓包实测、OQ-04=订阅值推送回显、OQ-07=与 web 一致、OQ-10=接受越权风险、OQ-13=域名可用；OQ-05/06/08/09/11/12 取推荐值。
- 进入架构阶段前，第 9 节抓包结果（尤其真实 `DeviceWrite` 映射）为硬前置；缺失则无法实现可工作的下发。
