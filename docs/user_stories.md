# FreeArk 用户故事清单（逆向整理）

**版本**：1.0.0  
**整理日期**：2026-04-12  
**整理方式**：根据源代码逆向分析

---

## 角色定义

| 角色 | 说明 |
|------|------|
| 管理员 | 系统管理员，具有 `role=admin`，可管理用户、查看所有数据 |
| 普通用户 | 具有 `role=user`，可查询能耗和账单数据 |
| 物联网触摸屏 | 安装在房间内的触摸屏终端，通过 `screenMAC` 标识身份，查询本房间账单 |
| 运维人员 | 操作后台服务、查看 PLC 状态和日志 |
| 数据采集服务 | 运行在采集机器上的 Python 服务，负责读取 PLC 并推送 MQTT |

---

## 用户故事列表

### 模块一：用户认证与账户管理

---

#### US-001：用户登录获取访问令牌

**作为** 管理员或普通用户  
**我希望** 使用用户名和密码登录系统  
**以便** 获取 Token 后访问需要认证的 API 接口

**验收标准（AC）：**

- **Given** 用户提供了正确的用户名和密码  
  **When** 发送 `POST /api/auth/login/` 请求  
  **Then** 响应状态码为 200，响应体包含 `token`、`user.role`、`user.username`

- **Given** 用户提供了错误的密码  
  **When** 发送 `POST /api/auth/login/` 请求  
  **Then** 响应状态码为 400，响应体包含错误信息

- **Given** 用户账户已被禁用（`is_active=False`）  
  **When** 发送 `POST /api/auth/login/` 请求  
  **Then** 响应状态码为 400，错误信息包含"账户已被禁用"

---

#### US-002：用户登出清除令牌

**作为** 已登录的用户  
**我希望** 主动退出登录  
**以便** 防止 Token 被他人使用

**验收标准（AC）：**

- **Given** 用户持有有效的 Token  
  **When** 发送携带 Token 的 `POST /api/auth/logout/` 请求  
  **Then** 响应状态码为 200，该 Token 被删除，后续使用该 Token 的请求返回 401

- **Given** 请求不携带 Token  
  **When** 发送 `POST /api/auth/logout/` 请求  
  **Then** 响应状态码为 401

---

#### US-003：管理员创建新用户

**作为** 管理员  
**我希望** 为新员工创建账号并分配角色  
**以便** 控制系统访问权限

**验收标准（AC）：**

- **Given** 管理员已登录，提供了不重复的用户名、密码、角色等信息  
  **When** 发送 `POST /api/users/create/` 请求  
  **Then** 响应状态码为 201，响应体包含新用户的 `id` 和 `username`

- **Given** 管理员提供的用户名已存在  
  **When** 发送 `POST /api/users/create/` 请求  
  **Then** 响应状态码为 400，错误信息包含"用户名已存在"

- **Given** 普通用户（`role=user`）已登录  
  **When** 发送 `POST /api/users/create/` 请求  
  **Then** 响应状态码为 403

---

#### US-004：管理员查看和管理用户列表

**作为** 管理员  
**我希望** 查看所有注册用户并能修改或删除账户  
**以便** 维护用户权限的准确性

**验收标准（AC）：**

- **Given** 管理员已登录  
  **When** 发送 `GET /api/users/` 请求  
  **Then** 响应状态码为 200，返回所有用户的列表

- **Given** 管理员已登录，目标用户 ID 存在  
  **When** 发送 `PUT /api/users/<pk>/` 更新用户信息  
  **Then** 响应状态码为 200，更新成功

- **Given** 管理员已登录  
  **When** 发送 `DELETE /api/users/<pk>/` 删除用户  
  **Then** 响应状态码为 204，用户被删除

---

#### US-005：用户修改自己的密码

**作为** 已登录的用户  
**我希望** 修改账户密码  
**以便** 定期更新密码提升安全性

**验收标准（AC）：**

- **Given** 用户已登录，提供了正确的当前密码和新密码  
  **When** 发送 `POST /api/change-password/` 请求  
  **Then** 响应状态码为 200，`success=true`

- **Given** 用户提供了错误的当前密码  
  **When** 发送 `POST /api/change-password/` 请求  
  **Then** 响应状态码为 400，错误信息为"当前密码错误"

- **Given** 请求体缺少 `current_password` 或 `new_password`  
  **When** 发送 `POST /api/change-password/` 请求  
  **Then** 响应状态码为 400，错误信息提示字段不能为空

---

### 模块二：能耗数据查询

---

#### US-010：运维人员查看每日能耗明细

**作为** 运维人员  
**我希望** 按房间、能源模式和日期范围查询每天的能耗用量明细  
**以便** 核实数据完整性和排查异常

