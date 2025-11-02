# PLC数据定时清理服务使用说明

## 概述

此Django管理命令提供了一个定时调度服务，用于自动清理PLC数据表中的历史数据。服务支持灵活的时间配置，可以设置为每周日凌晨自动运行，也可以根据需要自定义执行频率。

## 文件结构

- `schedule_plc_cleanup.py` - 定时调度服务主文件
- `../plc_data_cleaner.py` - 实际执行数据清理的功能模块（需单独创建）

## 使用方法

### 基本用法

在Django项目根目录下执行以下命令启动定时清理服务：

```bash
python manage.py schedule_plc_cleanup
```

默认配置：
- 清理7天前的数据
- 每周日凌晨0点0分执行
- 作为长期运行的服务保持在前台

### 命令行参数

#### 1. 指定保留天数

```bash
python manage.py schedule_plc_cleanup --days=30
```

此命令将配置服务清理30天前的数据。

#### 2. 使用cron表达式配置执行时间

```bash
python manage.py schedule_plc_cleanup --cron="30 2 * * 1"
```

此命令将配置服务在每周一凌晨2点30分执行清理任务。

Cron表达式格式为：`分 时 日 月 周`

#### 3. 使用简单的时间间隔

```bash
python manage.py schedule_plc_cleanup --interval=daily
```

支持的时间间隔值：
- `daily` - 每天凌晨0点0分
- `weekly` - 每周日凌晨0点0分
- `monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday`, `sunday` - 对应星期的凌晨0点0分

#### 4. 仅执行一次

```bash
python manage.py schedule_plc_cleanup --once
```

此命令将立即执行一次清理任务，然后退出，不启动长期运行的服务。

#### 5. 组合使用参数

```bash
python manage.py schedule_plc_cleanup --days=14 --cron="0 1 * * *"  # 每天凌晨1点清理14天前的数据
```

## 后台运行

### 在Linux系统上

使用nohup命令使服务在后台持续运行：

```bash
nohup python manage.py schedule_plc_cleanup > plc_cleanup.log 2>&1 &
```

### 在Windows系统上

使用Windows任务计划程序或创建批处理文件：

```batch
@echo off
cd /d "项目路径"
python manage.py schedule_plc_cleanup
```

然后可以使用Windows任务计划程序设置此批处理文件在系统启动时运行。

## 日志

服务会输出日志信息到控制台，同时也会记录到Python日志系统中。日志包含以下信息：
- 服务启动和停止事件
- 清理任务执行时间和结果
- 错误和警告信息

## 注意事项

1. 确保Django环境已正确配置，包括数据库连接等
2. 长期运行的服务需要确保系统稳定性，建议配置为系统服务或使用进程管理工具
3. 对于大量数据的清理操作，可能需要较长时间，请确保有足够的系统资源
4. 建议先使用`--once`参数进行测试，确认清理逻辑正确后再启动定时服务

## 示例配置

### 配置1：每周日凌晨2点清理14天前的数据

```bash
python manage.py schedule_plc_cleanup --days=14 --cron="0 2 * * 0"
```

### 配置2：每天凌晨3点清理30天前的数据

```bash
python manage.py schedule_plc_cleanup --days=30 --interval=daily
```

### 配置3：每月1日凌晨0点清理90天前的数据

```bash
python manage.py schedule_plc_cleanup --days=90 --cron="0 0 1 * *"
```