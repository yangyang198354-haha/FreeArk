@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: FreeArk 数据收集系统安装与使用脚本

:: 检查Python是否安装
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo  错误：未找到Python！
    echo 请先安装Python 3.8或更高版本。
    echo ===============================================================================
    pause
    exit /b 1
)

:: 获取Python版本
echo 获取Python版本...
python --version

:: 安装依赖
echo ===============================================================================
echo 安装依赖包...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo  错误：安装依赖包失败！
    echo 请检查网络连接或Python环境。
    echo ===============================================================================
    pause
    exit /b 1
)

:: 安装打包工具
echo ===============================================================================
echo 安装打包工具...
python -m pip install setuptools wheel
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo  错误：安装打包工具失败！
    echo 请检查网络连接或Python环境。
    echo ===============================================================================
    pause
    exit /b 1
)

:: 打包为Wheel
echo ===============================================================================
echo 打包为Wheel格式...
python setup.py bdist_wheel
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo  错误：打包为Wheel格式失败！
    echo ===============================================================================
    pause
    exit /b 1
)
echo 打包成功！Wheel文件已生成在 dist 目录中。
echo ===============================================================================

:: 安装包到本地环境
echo ===============================================================================
echo 安装包到本地环境...
python -m pip install -e .
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo  错误：安装包失败！
    echo ===============================================================================
    pause
    exit /b 1
)
echo 安装成功！现在可以通过以下命令运行应用：
echo   - run-data-collection -f [配置文件]
echo ===============================================================================

:: 显示使用说明
echo ===============================================================================
echo FreeArk 数据收集系统安装完成！
echo 您可以通过以下方式使用：
echo 1. 通过pip安装的命令行工具：
echo    - run-data-collection -f [配置文件]
echo 2. 直接运行Python脚本：
echo    - python datacollection\improved_data_collection_manager.py
    - python datacollection\plc_data_viewer_gui.py
    - python datacollection\quantity_statistics.py
echo 3. 使用预构建的批处理文件：
echo    - run_improved_data_collection_manager.bat
echo    - run_plc_data_viewer_gui.bat
echo    - run_quantity_statistics.bat
echo 4. Wheel包位置：
echo    - dist\freeark_datacollection-1.0.0-py3-none-any.whl
echo    可以复制到其他Windows环境通过 pip install [wheel文件路径] 安装

echo ===============================================================================
pause
endlocal
