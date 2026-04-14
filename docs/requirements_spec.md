# FreeArk 需求规格说明书（逆向整理）

**版本**：1.0.0  
**整理日期**：2026-04-12  
**整理方式**：根据源代码逆向分析  
**项目路径**：`C:\Users\yanggyan\MyProject\FreeArk`

---

## 1. 项目概述

### 1.1 系统名称
FreeArk — 三恒系统计量管理平台

### 1.2 系统定位
FreeArk 是一套面向住宅楼栋的三恒系统（恒温、恒湿、恒氧）能耗计量与计费管理平台，核心职责：
- 通过西门子 S7 协议（snap7 / python-snap7）周期性采集各房间 PLC 设备的冷热量累计数据
- 经 MQTT 中间件将采集数据传输至 Django 后端并持久化到 MySQL 数据库
- 对原始 PLC 数据按日、按月进行汇聚计算，生成结构化的用量记录
- 通过 REST API 为前端（物联网触摸屏、管理后台）提供用量查询与账单查询接口
- 实时监控 PLC 设备在线/离线状态并记录历史

### 1.3 技术栈（已确认）
| 层级 | 技术 |
|------|------|
| 后端框架 | Django 5.2 + Django REST Framework |
| 数据库 | MySQL（生产）/ SQLite（开发） |
| PLC 通信 | python-snap7（西门子 S7 协议） |
| 消息队列 | MQTT（paho-mqtt） |
| 服务器 | Waitress（WSGI） |
| 认证 | Token Authentication + Session Authentication |
| 跨域 | django-corsheaders |
| 数据采集端 | Python 多线程 + PyInstaller 可打包应用 |

---

## 2. 系统架构

### 2.1 子系统划分
```
FreeArk
├── datacollection/              # 数据采集端（独立 Python 应用）
│   ├── ImprovedDataCollectionManager   # 多线程 PLC 数据采集主控
│   ├── PLCReadWriter / PLCManager      # snap7 PLC 读写封装
│   ├── MQTTClient                      # MQTT 发布客户端
│   ├── TaskScheduler                   # 采集任务调度（定时触发）
│   ├── RoomDataCollector               # 单房间数据采集器
│   └── QuantityStatistics              # 离线统计工具（读取 JSON 输出）
│
└── FreeArkWeb/backend/                # Django 后端
    ├── api/models.py                  # 数据模型层（6 个模型）
    ├── api/views.py                   # REST API 视图
    ├── api/serializers.py             # DRF 序列化器
    ├── api/mqtt_consumer.py           # MQTT 订阅消费（Django 管理命令）
    ├── api/mqtt_handlers.py           # MQTT 消息处理器（数据保存 + 状态更新）
    ├── api/daily_usage_calculator.py  # 日用量计算核心
    ├── api/monthly_usage_calculator.py# 月用量计算核心
    ├── api/plc_data_cleaner.py        # PLC 历史数据清理工具
    └── api/management/commands/       # 后台常驻服务
        ├── daily_usage_service         # 日用量计算定时服务
        ├── monthly_usage_service       # 月用量计算定时服务
        ├── mqtt_consumer_service       # MQTT 消费者服务
        └── plc_connection_monitor      # PLC 连接状态监控服务
```

### 2.2 数据流
```
PLC 设备 (西门子 S7)
    ↓ snap7 TCP/IP
PLCReadWriter (datacollection)
    ↓ JSON via MQTT topic: /datacollection/plc/to/collector/#
MQTT Broker (192.168.31.97:32795)
    ↓ paho-mqtt subscribe
MQTTConsumer (Django management command)
    ↓ PLCDataHandler.batch_save_plc_data()
PLCData 表 (MySQL)
    ↓ DailyUsageCalculator.calculate_daily_usage()（每日 00:00 触发）
UsageQuantityDaily 表
    ↓ MonthlyUsageCalculator.calculate_monthly_usage()（每月触发）
UsageQuantityMonthly 表
    ↓ REST API
前端（触摸屏 / 管理后台）
```

---

## 3. 数据模型需求

### REQ-MODEL-001：自定义用户模型（CustomUser）
- 扩展 Django AbstractUser，增加 `role`（admin/user）、`department`、`position` 字段
- 角色用于控制 API 权限（管理员可进行用户管理操作）

