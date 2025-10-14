@echo off
REM 搜索Python的安装路径
echo 正在搜索Python安装路径...
dir "C:\Program Files\python.exe" /s /b > python_path.txt 2>nul
dir "C:\Program Files (x86)\python.exe" /s /b >> python_path.txt 2>nul

REM 检查是否找到Python
if exist python_path.txt (
    echo 找到Python安装路径：
    type python_path.txt
) else (
    echo 未找到Python安装路径
)
echo.
echo 按任意键继续...
pause >nul