@echo off

REM 设置控制台编码为UTF-8，确保中文正常显示
chcp 65001 > nul

REM 进入脚本所在目录
cd /d "%~dp0"

REM 检查Python是否安装
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未找到Python。请先安装Python并确保它在系统路径中。
    pause
    exit /b 1
)

REM 运行PLC数据查看器GUI
echo 正在启动PLC数据查看器...
python plc_data_viewer_gui.py

REM 如果程序退出，等待用户按键
if %errorlevel% neq 0 (
    echo 程序出现错误，请检查错误信息。
    pause
)