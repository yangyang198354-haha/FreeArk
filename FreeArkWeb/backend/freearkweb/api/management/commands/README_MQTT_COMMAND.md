# 如何运行 MQTT 消费者管理命令

`mqtt_consumer_service` 是一个 Django 管理命令，用于启动 MQTT 消费者服务，监听 PLC 数据并将其保存到数据库。该命令使用 schedule 机制进行管理，支持自动重启功能。

## 运行步骤

### 1. 确保在正确的工作目录

首先，确保您位于正确的工作目录：

```bash
cd C:\Users\yanggyan\TRAE\FreeArk\FreeArkWeb\backend\freearkweb
```

### 2. 运行 Django 管理命令

使用 `python manage.py` 运行该命令：

```bash
python manage.py mqtt_consumer_service
```

### 3. 验证服务是否成功启动

如果命令成功执行，您将看到类似以下输出：

```
🚀 正在启动MQTT消费者服务...
✅ MQTT消费者服务已成功启动
📝 正在监听主题: /datacollection/plc/to/collector/#
⚠️  按 Ctrl+C 停止服务
```

### 4. 停止服务

要停止服务，请按 `Ctrl+C` 组合键。

## 命令参数

### --monitor-interval

服务监控间隔（秒），默认为 60 秒。用于设置服务状态监控的时间间隔。

```bash
python manage.py mqtt_consumer_service --monitor-interval 30
```

### --auto-restart

当 MQTT 服务异常停止时自动重启。

```bash
python manage.py mqtt_consumer_service --auto-restart
```

### 组合使用参数

```bash
python manage.py mqtt_consumer_service --monitor-interval 30 --auto-restart
```

## 注意事项

1. **环境要求**：确保已安装所有必要的依赖（可以查看 `requirements.txt`）

2. **数据库配置**：确保数据库连接正常，且 `PLCData` 模型已正确创建

3. **MQTT 配置**：命令会读取 `mqtt_config.json` 文件来连接 MQTT 代理

4. **日志**：运行日志将写入到配置的日志文件中（配置在 `settings.py` 的 `LOGGING` 部分）

5. **后台运行**：如果需要在后台运行，可以使用适当的进程管理工具

## 故障排除

如果命令执行失败，请检查：

- 数据库连接是否正常
- MQTT 代理配置是否正确（检查 `mqtt_config.json` 文件）
- 所有依赖是否已安装（特别是 paho-mqtt 和 Django）
- 日志文件中是否有详细的错误信息
- 权限是否足够连接到 MQTT 代理和数据库