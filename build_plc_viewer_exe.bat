@echo off
chcp 65001 >nul

echo ====================================================
echo        朗诗乐府自由方舟 PLC数据查看器 打包工具
echo ====================================================

:: 检查Python环境
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo 错误: 未找到Python环境，请先安装Python
    pause
    exit /b 1
)

echo 正在使用Python环境: 
for /f "delims=" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo %PYTHON_VERSION%

:: 运行打包脚本
echo 开始打包PLC数据查看器...
python build_exe.py

:: 检查打包结果
if %errorlevel% neq 0 (
    echo 打包失败！
    pause
    exit /b 1
)

echo 打包成功！
echo 可执行文件位置: dist/PLC数据查看器.exe
echo 运行前请确保resource目录与可执行文件在同一目录下

echo.  
echo ====================================================
echo                     打包完成
echo ====================================================
pause
