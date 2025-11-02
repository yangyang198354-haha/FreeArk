@echo off

echo 正在安装PLC数据清理服务所需的依赖...
echo ==============================================

REM 检查是否已经安装了pip
where pip >nul 2>nul
if %errorlevel% neq 0 (
    echo 错误: 未找到pip，请先安装Python并确保pip可用
    pause
    exit /b 1
)

REM 安装schedule库
echo 安装schedule库...
pip install schedule
if %errorlevel% neq 0 (
    echo 警告: 安装schedule库失败，您可以手动运行: pip install schedule
    pause
)

REM 检查是否安装成功
pip show schedule >nul 2>nul
if %errorlevel% equ 0 (
    echo 依赖安装成功！
    echo 您现在可以运行以下命令启动定时清理服务：
    echo python manage.py schedule_plc_cleanup
    echo 或查看使用说明：
    echo README_PLC_CLEANUP_SCHEDULE.md
) else (
    echo 依赖安装失败，请手动运行: pip install schedule
)

echo ==============================================
echo 安装完成
pause