**验收标准（AC）：**

- **Given** 系统中已有 `specific_part="3-1-7-702"` 的 `UsageQuantityDaily` 记录  
  **When** 发送 `GET /api/usage/quantity/?specific_part=3-1-7-702&start_time=2025-01-01&end_time=2025-01-31`  
  **Then** 响应状态码为 200，`data` 数组只包含该房间 1 月份的记录，按 `time_period` 升序排列

- **Given** 不提供任何过滤参数  
  **When** 发送 `GET /api/usage/quantity/?page=1&page_size=20`  
  **Then** 响应状态码为 200，返回最多 20 条记录，`total` 为全部记录数

- **Given** 提供 `energy_mode=制冷`  
  **When** 发送 `GET /api/usage/quantity/?energy_mode=制冷`  
  **Then** 响应数据中所有记录的 `energy_mode` 均为 `制冷`

---

#### US-011：运维人员查看指定时间段汇总能耗

**作为** 运维人员  
**我希望** 查看指定时间段内每个房间的汇总能耗（而非逐日明细）  
**以便** 快速评估某个周期的总用量

**验收标准（AC）：**

- **Given** 房间 `3-1-7-702` 在 2025-01-01 至 2025-01-31 内有日用量记录  
  **When** 发送 `GET /api/usage/quantity/specifictimeperiod/?specific_part=3-1-7-702&start_time=2025-01-01&end_time=2025-01-31`  
  **Then** 响应包含该房间的 `initial_energy`（月内最小值）、`final_energy`（月内最大值）和 `usage_quantity`（两者之差）

- **Given** 过滤后存在多个 `(specific_part, energy_mode)` 组合  
  **When** 发送查询  
  **Then** 结果按 `specific_part` + `energy_mode` 升序排列，分页正确

- **Given** `energy_mode=制冷` 过滤后有 5 个组合  
  **When** 请求 `page_size=3&page=2`  
  **Then** 返回第 4、5 组合，`total=5`

---

#### US-012：管理员查看月度能耗报表

**作为** 管理员  
**我希望** 按楼栋、月份查看所有房间的月度能耗数据  
**以便** 生成月度账单报表

**验收标准（AC）：**

- **Given** 系统中有 2025-01 的月用量数据  
  **When** 发送 `GET /api/usage/quantity/monthly/?usage_month=2025-01&energy_mode=制冷`  
  **Then** 响应状态码为 200，返回该月所有房间的制冷月用量

- **Given** 使用 `start_month=2025-01&end_month=2025-03`  
  **When** 发送 `GET /api/usage/quantity/monthly/`  
  **Then** 只返回 2025-01、2025-02、2025-03 的数据

- **Given** 按 `building=3&unit=1` 过滤  
  **When** 发送 `GET /api/usage/quantity/monthly/?building=3&unit=1`  
  **Then** 返回 3 栋 1 单元所有房间的数据

---

### 模块三：计费管理

---

#### US-020：触摸屏查询本房间历史用能账单

**作为** 物联网触摸屏  
**我希望** 根据自身的 MAC 地址查询本房间的历史账单  
**以便** 向住户展示能耗费用

**验收标准（AC）：**

- **Given** 触摸屏的 `screenMAC` 已在 `SpecificPartInfo` 中注册，对应房间有月度用量数据  
  **When** 发送携带 `screenMAC` 请求头的 `POST /api/billing/list/`，请求体含有效的 `startDate`、`endDate`  
  **Then** 响应 `code=200`，`data` 数组包含该房间指定月份范围内的所有账单记录

- **Given** 账单记录中 `usage_quantity=100`，单价 `0.28`  
  **When** API 返回该账单  
  **Then** `billAmount="28.00"`，`usageAmount="100"`，`billingCycle` 格式为 `"YYYY年MM月"`

- **Given** 请求头中缺少 `screenMAC`  
  **When** 发送 `POST /api/billing/list/`  
  **Then** 响应 `code=400`，`message="请求头中缺少screenMAC信息"`

- **Given** `screenMAC` 未在系统中注册  
  **When** 发送 `POST /api/billing/list/`  
  **Then** 响应 `code=404`，`message` 包含"未找到对应的专有部分信息"

- **Given** `energyType=制冷`  
  **When** 发送 `POST /api/billing/list/`  
  **Then** `data` 数组中所有记录的 `modeName` 均为 `制冷`

- **Given** `startDate="202501"` 格式（6 位 YYYYMM）  
  **When** 发送 `POST /api/billing/list/`  
  **Then** 正确转换为 `2025-01` 进行查询，不报错

