# 用户故事清单

**版本**：v1.10.0_miniprogram_param_settings
**日期**：2026-06-26
**状态**：✅ APPROVED（2026-06-26 用户确认）
**配套**：`requirements_spec.md`（同目录）

> 验收标准采用 Given / When / Then。标「(对齐 web)」表示**可配置参数集合/校验**须与 web 版一致。
> **已决策（2026-06-26）**：OQ-01=仅业主自助（role=user）；OQ-02=小程序前端直连 `wss://...:8084`。
> 因此本清单角色默认为**业主**，US-08 为主路径（隔离强约束）；US-03 为客户端直连下发。

---

## US-01 查看某房间的可配置参数（对齐 web）

**作为** 运维人员
**我希望** 在小程序中选择一个房间（specific_part）后看到其全部可配置参数
**以便** 知道有哪些参数可以调整及其当前值

**关联**：REQ-FUNC-001、REQ-FUNC-002（当前值来自订阅 screen→cloud 的 `DeviceStatusUpdate` 主动推送，OQ-04）

**验收标准**
- AC-01-1
  - Given 我（业主）已登录且选定自己绑定的 specific_part
  - When 进入「参数设置」页并订阅 `/screen/service/screen/to/cloud/{screenMac}`
  - Then 页面按 sub_type 分组展示**可写**参数，当前值取自屏端主动推送，格式化展示（如开/关、制冷/制热、26.0 ℃）
- AC-01-2 (对齐 web)
  - Given 该房间存在只读参数（`*_temperature` / `*_humidity` / `*_dew_point_setting` / `*_error` / `*_alert` / `*_fault`）
  - When 加载参数列表
  - Then 这些只读参数**不**出现在可编辑列表中
- AC-01-3 (对齐 web)
  - Given 同一 specific_part
  - When 对比小程序与 web 的可写参数集合
  - Then 两端可写项**完全一致**（后缀 `_temp_setting`/`_switch`/`_mode` + 精确名 `away_energy_saving`/`central_energy_supply`）
- AC-01-4
  - Given `*_temp_setting` 在后端存储为 ×10 整数（如 260）
  - When 展示
  - Then 显示为 26.0 ℃（÷10、保留 1 位、带单位）

---

## US-02 编辑参数值并本地校验（对齐 web）

**作为** 运维人员
**我希望** 用合适的控件修改参数（开关/枚举用选择器，温度用数值输入）
**以便** 准确设置目标值

**关联**：REQ-FUNC-003

**验收标准**
- AC-02-1
  - Given 参数为 `*_switch` 或 `*_mode` 或枚举（如 `central_energy_supply`）
  - When 编辑
  - Then 提供与 web 一致的可选项（制冷/制热/通风/除湿、开/关、制冷/制热/无 等）
- AC-02-2
  - Given 参数为 `*_temp_setting`
  - When 编辑
  - Then 提供数值输入，单位 ℃，按设定范围限制
- AC-02-3
  - Given 我未改变某些参数
  - When 提交
  - Then 仅发生变化的项进入下发列表

---

## US-03 下发参数到屏端（业主小程序直连 MQTT）

**作为** 业主
**我希望** 确认后将变更通过 MQTT 直接下发到我房间对应的屏设备
**以便** 实际生效到 PLC

**关联**：REQ-FUNC-004、REQ-FUNC-005、NFR-03（直连，OQ-02=B；依赖 OQ-03 映射、OQ-10/12）

**验收标准**
- AC-03-1
  - Given 我已修改若干可写参数并点击「下发」
  - When 客户端处理
  - Then 客户端用后端下发的 screenMac（= 我绑定房间的 `OwnerInfo.unique_id`）与映射，直接 publish `DeviceWrite` 到 `/screen/service/cloud/to/screen/{screenMac}`
- AC-03-2
  - Given 下发报文
  - Then 报文结构符合屏端协议：`{header:{ackCode,messageId,name:"DeviceWrite",screenMac}, payload:{...,data:{deviceSn,items:[{attrTag,attrValue}]}}}`
- AC-03-3 (幂等)
  - Given 同一批次因网络重试被发送两次（相同 request_id）
  - When 屏端/后端处理
  - Then 只生效一次（按 request_id 去重）
- AC-03-4 (真实生效)
  - Given 下发成功
  - When 在屏端/PLC 侧核对
  - Then 对应参数被正确写入（attrValue 表示与 OQ-07 结论一致）

---

## US-04 写入结果反馈

**作为** 运维人员
**我希望** 看到本次下发是 pending、成功还是失败
**以便** 确认是否需要重试

**关联**：REQ-FUNC-006（依赖 OQ-05）

**验收标准**
- AC-04-1
  - Given 我点击下发
  - When 请求被后端接受
  - Then UI 立即显示「下发中（pending）」，≤2s 给出已提交反馈
- AC-04-2（屏端有回执，OQ-05=是）
  - Given 屏端在 `screen/to/cloud` 回执
  - When 后端按 request_id 关联回执
  - Then 每项更新为成功/失败，失败项显示原因
- AC-04-3（屏端无可靠回执，OQ-05=否，降级）
  - Given 下发后延时重读当前值
  - When 新值与目标值一致
  - Then 标记为成功；不一致则提示「未确认，请重试或刷新」

---

