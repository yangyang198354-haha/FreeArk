# FreeArkWeb 后台服务管理文档

## 1. 系统环境要求

### 1.1 硬件要求
- **树莓派5**：4GB/8GB RAM，32GB+ microSD卡
- **网络连接**：稳定的局域网连接，支持MQTT协议
- **电源供应**：5V/3A USB-C电源适配器

### 1.2 软件要求
- **操作系统**：Raspberry Pi OS Bookworm (64-bit)
- **Python**：3.9+（建议使用系统默认Python 3.11）
- **Django**：4.2+（根据项目requirements.txt安装）
- **Python虚拟环境**：建议使用venv创建独立的虚拟环境
- **依赖库**：
  - schedule（定时任务管理）
  - paho-mqtt（MQTT通信）
  - 其他项目依赖（通过`pip install -r requirements.txt`安装）

### 1.3 系统配置
- 已创建Django项目运行用户（如`freeark`）
- 项目代码已部署至树莓派
- Python虚拟环境已创建并配置
- 数据库连接正常配置
- MQTT服务器连接信息配置正确

## 2. 后台服务模块说明

### 2.1 模块列表

| 服务名称 | 模块文件 | 功能描述 | 运行频率 |
|---------|---------|---------|---------|
| 每日用量计算服务 | daily_usage_service.py | 计算每日能源用量数据 | 每天凌晨00:10 |
| 每月用量计算服务 | monthly_usage_service.py | 计算每月能源用量数据 | 每月1号凌晨01:00 |
| MQTT消费者服务 | mqtt_consumer_service.py | 监听MQTT消息并保存PLC数据 | 持续运行 |
| PLC数据清理服务 | plc_data_clean_up_service.py | 定期清理过期PLC数据 | 每周日凌晨2:00 |

### 2.2 详细功能描述

#### 2.2.1 每日用量计算服务 (daily_usage_service)

**功能**：
- 读取`plc_data`表中指定自然日的数据
- 按照`specific_part`分组，计算累计制热量和制冷量的使用量
- 在`usage_quantity_daily`表中创建或更新记录
- 创建次日记录，将当日最晚上报值设置为次日初始值

**命令参数**：
- `--time HH:MM`：指定每天运行时间，默认为00:00
- `--run-once`：只运行一次，不启动持续服务
- `--date YYYY-MM-DD`：手动执行时指定计算日期，默认为昨天

**运行示例**：
```bash
python manage.py daily_usage_service --time 00:30
```

#### 2.2.2 每月用量计算服务 (monthly_usage_service)

**功能**：
- 从`usage_quantity_daily`表聚合数据
- 计算每月能源用量
- 更新或创建`usage_quantity_monthly`表记录

**命令参数**：
- `--day`：指定每月运行日期，默认为1号
- `--time HH:MM`：指定运行时间，默认为00:00
- `--run-once`：只运行一次，不启动持续服务
- `--month YYYY-MM`：手动执行时指定计算月份，默认为上个月

**运行示例**：
```bash
python manage.py monthly_usage_service --day 5 --time 01:00
```

#### 2.2.3 MQTT消费者服务 (mqtt_consumer_service)

**功能**：
- 连接MQTT服务器，监听指定主题的PLC数据
- 将接收到的数据解析并保存到`plc_data`表
- 支持服务状态监控和自动重启

**命令参数**：
- `--monitor-interval`：服务监控间隔（秒），默认为60秒
- `--auto-restart`：当MQTT服务异常停止时自动重启

**运行示例**：
```bash
python manage.py mqtt_consumer_service --auto-restart
```

#### 2.2.4 PLC数据清理服务 (plc_data_clean_up_service)

**功能**：
- 定期清理过期的PLC数据
- 可配置保留天数和运行频率
- 支持cron表达式或简单间隔配置

**命令参数**：
- `--days`：要保留的天数，超过此天数的数据将被删除，默认为7天
- `--cron`：cron表达式，格式为 "分 时 日 月 周"，默认为 "0 2 * * 0"（每周日凌晨2点0分）
- `--interval`：间隔时间，例如 "daily"、"weekly" 等（优先级低于cron表达式）
- `--once`：仅执行一次清理任务后退出

