# FreeArk

FreeArk是一个功能强大的PLC数据收集、处理和可视化综合解决方案。该项目专为工业控制系统设计，支持多线程PLC数据读取、MQTT通信、多格式数据存储（JSON、Excel）以及直观的数据可视化展示。系统采用模块化架构，提供高度的可配置性和扩展性，适用于各类工业监控场景。

## 项目结构

```
FreeArk/
├── datacollection/          # 数据收集核心模块
│   ├── improved_data_collection_manager.py  # 改进版数据收集管理器（核心组件）
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
│   ├── plc_mode_update_config.json          # PLC模式更新配置
│   ├── log_config.json                      # 日志配置
│   └── mqtt_config.json                     # MQTT配置
├── output/                  # 数据输出目录
│   ├── json/                                # JSON格式输出
│   └── excel/                               # Excel格式输出
├── log/                     # 日志文件目录
├── reference/               # 参考代码和工具
├── FreeArkWeb/              # Web可视化界面相关文件
├── *_data_collection.bat    # 数据收集相关批处理脚本
├── *_task_scheduler.bat     # 任务调度相关批处理脚本
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
- 单位信息

#### 2. PLC模式更新配置
文件：`resource/plc_mode_update_config.json`

用于配置PLC模式更新相关参数，包括：
- 模式定义和映射关系
- 更新频率和条件
- 状态监控参数

#### 3. 日志配置
文件：`resource/log_config.json`

控制各模块的日志输出级别和格式：
- global：全局默认日志级别
- improved_data_collection：数据收集管理器日志级别
- plc_reader：PLC读取器日志级别
- mqtt_client：MQTT客户端日志级别
- quantity_statistics：用量统计日志级别
- plc_data_viewer：PLC查看器日志级别

#### 4. MQTT配置
文件：`resource/mqtt_config.json`

配置MQTT连接参数和消息发布设置：
- 服务器地址和端口
- 用户名和密码
- 连接池配置
- 主题构建规则
- 消息质量等级

#### 5. 输出配置
文件：`resource/output_config.json`

配置数据输出参数，支持多种输出格式和选项：
- JSON格式配置：路径、命名规则、格式化选项
- Excel格式配置：路径、命名规则、样式设置
- MQTT格式配置：启用/禁用、主题模板
- 结果分离：成功/失败数据分开存储

#### 6. 楼栋数据配置
文件：`resource/*#_data.json`

每个楼栋的配置信息，包括：
- 楼栋基本信息
- PLC设备IP地址列表
- 设备分组信息
- 连接参数设置

## 运行工程

项目提供了多个批处理脚本，用于快速启动各个模块：

### 1. 启动数据收集管理器

```bash
run_data_collection.bat
```

功能：启动主数据收集程序，根据配置批量读取PLC数据并进行处理。

### 2. 启动任务调度器

```bash
run_task_scheduler.bat
```

功能：启动定时任务调度器，按设定的时间间隔自动执行数据收集任务。

### 3. 启动PLC数据查看器GUI

```bash
run_plc_data_viewer_gui.bat
```

功能：启动图形界面，用于实时查看和监控PLC数据，支持可视化展示。

### 4. 启动用量统计

```bash
run_quantity_statistics.bat
```

功能：生成和导出用量统计报表，支持历史数据分析。

## 主要模块说明

### 1. 改进版数据收集管理器 (ImprovedDataCollectionManager)

**文件**：`datacollection/improved_data_collection_manager.py`

**核心功能**：
- 协调多线程PLC数据读取和处理
- 支持批量处理多个楼栋/设备的数据
- 提供灵活的数据输出选项（JSON、Excel、MQTT）
- 实现连接池管理和资源优化
- 完善的错误处理和日志记录

**主要特点**：
- **多线程并行处理**：采用线程池技术，高效并发读取多个PLC设备
- **分组执行策略**：按IP地址分组执行读取任务，优化资源使用
- **智能结果组织**：自动分类成功/失败数据，便于分析
- **Excel格式化**：支持自定义表头样式、单元格边框和列宽调整
- **MQTT连接池**：优化MQTT连接管理，提高消息发布效率
- **全楼栋扫描**：支持遍历所有配置的楼栋，批量执行数据收集

### 2. 多线程PLC读取器 (MultiThreadPLCReader)

**文件**：`datacollection/multi_thread_plc_handler.py`

**功能**：
- 基于Snap7库的高效PLC通信
- 多线程并发数据读取
- 连接池管理和自动重试机制
- 线程安全的数据处理操作
- 支持多种数据类型的读取和转换

### 3. PLC数据查看器GUI

**文件**：`datacollection/plc_data_viewer_gui.py`

**功能**：
- 图形界面展示实时PLC数据
- 动态数据更新和监控
- 直观的数据可视化图表
- 支持历史数据导入和分析
- 数据导出功能（JSON、Excel）

### 4. MQTT客户端池

**文件**：`datacollection/mqtt_client_pool.py`

**功能**：
- 管理MQTT客户端连接池
- 优化连接资源使用
- 支持并发消息发布
- 错误处理和自动重连
- 主题构建和消息格式化

### 5. 日志配置管理器

**文件**：`datacollection/log_config_manager.py`

**功能**：
- 统一的日志配置管理
- 支持动态调整各模块日志级别
- 日志文件轮转和管理
- 确保中文显示正常
- 多级别日志过滤

### 6. 用量统计

**文件**：`datacollection/quantity_statistics.py`

**功能**：
- 计算和统计能源用量数据
- 生成格式化的Excel报表
- 多维度数据分析和汇总
- 支持从多个历史文件提取和整合数据
- 趋势分析和异常检测

## 工作流程

1. **配置阶段**：
   - 编辑resource目录下的配置文件
   - 设置PLC参数、输出选项和MQTT连接
   - 配置日志级别和存储位置

2. **运行阶段**：
   - 启动数据收集管理器或任务调度器
   - 系统自动加载配置并初始化组件
   - 按配置执行数据读取和处理流程

3. **输出阶段**：
   - 数据保存在output目录下（按格式分类）
   - 日志文件存储在log目录下
   - 成功/失败数据分离存储，便于分析

## 故障排除

### 常见问题

1. **PLC连接失败**
   - 检查PLC IP地址和端口配置是否正确
   - 确认网络连接和防火墙设置
   - 验证PLC DB块号和偏移量配置
   - 查看日志获取详细错误信息

2. **数据读取错误**
   - 检查数据类型配置是否与PLC实际类型匹配
   - 确认PLC程序正在运行且数据点有效
   - 验证参数名称和路径配置

3. **日志中文显示异常**
   - 确保使用UTF-8编码打开日志文件
   - 检查配置文件编码格式
   - 验证日志系统配置是否正确

4. **依赖模块缺失**
   - 运行`pip install -r requirements.txt`安装所有依赖
   - 检查Python版本是否符合要求

5. **MQTT连接问题**
   - 验证MQTT服务器地址、端口和认证信息
   - 检查网络连接和防火墙设置
   - 查看MQTT相关日志获取详细错误

## 开发指南

### 添加新的PLC数据点

1. 在`plc_config.json`中添加新的数据点定义
2. 在对应的楼栋数据文件中更新配置
3. 根据需要调整output_config.json中的输出设置
4. 重启相关模块以应用更改

### 自定义日志级别

编辑`log_config.json`中的log_levels部分，可以设置为DEBUG、INFO、WARNING、ERROR或CRITICAL。

### 扩展功能

项目采用模块化设计，可以方便地扩展新功能：
- 添加新的数据处理模块
- 实现自定义的输出格式
- 集成其他通信协议或设备类型
- 扩展可视化界面功能

## 技术特点

1. **模块化架构**：各功能模块松耦合，易于维护和扩展
2. **高性能并发**：多线程和连接池技术，高效处理大量设备
3. **全面错误处理**：完善的异常捕获和详细的错误日志记录
4. **灵活配置系统**：通过JSON配置文件实现参数自定义，无需修改代码
5. **多格式输出支持**：同时支持JSON、Excel和MQTT多种数据输出方式
6. **资源优化**：实现连接池和线程池，有效管理系统资源
7. **数据分离存储**：成功/失败数据分开处理，便于问题诊断
8. **可打包部署**：兼容PyInstaller打包，可生成独立可执行文件

## 联系与支持

如有任何问题、建议或功能请求，请联系项目维护团队。我们欢迎社区贡献和反馈，共同改进FreeArk系统。