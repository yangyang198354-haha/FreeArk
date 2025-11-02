@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ===============================================================================
echo FreeArk 数量统计工具

echo 检查Python环境...
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo  错误：未找到Python！
    echo 请先安装Python 3.8或更高版本。
    pause
    exit /b 1
)

:: 确保在正确的目录下运行
cd /d %~dp0

:: 尝试导入依赖，如果缺少则提示安装
echo 检查依赖...
python -c "import pandas; import openpyxl; print(' 依赖检查通过')" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo   警告：缺少部分依赖！请先运行 install_and_use.bat 安装依赖。
    echo 正在尝试直接运行，可能会失败...
)

:: 运行主程序
echo 启动数量统计工具...
python datacollection\quantity_statistics.py

pause
endlocal
