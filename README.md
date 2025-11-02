# FreeArk

FreeArk是一个用于PLC数据收集、处理和可视化的综合解决方案。该项目支持多线程PLC数据读取、MQTT通信、数据存储和可视化展示，适用于工业控制系统的数据监控场景。

## 项目结构

```
FreeArk/
├── datacollection/          # 数据收集核心模块
│   ├── improved_data_collection_manager.py  # 改进版数据收集管理器
│   ├── multi_thread_plc_handler.py           # 多线程PLC处理器
│   ├── mqtt_client.py                       # MQTT客户端
│   ├── log_config_manager.py                # 日志配置管理器
│   ├── plc_data_viewer_gui.py               # PLC数据可视化界面
│   ├── quantity_statistics.py               # 用量统计模块
│   └── mqtt_client_pool.py                  # MQTT客户端池管理
├── resource/                # 配置文件目录
│   ├── *_data.json                          # 楼栋数据文件
│   ├── plc_config.json                      # PLC参数配置
│   ├── output_config.json                   # 输出配置
│   ├── log_config.json                      # 日志配置
│   └── mqtt_config.json                     # MQTT配置
├── output/                  # 数据输出目录
├── log/                     # 日志文件目录
├── reference/               # 参考代码和工具
├── *.bat                    # 批处理运行脚本
└── requirements.txt         # 项目依赖
```

## 安装配置

### 环境要求
- Python 3.7+
- 所需依赖包（通过pip安装）：
  ```bash
  pip install -r requirements.txt
  ```

### 配置文件说明

#### 1. PLC配置
文件：`resource/plc_config.json`

定义了PLC数据点的配置信息，包括：
- 数据点名称和描述
- PLC DB块号和偏移量
- 数据类型和长度

#### 2. 日志配置
文件：`resource/log_config.json`

控制各模块的日志输出级别：
- global：全局默认日志级别
- improved_data_collection：数据收集管理器日志级别
- plc_reader：PLC读取器日志级别
- mqtt_client：MQTT客户端日志级别
- quantity_statistics：用量统计日志级别
- plc_data_viewer：PLC查看器日志级别

#### 3. MQTT配置
文件：`resource/mqtt_config.json`

配置MQTT连接参数，包括：
- 服务器地址和端口
- 用户名和密码
- 主题配置

#### 4. 输出配置
文件：`resource/output_config.json`

配置数据输出参数，支持JSON、Excel和MQTT三种输出格式。

#### 5. 楼栋数据配置
文件：`resource/*#_data.json`

每个楼栋的配置信息，包括IP地址和设备信息。

## 运行工程

项目提供了多个批处理脚本，用于快速启动各个模块：

### 1. 启动数据收集管理器

```bash
run_improved_data_collection_manager.bat
```

功能：启动主数据收集程序，负责协调PLC读取、数据处理和存储。

### 2. 启动PLC数据查看器GUI

```bash
run_plc_data_viewer_gui.bat
```

功能：启动图形界面，用于实时查看和监控PLC数据。

### 3. 启动多线程PLC读取器

```bash
run_multi_thread_plc_reader.bat
```

功能：单独运行PLC数据读取器，用于测试或特定场景。

### 4. 启动用量统计

```bash
run_quantity_statistics.bat
```

功能：生成和导出用量统计报表。

## 主要模块说明

### 1. 改进版数据收集管理器 (ImprovedDataCollectionManager)

**文件**：`datacollection/improved_data_collection_manager.py`

**功能**：
- 协调多线程PLC数据读取
- 处理和整合收集的数据
- 支持数据导出为JSON和Excel格式
- 与MQTT系统集成

**主要特点**：
- 多线程并行读取多个PLC设备
- 可配置的数据处理流程
- 支持批量操作和定时任务
- 完善的错误处理和日志记录

### 2. 多线程PLC读取器 (MultiThreadPLCReader)

**文件**：`datacollection/multi_thread_plc_handler.py`

**功能**：
- 基于Snap7库的PLC通信
- 多线程并发读取
- 连接池管理和错误重试
- 线程安全的数据读取操作

### 3. PLC数据查看器GUI

**文件**：`datacollection/plc_data_viewer_gui.py`

**功能**：
- 图形界面展示PLC数据
- 实时数据监控
- 数据可视化和图表展示
- 支持JSON和Excel数据导出

### 4. MQTT客户端

**文件**：`datacollection/mqtt_client.py`

**功能**：
- MQTT消息发布和订阅
- 与物联网平台集成
- 消息格式转换和处理

### 5. 日志配置管理器

**文件**：`datacollection/log_config_manager.py`

**功能**：
- 统一的日志配置管理
- 支持动态调整日志级别
- 日志文件轮转和存储
- 确保中文显示正常

### 6. 用量统计

**文件**：`datacollection/quantity_statistics.py`

**功能**：
- 计算和统计能源用量数据
- 生成Excel报表
- 数据分析和汇总
- 支持从多个历史文件提取数据

## 工作流程

1. 配置阶段：
   - 编辑resource目录下的配置文件
   - 设置PLC参数、日志级别和输出选项

2. 运行阶段：
   - 启动improved_data_collection_manager进行数据收集
   - 或使用plc_data_viewer_gui进行实时监控

3. 输出阶段：
   - 数据保存在output目录下
   - 日志文件存储在log目录下

## 故障排除

### 常见问题

1. **PLC连接失败**
   - 检查PLC IP地址和端口配置
   - 确认网络连接和防火墙设置
   - 验证PLC DB块号和偏移量是否正确

2. **数据读取错误**
   - 检查数据类型配置是否匹配
   - 查看日志文件获取详细错误信息
   - 确认PLC程序是否正在运行

3. **日志中文显示异常**
   - 确保使用UTF-8编码打开日志文件
   - 检查配置文件的编码格式

4. **依赖模块缺失**
   - 运行`pip install -r requirements.txt`安装所有依赖

## 开发指南

### 添加新的PLC数据点

1. 在`plc_config.json`中添加新的数据点定义
2. 在对应的楼栋数据文件中更新配置
3. 重启相关模块以应用更改

### 自定义日志级别

编辑`log_config.json`中的log_levels部分，可以设置为DEBUG、INFO、WARNING、ERROR或CRITICAL。

### 扩展功能

项目采用模块化设计，可以方便地扩展新功能：
- 添加新的数据处理模块
- 实现自定义的输出格式
- 集成其他通信协议或设备类型

## 技术特点

1. **模块化设计**：各功能模块松耦合，易于维护和扩展
2. **线程安全**：使用锁机制确保并发操作的安全性
3. **错误处理**：完善的异常捕获和错误日志记录
4. **灵活配置**：通过JSON配置文件实现参数自定义
5. **多格式输出**：支持JSON、Excel和MQTT多种输出方式
6. **打包支持**：兼容PyInstaller打包，可生成独立可执行文件

## 联系方式

如有任何问题或建议，请联系项目维护人员。