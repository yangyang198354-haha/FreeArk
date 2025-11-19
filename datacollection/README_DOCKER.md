# FreeArk数据收集模块Docker部署指南

## 1. 概述
该文档提供了将FreeArk数据收集模块部署为Docker容器的详细步骤，包括Docker镜像构建、Docker Compose编排、Linux系统服务配置和定时任务设置。

## 2. 文件结构
```
datacollection/
├── Dockerfile              # Docker镜像构建文件
├── docker-compose.yml      # Docker Compose服务编排文件
├── freeark-data-collector.service  # systemd服务文件
├── deploy.sh               # 自动部署脚本
├── run_task_scheduler.py   # 任务调度器入口
├── task_scheduler.py       # 任务调度器核心逻辑
└── improved_data_collection_manager.py  # 数据收集核心逻辑
```

## 3. Docker部署

### 3.1 手动构建和运行

#### 3.1.1 构建Docker镜像
```bash
cd c:\Users\yanggyan\TRAE\FreeArk\datacollection
docker build -t freeark-data-collector .
```

#### 3.1.2 运行Docker容器
```bash
docker run -d \
  --name freeark-data-collector \
  -v ./output:/app/output \
  -v ../resource:/app/resource \
  freeark-data-collector
```

### 3.2 使用Docker Compose

#### 3.2.1 启动服务
```bash
docker-compose up -d
```

#### 3.2.2 查看日志
```bash
docker-compose logs -f
```

#### 3.2.3 停止服务
```bash
docker-compose down
```

## 4. Linux系统服务

### 4.1 手动部署

#### 4.1.1 复制服务文件
```bash
sudo cp freeark-data-collector.service /etc/systemd/system/
```

#### 4.1.2 更新服务配置
```bash
sudo systemctl daemon-reload
```

#### 4.1.3 启用并启动服务
```bash
sudo systemctl enable freeark-data-collector
sudo systemctl start freeark-data-collector
sudo systemctl status freeark-data-collector
```

#### 4.1.4 查看服务日志
```bash
sudo journalctl -u freeark-data-collector -f
```

#### 4.1.5 重启服务
```bash
sudo systemctl restart freeark-data-collector
```

### 4.2 使用自动部署脚本

#### 4.2.1 赋予执行权限
```bash
chmod +x deploy.sh
```

#### 4.2.2 执行部署脚本
```bash
sudo ./deploy.sh
```

## 5. Crontab定时任务

### 5.1 配置Crontab
```bash
crontab -e
```

### 5.2 添加定时任务
```bash
# 每天凌晨2点执行数据收集任务
0 2 * * * docker run --rm -v /opt/freeark/output:/app/output -v /opt/freeark/resource:/app/resource freeark-data-collector

# 每小时执行一次数据收集任务
0 * * * * docker run --rm -v /opt/freeark/output:/app/output -v /opt/freeark/resource:/app/resource freeark-data-collector
```

### 5.3 验证定时任务
```bash
crontab -l
```

## 6. 配置文件

### 6.1 任务调度器配置
位置：`resource/task_scheduler_config.json`

```json
{
  "scheduler": {
    "interval_seconds": 300,
    "building_files": [
      "1#_data.json",
      "2#_data.json",
      "3#_data.json"
    ]
  }
}
```

### 6.2 PLC配置
位置：`resource/plc_config.json`

```json
{
  "plcs": {
    "192.168.1.100": {
      "ip": "192.168.1.100",
      "port": 102,
      "rack": 0,
      "slot": 1
    },
    "192.168.1.101": {
      "ip": "192.168.1.101",
      "port": 102,
      "rack": 0,
      "slot": 1
    }
  }
}
```

## 7. 输出目录
数据收集模块将收集到的数据存储在`output/`目录下，可以通过Docker挂载到宿主机上：

```bash
docker run -v ./output:/app/output freeark-data-collector
```

## 8. 跨平台兼容性

### 8.1 Windows环境
```bash
run_task_scheduler.bat
```

### 8.2 Linux环境
```bash
python run_task_scheduler.py
```

### 8.3 Docker环境
```bash
docker-compose up -d
```

## 9. 监控与调试

### 9.1 查看Docker容器日志
```bash
docker logs -f freeark-data-collector
```

### 9.2 查看系统服务日志
```bash
sudo journalctl -u freeark-data-collector -n 20
```

### 9.3 进入Docker容器
```bash
docker exec -it freeark-data-collector bash
```

## 10. 注意事项

1. **网络配置**：如果需要访问外部PLC设备，可以考虑使用`host`网络模式。
2. **权限管理**：确保Docker容器有足够的权限访问挂载目录。
3. **配置文件**：在修改配置文件后，需要重启Docker容器或系统服务才能生效。
4. **资源限制**：根据实际情况，为Docker容器设置适当的资源限制。
5. **日志管理**：定期清理日志文件，避免占用过多磁盘空间。