- **Given** `billingDate` 字段  
  **When** API 返回账单  
  **Then** `billingDate` 为该月的最后一天，如 2025 年 1 月为 `"2025-01-31"`

---

### 模块四：PLC 设备状态监控

---

#### US-030：运维人员查看所有 PLC 设备在线状态

**作为** 运维人员  
**我希望** 查看当前所有 PLC 设备的在线/离线状态  
**以便** 及时发现设备通信故障

**验收标准（AC）：**

- **Given** 系统中登记了 10 台 PLC 设备，其中 8 台在线  
  **When** 发送 `GET /api/plc/connection-status/`  
  **Then** 响应包含 `statistics.online_count=8`、`statistics.offline_count=2`、`statistics.online_rate=80.0`

- **Given** 按 `building=3&unit=1` 过滤  
  **When** 发送 `GET /api/plc/connection-status/?building=3&unit=1`  
  **Then** 只返回 3 栋 1 单元的设备，统计数据为全局值（非过滤后）

- **Given** 使用 `connection_status=offline` 过滤  
  **When** 发送 `GET /api/plc/connection-status/?connection_status=offline`  
  **Then** 返回的设备状态均为 `offline`

---

#### US-031：运维人员查看单台设备状态详情

**作为** 运维人员  
**我希望** 查看某台特定 PLC 设备的详细状态  
**以便** 了解最后在线时间等信息

**验收标准（AC）：**

- **Given** `specific_part="3-1-7-702"` 的设备存在  
  **When** 发送 `GET /api/plc/connection-status/3-1-7-702/`  
  **Then** 响应状态码 200，返回该设备的 `connection_status`、`last_online_time` 等完整信息

- **Given** 请求一个不存在的 `specific_part`  
  **When** 发送 `GET /api/plc/connection-status/99-9-9-999/`  
  **Then** 响应状态码 404，错误消息包含"未找到"

---

#### US-032：运维人员查看设备历史状态变化

**作为** 运维人员  
**我希望** 查看某台 PLC 设备的历史上线/下线事件  
**以便** 分析设备稳定性和故障模式

**验收标准（AC）：**

- **Given** `specific_part="3-1-7-702"` 有 5 条状态变化历史  
  **When** 发送 `GET /api/plc/status-change-history/3-1-7-702/?page=1&page_size=20`  
  **Then** 响应状态码 200，`data` 包含 5 条记录，按 `change_time` 倒序排列，`total=5`

- **Given** 设备从未发生状态变化  
  **When** 发送 `GET /api/plc/status-change-history/3-1-7-702/`  
  **Then** 响应状态码 200，`data=[]`，`total=0`

---

### 模块五：数据采集端行为

---

#### US-040：采集服务读取 PLC 设备数据并发布至 MQTT

**作为** 数据采集服务  
**我希望** 按配置的时间间隔读取各房间 PLC 的冷热量累计数据  
**以便** 后端能持续获得最新能耗读数

**验收标准（AC）：**

- **Given** PLC IP 可达，DB 块数据可正常读取  
  **When** 采集服务触发一次采集任务  
  **Then** 成功读取 `total_cold_quantity` 和 `total_hot_quantity`，并以 JSON 格式发布到 MQTT Topic

- **Given** PLC IP 不可达（连接失败）  
  **When** 采集服务尝试读取  
  **Then** 连接超时后跳过该设备，不发布 MQTT 消息，记录错误日志

- **Given** 某个参数读取失败（`success=false`）  
  **When** MQTT Handler 接收到消息  
  **Then** 跳过该失败参数，不写入数据库，记录 warning 日志

---

#### US-041：采集服务上报设备连接状态

**作为** 数据采集服务  
**我希望** 在每次发布数据时同时更新设备的在线/离线状态  
**以便** 后端能实时掌握设备通信质量

**验收标准（AC）：**

- **Given** 采集消息中包含至少一个 `success=true` 的数据项  
  **When** MQTT Handler 处理该消息  
  **Then** 对应 `specific_part` 的 `PLCConnectionStatus.connection_status` 更新为 `online`，`last_online_time` 更新为当前时间

- **Given** 采集消息中所有数据项均为 `success=false`  
  **When** MQTT Handler 处理该消息  
  **Then** 对应设备状态更新为 `offline`

- **Given** 设备状态发生变化（从 online 变为 offline 或反之）  
  **When** 状态更新  
  **Then** 写入一条 `PLCStatusChangeHistory` 记录

---

### 模块六：后台计算服务

---

#### US-050：日用量计算服务每日自动汇聚 PLC 数据

**作为** 后台计算服务  
**我希望** 每天凌晨 00:00 自动将当日最新 PLC 读数转化为日用量记录  
**以便** 形成结构化的日能耗数据供查询和汇报

