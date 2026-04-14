# FreeArkWeb 实现计划（逆向工程版）

<!-- file_header
author_agent: sub_agent_software_developer
phase: PHASE_05
project: FreeArkWeb
created_at: 2026-04-14
status: DRAFT
note: 代码已存在，本文档为逆向生成的实现记录
-->

---

## 1. 已实现模块状态

| 模块 | 文件 | 状态 | 覆盖需求 |
|------|------|------|---------|
| 数据模型 | api/models.py | 已实现 | REQ-FUNC-001~026（数据层） |
| 序列化器 | api/serializers.py | 已实现 | REQ-FUNC-001~026（数据校验） |
| REST 视图 | api/views.py | 已实现 | REQ-FUNC-001~026 |
| URL 路由 | api/urls.py | 已实现 | 所有接口端点 |
| 日用量计算器 | api/daily_usage_calculator.py | 已实现 | 日用量计算逻辑 |
| 月用量计算器 | api/monthly_usage_calculator.py | 已实现 | 月用量聚合逻辑 |
| MQTT 处理器 | api/mqtt_handlers.py | 已实现 | PLC 数据采集和状态监控 |
| MQTT 消费者 | api/mqtt_consumer.py | 已实现 | MQTT 客户端 |
| PLC 数据清理 | api/plc_data_cleaner.py | 已实现 | 过期数据清理 |
| 管理命令 | api/management/commands/ | 已实现 | 后台服务入口 |

---

## 2. 关键实现细节记录

### 2.1 用户模型扩展

- 继承 `AbstractUser`，添加 `role`、`department`、`position` 字段
- 重写 `groups` 和 `user_permissions` 的 `related_name` 以避免 Django 默认冲突
- `AUTH_USER_MODEL = 'api.CustomUser'` 在 settings.py 中配置

### 2.2 账单查询特殊逻辑

- screenMAC 从 `request.META['HTTP_SCREENMAC']` 获取
- 日期格式兼容：YYYY-MM（7位）和 YYYYMM（6位），6位时自动转换
- 计费单价硬编码为 0.28 元/kWh
- familyName 解析：specific_part 按 "-" 分割，building=parts[0], unit=parts[1], room_number=parts[3]（4段格式）

### 2.3 PLC 数据 Upsert 策略

- `update_or_create` 按 (specific_part, energy_mode, usage_date) 唯一键执行
- 状态变更历史只在 connection_status 发生实际变化时写入

### 2.4 特定时间段汇总逻辑

- 先获取满足条件的 (specific_part, energy_mode) 唯一组合列表
- 对每个组合使用 `aggregate(Min, Max)` 计算边界值
- 分页作用于组合列表，而非原始记录

---

## 3. 未实现功能（Gap 分析）

无重大 Gap。所有 REQ-FUNC-001~026 均有对应实现。

以下为已知的设计局限（非缺陷）：
- 账单单价（0.28）硬编码，不支持动态配置
- 账单的 realestateId（67754642）和 familyId（521697181）为固定值
- 注册接口（REQ-FUNC-004）为公开接口，无邀请码机制