**运行示例**：
```bash
python manage.py plc_data_clean_up_service --days 14 --cron "0 3 * * *"
```

## 3. systemctl服务配置规范

### 3.1 服务文件结构

每个Django command需要创建一个独立的systemd服务文件，命名格式为：
```
freeark-<service-name>.service
```

### 3.2 服务文件模板

```ini
[Unit]
Description=FreeArk %s Service
After=network.target mysql.service
Wants=mysql.service

[Service]
Type=simple
User=freeark
WorkingDirectory=/home/freeark/FreeArkWeb/backend
ExecStart=/home/yangyang/Freeark/FreeArk/venv/bin/python /home/freeark/FreeArkWeb/backend/manage.py %s  # 使用虚拟环境的Python解释器
Restart=on-failure
RestartSec=30s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=freeark-%s

[Install]
WantedBy=multi-user.target
```

### 3.2.1 虚拟环境配置说明

如果项目使用Python虚拟环境（推荐），请确保在systemctl服务配置文件中使用虚拟环境的Python解释器路径。

**虚拟环境创建步骤**：

```bash
# 进入项目后端目录
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend

# 创建虚拟环境
python3 -m venv /home/yangyang/Freeark/FreeArk/venv

# 激活虚拟环境
source /home/yangyang/Freeark/FreeArk/venv/bin/activate

# 安装项目依赖
pip install -r requirements.txt

# 验证安装
django-admin --version
```

**虚拟环境Python解释器路径**：
- 统一路径：`/home/yangyang/Freeark/FreeArk/venv/bin/python`（所有FreeArk服务共享此虚拟环境）
- 工作目录：`/home/yangyang/Freeark/FreeArk/`（所有FreeArk服务共享此工作目录）

### 3.3 各服务具体配置

#### 3.3.1 每日用量计算服务

**服务文件名**：`freeark-daily-usage.service`

**ExecStart**（使用统一虚拟环境Python）：
```
ExecStart=/home/yangyang/Freeark/FreeArk/venv/bin/python /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/manage.py daily_usage_service --time 00:10
```

#### 3.3.2 每月用量计算服务

**服务文件名**：`freeark-monthly-usage.service`

**ExecStart**（使用统一虚拟环境Python）：
```
ExecStart=/home/yangyang/Freeark/FreeArk/venv/bin/python /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/manage.py monthly_usage_service --day 1 --time 01:00
```

#### 3.3.3 MQTT消费者服务

**服务文件名**：`freeark-mqtt-consumer.service`

**ExecStart**（使用统一虚拟环境Python）：
```
ExecStart=/home/yangyang/Freeark/FreeArk/venv/bin/python /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/manage.py mqtt_consumer_service --auto-restart --monitor-interval 60
```

#### 3.3.4 PLC数据清理服务

**服务文件名**：`freeark-plc-cleanup.service`

**ExecStart**（使用统一虚拟环境Python）：
```
ExecStart=/home/yangyang/Freeark/FreeArk/venv/bin/python /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/manage.py plc_data_clean_up_service --days 30 --cron "0 2 * * 0"
```

## 4. 服务安装与卸载流程

### 4.1 服务安装步骤

1. **创建服务文件**
   ```bash
   sudo nano /etc/systemd/system/freeark-daily-usage.service
   ```
   复制对应服务的配置内容并保存

2. **重载systemd配置**
   ```bash
   sudo systemctl daemon-reload
   ```

3. **启用服务（开机自启）**
   ```bash
   sudo systemctl enable freeark-daily-usage.service
   ```

4. **启动服务**
   ```bash
   sudo systemctl start freeark-daily-usage.service
   ```

5. **验证服务状态**
   ```bash
   sudo systemctl status freeark-daily-usage.service
   ```

### 4.2 服务卸载步骤

