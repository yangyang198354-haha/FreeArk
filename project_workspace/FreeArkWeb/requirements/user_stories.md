# FreeArkWeb 用户故事

<!-- file_header
author_agent: sub_agent_requirement_analyst
phase: PHASE_02
project: FreeArkWeb
created_at: 2026-04-14
status: DRAFT
source: reverse_engineering — api/views.py, api/models.py, api/urls.py
-->

---

## US-001 用户登录

**As** 系统用户
**I want to** 使用用户名和密码登录
**So that** 获取 Token 并访问受保护接口

### 验收标准

**AC-001-01**
- Given：用户提交正确的用户名和密码
- When：POST /api/auth/login/
- Then：响应 HTTP 200，包含 token 字段和 user 信息（id、username、email、role）

**AC-001-02**
- Given：用户提交错误的密码
- When：POST /api/auth/login/
- Then：响应 HTTP 400，不返回 token

**AC-001-03**
- Given：请求体缺少 password 字段
- When：POST /api/auth/login/
- Then：响应 HTTP 400

---

## US-002 用户登出

**As** 已登录用户
**I want to** 登出系统
**So that** Token 被删除，会话结束

### 验收标准

**AC-002-01**
- Given：请求头携带有效 Token
- When：POST /api/auth/logout/
- Then：响应 HTTP 200，Token 被删除，success=true

**AC-002-02**
- Given：请求未携带 Token
- When：POST /api/auth/logout/
- Then：响应 HTTP 401

---

## US-003 查询当前用户信息

**As** 已登录用户
**I want to** 查询自己的账号信息
**So that** 了解自己的角色和部门信息

### 验收标准

**AC-003-01**
- Given：请求头携带有效 Token
- When：GET /api/auth/me/
- Then：响应 HTTP 200，data 包含 username、role、department、position 等字段

**AC-003-02**
- Given：未携带 Token
- When：GET /api/auth/me/
- Then：响应 HTTP 401

---

## US-004 用户自主注册

**As** 新用户
**I want to** 注册账号
**So that** 获得系统访问权限，默认角色为普通用户

### 验收标准

**AC-004-01**
- Given：提供合法的 username、password、password2（两次密码一致）
- When：POST /api/auth/register/
- Then：响应 HTTP 201，包含 token，用户 role 为 user

**AC-004-02**
- Given：password 与 password2 不一致
- When：POST /api/auth/register/
- Then：响应 HTTP 400

---

## US-005 修改密码

**As** 已登录用户
**I want to** 修改自己的密码
**So that** 账号更安全

### 验收标准

**AC-005-01**
- Given：携带有效 Token，提供正确的 current_password 和 new_password
- When：POST /api/change-password/
- Then：响应 HTTP 200，success=true

**AC-005-02**
- Given：current_password 错误
- When：POST /api/change-password/
- Then：响应 HTTP 400，success=false

**AC-005-03**
- Given：缺少 current_password 或 new_password 字段
- When：POST /api/change-password/
- Then：响应 HTTP 400

---

## US-006 管理员查看用户列表

**As** 管理员
**I want to** 查看全部用户
**So that** 了解系统用户情况

### 验收标准

**AC-006-01**
- Given：管理员 Token
- When：GET /api/users/
- Then：响应 HTTP 200，返回所有用户列表

**AC-006-02**
- Given：普通用户 Token
- When：GET /api/users/
- Then：响应 HTTP 403

---

## US-007 管理员创建用户

**As** 管理员
**I want to** 创建新用户
**So that** 为员工分配系统账号

### 验收标准

**AC-007-01**
- Given：管理员 Token，提供新用户的 username、password、role
- When：POST /api/users/create/
- Then：响应 HTTP 201，用户被创建

**AC-007-02**
- Given：管理员 Token，提供已存在的 username
- When：POST /api/users/create/
- Then：响应 HTTP 400，error 消息包含"已存在"

**AC-007-03**
- Given：普通用户 Token
- When：POST /api/users/create/
- Then：响应 HTTP 403

---

## US-008 健康检查

**As** 运维人员
**I want to** 检查服务是否正常运行
**So that** 快速判断后端服务状态

### 验收标准

**AC-008-01**
- Given：无需认证
- When：GET /api/health/
- Then：响应 HTTP 200，status="ok"

---

## US-009 查询日用量列表

**As** 能源管理员
**I want to** 查询各房间各日的能耗数据
**So that** 了解能耗趋势

### 验收标准

**AC-009-01**
- Given：无需认证，无过滤参数
- When：GET /api/usage/quantity/
- Then：响应 HTTP 200，success=true，返回所有日用量记录，按 time_period 升序

**AC-009-02**
- Given：指定 specific_part 过滤
- When：GET /api/usage/quantity/?specific_part=3-1-7-702
- Then：仅返回该房间的记录

**AC-009-03**
- Given：指定 energy_mode 过滤
- When：GET /api/usage/quantity/?energy_mode=制冷
- Then：仅返回制冷记录

**AC-009-04**
- Given：指定 start_time 和 end_time
- When：GET /api/usage/quantity/?start_time=2025-01-01&end_time=2025-01-31
- Then：仅返回该时间段内的记录

