@echo off
:: 设置代码页为UTF-8以支持中文显示
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ========================================================
:: 用量统计工具启动脚本
:: 功能：执行quantity_statistics.py，收集所有PLC数据并生成统计报表
:: 作者：系统自动生成
:: 版本：v1.0
:: ========================================================

:: 设置批处理文件所在目录为当前工作目录
cd /d "%~dp0"

:: 记录脚本开始执行时间
set "START_TIME=%TIME%"
echo [日志] 脚本开始执行：%DATE% %START_TIME%

:: 查找Python安装路径
set "PYTHON_PATH="
:: 先尝试从环境变量获取Python
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    for /f "delims=" %%P in ('where python') do (
        set "PYTHON_PATH=%%P"
        goto :PythonFound
    )
)

:: 如果环境变量中没有，则检查常见的Python安装路径
echo [日志] 从环境变量未找到Python，开始检查常见安装路径...
for %%P in (
    "C:\Program Files\Python312\python.exe",
    "C:\Program Files\Python311\python.exe",
    "C:\Program Files\Python310\python.exe",
    "C:\Program Files\Python39\python.exe",
    "C:\Program Files\Python38\python.exe",
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe",
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe",
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe",
    "%LOCALAPPDATA%\Programs\Python\Python39\python.exe",
    "%LOCALAPPDATA%\Programs\Python\Python38\python.exe"
) do (
    if exist "%%~P" (
        set "PYTHON_PATH=%%~P"
        goto :PythonFound
    )
)

:PythonFound
if "%PYTHON_PATH%" == "" (
    echo ===============================================================================
    echo ❌ 错误：未找到Python安装路径！
    echo 请手动安装Python，或检查Python是否已正确安装。
    echo 推荐安装Python 3.8或更高版本。
    echo ===============================================================================
    pause
    exit /b 1
)

echo ===============================================================================
echo ✅ 已找到Python：%PYTHON_PATH%
:: 输出Python版本信息
"%PYTHON_PATH%" --version

:: 检查统计脚本是否存在
echo [日志] 检查Python脚本是否存在...
if not exist ".\datacollection\quantity_statistics.py" (
    echo ===============================================================================
    echo ❌ 错误：未找到Python脚本 datacollection/quantity_statistics.py！
    echo 请确保脚本文件存在于正确的路径。
    echo ===============================================================================
    pause
    exit /b 1
)

:: 运行Python脚本
echo ===============================================================================
echo 🚀 正在运行用量统计工具...
echo 请稍候，正在收集和处理数据...
echo （按Ctrl+C可以随时终止程序）
echo ===============================================================================

:: 尝试运行脚本并捕获错误
set "SCRIPT_ERROR=0"
"%PYTHON_PATH%" datacollection\quantity_statistics.py
set "SCRIPT_ERROR=%ERRORLEVEL%"

:: 记录脚本结束执行时间
set "END_TIME=%TIME%"
echo [日志] 脚本执行结束：%DATE% %END_TIME%

:: 检查运行结果
if %SCRIPT_ERROR% neq 0 (
    echo ===============================================================================
    echo ❌ 用量统计工具运行失败！错误代码：%SCRIPT_ERROR%
    echo 可能的原因：
    echo 1. 缺少必要的Python库（如pandas、openpyxl等）
    echo 2. 数据文件不存在或格式错误
    echo 3. 数据库连接失败
    echo 4. Python脚本内部错误
    echo 请查看程序输出的详细错误信息。
    echo ===============================================================================
) else (
    echo ===============================================================================
    echo ✅ 用量统计工具运行成功！
    echo 统计结果已保存至output目录的"用量统计.xlsx"文件
    echo ===============================================================================
)

:: 等待用户按键退出
echo 按任意键退出...
pause >nul

endlocal