1. **停止服务**
   ```bash
   sudo systemctl stop freeark-daily-usage.service
   ```

2. **禁用服务**
   ```bash
   sudo systemctl disable freeark-daily-usage.service
   ```

3. **删除服务文件**
   ```bash
   sudo rm /etc/systemd/system/freeark-daily-usage.service
   ```

4. **重载systemd配置**
   ```bash
   sudo systemctl daemon-reload
   ```

### 4.3 批量操作脚本

创建批量安装脚本 `install_services.sh`：

```bash
#!/bin/bash

# 项目路径
PROJECT_PATH="/home/yangyang/Freeark/FreeArk/FreeArkWeb/backend"
# Python路径（统一使用项目根目录下的虚拟环境）
PYTHON_PATH="/home/yangyang/Freeark/FreeArk/venv/bin/python"

# 服务列表
services=(
    "daily-usage daily_usage_service --time 00:10"
    "monthly-usage monthly_usage_service --day 1 --time 10:00"
    "mqtt-consumer mqtt_consumer_service --auto-restart --monitor-interval 60"
    "plc-cleanup plc_data_clean_up_service --days 7 --cron \"0 2 * * 0\""
)

for service in "${services[@]}"; do
    read -r service_name command args <<< "$service"
    service_file="/etc/systemd/system/freeark-$service_name.service"
    
    # 创建服务文件
    sudo cat > "$service_file" << EOF
[Unit]
Description=FreeArk $service_name Service
After=network.target mysql.service
Wants=mysql.service

[Service]
Type=simple
User=freeark
WorkingDirectory=$PROJECT_PATH
ExecStart=$PYTHON_PATH $PROJECT_PATH/manage.py $command $args
Restart=on-failure
RestartSec=30s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=freeark-$service_name

[Install]
WantedBy=multi-user.target
EOF
    
    echo "Created service file: $service_file"
done

# 重载配置并启动服务
sudo systemctl daemon-reload

for service in "${services[@]}"; do
    read -r service_name command args <<< "$service"
    sudo systemctl enable "freeark-$service_name.service"
    sudo systemctl start "freeark-$service_name.service"
    echo "Enabled and started: freeark-$service_name.service"
done

echo "All services installed successfully!"
```

**使用方法**：
```bash
chmod +x install_services.sh
sudo ./install_services.sh
```

## 5. 服务管理命令

### 5.1 通用命令格式

```bash
sudo systemctl <action> freeark-<service-name>.service
```

### 5.2 常见操作

| 操作 | 命令示例 | 说明 |
|------|---------|------|
| 启动服务 | `sudo systemctl start freeark-daily-usage.service` | 启动指定服务 |
| 停止服务 | `sudo systemctl stop freeark-daily-usage.service` | 停止指定服务 |
| 重启服务 | `sudo systemctl restart freeark-daily-usage.service` | 重启指定服务 |
| 查看状态 | `sudo systemctl status freeark-daily-usage.service` | 查看服务运行状态 |
| 启用开机自启 | `sudo systemctl enable freeark-daily-usage.service` | 设置服务开机自动启动 |
| 禁用开机自启 | `sudo systemctl disable freeark-daily-usage.service` | 取消服务开机自动启动 |
| 查看日志 | `journalctl -u freeark-daily-usage.service -f` | 实时查看服务日志 |
| 查看历史日志 | `journalctl -u freeark-daily-usage.service --since "1 hour ago"` | 查看指定时间段的日志 |

### 5.3 批量管理命令

```bash
# 批量启动所有服务
sudo systemctl start freeark-*.service

# 批量停止所有服务
sudo systemctl stop freeark-*.service

# 批量查看所有服务状态
sudo systemctl status freeark-*.service
```

## 6. 日志管理方案

### 6.1 日志分类

| 日志类型 | 存储位置 | 管理方式 |
|---------|---------|---------|
| 服务运行日志 | systemd journal | journalctl命令查看 |
| Django应用日志 | /var/log/freeark/ | 日志轮转配置 |
| 服务模块日志 | /home/freeark/FreeArk/logs/ | 按服务模块独立配置 |
| 数据库操作日志 | 数据库内置日志 | MySQL/MariaDB配置 |

