# FreeArk 数据采集系统安装指南

本文档说明如何通过 pip 安装 FreeArk 数据采集系统及其依赖。

## 安装步骤

### 1. 克隆或下载项目

首先确保您已获取项目源代码。

### 2. 安装依赖

在项目根目录下，使用以下命令安装所有必要的依赖：

```bash
pip install -r requirements.txt
```

### 3. 安装为可执行包

将项目安装为本地包，这样您就可以直接使用命令行工具：

```bash
pip install -e .
```

参数 `-e` 表示以开发模式安装，这样对源代码的修改会立即生效，无需重新安装。

## 使用方法

安装完成后，您可以使用以下命令行工具：

### 运行数据采集

```bash
run-data-collection
```

### 运行任务调度器

```bash
run-task-scheduler
```

## 卸载方法

如果需要卸载该包，可以使用以下命令：

```bash
pip uninstall freeark-datacollection
```

## 注意事项

1. 确保 Python 版本 >= 3.8
2. 安装前请确保系统已安装必要的编译工具（对于 python-snap7 可能需要）
3. 运行前请确保配置文件位于正确的位置