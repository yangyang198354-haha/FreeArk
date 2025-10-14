@echo off

REM 查找Python解释器
set "python_exe="
for /f "tokens=* usebackq" %%i in (`where python 2^>nul`) do (
    set "python_exe=%%i"
    goto :found_python
)

REM 如果没有找到Python，尝试从Python安装目录查找
if not defined python_exe (
    echo 正在搜索Python安装目录...
    for /d "tokens=*" %%i in ("%ProgramFiles%\Python*", "%ProgramFiles(x86)%\Python*") do (
        if exist "%%i\python.exe" (
            set "python_exe=%%i\python.exe"
            goto :found_python
        )
    )
)

:found_python
if defined python_exe (
    echo 找到Python解释器: %python_exe%
    echo 正在启动改进版数据收集管理器...
    "%python_exe%" "%~dp0datacollection\improved_data_collection_manager.py"
) else (
    echo 错误: 未找到Python解释器，请先安装Python。
    pause
    exit /b 1
)

pause