**AC-009-05**
- Given：指定 page=1&page_size=2
- When：GET /api/usage/quantity/
- Then：data 列表最多2条，total 返回全量数量

---

## US-010 查询特定时间段汇总用量

**As** 能源管理员
**I want to** 查询某时间段内各房间的汇总用量（初期~末期）
**So that** 计算某段时间的实际消耗

### 验收标准

**AC-010-01**
- Given：指定 specific_part、energy_mode、start_time、end_time
- When：GET /api/usage/quantity/specifictimeperiod/
- Then：返回该组合的 initial_energy=min，final_energy=max，usage_quantity=差值

**AC-010-02**
- Given：无对应数据的 specific_part
- When：GET /api/usage/quantity/specifictimeperiod/
- Then：total=0，data 为空

**AC-010-03**
- Given：存在制冷和制热两种模式数据，请求过滤 energy_mode=制冷
- When：GET /api/usage/quantity/specifictimeperiod/
- Then：结果仅包含制冷模式，不混入制热数据

---

## US-011 查询月度用量

**As** 能源管理员
**I want to** 查询各房间的月度用量汇总
**So that** 支持月度账单生成

### 验收标准

**AC-011-01**
- Given：无过滤参数
- When：GET /api/usage/quantity/monthly/
- Then：返回所有月度记录，total 正确

**AC-011-02**
- Given：指定 specific_part、energy_mode 过滤
- When：GET /api/usage/quantity/monthly/
- Then：仅返回符合条件的记录

**AC-011-03**
- Given：指定 start_month 和 end_month
- When：GET /api/usage/quantity/monthly/
- Then：仅返回该月份区间内的记录

**AC-011-04**
- Given：指定分页参数
- When：GET /api/usage/quantity/monthly/?page=1&page_size=2
- Then：data 列表条数 <= page_size，total 为全量数量

---

## US-012 查询 PLC 设备连接状态列表

**As** 设备运维人员
**I want to** 查看所有 PLC 设备的在线/离线状态
**So that** 快速发现离线设备

### 验收标准

**AC-012-01**
- Given：无过滤参数
- When：GET /api/plc/connection-status/
- Then：返回所有设备，statistics 包含 online_count、offline_count、total_devices、online_rate

**AC-012-02**
- Given：指定 connection_status=offline
- When：GET /api/plc/connection-status/
- Then：仅返回离线设备，total 正确

**AC-012-03**
- Given：指定 building 过滤
- When：GET /api/plc/connection-status/
- Then：仅返回该楼栋的设备

---

## US-013 查询单个 PLC 设备详情

**As** 设备运维人员
**I want to** 查询指定 PLC 设备的连接状态详情
**So that** 确认特定设备的状态

### 验收标准

**AC-013-01**
- Given：数据库中存在该 specific_part 的设备
- When：GET /api/plc/connection-status/{specific_part}/
- Then：HTTP 200，data.specific_part 匹配

**AC-013-02**
- Given：数据库中不存在该 specific_part
- When：GET /api/plc/connection-status/{specific_part}/
- Then：HTTP 404

---

## US-014 查询 PLC 状态变化历史

**As** 设备运维人员
**I want to** 查看某 PLC 设备的上下线历史
**So that** 排查设备稳定性问题

### 验收标准

**AC-014-01**
- Given：存在多条状态变化记录
- When：GET /api/plc/status-change-history/{specific_part}/
- Then：HTTP 200，结果按 change_time 倒序，第一条为最新事件

**AC-014-02**
- Given：无状态变化记录
- When：GET /api/plc/status-change-history/{specific_part}/
- Then：HTTP 200，total=0，data 为空

---

## US-015 查询历史用能账单

**As** 住户（通过屏幕设备访问）
**I want to** 查看自己的历史用能账单
**So that** 了解用能费用情况

### 验收标准

**AC-015-01**
- Given：请求头含有效 screenMAC，指定 startDate 和 endDate
- When：POST /api/billing/list/
- Then：HTTP 200，code=200，返回账单列表

**AC-015-02**
- Given：请求头缺少 screenMAC
- When：POST /api/billing/list/
- Then：HTTP 400，code=400

**AC-015-03**
- Given：screenMAC 在系统中无对应的 specific_part
- When：POST /api/billing/list/
- Then：HTTP 404，code=404

**AC-015-04**
- Given：指定 energyType=制冷
- When：POST /api/billing/list/
- Then：仅返回制冷账单数据

**AC-015-05**
- Given：usage_quantity=100，单价 0.28
- When：POST /api/billing/list/
- Then：billAmount="28.00"，basicPrice="0.28"

**AC-015-06**
- Given：账单数据的 usage_month="2025-01"
- When：POST /api/billing/list/
- Then：billingCycle="2025年01月"，billingDate="2025-01-31"

**AC-015-07**
- Given：specific_part="3-1-7-702"（解析为 building=3, unit=1, room=702）
- When：POST /api/billing/list/
- Then：familyName="3栋1单元702"

**AC-015-08**
- Given：startDate/endDate 使用 YYYYMM（6位）格式，如 "202501"
- When：POST /api/billing/list/
- Then：HTTP 200，正常返回账单数据（自动转换为 YYYY-MM 格式）
