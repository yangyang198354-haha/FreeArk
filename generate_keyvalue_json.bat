@echo off

REM 设置Python解释器路径
set PYTHON_PATH="C:\Program Files\Python312\python.exe"

REM 检查Python是否存在
if not exist %PYTHON_PATH% (
    echo 错误：未找到Python解释器在 %PYTHON_PATH%
    echo 请检查Python安装路径是否正确
    pause
    exit /b 1
)

REM 显示Python版本信息
%PYTHON_PATH% --version

REM 进入脚本所在目录
cd /d %~dp0

REM 运行转换脚本
echo 开始将JSON文件从数组格式转换为键值对格式...
echo.
%PYTHON_PATH% convert_to_key_value_json.py

REM 检查执行结果
if %errorlevel% equ 0 (
    echo.
    echo 转换完成！键值对格式的JSON文件已保存到resource目录
    echo 文件名格式：楼栋号_data_keyvalue.json
    echo.
    echo 键值对格式特点：
echo 1. 使用"楼栋-单元-楼层-户号"作为唯一标识符键，格式为纯数字+'-'（如'1-1-2-201'）
echo 2. 可以通过键直接访问对应的住户信息，无需遍历整个文件
echo 3. 保留了原始数据的所有字段和值
echo 4. 方便快速查找和访问特定住户的信息
) else (
    echo.
    echo 转换过程中出现错误，请查看上方错误信息
)

pause