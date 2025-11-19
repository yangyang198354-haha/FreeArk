# 多架构Docker镜像构建指南

## 1. 概述

本指南将指导您为FreeArk数据采集系统构建x86和aarch64（树莓派）两种架构的Docker镜像，并推送到指定的Docker仓库。

## 2. 前置条件

- 已安装Docker Desktop（Windows版本）
- 已拥有Docker仓库账号（如Docker Hub、私有仓库等）
- 网络连接正常

## 3. 配置构建环境

### 3.1 运行构建环境配置脚本

```powershell
# 方式一：进入datacollection目录并运行脚本
powershell -ExecutionPolicy Bypass -Command "cd c:\Users\yanggyan\TRAE\FreeArk\datacollection; .\install_buildx.ps1"

# 方式二：在FreeArk目录直接运行脚本
powershell -ExecutionPolicy Bypass -File .\datacollection\install_buildx.ps1
```

该脚本将：
- 检查Docker是否已安装并启动
- 启用Docker Buildx多架构构建功能
- 创建并配置多架构构建上下文

### 3.2 验证构建环境

运行以下命令验证Buildx是否已成功配置：

```powershell
docker buildx ls
```

如果输出包含`linux/amd64`和`linux/arm64`等平台信息，则配置成功。

## 4. 构建并推送多架构镜像

### 4.1 登录Docker仓库

```powershell
docker login <your-registry-url> -u <username>
```

### 4.2 运行构建推送脚本

```powershell
# 进入datacollection目录
cd c:\Users\yanggyan\TRAE\FreeArk\datacollection

# 方式一：直接指定仓库URL
.uild_push.ps1 -RepositoryUrl <your-username>/freeark-data-collector

# 方式二：交互式输入仓库URL
.uild_push.ps1
```

该脚本将：
- 检查构建环境是否配置完成
- 使用Buildx构建x86（linux/amd64）和aarch64（linux/arm64）两种架构的镜像
- 为镜像添加`latest`标签和时间戳标签
- 将镜像推送到指定的Docker仓库

## 5. 验证镜像

### 5.1 查看本地镜像

```powershell
docker buildx imagetools inspect <your-username>/freeark-data-collector:latest
```

### 5.2 在树莓派上运行镜像

```bash
docker run -it --rm <your-username>/freeark-data-collector:latest python --version
```

## 6. 脚本说明

### 6.1 install_buildx.ps1

用于配置Docker Buildx多架构构建环境。

### 6.2 build_push.ps1

用于构建多架构镜像并推送到Docker仓库。

参数说明：
- `-RepositoryUrl`: Docker仓库URL（可选，未提供则交互式输入）

## 7. 注意事项

- 确保Docker Desktop已启用WSL 2后端以获得更好的性能
- 构建过程可能需要较长时间，尤其是第一次构建
- 确保本地网络可以访问Docker Hub或您指定的私有仓库
- 树莓派需要安装Docker才能运行镜像