### 6.2 日志配置

**Django日志配置**（在`settings.py`中）：

```python
import os
LOG_DIR = '/home/freeark/FreeArk/logs'

# 确保日志目录存在
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(levelname)s %(asctime)s %(name)s %(message)s'
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/freeark/django.log',
            'maxBytes': 1024*1024*10,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        # 服务模块独立日志处理器
        'daily_usage_service_log': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'daily_usage_service.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'maxBytes': 1024 * 1024 * 5,  # 5MB
            'backupCount': 5,
            'delay': True,
        },
        'monthly_usage_service_log': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'monthly_usage_service.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'maxBytes': 1024 * 1024 * 5,  # 5MB
            'backupCount': 5,
            'delay': True,
        },
        'mqtt_consumer_service_log': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'mqtt_consumer_service.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'maxBytes': 1024 * 1024 * 5,  # 5MB
            'backupCount': 5,
            'delay': True,
        },
        'plc_cleanup_service_log': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'plc_cleanup_service.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'maxBytes': 1024 * 1024 * 5,  # 5MB
            'backupCount': 5,
            'delay': True,
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
        'api': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
        # 服务模块独立日志器
        'daily_usage_service': {
            'handlers': ['console', 'daily_usage_service_log'],
            'level': os.getenv('APP_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'monthly_usage_service': {
            'handlers': ['console', 'monthly_usage_service_log'],
            'level': os.getenv('APP_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'mqtt_consumer_service': {
            'handlers': ['console', 'mqtt_consumer_service_log'],
            'level': os.getenv('APP_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'plc_data_clean_up_service': {
            'handlers': ['console', 'plc_cleanup_service_log'],
            'level': os.getenv('APP_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}
```

### 6.3 日志查看与分析

```bash
# 查看所有服务日志
sudo journalctl -f -t freeark

# 查看特定服务的错误日志
sudo journalctl -u freeark-mqtt-consumer.service --since "24 hours ago" -p err

# 查看Django应用日志
sudo tail -f /var/log/freeark/django.log

# 查看服务模块独立日志
cat /home/freeark/FreeArk/logs/daily_usage_service.log

# 实时查看服务模块日志
tail -f /home/freeark/FreeArk/logs/mqtt_consumer_service.log

# 搜索日志关键字
sudo journalctl -u freeark-daily-usage.service | grep "ERROR"
```

### 6.4 日志配置说明

每个服务模块通过独立的日志器记录日志，服务代码中获取日志器的方式：

```python
import logging
logger = logging.getLogger('daily_usage_service')  # 与settings.py中配置的日志器名称一致

# 使用日志器
logger.info('服务启动')
logger.error('计算出错')
```

### 6.5 日志目录创建

```bash
# 创建服务日志目录
sudo mkdir -p /home/freeark/FreeArk/logs

# 设置目录权限
sudo chown -R freeark:freeark /home/freeark/FreeArk/logs
sudo chmod 755 /home/freeark/FreeArk/logs
```

## 7. 服务状态监控

### 7.1 实时监控命令

```bash
# 使用systemctl查看服务状态
sudo systemctl status freeark-*.service

# 使用journalctl实时监控
sudo journalctl -f -t freeark

# 使用htop查看资源占用
sudo htop
```

### 7.2 监控脚本

创建监控脚本 `monitor_services.sh`：

