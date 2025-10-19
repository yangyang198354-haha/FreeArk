@echo off
:: 设置代码页为UTF-8以支持中文显示
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ========================================================
:: 多线程西门子PLC数据读取工具启动脚本
:: 功能：启动多线程PLC数据读取程序，支持配置线程池大小
:: 作者：系统自动生成
:: 版本：v1.0
:: ========================================================

REM 配置参数
set "SCRIPT_NAME=multi_thread_plc_reader.py"
set "DEFAULT_THREAD_COUNT=5"

REM 清屏
cls

REM 打印程序信息
echo ===============================================================================
echo                  多线程西门子PLC数据读取工具
 echo                                v1.0
REM 绘制简单的图案
echo  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄
echo ▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌
echo ▐░█▀▀▀▀▀▀▀█░▌▐░█▀▀▀▀▀▀▀█░▌▐░█▀▀▀▀▀▀▀█░▌ ▀▀▀▀█░█▀▀▀▀
echo ▐░▌       ▐░▌▐░▌       ▐░▌▐░▌       ▐░▌     ▐░▌     
echo ▐░█▄▄▄▄▄▄▄█░▌▐░█▄▄▄▄▄▄▄█░▌▐░█▄▄▄▄▄▄▄█░▌     ▐░▌     
echo ▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌     ▐░▌     
echo ▐░█▀▀▀▀▀▀▀█░▌ ▀▀▀▀▀▀▀▀▀█░▌▐░█▀▀▀▀▀▀▀█░▌     ▐░▌     
echo ▐░▌       ▐░▌          ▐░▌▐░▌       ▐░▌     ▐░▌     
echo ▐░▌       ▐░▌ ▄▄▄▄▄▄▄▄▄█░▌▐░▌       ▐░▌     ▐░▌     
echo ▐░▌       ▐░▌▐░░░░░░░░░░░▌▐░▌       ▐░▌     ▐░▌     
echo  ▀         ▀  ▀▀▀▀▀▀▀▀▀▀▀  ▀         ▀       ▀      
echo ===============================================================================
echo 功能说明：
echo  1. 支持多线程并发读取多个PLC的数据
  echo  2. 可配置线程池大小以优化性能
  echo  3. 支持多种数据类型：uint16, int16, uint32, int32, float32, float64
  echo  4. 提供详细的读取结果统计
  echo  5. 自动管理PLC连接和断开
  echo  6. 支持配置多个IP地址、DB块、偏移量等参数
  echo 
  echo 注意：使用前请确保已安装snap7库（pip install python-snap7）
echo ===============================================================================

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

:: 检查snap7库是否已安装
echo [日志] 检查snap7库是否已安装...
"%PYTHON_PATH%" -c "import snap7" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo ⚠️  警告：未安装snap7库！
    echo 正在尝试自动安装...
    echo ===============================================================================
    
    :: 检查pip是否可用
    "%PYTHON_PATH%" -m pip --version >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo ❌ 错误：pip不可用！请确保Python已正确安装并包含pip。
        pause
        exit /b 1
    )
    
    "%PYTHON_PATH%" -m pip install python-snap7
    if %ERRORLEVEL% neq 0 (
        echo ===============================================================================
        echo ❌ 错误：snap7库安装失败！
        echo 可能的原因：
        echo 1. 网络连接问题
        echo 2. 权限不足
        echo 3. Python版本不兼容
        echo 请手动运行：pip install python-snap7
        echo ===============================================================================
        pause
        exit /b 1
    )
    echo ===============================================================================
    echo ✅ snap7库安装成功！
    echo ===============================================================================
) else (
    echo ✅ snap7库已安装。
)

:: 询问用户是否要修改线程池大小
echo [日志] 配置线程池大小...
set /p "USER_INPUT=请输入线程池大小（默认%DEFAULT_THREAD_COUNT%，建议1-20）: "
if "%USER_INPUT%" == "" (
    echo [日志] 使用默认线程池大小：%DEFAULT_THREAD_COUNT%
    set "THREAD_COUNT=%DEFAULT_THREAD_COUNT%"
) else (
    echo [日志] 用户输入线程池大小：%USER_INPUT%
    set "THREAD_COUNT=%USER_INPUT%"
)

