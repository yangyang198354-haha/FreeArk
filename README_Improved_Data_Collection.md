# 改进版PLC数据收集系统

## 功能概述

这个改进版PLC数据收集系统是一个高性能的工业数据采集解决方案，主要特性包括：

1. **多线程并行数据采集**：使用线程池技术并行读取多个PLC设备的数据，显著提高数据采集效率
2. **智能IP地址选择策略**：优先使用设备配置中的PLC IP地址，确保准确连接目标设备
3. **多格式输出支持**：同时支持JSON、Excel和MQTT三种输出方式，灵活满足不同场景需求
4. **统一日志管理**：通过集中式日志配置文件控制所有模块的日志级别和输出格式
5. **灵活的配置系统**：支持通过JSON配置文件自定义输出行为、数据处理策略等
6. **完整的错误处理**：提供详细的错误信息和异常捕获机制，确保系统稳定运行

## 文件结构

```
FreeArk/
├── datacollection/
│   ├── improved_data_collection_manager.py  # 改进版数据收集管理器（核心模块）
│   ├── multi_thread_plc_reader.py           # 多线程PLC读取器
│   ├── mqtt_client.py                       # MQTT客户端实现
│   ├── mqtt_client_pool.py                  # MQTT客户端池管理
│   ├── log_config_manager.py                # 日志配置管理器
│   └── plc_data_viewer_gui.py               # PLC数据可视化界面
├── resource/
│   ├── *_data.json                          # 楼栋数据文件（包含设备信息）
│   ├── plc_config.json                      # PLC参数配置文件
│   ├── output_config.json                   # 输出配置文件
│   └── log_config.json                      # 日志配置文件
├── output/                                  # 数据输出目录
├── log/                                     # 日志文件目录
├── run_improved_data_collection_manager.bat # 启动批处理脚本
└── README_Improved_Data_Collection.md       # 本说明文档
```

## 安装与配置

### 环境要求

- Python 3.6+
- 依赖库：snap7（用于PLC通信）、pandas（用于Excel输出）、paho-mqtt（用于MQTT通信）

### 配置文件说明

1. **PLC配置文件** (`resource/plc_config.json`)
   - 定义需要从PLC读取的参数信息
   - 包含DB块号、偏移量、数据长度和数据类型等关键配置

2. **输出配置文件** (`resource/output_config.json`)
   - 控制数据收集结果的保存方式
   - 支持配置JSON、Excel和MQTT三种输出格式的详细参数
   - 示例配置：
     ```json
     {
       "output": {
         "type": "Excel",
         "excel": {
           "enabled": true,
           "file_name": "累计用量",
           "directory": "c:/Users/yanggyan/TRAE/FreeArk/output/",
           "include_all_params": false
         },
         "json": {
           "enabled": true
         },
         "mqtt": {
           "enabled": false,
           "server": {
             "host": "192.168.31.141",
             "port": 11883,
             "username": "",
             "password": "",
             "tls_enabled": false,
             "pool_size": 5
           }
         }
       }
     }
     ```

3. **日志配置文件** (`resource/log_config.json`)
   - 集中管理所有模块的日志级别和输出格式

## 使用方法

### 快速启动

直接双击运行`run_improved_data_collection_manager.bat`批处理文件，系统会自动：

1. 搜索并找到已安装的Python解释器
2. 默认处理所有符合`*data.json`模式的数据文件
3. 启动改进版数据收集管理器并显示运行状态

### 命令行参数

启动脚本支持通过命令行参数指定要处理的数据文件：

```cmd
cd /d "c:\Users\yanggyan\TRAE\FreeArk"
python datacollection\improved_data_collection_manager.py -f 3#_data.json
```

参数说明：
- `-f` 或 `--file`：指定要处理的数据文件，可以使用通配符（如`*data.json`）

## 系统工作原理

### 数据收集流程

1. **初始化阶段**
   - 创建`ImprovedDataCollectionManager`实例
   - 初始化线程池（默认大小为10）
   - 加载并验证配置文件