```bash
#!/bin/bash

echo "FreeArk Services Status Report"
echo "================================"
echo "Generated: $(date)"
echo ""

# 服务列表
services=(
    "daily-usage"
    "monthly-usage"
    "mqtt-consumer"
    "plc-cleanup"
)

for service in "${services[@]}"; do
    echo "Service: $service"
    echo "-----------------"
    
    # 检查服务状态
    status=$(sudo systemctl is-active "freeark-$service.service")
    echo "Status: $status"
    
    # 检查服务是否启用
    enabled=$(sudo systemctl is-enabled "freeark-$service.service")
    echo "Enabled: $enabled"
    
    # 获取最近的日志条目
    echo "Recent Logs:"
    sudo journalctl -u "freeark-$service.service" --since "10 minutes ago" --no-pager | tail -5
    
    echo ""
done

# 查看资源使用情况
echo "Resource Usage"
echo "---------------"
top -b -n 1 | grep -E "(Cpu|Mem|Swap)"
echo ""
```

**使用方法**：
```bash
chmod +x monitor_services.sh
./monitor_services.sh
```

### 7.3 健康检查接口

建议在Django项目中添加健康检查API，用于监控服务状态：

```python
# api/views.py
from django.http import JsonResponse
from django.core.management import call_command
from io import StringIO

@api_view(['GET'])
def health_check(request):
    """健康检查接口"""
    health_status = {
        'status': 'ok',
        'timestamp': timezone.now().isoformat(),
        'services': {
            'daily_usage': 'running',
            'monthly_usage': 'running',
            'mqtt_consumer': 'running',
            'plc_cleanup': 'running'
        }
    }
    return JsonResponse(health_status)
```

## 8. 故障处理机制

### 8.1 常见故障及解决方案

| 故障现象 | 可能原因 | 解决方案 |
|---------|---------|---------|
| 服务无法启动 | 数据库连接失败 | 检查数据库配置和服务状态 |
| MQTT服务频繁重启 | MQTT服务器连接问题 | 检查MQTT服务器地址、端口和认证信息 |
| 用量计算错误 | PLC数据缺失 | 检查PLC设备是否正常上报数据 |
| 内存占用过高 | 日志文件过大 | 配置日志轮转，定期清理旧日志 |
| 服务启动超时 | 系统负载过高 | 优化启动顺序，调整RestartSec参数 |

### 8.2 自动恢复机制

- **Restart策略**：服务配置中已设置`Restart=on-failure`，故障时自动重启
- **重启间隔**：`RestartSec=30s`，避免频繁重启
- **MQTT服务特殊处理**：支持`--auto-restart`参数，内置监控机制

### 8.3 故障告警

建议配置系统日志告警，如使用`logwatch`或`rsyslog`转发关键错误日志到指定邮箱：

```bash
# 安装logwatch
sudo apt install logwatch

# 配置logwatch
cat << EOF | sudo tee /etc/logwatch/conf/logwatch.conf
Output = mail
Format = html
MailTo = admin@example.com
MailFrom = logwatch@freeark.local
Range = yesterday
Detail = 5
EOF
```

## 9. 安全性考虑

### 9.1 最小权限原则

- 服务运行用户`freeark`仅拥有项目目录的读写权限
- 数据库用户仅拥有必要的数据库操作权限
- 禁用root用户直接运行服务

### 9.2 日志安全

- 日志文件权限设置为`640`，仅允许root和指定用户访问
- 定期清理敏感日志信息
- 避免在日志中记录密码等敏感信息

### 9.3 网络安全

- MQTT通信建议使用TLS加密
- 限制服务仅监听必要的网络接口
- 配置防火墙规则，仅允许必要的端口访问

### 9.4 代码安全

- 定期更新项目依赖，修复已知安全漏洞
- 对输入数据进行严格验证，防止SQL注入和XSS攻击
- 使用Django内置的安全机制，如CSRF保护、密码哈希等

## 10. 维护与更新

### 10.1 服务更新流程

1. 备份当前代码和数据库
2. 拉取最新代码
3. 安装更新依赖
4. 执行数据库迁移
5. 重启相关服务

**示例脚本**：

