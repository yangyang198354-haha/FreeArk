# 用户故事清单增量 — FreeArk v0.5.7 按房型过滤设备面板与采集点裁剪

```
file_header:
  document_id: REQ-US-v0.5.7
  title: FreeArk v0.5.7 — 用户故事（按房型过滤设备面板、参数设置与 PLC 采集点裁剪）
  author_agent: sub_agent_system_architect (via PM Orchestrator, incremental revision)
  project: FreeArk 能耗采集平台
  version: v0.5.7-rev1
  created_at: 2026-05-22
  revised_at: 2026-05-22
  status: APPROVED
  revision_note: |
    PM 决策锁定（2026-05-22）：
    - OQ-v0.5.7-02 = 方案 B，US-v0.5.7-01 降级策略验收标准更新
    - OQ-v0.5.7-03 = 不纳入，US-v0.5.7-05 标记为本版本不实施
    - OQ-v0.5.7-04 = 纳入，US-v0.5.7-06 升级为必须项，验收口径改为「采集侧实际不发起无效点位读取」
  base_document: docs/user_stories.md (v1.0.0)
  references:
    - docs/requirements_spec_v0.5.7.md
    - FR-v0.5.7-01 ~ FR-v0.5.7-06
```

---

## 角色定义（本版本新增/沿用）

| 角色 | 说明 |
|------|------|
| 物业管理员 | 登录 Web 管理后台，查看和管理各专有部分设备状态、参数设置 |
| 运维人员 | 负责系统运维，关注数据准确性与存储效率 |
| 数据采集服务 | datacollection 进程，负责 PLC 采集并通过 MQTT 发布数据 |

---

## 用户故事列表（v0.5.7 新增）

### 模块：设备面板（按房型过滤）

---

#### US-v0.5.7-01：物业管理员查看设备面板时仅显示实际存在的房间

**作为** 物业管理员  
**我希望** 在查看某专有部分的设备面板时，只看到该专有部分实际存在的房间温控面板  
**以便** 避免看到通讯故障等无意义的数据，做出准确判断

**来源**：FR-v0.5.7-01；PM 描述「按实际房型动态渲染，而非统一模板」

**验收标准（AC）：**

- **Given** 专有部分 `9-1-10-1002` 的 `device_room` 表中不存在「儿童房」对应的房间记录  
  **When** 管理员打开该专有部分的设备面板页（`GET /api/devices/realtime-params/?specific_part=9-1-10-1002`）  
  **Then** 响应数据中不包含 `panel_fourth_children`（儿童房-温控面板）子类型，管理员界面中看不到「儿童房-温控面板」卡片

- **Given** 专有部分 `9-1-10-1001` 的 `device_room` 表中存在「书房」对应的房间记录  
  **When** 管理员打开该专有部分的设备面板页  
  **Then** 响应数据中包含 `panel_study_room`（书房-温控面板）子类型，且展示真实数据

- **Given** 专有部分 `9-1-10-1002` 的 `device_room` 表中存在「次卧」、「主卧」、「客厅」等房间记录  
  **When** 管理员打开该专有部分的设备面板页  
  **Then** 响应数据中包含对应的 `panel_bedroom`、`panel_children_room`、`main_thermostat` 子类型，数据正常展示

- **Given** 主温控（`main_thermostat`）、新风（`fresh_air`）、能耗表（`energy_meter`）、水力模块（`hydraulic_module`）、空气品质（`air_quality`）属于系统级面板，不依赖房间存在  
  **When** 管理员打开任意专有部分的设备面板页  
  **Then** 上述系统级面板不受房型过滤影响，在有 PLCLatestData 记录的情况下正常显示

- **Given** 某专有部分尚未完成设备树同步（`device_floor` 表中无该 specific_part 记录）  
  **When** 管理员打开该专有部分的设备面板页  
  **Then** 降级处理（**方案 B，PM 已锁定**）：系统级面板（main_thermostat / fresh_air / energy_meter / hydraulic_module / air_quality）正常显示，所有房间温控面板（`panel_*`）全部隐藏；页面不报错，数据展示与已同步设备树的专有部分相同格式

---

#### US-v0.5.7-02：物业管理员在参数设置页面仅看到实际存在房间的可写参数

**作为** 物业管理员  
**我希望** 在参数设置页面中，只看到该专有部分实际存在的房间的温控参数  
**以便** 避免对不存在的设备发起错误的 PLC 写入命令

**来源**：FR-v0.5.7-02；PM 描述「参数设置页面也不应显示不存在的房间温控面板」

**验收标准（AC）：**

- **Given** 专有部分 `9-1-10-1002` 的 `device_room` 表中不存在「儿童房」  
  **When** 管理员进入该专有部分的参数设置页（`GET /api/device-settings/params/9-1-10-1002/`）  
  **Then** 响应中不包含 `panel_fourth_children` 参数分组，管理员无法看到也无法误操作「儿童房」温度设置

- **Given** 专有部分 `9-1-10-1001` 的 `device_room` 表中存在「书房」  
  **When** 管理员进入该专有部分的参数设置页  
  **Then** 响应中包含 `panel_study_room` 参数分组（含书房的温度、开关等可写参数）

- **Given** 新风、水力模块等系统级可写参数  
  **When** 管理员进入任意专有部分的参数设置页  
  **Then** 上述参数不受房型过滤影响，正常显示

---

### 模块：数据落库过滤

---

