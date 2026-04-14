# FreeArkWeb 模块设计

<!-- file_header
author_agent: sub_agent_system_architect
phase: PHASE_04
project: FreeArkWeb
created_at: 2026-04-14
status: DRAFT
source: reverse_engineering — api/ directory
-->

---

## 1. 模块清单

| 模块 | 文件路径 | 职责 |
|------|---------|------|
| MOD-01 数据模型 | api/models.py | 定义所有 ORM 模型和约束 |
| MOD-02 序列化器 | api/serializers.py | 数据校验与序列化 |
| MOD-03 REST 视图 | api/views.py | HTTP 请求处理、业务逻辑编排 |
| MOD-04 URL 路由 | api/urls.py | URL 到视图函数的映射 |
| MOD-05 日用量计算 | api/daily_usage_calculator.py | PLCData -> UsageQuantityDaily |
| MOD-06 月用量计算 | api/monthly_usage_calculator.py | UsageQuantityDaily -> UsageQuantityMonthly |
| MOD-07 MQTT 处理器 | api/mqtt_handlers.py | MQTT 消息解析与数据库写入 |
| MOD-08 MQTT 消费者 | api/mqtt_consumer.py | MQTT 客户端连接与消息分发 |
| MOD-09 PLC 数据清理 | api/plc_data_cleaner.py | 定期清理过期 PLCData |

---

## 2. 模块接口定义

### MOD-01 数据模型接口

```python
# 关键类型定义
CustomUser.role: Literal['admin', 'user']
PLCData.unique_together: ('specific_part', 'energy_mode', 'usage_date')
PLCConnectionStatus.specific_part: unique CharField
SpecificPartInfo.screenMAC: unique CharField
UsageQuantityDaily.time_period: DateField
UsageQuantityMonthly.usage_month: CharField  # YYYY-MM format
```

### MOD-02 序列化器接口

```python
UserLoginSerializer.validate(attrs) -> {'user': CustomUser, ...}
UserRegistrationSerializer.create(validated_data) -> CustomUser
UserCreateSerializer.create(validated_data) -> CustomUser
UsageQuantityDailySerializer.fields: [id, specific_part, building, unit, room_number,
                                       energy_mode, initial_energy, final_energy,
                                       usage_quantity, time_period]
UsageQuantityMonthlySerializer.fields: [id, specific_part, building, unit, room_number,
                                         energy_mode, initial_energy, final_energy,
                                         usage_quantity, usage_month]
PLCConnectionStatusSerializer.fields: [id, specific_part, connection_status,
                                        last_online_time, building, unit, room_number,
                                        created_at, updated_at]
```

### MOD-03 REST 视图接口

```python
# 认证端点
user_login(request: POST) -> Response({'success': bool, 'token': str, 'user': dict})
user_logout(request: POST) -> Response({'success': bool, 'message': str})
get_current_user(request: GET) -> Response({'success': bool, 'data': dict})
user_register(request: POST) -> Response({'success': bool, 'token': str, 'user': dict}, 201)
change_password(request: POST) -> Response({'success': bool})

# 能耗查询端点
get_usage_quantity(request: GET) -> Response({'success': bool, 'data': list, 'total': int})
get_usage_quantity_specific_time_period(request: GET) -> Response({'success': bool, 'data': list, 'total': int})
get_usage_quantity_monthly(request: GET) -> Response({'success': bool, 'data': list, 'total': int})

# PLC 状态端点
get_plc_connection_status(request: GET) -> Response({'success': bool, 'data': list, 'total': int, 'statistics': dict})
get_plc_connection_status_detail(request: GET, specific_part: str) -> Response({'success': bool, 'data': dict})
get_plc_status_change_history(request: GET, specific_part: str) -> Response({'success': bool, 'data': list, 'total': int})

# 账单端点（screenMAC 从 HTTP_SCREENMAC 请求头获取）
get_bill_list(request: POST) -> Response({'code': int, 'message': str, 'data': list})
```

### MOD-05 日用量计算器接口

```python
DailyUsageCalculator.parse_specific_part(specific_part: str) -> Tuple[str, str, str]  # (building, unit, room_number)
DailyUsageCalculator.calculate_daily_usage(target_date: date) -> dict
# 返回: {'processed_count': int, 'created_count': int, 'updated_count': int, ...}
```

### MOD-06 月用量计算器接口

```python
MonthlyUsageCalculator.calculate_monthly_usage(target_date: date) -> dict
# 返回: {'processed': int, 'created': int, 'updated': int, 'skipped': bool, ...}
# 异常: 非 date 类型返回 {'error': str}
```

### MOD-07 MQTT 处理器接口

```python
PLCDataHandler.batch_save_plc_data(batch: list[dict]) -> None
PLCDataHandler.handle(topic: str, payload: dict) -> None
ConnectionStatusHandler.handle(topic: str, payload: dict) -> None
ConnectionStatusHandler._parse_building_info(specific_part: str) -> Tuple[str, str, str]
```

### MOD-09 PLC 数据清理接口

```python
clean_old_plc_data(days: int) -> dict
# 返回: {'deleted_count': int, 'message': str}
```

---

## 3. 模块依赖关系（无循环依赖）

```
urls.py --> views.py --> serializers.py --> models.py
                     --> models.py
daily_usage_calculator.py --> models.py
monthly_usage_calculator.py --> models.py
mqtt_handlers.py --> models.py
mqtt_consumer.py --> mqtt_handlers.py
plc_data_cleaner.py --> models.py
```

**循环依赖检查**：所有依赖为单向，无循环依赖。

---

## 4. 权限控制矩阵

| 视图 | 匿名用户 | 普通用户 | 管理员 |
|------|---------|---------|-------|
| health_check | 允许 | 允许 | 允许 |
| get_csrf_token | 允许 | 允许 | 允许 |
| user_login | 允许 | 允许 | 允许 |
| user_register | 允许 | 允许 | 允许 |
| user_logout | 拒绝(401) | 允许 | 允许 |
| get_current_user | 拒绝(401) | 允许 | 允许 |
| change_password | 拒绝(401) | 允许 | 允许 |
| UserList | 拒绝(401) | 拒绝(403) | 允许 |
| UserDetail | 拒绝(401) | 拒绝(403) | 允许 |
| AdminUserCreate | 拒绝(401) | 拒绝(403) | 允许 |
| get_usage_quantity* | 允许 | 允许 | 允许 |
| get_plc_connection_status* | 允许 | 允许 | 允许 |
| get_bill_list | screenMAC验证 | screenMAC验证 | screenMAC验证 |
