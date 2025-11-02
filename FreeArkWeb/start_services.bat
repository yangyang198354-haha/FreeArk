@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cls

echo 启动FreeArkWeb服务
===============
REM 使用MySQL
set DB_ENGINE=django.db.backends.mysql
set DB_NAME=freeark
set DB_USER=root
set DB_PASSWORD=root
set DB_HOST=192.168.31.97
set DB_PORT=3306

REM 设置目录路径
set SCRIPT_DIR=%~dp0
set FRONTEND_DIR=%SCRIPT_DIR%frontend
set BACKEND_DIR=%SCRIPT_DIR%backend\freearkweb

REM 启动后端服务
echo 启动后端服务...
start "后端服务" cmd /k "cd /d %BACKEND_DIR% && python manage.py runserver 0.0.0.0:8000"

REM 等待后端启动
ping 127.0.0.1 -n 5 >nul

REM 构建前端
echo 构建前端项目...
cd /d %FRONTEND_DIR%

REM 尝试找到npm的完整路径 - 改进版本
set "NPM_PATH="
set "NPM_CMD="

REM 方法1: 直接检查PATH环境变量中的npm
for %%i in (npm.cmd) do (
    if exist "%%~$PATH:i" (
        set "NPM_CMD=%%~$PATH:i"
        set "NPM_PATH=%%~dp$PATH:i"
        goto npm_found
    )
)

REM 方法2: 尝试常见的Node.js安装路径
set "NODEJS_PATHS[0]=C:\Program Files\nodejs"
set "NODEJS_PATHS[1]=C:\Program Files (x86)\nodejs"
set "NODEJS_PATHS[2]=%LOCALAPPDATA%\nvs\default\bin"

for /L %%j in (0,1,2) do (
    if exist "!NODEJS_PATHS[%%j]!\npm.cmd" (
        set "NPM_CMD=!NODEJS_PATHS[%%j]!\npm.cmd"
        set "NPM_PATH=!NODEJS_PATHS[%%j]!\"
        goto npm_found
    )
)

:npm_found
if not defined NPM_CMD (
    echo 错误: 未找到npm命令，请确保Node.js已正确安装
    echo 请手动安装Node.js并将其添加到系统PATH
    goto end
)

REM 使用完整路径执行npm命令
echo 使用npm命令路径: %NPM_CMD%
echo 当前工作目录: %CD%

REM 使用call命令和完整路径执行npm
call "%NPM_CMD%" install > npm_install.log 2>&1
if %ERRORLEVEL% neq 0 (
    echo 前端依赖安装失败，请检查npm_install.log
    echo 错误详情:
    type npm_install.log
    goto end
)

echo 依赖安装成功，开始构建...
call "%NPM_CMD%" run build > npm_build.log 2>&1
if %ERRORLEVEL% neq 0 (
    echo 前端构建失败，请检查npm_build.log
    echo 构建错误详情:
    type npm_build.log
    goto end
)

REM 启动前端服务
echo 启动前端服务...
start "前端服务" cmd /k "cd /d %FRONTEND_DIR% && python server.py"

REM 等待前端启动
ping 127.0.0.1 -n 3 >nul

REM 打开浏览器
start http://localhost:8080/

echo 服务已启动
echo Backend: http://localhost:8000/
echo Frontend: http://localhost:8080/

:end
pause