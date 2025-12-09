# FreeArk Task Scheduler Systemctl 服务配置说明

## 1. 需求分析

### 1.1 功能需求
- 将 `run_task_scheduler.py` 脚本配置为 systemd 服务，实现自动启动和管理
- 确保服务能够在系统启动时自动运行
- 提供可靠的服务监控和故障重启机制
- 支持标准的 systemd 服务管理命令（启动、停止、重启、状态查询）
- 实现结构化日志记录，便于问题排查

### 1.2 非功能需求
- 服务配置符合 Linux 系统安全最佳实践
- 支持虚拟环境运行，确保依赖隔离
- 服务启动和停止过程平稳，避免数据丢失
- 提供详细的部署和使用文档

## 2. 设计思路

### 2.1 架构设计
- **服务类型**：使用 simple 类型服务，适合长时间运行的后台进程
- **重启策略**：采用 always 重启策略，确保服务在意外退出时能够自动恢复
- **日志管理**：利用 systemd journal 进行日志集中管理
- **依赖管理**：确保服务在网络服务启动后再启动

### 2.2 配置设计
- **环境变量**：设置 PYTHONPATH 确保模块导入正确
- **工作目录**：指定到 datacollection 目录，确保相对路径正确
- **执行命令**：使用虚拟环境中的 Python 解释器，确保依赖一致性
- **用户权限**：支持配置特定用户运行服务，提高安全性

## 3. 服务文件配置说明

### 3.1 服务文件路径
`/home/yangyang/Freeark/FreeArk/systemctl/freeark-task-scheduler.service`

### 3.2 配置内容详解

```ini
[Unit]
Description=FreeArk Task Scheduler Service  # 服务描述
Documentation=https://github.com/your-repo/freeark  # 文档地址
After=network.target  # 网络服务启动后再启动本服务

[Service]
Type=simple  # 服务类型：简单后台进程
Restart=always  # 重启策略：总是重启
RestartSec=5  # 重启间隔：5秒

# 定义环境变量
Environment=PYTHONPATH=/home/yangyang/Freeark/FreeArk  # 设置Python模块搜索路径

# 工作目录
WorkingDirectory=/home/yangyang/Freeark/FreeArk/datacollection  # 设置服务工作目录

# 启动命令 - 使用虚拟环境中的Python
ExecStart=/home/yangyang/Freeark/FreeArk/venv/bin/python /home/yangyang/Freeark/FreeArk/datacollection/run_task_scheduler.py  # 服务启动命令

# 停止命令
ExecStop=/bin/kill -s SIGINT $MAINPID  # 服务停止命令

# 设置用户和组（根据实际部署需求调整）
# User=freeark  # 运行服务的用户
# Group=freeark  # 运行服务的组

# 日志输出
StandardOutput=journal  # 标准输出到journal
StandardError=journal  # 标准错误到journal
SyslogIdentifier=freeark-task-scheduler  # 日志标识符

[Install]
WantedBy=multi-user.target  # 多用户模式下自动启动
```

## 4. 安装和使用步骤

### 4.1 前提条件
- Linux 系统（支持 systemd）
- Python 虚拟环境已配置（路径：`/home/yangyang/Freeark/FreeArk/venv`）
- FreeArk 项目已部署到相应目录

### 4.2 安装步骤

1. **复制服务文件到 systemd 目录**
   ```bash
   sudo cp /home/yangyang/Freeark/FreeArk/systemctl/freeark-task-scheduler.service /etc/systemd/system/
   ```

2. **重新加载 systemd 配置**
   ```bash
   sudo systemctl daemon-reload
   ```

3. **启用服务（开机自启）**
   ```bash
   sudo systemctl enable freeark-task-scheduler.service
   ```

4. **启动服务**
   ```bash
   sudo systemctl start freeark-task-scheduler.service
   ```

### 4.3 使用命令