## US-05 异常与不可达处理

**作为** 运维人员
**我希望** 在通道/设备异常时得到明确提示而非「假成功」
**以便** 不被误导

**关联**：REQ-FUNC-009、NFR-03

**验收标准**
- AC-05-1
  - Given 屏端 broker 不可达 / publish 未获 PUBACK
  - When 下发
  - Then 返回明确失败，不标记为成功，审计记录为 failed
- AC-05-2
  - Given 目标屏设备离线
  - When 下发
  - Then 提示「设备离线」，并按 OQ-09 策略处理（默认提示后可选择是否仍下发）

---

## US-06 后端权威校验（对齐 web）

**作为** 系统
**我希望** 在后端对所有下发做权威校验
**以便** 防止非法/越权写入

**关联**：REQ-FUNC-003、REQ-FUNC-008

**验收标准**
- AC-06-1 (对齐 web)
  - Given 请求包含不可写参数（如 `*_temperature`）
  - When 后端校验
  - Then 返回 400「参数不在可写白名单」
- AC-06-2 (对齐 web)
  - Given `central_energy_supply` 的值不在 {1,2,3}
  - When 后端校验
  - Then 返回 400「超出合法枚举范围」
- AC-06-3
  - Given `*_temp_setting` 值超出允许范围
  - When 后端校验
  - Then 拒绝并提示

---

## US-07 写操作审计

**作为** 管理员
**我希望** 每次下发都有可追溯记录
**以便** 事后审计与排障

**关联**：REQ-FUNC-007（依赖 OQ-08、OQ-11；直连模型下后端不在写入路径上）

**验收标准**
- AC-07-1
  - Given 一次成功/失败的下发
  - And 后端被动订阅消费者已观察到屏端主题（OQ-11=A）
  - Then 生成审计记录，含 operator(业主)、specific_part/screenMac、param_name、old_value、new_value、channel=screen-mqtt、request_id、status、时间
- AC-07-2
  - Given 审计查询（若提供查询入口）
  - When 按 specific_part / operator / status 过滤
  - Then 可区分 screen-mqtt 与 s7 两个通道的记录

---

## US-08 业主自助调参 + 隔离（主路径，OQ-01=仅业主）

**作为** 业主（role=user）
**我希望** 在小程序中调整我已绑定房间的参数，且无法触及他人房间
**以便** 安全地自助管理自己的环境

**关联**：REQ-FUNC-008、C-02、C-03、OQ-10

**验收标准**
- AC-08-1
  - Given 业主已绑定 specific_part = X
  - When 进入参数设置并下发
  - Then 后端只返回 X 的参数与 screenMac，下发针对 X 的 screenMac
- AC-08-2 (隔离 — 接口层)
  - Given 业主请求**未绑定**的 specific_part = Y 的参数/凭证
  - When 后端校验绑定关系
  - Then 返回 403，不返回 Y 的 screenMac 或凭证
- AC-08-3 (残余风险，已接受 — OQ-10)
  - Given 直连模型不加 broker ACL（用户已接受越权风险）
  - When 业主用通用凭证向他人 screenMac 主题 publish
  - Then 系统**不**强制阻止；隔离仅靠「后端只下发自己房间 screenMac + 客户端 UI 限制」，此为已知残余风险，非本版本阻塞项
- AC-08-4 (范围)
  - Given 业主可见参数集合（后端下发）
  - Then 不超出 web 可写白名单（不因角色放宽/收紧造成不一致）

---

## US-09 web 零回归（约束型）

**作为** 现有 web 运维/管理员
**我希望** 本次小程序改动不影响 web 参数设置与 S7 链路
**以便** 现网稳定

**关联**：C-01、NFR-06

**验收标准**
- AC-09-1
  - Given 本版本上线
  - When 在 web 使用 `/api/device-settings/*` 下发
  - Then 行为、链路、结果与上线前完全一致
- AC-09-2
  - Given datacollection S7 写订阅器
  - Then 其逻辑与配置不被本版本改动影响

---

## 故事-OQ 依赖矩阵

| 故事 | 关键依赖 / 状态 |
|------|------------------------|
| US-03 | OQ-03 抓包映射（**硬前置，未完成**）、OQ-12 后端下发白名单/映射（推荐已采） |
| US-04 | ✅ OQ-04 订阅 screen→cloud 值推送；OQ-05/06 抓包确认 |
| US-03/US-06 | ✅ OQ-07 与 web 一致；on-wire 表示待 OQ-03 抓包样例确认 |
| US-07 | OQ-08 复用 PLCWriteRecord+channel、OQ-11 后端被动订阅审计（推荐已采） |
| US-05 | OQ-09 不强约束（推荐已采） |
| US-08 | ✅ OQ-10 接受越权残余风险（不加 broker ACL）；✅ OQ-13 域名可用 |

> **开发前置硬阻塞（唯一剩余）**：US-03 依赖 OQ-03 **抓包实测**得到真实 `DeviceWrite` 映射与 `DeviceStatusUpdate` 值推送样例。
> 抓包脚本已就绪：`scripts/tmp/sniff_screen_param_rw.py`。运行期需用原厂云/App 触发一次真实写才能采到 `DeviceWrite`。
> 其余 OQ 均已决策或采纳推荐，不再阻塞。