### REQ-MODEL-002：PLC 原始数据表（PLCData）
- 存储 MQTT 接收到的每条 PLC 读数
- 唯一约束：`(specific_part, energy_mode, usage_date)` — 每个房间每种能源模式每天只保留一条最新数据
- `specific_part` 格式：`楼栋-单元-楼层-房号`（如 `3-1-7-702`）
- `energy_mode`：`制冷` 或 `制热`（由 MQTT handler 从参数名映射：`total_cold_quantity` → `制冷`，`total_hot_quantity` → `制热`）
- `value`：BigInteger，表示 PLC 读取的累积能量值（kWh）
- 保留 7 天，超期由 `plc_data_clean_up_service` 清理

### REQ-MODEL-003：每日用量数据表（UsageQuantityDaily）
- 记录每个房间每种能源模式每天的用量
- `initial_energy`：当日起始读数（前一日末期值）
- `final_energy`：当日末期读数（当日最新 PLC 值）
- `usage_quantity = final_energy - initial_energy`
- `time_period`：日期（YYYY-MM-DD）

### REQ-MODEL-004：每月用量数据表（UsageQuantityMonthly）
- 从 `UsageQuantityDaily` 聚合，取月内 `min(initial_energy)` 和 `max(final_energy)` 计算月用量
- `usage_month`：字符串格式 `YYYY-MM`

### REQ-MODEL-005：PLC 连接状态表（PLCConnectionStatus）
- 每个 `specific_part` 唯一一条记录
- `connection_status`：`online` / `offline`
- `last_online_time`：最后一次在线的时间戳
- 超过 `timeout_threshold`（默认 600 秒）未收到数据则标记为 `offline`

### REQ-MODEL-006：PLC 状态变化历史表（PLCStatusChangeHistory）
- 每当 `PLCConnectionStatus` 发生状态变化（online↔offline）时记录一条事件
- 包含 `specific_part`、`status`、`change_time`

### REQ-MODEL-007：专有部分信息表（SpecificPartInfo）
- 维护触摸屏 MAC 地址（`screenMAC`）与 `specific_part` 的对应关系
- `screenMAC` 唯一，用于账单查询鉴权

---

## 4. 功能需求

### 4.1 用户认证与管理

#### REQ-FUNC-001：用户登录
- 接口：`POST /api/auth/login/`
- 输入：`username`、`password`
- 成功返回 Token、用户基本信息（id、username、email、role）
- 失败返回 400，含错误描述
- CSRF 豁免（`@csrf_exempt`）

#### REQ-FUNC-002：用户登出
- 接口：`POST /api/auth/logout/`
- 需要认证（Token）
- 删除 Token、清除 Session

#### REQ-FUNC-003：获取当前用户信息
- 接口：`GET /api/auth/me/`
- 需要认证
- 返回完整用户信息（含 department、position）

#### REQ-FUNC-004：用户注册
- 接口：`POST /api/auth/register/`
- 公开接口
- 需提供 `password` 和 `password2`，两者必须一致
- 注册后自动登录，返回 Token

#### REQ-FUNC-005：管理员创建用户
- 接口：`POST /api/users/create/`
- 仅 `role=admin` 的用户可调用
- 若用户名重复，返回 400 并给出明确提示

#### REQ-FUNC-006：用户列表查询
- 接口：`GET /api/users/`
- 仅管理员可访问

#### REQ-FUNC-007：用户详情/更新/删除
- 接口：`GET/PUT/PATCH/DELETE /api/users/<pk>/`
- 仅管理员可访问
- 支持修改密码（传入 `password` 字段时使用 `set_password` 正确哈希）

#### REQ-FUNC-008：修改密码
- 接口：`POST /api/change-password/`
- 需要认证
- 输入：`current_password`、`new_password`
- 须先校验当前密码正确后才允许修改

---

### 4.2 能耗数据查询

#### REQ-FUNC-010：每日用量列表查询
- 接口：`GET /api/usage/quantity/`
- 公开接口
- 支持过滤：`specific_part`、`energy_mode`、`start_time`（YYYY-MM-DD）、`end_time`（YYYY-MM-DD）
- 支持分页：`page`（默认 1）、`page_size`（默认 20）
- 按 `time_period` 升序排序
- 返回：`{success, data[...], total}`

#### REQ-FUNC-011：特定时间段汇总查询
- 接口：`GET /api/usage/quantity/specifictimeperiod/`
- 公开接口
- 按 `(specific_part, energy_mode)` 分组，计算指定时间段内 `min(initial_energy)` 至 `max(final_energy)` 的汇总用量
- 支持同样的过滤参数和分页（按 specific_part + energy_mode 升序）
- 返回每组：`{specific_part, building, unit, room_number, energy_mode, initial_energy, final_energy, usage_quantity, time_period}`