**验收标准（AC）：**

- **Given** 目标日期有 N 条 PLCData 记录（每个 specific_part + energy_mode 一条）  
  **When** `DailyUsageCalculator.calculate_daily_usage(target_date)` 执行  
  **Then** 为每条记录在 `UsageQuantityDaily` 中 upsert 记录，`usage_quantity = final_energy - initial_energy`，返回包含 `processed_count=N` 的结果字典

- **Given** 目标日期某 `(specific_part, energy_mode)` 在 `UsageQuantityDaily` 中已存在记录  
  **When** 日用量计算执行  
  **Then** 更新该记录的 `final_energy` 和 `usage_quantity`，不重复创建

- **Given** 前一天存在 `final_energy=NULL` 的未完成记录  
  **When** 日用量计算执行  
  **Then** 将这些记录的 `final_energy` 设置为 `initial_energy`，`usage_quantity` 设置为 0

- **Given** 计算过程中发生异常  
  **When** 异常抛出  
  **Then** 错误信息被记录到日志，异常继续向上抛出（不静默吞噬）

---

#### US-051：月用量计算服务汇聚日数据为月报

**作为** 后台计算服务  
**我希望** 根据日用量数据生成月度用量汇总  
**以便** 计费模块可以直接使用月度数据

**验收标准（AC）：**

- **Given** 目标月份有完整的日用量记录  
  **When** `MonthlyUsageCalculator.calculate_monthly_usage(target_date)` 执行  
  **Then** 每个 `(specific_part, energy_mode)` 生成一条月度记录，`usage_quantity = max(final_energy) - min(initial_energy)`

- **Given** `final_energy < initial_energy`（数据异常）  
  **When** 月用量计算执行  
  **Then** `usage_quantity` 设置为 0，记录 warning 日志

- **Given** 目标月份无日用量数据  
  **When** 月用量计算执行  
  **Then** 返回 `{"processed": 0, "skipped": True}`，不抛出异常

---

### 模块七：系统运维

---

#### US-060：健康检查

**作为** 负载均衡器或监控系统  
**我希望** 定期探测服务是否正常运行  
**以便** 在服务异常时发出告警或自动重启

**验收标准（AC）：**

- **Given** 服务正常运行  
  **When** 发送 `GET /api/health/`  
  **Then** 响应状态码为 200，`status="ok"`

---

#### US-061：PLC 连接状态超时自动标记离线

**作为** 运维人员  
**我希望** 系统自动将长时间未收到数据的 PLC 设备标记为离线  
**以便** 不必人工检查每台设备

**验收标准（AC）：**

- **Given** 设备 `last_online_time` 超过 600 秒前，当前状态为 `online`  
  **When** PLC 连接监控服务执行检查  
  **Then** 设备状态更新为 `offline`，写入 `PLCStatusChangeHistory` 记录

- **Given** 设备状态已为 `offline`，再次检查时仍超时  
  **When** PLC 连接监控服务执行检查  
  **Then** 不重复写入 `PLCStatusChangeHistory`（状态未发生变化）

---

#### US-062：PLC 数据自动清理

**作为** 运维人员  
**我希望** 系统自动清理超过 7 天的原始 PLC 数据  
**以便** 控制数据库容量增长

**验收标准（AC）：**

- **Given** `PLCData` 中有超过 7 天的历史记录  
  **When** 清理服务执行  
  **Then** 这些记录被删除，返回 `deleted_count > 0`，日志中记录删除数量

- **Given** 没有超过 7 天的历史记录  
  **When** 清理服务执行  
  **Then** 返回 `deleted_count=0`，无异常

---

## 附录：用户故事与需求映射表

| 用户故事 | 对应需求编号 |
|---------|------------|
| US-001 | REQ-FUNC-001 |
| US-002 | REQ-FUNC-002 |
| US-003 | REQ-FUNC-005 |
| US-004 | REQ-FUNC-006, REQ-FUNC-007 |
| US-005 | REQ-FUNC-008 |
| US-010 | REQ-FUNC-010 |
| US-011 | REQ-FUNC-011 |
| US-012 | REQ-FUNC-012 |
| US-020 | REQ-FUNC-020 |
| US-030 | REQ-FUNC-030 |
| US-031 | REQ-FUNC-031 |
| US-032 | REQ-FUNC-032 |
| US-040 | REQ-DC-001, REQ-DC-002 |
| US-041 | REQ-SVC-001 |
| US-050 | REQ-SVC-002 |
| US-051 | REQ-SVC-003 |
| US-060 | REQ-FUNC-041 |
| US-061 | REQ-SVC-004 |
| US-062 | REQ-SVC-005 |
