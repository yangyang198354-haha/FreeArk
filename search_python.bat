@echo off
REM 在整个C盘搜索Python的安装路径
echo 正在C盘搜索Python安装路径...
dir C:\python.exe /s /b > python_locations.txt 2>nul

REM 检查是否找到Python
if exist python_locations.txt (
    echo 找到以下Python安装路径：
    type python_locations.txt
) else (
    echo 在C盘未找到Python安装路径
)
echo.
echo 按任意键继续...
pause >nul