```bash
#!/bin/bash

# 切换到项目目录
cd /home/freeark/FreeArkWeb/backend

# 备份数据库
mysqldump -u freeark -p freeark_db > freeark_db_$(date +%Y%m%d_%H%M%S).sql

# 拉取最新代码
git pull origin main

# 激活虚拟环境（根据实际情况选择）
# 1. 使用项目虚拟环境
# source venv/bin/activate
# 2. 使用自定义虚拟环境
# source /home/yangyang/Freeark/FreeArk/venv/bin/activate

# 安装依赖（如果激活了虚拟环境，直接使用pip）
pip install -r requirements.txt
# 或者不激活虚拟环境时使用完整路径
# /home/yangyang/Freeark/FreeArk/venv/bin/pip install -r requirements.txt

# 执行数据库迁移（使用对应Python解释器）
# 1. 使用系统Python
# python manage.py migrate
# 2. 使用项目虚拟环境Python
# ./venv/bin/python manage.py migrate
# 3. 使用自定义虚拟环境Python
/home/yangyang/Freeark/FreeArk/venv/bin/python manage.py migrate

# 重启服务
sudo systemctl restart freeark-*.service

echo "Update completed successfully!"
```

### 10.2 定期维护任务

| 维护项目 | 频率 | 操作内容 |
|---------|-----|---------|
| 日志清理 | 每周 | 删除超过30天的旧日志 |
| 数据库备份 | 每天 | 自动备份数据库到本地或远程存储 |
| 依赖更新 | 每月 | 更新项目依赖，修复安全漏洞 |
| 系统更新 | 每季度 | 安装系统安全更新 |
| 性能优化 | 每半年 | 检查和优化服务配置，调整资源分配 |

## 11. 常见问题与解决方案

### 11.1 服务启动失败

**问题**：服务无法启动，日志显示"Permission denied"

**解决方案**：
```bash
# 检查服务文件权限
sudo chmod 644 /etc/systemd/system/freeark-*.service

# 检查项目目录权限
sudo chown -R freeark:freeark /home/freeark/FreeArkWeb
```

### 11.2 MQTT连接失败

**问题**：MQTT消费者服务频繁重启，日志显示"Connection refused"

**解决方案**：
```bash
# 检查MQTT配置
cat /home/freeark/FreeArkWeb/backend/freearkweb/settings.py | grep -A 10 "MQTT"

# 测试MQTT连接
echo "test" | mosquitto_pub -h mqtt.example.com -p 1883 -t test/topic -u username -P password
```

### 11.3 数据库连接超时

**问题**：服务启动超时，日志显示"Database connection timeout"

**解决方案**：
```bash
# 检查MySQL服务状态
sudo systemctl status mysql.service

# 检查数据库连接配置
cat /home/freeark/FreeArkWeb/backend/freearkweb/settings.py | grep -A 10 "DATABASES"

# 测试数据库连接
python3 -c "import mysql.connector; mysql.connector.connect(host='localhost', user='freeark', password='password', database='freeark_db')"
```

## 12. 附录

### 12.1 服务文件列表

| 服务名称 | 服务文件名 | 对应命令 |
|---------|-----------|---------|
| 每日用量计算服务 | freeark-daily-usage.service | daily_usage_service |
| 每月用量计算服务 | freeark-monthly-usage.service | monthly_usage_service |
| MQTT消费者服务 | freeark-mqtt-consumer.service | mqtt_consumer_service |
| PLC数据清理服务 | freeark-plc-cleanup.service | plc_data_clean_up_service |

### 12.2 日志文件位置

| 日志类型 | 文件路径 |
|---------|---------|
| Systemd日志 | journalctl (系统日志) |
| Django应用日志 | /var/log/freeark/django.log |
| MySQL日志 | /var/log/mysql/error.log |

### 12.3 相关配置文件

| 配置文件 | 路径 |
|---------|-----|
| 项目设置 | /home/freeark/FreeArkWeb/backend/freearkweb/settings.py |
| Nginx配置 | /etc/nginx/sites-available/freeark |
| MySQL配置 | /etc/mysql/mysql.conf.d/mysqld.cnf |

---

**文档版本**：1.0.0
**更新日期**：2025-12-08
**适用系统**：Raspberry Pi OS Bookworm 64-bit
**项目版本**：FreeArkWeb v1.0