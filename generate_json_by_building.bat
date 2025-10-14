@echo off
REM 批量生成楼栋JSON数据文件的批处理脚本

REM 设置Python安装路径
set PYTHON_PATH="C:\Program Files\Python312\python.exe"

REM 检查Python是否存在
if not exist %PYTHON_PATH% (
    echo 错误：未找到Python安装在C:\Program Files\Python312\python.exe
    echo 请手动修改此批处理文件中的PYTHON_PATH为正确的Python安装路径
    pause
    exit /b 1
)

REM 进入脚本所在目录
cd /d %~dp0

REM 运行转换脚本
echo 正在运行JSON转换脚本...
echo.
%PYTHON_PATH% convert_to_json_by_building.py

REM 检查是否成功执行
if %errorlevel% equ 0 (
    echo.
echo 脚本执行成功！
echo 已在resource文件夹下生成了10个楼栋JSON数据文件。
) else (
    echo.
echo 脚本执行失败！
)

echo.
echo 按任意键退出...
pause >nul