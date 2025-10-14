@echo off
setlocal enabledelayedexpansion

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

REM 查找Python安装路径
set "PYTHON_PATH="

REM 检查常见的Python安装路径
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
    echo ===============================================================================
    pause
    exit /b 1
)

echo ===============================================================================
echo ✅ 已找到Python：%PYTHON_PATH%

REM 检查snap7库是否已安装
"%PYTHON_PATH%" -c "import snap7" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo ⚠️  警告：未安装snap7库！
    echo 正在尝试自动安装...
    "%PYTHON_PATH%" -m pip install python-snap7
    if %ERRORLEVEL% neq 0 (
        echo ❌ 错误：snap7库安装失败！
        echo 请手动运行：pip install python-snap7
        pause
        exit /b 1
    )
    echo ✅ snap7库安装成功！
echo ===============================================================================
)

REM 询问用户是否要修改线程池大小
set /p "USER_INPUT=请输入线程池大小（默认%DEFAULT_THREAD_COUNT%）: "
if "%USER_INPUT%" == "" (
    set "THREAD_COUNT=%DEFAULT_THREAD_COUNT%"
) else (
    set "THREAD_COUNT=%USER_INPUT%"
)

REM 验证线程池大小是否为数字
for /f "delims=0123456789" %%i in ("%THREAD_COUNT%") do (
    echo ===============================================================================
    echo ❌ 错误：输入的线程池大小不是有效数字！
    echo 使用默认线程池大小：%DEFAULT_THREAD_COUNT%
    set "THREAD_COUNT=%DEFAULT_THREAD_COUNT%"
echo ===============================================================================
)

REM 修改Python脚本中的线程池大小
set "TEMP_SCRIPT=%TEMP%\%SCRIPT_NAME%.tmp"
if exist "%TEMP_SCRIPT%" del "%TEMP_SCRIPT%"

REM 使用PowerShell替换线程池大小（避免批处理中的复杂文本处理）
powershell -Command "
    $content = Get-Content -Path '.\%SCRIPT_NAME%' -Raw
    $pattern = 'plc_manager = PLCManager\(max_workers=\d+\)'
    $replacement = 'plc_manager = PLCManager\(max_workers=%THREAD_COUNT%\)'
    $content -replace $pattern, $replacement | Set-Content -Path '%TEMP_SCRIPT%' -Encoding UTF8
"

REM 检查临时文件是否生成成功
if not exist "%TEMP_SCRIPT%" (
    echo ===============================================================================
    echo ❌ 错误：无法修改Python脚本配置！
    echo 使用脚本默认配置运行...
echo ===============================================================================
    goto :RunScript
)

REM 替换原脚本
copy /y "%TEMP_SCRIPT%" ".\%SCRIPT_NAME%" >nul
if exist "%TEMP_SCRIPT%" del "%TEMP_SCRIPT%"

echo ===============================================================================
echo ✅ 线程池大小已设置为：%THREAD_COUNT%
echo ===============================================================================

:RunScript
REM 运行Python脚本
echo ===============================================================================
echo 🚀 正在启动多线程PLC数据读取程序...
echo （按Ctrl+C可以随时终止程序）
echo ===============================================================================
"%PYTHON_PATH%" %SCRIPT_NAME%

REM 检查运行结果
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo ❌ 程序执行出错！
echo ===============================================================================
) else (
    echo ===============================================================================
    echo ✅ 程序执行完成！
echo ===============================================================================
)

REM 等待用户按键退出
pause

endlocal