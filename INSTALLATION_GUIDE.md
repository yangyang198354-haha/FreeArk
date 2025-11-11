# FreeArk 数据采集系统安装指南

本文档详细说明如何安装和配置 FreeArk 数据采集系统及其依赖。

## 安装步骤

### 1. 克隆或下载项目

首先确保您已获取项目源代码。

### 2. 安装依赖

在项目根目录下，使用以下命令安装所有必要的依赖：

```bash
pip install -r requirements.txt
```

主要依赖包括：
- snap7（用于PLC通信）
- pandas（用于Excel输出）
- openpyxl（用于Excel格式处理）
- paho-mqtt（用于MQTT通信）
- concurrent.futures（用于多线程处理）

### 3. 开发模式安装（可选）

如果您需要进行开发或修改，可以将项目安装为可编辑模式：

```bash
pip install -e .
```

参数 `-e` 表示以开发模式安装，这样对源代码的修改会立即生效，无需重新安装。

## 使用方法

### 通过批处理脚本运行

直接双击运行项目根目录下的批处理文件：

```
run_improved_data_collection_manager.bat
```

### 通过命令行运行

也可以直接使用Python运行核心模块：

```cmd
cd /d "项目路径"
python datacollection\improved_data_collection_manager.py -f *_data.json
```

参数说明：
- `-f` 或 `--file`：指定要处理的数据文件，可以使用通配符（如`*_data.json`）

### 处理特定楼栋数据

如需只处理特定楼栋的数据文件：

```cmd
python datacollection\improved_data_collection_manager.py -f 3#_data.json
```

## 配置文件设置

在运行系统前，请确保以下配置文件位于正确位置：

1. **resource/plc_config.json** - PLC参数配置
2. **resource/plc_mode_update_config.json** - PLC模式更新配置（新增）
3. **resource/output_config.json** - 输出格式配置
4. **resource/log_config.json** - 日志系统配置
5. **resource/mqtt_config.json** - MQTT服务器配置

## 目录结构说明

确保项目目录结构如下：

```
FreeArk/
├── datacollection/    # 核心数据收集模块
├── resource/          # 配置文件和资源文件
├── output/            # 数据输出目录
├── log/               # 日志文件目录
├── FreeArkWeb/        # Web界面相关文件
└── 其他项目文件
```

## 卸载方法

如果需要卸载已安装的包，可以使用以下命令：

```bash
pip uninstall freeark-datacollection
```

## 注意事项

1. **Python版本要求**：确保 Python 版本 >= 3.7
2. **编译工具**：安装前请确保系统已安装必要的编译工具（对于 python-snap7 可能需要）
3. **配置文件位置**：运行前请确保所有配置文件位于 `resource/` 目录下
4. **输出目录权限**：确保程序对 `output/` 目录有写入权限
5. **网络连接**：确保计算机可以访问目标PLC设备和MQTT服务器（如使用）
6. **管理员权限**：在Windows系统上，某些情况下可能需要以管理员身份运行脚本
7. **防火墙设置**：确保防火墙不会阻止与PLC设备的通信（通常使用TCP端口102）

## 常见问题

### 1. 依赖安装失败

如果安装snap7等依赖失败，可能需要：
- 安装Visual C++ Build Tools
- 确保pip版本是最新的：`python -m pip install --upgrade pip`

### 2. PLC连接问题

如果无法连接到PLC设备，请检查：
- PLC设备IP地址配置
- 网络连接状态
- 设备是否在线
- 防火墙设置