#### US-v0.5.7-03：系统不将不存在房间的参数写入 plc_latest_data

**作为** 运维人员  
**我希望** 系统仅将实际存在房间的参数数据写入 plc_latest_data  
**以便** 保持数据库数据的准确性，减少存储占用

**来源**：FR-v0.5.7-03；PM 描述「plc_latest_data 不再写入无效信息」

**验收标准（AC）：**

- **Given** 专有部分 `9-1-10-1002` 的 `device_room` 表中不存在「儿童房」，PLC 采集侧上报了 `fourth_children_room_temperature=0` 和 `fourth_children_room_communication_error=1`  
  **When** `PLCLatestDataHandler` 处理该 MQTT 消息  
  **Then** `plc_latest_data` 表中 `specific_part=9-1-10-1002` 且 `param_name IN (fourth_children_room_*)` 的记录不被写入或更新；日志中记录 debug 信息「跳过不存在房间的参数」

- **Given** 同一条 MQTT 消息中包含客厅、次卧等实际存在房间的参数  
  **When** `PLCLatestDataHandler` 处理该消息  
  **Then** 实际存在房间的参数正常写入 `plc_latest_data`，不受过滤影响

- **Given** 系统级参数（`system_switch`、`operation_mode`、`fan_speed` 等）  
  **When** `PLCLatestDataHandler` 处理消息  
  **Then** 系统级参数不受房型过滤影响，照常写入

---

#### US-v0.5.7-04：系统不将不存在房间的参数写入 device_param_history

**作为** 运维人员  
**我希望** 系统仅将实际存在房间的参数历史记录写入 device_param_history  
**以便** 历史数据表只包含有业务价值的数据，便于后续查询和分析

**来源**：FR-v0.5.7-04；PM 描述「device_param_history 不再写入无效信息」

**验收标准（AC）：**

- **Given** 专有部分 `9-1-10-1002` 的 `device_room` 中不存在「儿童房」  
  **When** 触发 `PLCLatestDataHandler._write_history()`  
  **Then** `device_param_history` 表中不追加 `specific_part=9-1-10-1002` 且 `param_name IN (fourth_children_room_*)` 的历史记录

- **Given** 实际存在房间的参数在本小时内首次写入  
  **When** 触发历史写入逻辑  
  **Then** 该参数正常追加至 `device_param_history`，历史过滤逻辑（每小时第一条）不受影响

---

#### US-v0.5.7-05：运维人员清理已有冗余历史数据【本版本不实施】

**PM 决策**（OQ-v0.5.7-03，2026-05-22）：**本版本不实施**。存量冗余数据保留，后续单独处理。

**作为** 运维人员  
**我希望** 能够通过管理命令清理 plc_latest_data 和 device_param_history 中已有的冗余数据  
**以便** 恢复数据库的数据准确性，减少存储占用

**来源**：FR-v0.5.7-06（本版本不实施）；PM 描述「已有冗余数据的处理策略」

**注意**：此用户故事的验收标准留存供后续版本参考，本版本不纳入测试范围，不开发对应代码。

---

### 模块：按需采集优化

---

#### US-v0.5.7-06：按需采集仅轮询实际存在的数据点（**必须项，本版本实现**）

**PM 决策**（OQ-v0.5.7-04，2026-05-22）：**纳入本版本，必须实现**。

**作为** 数据采集服务  
**我希望** 在按需采集时只读取该专有部分实际存在房间的参数  
**以便** 减少对不存在设备的无效 PLC 读操作，降低 PLC 通信负载，使需求第 4 条彻底闭环

**来源**：FR-v0.5.7-05（必须项）；PM 描述「定时刷新也不再采集不必要的信息」；PM OQ-v0.5.7-04 决策

**验收标准（AC，PM 锁定口径）：**

- **Given** 专有部分 `9-1-10-1002` 的 `device_room` 表中不存在「儿童房」  
  **When** 前端触发按需采集（`POST /api/devices/ondemand-refresh/`）  
  **Then** 采集侧 `OndemandCollectSubscriber` **实际不发起** `fourth_children_room_*` 系列参数对应 PLC DB 地址的读取；采集侧日志中记录「allowed_params 白名单已过滤，跳过参数: fourth_children_room_*」

- **Given** Django 后端发布 ondemand MQTT 请求，payload 中包含 `allowed_params` 白名单  
  **When** 采集侧收到该指令  
  **Then** 仅构建 `allowed_params` 内的 PLC 读取配置；发布的 MQTT result 消息中不包含 `fourth_children_room_*` 参数；DB 不新增这些参数的记录

- **Given** payload 中不含 `allowed_params` 字段（向后兼容旧版 Django 部署）  
  **When** 采集侧收到该指令  
  **Then** 采集侧降级为全量采集（原有行为），不报错

**采集侧与落库侧过滤的关系（双道过滤）：**
- 第一道（采集侧，FR-v0.5.7-05）：`OndemandCollectSubscriber` 依据 `allowed_params` 白名单，**不发起**无效 PLC 地址读取，MQTT result 消息中不含无效参数数据。
- 第二道（落库侧，FR-v0.5.7-03/04）：`PLCLatestDataHandler` 依据 `param_blocklist`，**不落库**无效参数（兜底，适用于定时采集、历史遗留、向后兼容场景）。
- 两道过滤不重复也不遗漏：采集侧仅裁剪按需采集链路，落库侧兜底覆盖所有 MQTT 消息来源。