2. **数据加载阶段**
   - 加载指定的楼栋数据文件
   - 加载PLC参数配置
   - 加载输出配置文件

3. **IP地址策略选择**
   - 优先使用设备信息中的"PLC IP地址"字段
   - 如果不存在，则回退使用设备自身的"IP地址"字段
   - 注：系统代码中预留了从房间-PLC映射文件获取映射关系的功能，但当前项目中该文件（`room_plc_map.json`）不存在

4. **任务创建与执行**
   - 为每个设备的每个参数创建读取任务
   - 按PLC IP地址对任务进行分组
   - 提交任务到线程池并行执行

5. **数据处理与输出**
   - 组织和统计收集结果
   - 根据配置保存为JSON文件
   - 根据配置生成Excel报告
   - 根据配置通过MQTT发送数据

### 核心技术特性

1. **线程池优化**
   - 每个PLC IP地址作为一个独立任务提交给线程池
   - 单个PLC任务中可以读取多个参数，减少连接开销
   - 使用`concurrent.futures`实现高效的线程管理

2. **输出格式控制**
   - 支持同时启用多种输出格式
   - 可配置Excel文件名、目录等参数
   - 支持MQTT消息的QoS级别和保留消息设置

3. **错误处理机制**
   - 完善的异常捕获和日志记录
   - 单独记录每个参数的读取状态
   - 设备状态分为：success、partial_success、failed、pending

## 输出说明

### JSON输出

- 文件位置：`output/*_improved_data_collected_YYYYMMDD_HHMMSS.json`
- 包含完整的设备信息、参数值和状态标识
- 每个参数都有独立的时间戳和状态信息

### Excel输出

- 文件位置：`output/累计用量_YYYYMMDD_HHMMSS.xlsx`
- 自动汇总收集到的数据
- 支持配置是否包含所有参数

### MQTT输出

- 可配置的MQTT服务器地址和认证信息
- 支持主题前缀自定义
- 可配置消息质量级别（QoS）

## 日志系统

系统会在`log/`目录下生成按日期命名的日志文件：

1. **数据收集日志** (`log/improved_data_collection_YYYYMMDD.log`)
   - 记录数据收集过程的整体状态
   - 包含任务统计和耗时信息

2. **PLC读取日志** (`log/plc_reader_YYYYMMDD.log`)
   - 记录每个PLC连接和数据读取的详细信息
   - 包含连接状态和错误详情

3. **MQTT日志** (`log/mqtt_client_YYYYMMDD.log`)
   - 记录MQTT连接和消息发送状态

## 故障排查

### 常见问题与解决方案

1. **PLC连接失败**
   - 检查PLC设备IP地址是否正确
   - 验证网络连接和防火墙设置
   - 确认PLC设备处于运行状态

2. **数据读取错误**
   - 检查PLC配置文件中的DB块号、偏移量和数据类型是否正确
   - 确认PLC设备的数据结构与配置一致
   - 查看详细日志了解具体错误原因

3. **输出文件未生成**
   - 检查输出配置文件中的`enabled`设置
   - 验证输出目录是否存在且有写入权限
   - 查看日志确认是否有写入错误

4. **Python模块缺失**
   - 安装所需依赖：`pip install python-snap7 pandas paho-mqtt`
   - 确认Python版本符合要求（3.6+）

## 性能优化建议

1. **调整线程池大小**：根据系统硬件和PLC设备数量调整`max_workers`参数
2. **批量处理**：使用通配符处理多个数据文件，提高处理效率
3. **合理配置输出**：只启用必要的输出格式，避免不必要的资源消耗
4. **监控连接状态**：定期检查PLC连接状态，及时发现网络问题

## 未来改进方向

1. 实现设备分组功能，支持按楼栋或区域批量管理
2. 添加数据缓存机制，提高频繁访问数据的响应速度
3. 开发Web管理界面，实现配置的可视化管理
4. 支持更多工业协议，扩展系统兼容性