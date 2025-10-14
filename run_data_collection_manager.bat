@echo off
setlocal enabledelayedexpansion

REM 配置参数
set "SCRIPT_NAME=datacollection\data_collection_manager.py"
set "DEFAULT_THREAD_COUNT=10"

REM 清屏
cls

REM 打印程序信息
echo ===============================================================================
echo                  多线程PLC数据收集管理器
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
echo  1. 自动加载resource目录下的楼栋JSON文件和PLC配置文件
echo  2. 支持多线程并发读取多个PLC的累计制冷量和制热量数据
echo  3. 可配置线程池大小以优化性能
echo  4. 自动管理PLC连接和断开
echo  5. 结果保存为JSON格式，便于后续分析和处理
echo  6. 支持单楼栋或多楼栋批量数据收集
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
set "TEMP_SCRIPT=%TEMP%\data_collection_manager.py.tmp"
if exist "%TEMP_SCRIPT%" del "%TEMP_SCRIPT%"

REM 使用PowerShell替换线程池大小
powershell -Command "
    $content = Get-Content -Path '.\datacollection\data_collection_manager.py' -Raw
    $pattern = 'manager = DataCollectionManager\(max_workers=\d+\)'
    $replacement = 'manager = DataCollectionManager\(max_workers=%THREAD_COUNT%\)'
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
copy /y "%TEMP_SCRIPT%" ".\datacollection\data_collection_manager.py" >nul
if exist "%TEMP_SCRIPT%" del "%TEMP_SCRIPT%"

echo ===============================================================================
echo ✅ 线程池大小已设置为：%THREAD_COUNT%
echo ===============================================================================

REM 询问用户是否要为所有楼栋收集数据
echo.
echo 请选择数据收集模式：
echo  1. 为所有楼栋收集数据
echo  2. 为单个楼栋收集数据
set /p "MODE_INPUT=请输入选择 (1/2，默认1): "
if "%MODE_INPUT%" == "" (
    set "MODE=1"
) else (
    set "MODE=%MODE_INPUT%"
)

REM 根据选择修改脚本
if "%MODE%" == "2" (
    REM 为单个楼栋收集数据
    set /p "BUILDING_FILE=请输入楼栋文件名（例如：1#_data.json）: "
    if "%BUILDING_FILE%" == "" (
        echo ===============================================================================
        echo ❌ 错误：未输入楼栋文件名！
        echo 使用默认模式：为所有楼栋收集数据
        echo ===============================================================================
        set "MODE=1"
    ) else (
        REM 修改脚本以运行单个楼栋数据收集
        set "TEMP_SCRIPT_MODE=%TEMP%\data_collection_manager_mode.tmp"
        powershell -Command "
            $content = Get-Content -Path '.\datacollection\data_collection_manager.py' -Raw
            
            # 注释掉所有楼栋收集的代码
            $pattern_all = '^\s*all_results = manager\.collect_data_for_all_buildings\(\)'
            $replacement_all = '# all_results = manager.collect_data_for_all_buildings()'
            $content = $content -replace $pattern_all, $replacement_all
            
            # 取消注释单个楼栋收集的代码并修改文件名
            $pattern_single = '^\s*# building_file = .*$\s*# results = manager\.collect_data_for_building\(building_file\)$\s*# manager\.save_results_to_json\(building_file\)' 
            $replacement_single = "building_file = '%BUILDING_FILE%'\n    results = manager.collect_data_for_building(building_file)\n    manager.save_results_to_json(building_file)"
            $content = $content -replace $pattern_single, $replacement_single
            
            $content | Set-Content -Path '%TEMP_SCRIPT_MODE%' -Encoding UTF8
        "
        
        if exist "%TEMP_SCRIPT_MODE%" (
            copy /y "%TEMP_SCRIPT_MODE%" ".\datacollection\data_collection_manager.py" >nul
            del "%TEMP_SCRIPT_MODE%"
            echo ===============================================================================
            echo ✅ 已配置为单个楼栋数据收集模式：%BUILDING_FILE%
            echo ===============================================================================
        )
    )
) else (
    REM 为所有楼栋收集数据
    set "TEMP_SCRIPT_MODE=%TEMP%\data_collection_manager_mode.tmp"
    powershell -Command "
        $content = Get-Content -Path '.\datacollection\data_collection_manager.py' -Raw
        
        # 取消注释所有楼栋收集的代码
        $pattern_all = '^\s*# all_results = manager\.collect_data_for_all_buildings\(\)' 
        $replacement_all = 'all_results = manager.collect_data_for_all_buildings()'
        $content = $content -replace $pattern_all, $replacement_all
        
        # 注释掉单个楼栋收集的代码
        $pattern_single = '^\s*building_file = .*$\s*results = manager\.collect_data_for_building\(building_file\)$\s*manager\.save_results_to_json\(building_file\)' 
        $replacement_single = '# building_file = "1#_data.json"
    # results = manager.collect_data_for_building(building_file)
    # manager.save_results_to_json(building_file)'
        $content = $content -replace $pattern_single, $replacement_single
        
        $content | Set-Content -Path '%TEMP_SCRIPT_MODE%' -Encoding UTF8
    "
    
    if exist "%TEMP_SCRIPT_MODE%" (
        copy /y "%TEMP_SCRIPT_MODE%" ".\datacollection\data_collection_manager.py" >nul
        del "%TEMP_SCRIPT_MODE%"
    )
)

:RunScript
REM 运行Python脚本
echo ===============================================================================
echo 🚀 正在启动数据收集管理器...
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
    echo ✅ 数据收集程序执行完成！
echo ===============================================================================
)

REM 等待用户按键退出
pause

endlocal