#### REQ-FUNC-012：月度用量查询
- 接口：`GET /api/usage/quantity/monthly/`
- 公开接口
- 支持过滤：`specific_part`、`building`、`unit`、`room_number`、`energy_mode`、`usage_month`、`start_month`、`end_month`
- 支持分页：`page`（默认 1）、`page_size`（默认 10）
- 按 `specific_part`、`energy_mode`、`usage_month` 升序排序

---

### 4.3 计费管理

#### REQ-FUNC-020：历史用能账单查询
- 接口：`POST /api/billing/list/`
- 公开接口，CSRF 豁免
- 认证方式：HTTP 请求头 `screenMAC`（通过 `SpecificPartInfo` 表映射到 `specific_part`）
- 若请求头缺少 `screenMAC` → 返回 400
- 若 `screenMAC` 未注册 → 返回 404
- 请求体参数：
  - `startDate`：支持 `YYYYMM` 或 `YYYY-MM` 格式
  - `endDate`：同上
  - `energyType`：`制冷` / `制热`（其他值则不过滤）
- 账单单价：固定 `0.28元/kWh`（硬编码）
- 响应格式（数组，不分页）：
  ```json
  {
    "code": 200,
    "message": "成功",
    "data": [{
      "id": ...,
      "familyName": "X栋X单元XXX",
      "modeName": "制冷/制热",
      "chargeItems": "制冷费/制热费",
      "usageAmount": "100",
      "basicPrice": "0.28",
      "billingCycle": "2025年01月",
      "billingDate": "2025-01-31",
      "billAmount": "28.00"
    }]
  }
  ```

---

### 4.4 PLC 状态监控

#### REQ-FUNC-030：PLC 连接状态列表
- 接口：`GET /api/plc/connection-status/`
- 公开接口
- 支持过滤：`building`、`unit`、`connection_status`（online/offline）
- 支持分页：`page`（默认 1）、`page_size`（默认 10）
- 响应除数据列表外还包含全局统计：`{online_count, offline_count, total_devices, online_rate}`

#### REQ-FUNC-031：PLC 设备状态详情
- 接口：`GET /api/plc/connection-status/<specific_part>/`
- 公开接口
- 设备不存在返回 404

#### REQ-FUNC-032：PLC 状态变化历史
- 接口：`GET /api/plc/status-change-history/<specific_part>/`
- 公开接口
- 按 `change_time` 倒序
- 支持分页：`page`（默认 1）、`page_size`（默认 20）

---

### 4.5 系统辅助

#### REQ-FUNC-040：CSRF Token 获取
- 接口：`GET /api/get-csrf-token/`
- 公开接口
- 在响应体和 Cookie 中同时返回 csrftoken

#### REQ-FUNC-041：健康检查
- 接口：`GET /api/health/`
- 公开接口
- 返回 `{"status": "ok", "message": "..."}`

---

## 5. 后台服务需求

### REQ-SVC-001：MQTT 消费者服务（mqtt_consumer_service）
- 订阅 MQTT Topic：`/datacollection/plc/to/collector/#`
- 支持多种消息格式（详见 mqtt_handlers.py）：
  - `improved_data_collection_manager` 格式：`{device_id: {data: {param_key: {success, value, ...}}}}`
  - 新格式：包含 `data` 字段的字典
  - 旧格式：`{device_id: {param_key: value}}`
- 对成功的数据点进行 upsert（按唯一键 `specific_part + energy_mode + usage_date`）
- 同时触发连接状态更新（有任意成功数据 → online，否则 → offline）
- 连接断开时自动重连

### REQ-SVC-002：日用量计算服务（daily_usage_service）
- 默认每天 `00:00` 运行
- 可通过 `--time` 参数指定运行时间，通过 `--run-once --date` 参数手动触发
- 核心逻辑（`DailyUsageCalculator.calculate_daily_usage`）：
  1. 查询目标日期的所有 PLCData 记录（每个 specific_part + energy_mode 一条）
  2. 批量处理（每批 100 条）：
     - 若当日 UsageQuantityDaily 已存在 → 更新 final_energy 和 usage_quantity
     - 若不存在 → 新建记录（initial_energy = final_energy = 当前值，usage_quantity = 0）
     - 为次日创建 initial_energy 记录（桥接数据）
  3. 处理前一天 final_energy 为 NULL 的记录（补零）
- 使用 `bulk_create` / `bulk_update` 提高性能
- `_specific_part_cache` 缓存解析结果

