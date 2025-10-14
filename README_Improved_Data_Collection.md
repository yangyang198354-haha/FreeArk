# 改进版PLC数据收集系统

## 功能概述

这个改进版PLC数据收集系统是基于原有`data_collection_manager.py`的增强版本，主要改进点在于：

1. **使用PLC IP地址连接设备**：优先使用JSON文件中配置的"PLC IP地址"字段连接PLC设备，而不是使用设备自身的IP地址
2. **多策略IP匹配**：实现了多层次的IP地址获取策略，确保最大可能成功连接PLC设备
3. **房间-PLC映射支持**：支持从`room_plc_map.json`文件中获取房间与PLC的映射关系
4. **故障恢复机制**：当PLC IP连接失败时，自动尝试使用设备原始IP作为后备方案
5. **详细的日志记录**：提供更丰富的日志信息，便于故障排查
6. **优化的结果保存**：单独的输出文件命名规则，避免与原始系统结果混淆

## 文件结构

```
FreeArk/
├── datacollection/
│   ├── improved_data_collection_manager.py  # 改进版数据收集管理器
│   ├── multi_thread_plc_reader.py           # PLC读取器（复用原有）
│   └── data_collection_manager.py           # 原始数据收集管理器（保留）
├── resource/
│   ├── *_data.json                          # 楼栋数据文件（包含PLC IP地址）
│   ├── plc_config.json                      # PLC配置文件
│   └── room_plc_map.json                    # 房间与PLC IP映射文件
├── output/                                  # 结果输出目录
├── run_improved_data_collection_manager.bat # 启动批处理文件
└── README_Improved_Data_Collection.md       # 本说明文件
```

## 使用方法

### 快速启动

最简单的方法是直接双击运行`run_improved_data_collection_manager.bat`批处理文件，系统会自动：

1. 搜索并找到已安装的Python解释器
2. 启动改进版数据收集管理器
3. 显示运行日志和收集结果

### 命令行启动

也可以通过命令行方式启动：

```cmd
cd /d "c:\Users\yanggyan\TRAE\FreeArk"
python datacollection\improved_data_collection_manager.py
```

## 系统工作原理

### 数据收集流程

1. **初始化**：创建数据收集管理器，启动线程池
2. **数据加载**：
   - 加载楼栋JSON文件（包含设备信息和PLC IP地址）
   - 加载PLC配置文件（定义需要读取的参数）
   - 加载房间与PLC IP映射文件（作为备用匹配方案）
3. **任务创建**：为每个设备的每个参数创建读取任务
4. **IP地址选择逻辑**：
   - 优先使用设备信息中的"PLC IP地址"字段
   - 如果没有，尝试从房间-PLC映射文件中匹配
   - 作为最后方案，使用设备自身的IP地址
5. **并行数据读取**：使用多线程并行读取所有PLC设备的数据
6. **故障恢复**：当PLC IP连接失败时，自动尝试使用设备原始IP
7. **结果处理**：组织和统计收集结果
8. **结果保存**：将结果保存到output目录，并添加时间戳

### IP地址匹配策略

系统实现了多层次的IP地址匹配策略，以确保最大可能成功连接PLC设备：

```
┌─────────────────────────┐
│  1. 设备JSON中的PLC IP  │ ← 最高优先级
└───────────┬─────────────┘
            │ 失败
┌───────────▼─────────────┐
│ 2. 从room_plc_map.json  │ ← 中等优先级
│   中查找映射关系        │
└───────────┬─────────────┘
            │ 失败
┌───────────▼─────────────┐
│  3. 使用设备自身的IP    │ ← 最低优先级
└─────────────────────────┘
```

## 输入输出说明

### 输入文件

1. **楼栋数据文件** (`resource/*_data.json`)
   - 包含设备基本信息和PLC IP地址
   - 格式示例：
     ```json
     {
       "3-1-7-702": {
         "专有部分坐落": "成都乐府（二仙桥）-3-1-702",
         "IP地址": "192.168.3.26",
         "PLC IP地址": "192.168.3.27",
         ...
       }
     }
     ```

2. **PLC配置文件** (`resource/plc_config.json`)
   - 定义需要从PLC读取的参数
   - 包含DB块号、偏移量、数据类型等信息

3. **房间-PLC映射文件** (`resource/room_plc_map.json`)
   - 存储房间号与PLC IP地址的对应关系

### 输出文件

- **数据收集结果** (`output/*_improved_data_collected_YYYYMMDD_HHMMSS.json`)
  - 文件名包含原始楼栋文件名和时间戳
  - 包含设备基本信息、收集状态和读取的数据

## 日志系统

系统会生成两类日志文件：

1. **数据收集日志** (`log/improved_data_collection_YYYYMMDD.log`)
   - 记录系统运行状态、错误信息和统计数据

2. **PLC读取日志** (`log/plc_reader_YYYYMMDD.log`)
   - 记录PLC连接状态、读取结果和错误信息

## 故障排查

### 常见问题

1. **连接失败**：
   - 检查PLC设备是否在线
   - 确认PLC IP地址是否正确
   - 验证网络连接是否正常

2. **数据读取失败**：
   - 检查PLC配置文件中的DB块号、偏移量和数据类型是否正确
   - 确认PLC设备中的数据结构是否与配置一致

3. **Python环境问题**：
   - 确保已安装Python环境
   - 确保已安装必要的依赖库（如snap7）

## 示例输出

```
✅ 改进版数据收集管理器已启动，线程池大小：10
🔍 开始测试数据收集：使用测试文件 3#_data_test.json
✅ 成功加载楼栋JSON文件：3#_data_test.json，共1条记录
✅ 成功加载PLC配置文件，包含2个参数
✅ 成功加载房间与PLC IP映射文件，共634条映射关系
🚀 开始为楼栋 3#_data_test.json 收集数据，共2个读取任务，涉及1个PLC设备...
📊 数据收集结果统计：成功 1/2 个参数读取任务
⏱️  数据收集完成，耗时：3.42 秒
✅ 改进版结果已保存到：output/3#_data_test_improved_data_collected_20251012_214454.json
📋 收集到的数据:
  设备ID: 3-1-7-702
  基本信息: 成都乐府（二仙桥）-3-1-702, IP: 192.168.3.26
  PLC IP: 192.168.3.27
  收集状态: partial_success
  数据内容: {'total_heating_quantity': {'value': 0.0, 'success': True, 'message': '读取成功'}, 'total_hot_quantity': {'value': None, 'success': False, 'message': 'PLC和设备IP连接均失败'}}
  ----------
✅ PLC管理器已停止，线程池已关闭
✅ 改进版数据收集管理器已停止
```