:: 验证线程池大小是否为数字并在合理范围内
set "VALID_INPUT=true"
for /f "delims=0123456789" %%i in ("%THREAD_COUNT%") do (
    set "VALID_INPUT=false"
)

if "%VALID_INPUT%" == "false" (
    echo ===============================================================================
    echo ❌ 错误：输入的线程池大小不是有效数字！
    echo 使用默认线程池大小：%DEFAULT_THREAD_COUNT%
    set "THREAD_COUNT=%DEFAULT_THREAD_COUNT%"
    echo ===============================================================================
) else if %THREAD_COUNT% lss 1 ( 
    echo ===============================================================================
    echo ⚠️  警告：线程池大小不能小于1！
    echo 使用最小线程池大小：1
    set "THREAD_COUNT=1"
    echo ===============================================================================
) else if %THREAD_COUNT% gtr 50 ( 
    echo ===============================================================================
    echo ⚠️  警告：线程池大小过大可能导致系统资源不足！
    echo 使用最大线程池大小：50
    set "THREAD_COUNT=50"
    echo ===============================================================================
)

:: 检查Python脚本是否存在
echo [日志] 检查Python脚本是否存在...
if not exist ".\%SCRIPT_NAME%" (
    echo ===============================================================================
    echo ❌ 错误：未找到Python脚本 %SCRIPT_NAME%！
    echo 请确保脚本文件存在于当前目录。
    echo ===============================================================================
    pause
    exit /b 1
)

:: 修改Python脚本中的线程池大小
echo [日志] 更新Python脚本中的线程池配置...
set "TEMP_SCRIPT=%TEMP%\%SCRIPT_NAME%.tmp"
if exist "%TEMP_SCRIPT%" del "%TEMP_SCRIPT%"

:: 使用PowerShell替换线程池大小（避免批处理中的复杂文本处理）
powershell -Command "
    $content = Get-Content -Path '.\%SCRIPT_NAME%' -Raw
    $pattern = 'plc_manager = PLCManager\(max_workers=\d+\)'
    $replacement = 'plc_manager = PLCManager\(max_workers=%THREAD_COUNT%\)'
    $content -replace $pattern, $replacement | Set-Content -Path '%TEMP_SCRIPT%' -Encoding UTF8
"

:: 检查临时文件是否生成成功
if not exist "%TEMP_SCRIPT%" (
    echo ===============================================================================
    echo ⚠️  警告：无法修改Python脚本配置！
    echo 可能的原因：
    echo 1. 脚本格式不符合预期
    echo 2. 权限不足
    echo 使用脚本默认配置运行...
    echo ===============================================================================
    goto :RunScript
)

:: 替换原脚本
copy /y "%TEMP_SCRIPT%" ".\%SCRIPT_NAME%" >nul
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo ⚠️  警告：无法保存修改后的脚本！
    echo 使用脚本默认配置运行...
    echo ===============================================================================
    goto :RunScript
)

if exist "%TEMP_SCRIPT%" del "%TEMP_SCRIPT%"

echo ===============================================================================
echo ✅ 线程池大小已设置为：%THREAD_COUNT%
echo ===============================================================================

:RunScript
:: 运行Python脚本
echo ===============================================================================
echo 🚀 正在启动多线程PLC数据读取程序...
echo （按Ctrl+C可以随时终止程序）
echo ===============================================================================

:: 尝试运行脚本并捕获错误
set "SCRIPT_ERROR=0"
"%PYTHON_PATH%" %SCRIPT_NAME%
set "SCRIPT_ERROR=%ERRORLEVEL%"

:: 记录脚本结束执行时间
set "END_TIME=%TIME%"
echo [日志] 脚本执行结束：%DATE% %END_TIME%

:: 检查运行结果
if %SCRIPT_ERROR% neq 0 (
    echo ===============================================================================
    echo ❌ 程序执行出错！错误代码：%SCRIPT_ERROR%
    echo 可能的原因：
    echo 1. PLC连接失败
    echo 2. 配置文件错误
    echo 3. Python脚本内部错误
    echo 请查看程序输出的详细错误信息。
    echo ===============================================================================
) else (
    echo ===============================================================================
    echo ✅ 程序执行完成！
    echo 数据读取任务已完成。
    echo ===============================================================================
)

:: 等待用户按键退出
echo 按任意键退出...
pause >nul

endlocal