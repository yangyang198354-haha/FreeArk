@echo off

rem 数据库迁移脚本 - 将SQLite数据迁移到MySQL

set "SCRIPT_DIR=%~dp0"
set "PYTHON_EXECUTABLE=python"

echo =====================================================
echo 数据库迁移工具：从SQLite迁移到MySQL

echo 当前目录: %SCRIPT_DIR%
echo =====================================================

rem 检查Python是否安装
where %PYTHON_EXECUTABLE% >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo 错误：未找到Python。请确保Python已安装并添加到系统环境变量中。
    pause
    exit /b 1
)

rem 显示Python版本
echo 检查Python版本...
%PYTHON_EXECUTABLE% --version
if %ERRORLEVEL% neq 0 (
    echo 错误：无法获取Python版本。
    pause
    exit /b 1
)

rem 安装必要的依赖
echo.
echo 安装必要的Python依赖...
%PYTHON_EXECUTABLE% -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo 警告：安装依赖失败。尝试只安装MySQL驱动...
    %PYTHON_EXECUTABLE% -m pip install mysqlclient
    if %ERRORLEVEL% neq 0 (
        echo 错误：安装mysqlclient失败。尝试安装pymysql...
        %PYTHON_EXECUTABLE% -m pip install pymysql
    )
)

rem 创建导出目录
mkdir "%SCRIPT_DIR%export_data" 2>nul

rem 导出SQLite数据
echo.
echo =====================================================
echo 开始从SQLite数据库导出数据...
echo =====================================================
%PYTHON_EXECUTABLE% "%SCRIPT_DIR%export_sqlite_data.py"
if %ERRORLEVEL% neq 0 (
    echo 错误：导出SQLite数据失败。
    pause
    exit /b 1
)

rem 导入数据到MySQL
echo.
echo =====================================================
echo 开始导入数据到MySQL数据库...
echo 请确保MySQL服务已启动，并且数据库freeark已创建

echo MySQL连接信息：
echo - 主机: 192.168.31.97
echo - 端口: 3306
echo - 数据库: freeark
echo - 用户名: root
echo - 密码: root
echo =====================================================

choice /c YN /m "是否继续导入数据到MySQL?"
if %ERRORLEVEL% neq 1 (
    echo 操作已取消。
    pause
    exit /b 0
)

%PYTHON_EXECUTABLE% "%SCRIPT_DIR%import_to_mysql.py"
if %ERRORLEVEL% neq 0 (
    echo 错误：导入数据到MySQL失败。
    pause
    exit /b 1
)

echo.
echo =====================================================
echo 数据库迁移完成！
echo =====================================================
echo 所有SQLite表已迁移到MySQL数据库。
echo 您现在可以通过运行start_services.bat来启动使用MySQL的服务。

echo.
pause