- **启动服务**
  ```bash
  sudo systemctl start freeark-task-scheduler.service
  ```

- **停止服务**
  ```bash
  sudo systemctl stop freeark-task-scheduler.service
  ```

- **重启服务**
  ```bash
  sudo systemctl restart freeark-task-scheduler.service
  ```

- **查看服务状态**
  ```bash
  sudo systemctl status freeark-task-scheduler.service
  ```

- **查看服务日志**
  ```bash
  sudo journalctl -u freeark-task-scheduler.service
  ```

- **实时查看日志**
  ```bash
  sudo journalctl -u freeark-task-scheduler.service -f
  ```

- **查看最近的日志**
  ```bash
  sudo journalctl -u freeark-task-scheduler.service -n 100
  ```

## 5. 配置调整

### 5.1 虚拟环境路径调整
如果虚拟环境路径不是 `/home/yangyang/Freeark/FreeArk/venv`，需要修改 `ExecStart` 行中的 Python 解释器路径：

```ini
ExecStart=/path/to/your/venv/bin/python /home/yangyang/Freeark/FreeArk/datacollection/run_task_scheduler.py
```

### 5.2 工作目录调整
如果 FreeArk 项目部署路径不同，需要修改 `WorkingDirectory` 和 `PYTHONPATH`：

```ini
Environment=PYTHONPATH=/path/to/your/freeark
WorkingDirectory=/path/to/your/freeark/datacollection
ExecStart=/home/yangyang/Freeark/FreeArk/venv/bin/python /path/to/your/freeark/datacollection/run_task_scheduler.py
```

### 5.3 用户权限调整
为了提高安全性，建议使用非 root 用户运行服务，与其他 FreeArk 服务保持一致：

```ini
User=freeark
Group=freeark
```

确保该用户对项目目录有适当的读写权限。

## 6. 故障排除

### 6.1 服务启动失败

1. **查看服务状态**
   ```bash
   sudo systemctl status freeark-task-scheduler.service
   ```

2. **查看详细日志**
   ```bash
   sudo journalctl -u freeark-task-scheduler.service -xe
   ```

### 6.2 常见问题及解决方案

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 服务无法启动 | Python 路径错误 | 检查虚拟环境路径是否正确 |
| 模块导入错误 | PYTHONPATH 配置错误 | 确保 PYTHONPATH 包含 FreeArk 根目录 |
| 权限错误 | 用户权限不足 | 检查运行服务的用户对项目目录的权限 |
| 配置文件找不到 | 工作目录错误 | 确保 WorkingDirectory 配置正确 |

### 6.3 日志分析
服务日志记录了详细的运行信息，包括：
- 服务启动和停止事件
- 任务调度器执行情况
- 数据收集过程中的错误信息
- 系统异常和崩溃信息

使用 journalctl 工具可以方便地过滤和分析这些日志。

## 7. 维护与更新

### 7.1 服务更新

1. **更新 Python 脚本**
   ```bash
   # 替换新的脚本文件
   sudo systemctl restart freeark-task-scheduler.service
   ```

2. **更新服务配置**
   ```bash
   # 修改服务文件后执行
   sudo systemctl daemon-reload
   sudo systemctl restart freeark-task-scheduler.service
   ```

### 7.2 性能监控

可以使用以下命令监控服务资源使用情况：

```bash
# 查看服务进程资源使用
top -p $(pgrep -f run_task_scheduler.py)

# 查看系统d服务统计
systemctl status freeark-task-scheduler.service --no-pager
```

## 8. 总结

本配置将 FreeArk Task Scheduler 成功集成到 Linux 系统的 systemd 服务管理框架中，实现了：
- 服务的自动启动和管理
- 可靠的故障恢复机制
- 标准化的服务管理接口
- 结构化的日志记录

通过本配置，可以确保 FreeArk 任务调度器在 Linux 系统上稳定、可靠地运行，为数据收集任务提供持续的支持。