# 每日用量计算管理命令

## 功能说明

这个Django管理命令用于计算和更新每日能源用量数据，主要功能包括：

- 读取`plc_data`表中指定自然日的数据
- 按照`specific_part`分组，找出累计制热量和制冷量的最早和最晚上报值
- 在`usage_quantity_daily`表中查找当日记录，并根据情况创建或更新记录
- 创建次日记录，将当日最晚上报值设置为次日的初始值

## 使用方法

### 命令格式

```bash
python manage.py calculate_daily_usage [options]
```

### 可选参数

- `--date YYYY-MM-DD`：指定要计算的日期，默认为昨天
- `--run-once`：仅运行一次计算，不启动周期性任务
- `--schedule-time HH:MM`：设置每日执行时间，默认为凌晨00:01

### 运行示例

#### 1. 运行一次，计算昨天的数据

```bash
python manage.py calculate_daily_usage --run-once
```

#### 2. 运行一次，计算指定日期的数据

```bash
python manage.py calculate_daily_usage --date 2025-10-27 --run-once
```

#### 3. 启动周期性任务，每天凌晨2点执行

```bash
python manage.py calculate_daily_usage --schedule-time 02:00
```

## 工作原理

### 数据处理流程

1. **获取数据范围**：根据指定日期确定查询的时间范围（00:00:00 到 23:59:59）
2. **分组处理**：按照`specific_part`和`energy_mode`（累计制热量/累计制冷量）分组
3. **计算初始和最终值**：对每组数据，找出最早和最晚上报的`value`值
4. **记录管理**：
   - 如果当日记录不存在：创建新记录，设置初始值、最终值和使用量（差值）
   - 如果当日记录已存在：更新最终值和使用量
5. **次日记录**：为每个特定部分和模式创建次日记录，初始值为当日最终值

### 数据解析

命令会尝试解析`specific_part`来获取`building`、`unit`和`room_number`信息，支持以下格式：
- `building-unit-room_number`
- `building-unit-room_number-suffix`（如"9-1-31-3104"）
- 单一标识符（作为`room_number`）

## 注意事项

1. **数据库事务**：所有数据库操作都在原子事务中执行，确保数据一致性
2. **日志记录**：运行过程中的关键信息会输出到控制台，并记录到Django日志
3. **错误处理**：遇到错误时会记录详细信息并终止事务，确保数据不会部分更新
4. **并发安全**：通过数据库事务和唯一约束确保并发安全

## 停止服务

对于周期性运行的服务，可以通过以下方式停止：

- 按 `Ctrl+C` 发送中断信号
- 在Windows任务管理器中终止进程

## 故障排除

### 常见问题

1. **日期格式错误**：确保使用`YYYY-MM-DD`格式指定日期
2. **数据库连接问题**：检查数据库配置和连接状态
3. **权限问题**：确保运行命令的用户有足够权限访问数据库

### 日志查询

服务运行日志可在Django日志文件中查看，默认为：
`c:/Users/yanggyan/TRAE/FreeArk/logs/django.log`

## 依赖

- Django
- schedule 库（用于定时任务）

确保在运行前已安装所有必要的依赖。