### REQ-SVC-003：月用量计算服务（monthly_usage_service）
- 从 `UsageQuantityDaily` 按 `(specific_part, energy_mode)` 分组
- 月内 `initial_energy = min(initial_energy)`，`final_energy = max(final_energy)`
- 若 `final_energy < initial_energy` 则 `usage_quantity = 0`（防止数据异常）
- 批量处理（每批 1000 条），使用事务

### REQ-SVC-004：PLC 连接状态监控服务（plc_connection_monitor）
- 可配置检查间隔（`--check-interval`，默认 300 秒）
- 可配置超时阈值（`--timeout-threshold`，默认 600 秒）
- 将 `last_online_time` 超过阈值的设备标记为 `offline`
- 状态变化时写入 `PLCStatusChangeHistory`

### REQ-SVC-005：PLC 数据清理服务（plc_data_clean_up_service）
- 定期删除超过指定天数（默认 7 天）的 PLCData 记录

---

## 6. 数据采集端需求

### REQ-DC-001：多线程 PLC 读取
- 支持多楼栋并发采集（线程池，默认 10 个 worker）
- 每栋楼的设备通过 `resource/<楼栋>_data.json` 配置文件描述
- 参数配置通过 `resource/plc_config.json` 描述（`db_num`, `offset`, `length`, `data_type`）
- 关键参数：`total_cold_quantity`（制冷累积量）、`total_hot_quantity`（制热累积量）
- 连接失败不写入 MQTT（跳过）

### REQ-DC-002：PLC 数据读取重试
- `read_db_data` 方法支持最多 2 次重试（`max_retries=2`）
- 读取范围越界（offset + length > 65535）时直接返回失败

### REQ-DC-003：MQTT 发布
- 发布 Topic：`/datacollection/plc/to/collector/<楼栋标识>`
- Payload 格式：JSON，包含 device_id（`specific_part`）、PLC IP、各参数数据
- 支持连接池（`mqtt_client_pool.py`）

### REQ-DC-004：任务调度
- `TaskScheduler` 按配置文件（`resource/scheduler_config.json`）的 `interval` 周期触发采集
- 支持优雅停止（SIGINT / SIGTERM 信号处理）
- 支持 PyInstaller 打包为 Windows 可执行文件（`build_exe.py`）

---

## 7. 非功能需求

### REQ-NFR-001：性能
- PLCData、UsageQuantityDaily、UsageQuantityMonthly 均建有覆盖常用查询的复合索引
- 计算服务均使用 `bulk_create` / `bulk_update`，避免逐条 INSERT/UPDATE
- MQTT handler 采用批量 upsert（先查后批量写）

### REQ-NFR-002：可靠性
- MQTT 连接断开时自动重连
- 数据库操作使用 `transaction.atomic()` 保证原子性
- 数据库连接定期检查（`close_old_connections()`）

### REQ-NFR-003：安全
- 生产环境不开启 DEBUG
- `SECRET_KEY` 从环境变量读取
- Token 认证用于 API 保护
- CSRF 仅在必要的公开 POST 接口豁免
- ALLOWED_HOSTS 白名单控制

### REQ-NFR-004：可观测性
- 多个专用日志文件（轮转，5MB/文件，保留 5 份）：
  - `django.log`、`daily_usage_service.log`、`monthly_usage_service.log`
  - `mqtt_consumer.log`、`mqtt_consumer_service.log`、`plc_cleanup_service.log`
- 数据采集端使用统一 `log_config_manager` 管理日志级别

### REQ-NFR-005：可部署性
- 后端通过 Waitress 以 WSGI 方式部署（`start_waitress_server.py`）
- 前端通过 `frontend/server.py` 提供静态文件服务
- 数据采集端支持 PyInstaller 打包为 EXE（`build_exe.py`、`setup.py`）

---

## 8. 约束与假设

| 编号 | 约束/假设 |
|------|---------|
| C-001 | 账单单价固定为 0.28 元/kWh，当前硬编码于 `views.py`，未来需配置化 |
| C-002 | 专有部分标识格式固定为 `楼栋-单元-楼层-房号`（4 段）或 `楼栋-单元-房号`（3 段） |
| C-003 | `realestateId` 和 `familyId` 在账单响应中为固定占位值（67754642 / 521697181），未来需关联实际数据 |
| C-004 | MQTT Broker 地址当前硬编码为 `192.168.31.97:32795`，可通过 `mqtt_config.json` 或环境变量覆盖 |
| C-005 | 时区为 `Asia/Shanghai`，`USE_TZ = False`（数据库存本地时间） |
| C-006 | 当前无 HTTPS 强制跳转（`SECURE_SSL_REDIRECT = False`），生产环境建议启用 |
