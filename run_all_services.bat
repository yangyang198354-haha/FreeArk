@echo off
cls

echo 启动脚本
==============

set DB_ENGINE=django.db.backends.mysql
set DB_NAME=freeark
set DB_USER=root
set DB_PASSWORD=root
set DB_HOST=192.168.31.97
set DB_PORT=3306



REM 设置目录路径
set SCRIPT_DIR=%~dp0
set FRONTEND_DIR=%SCRIPT_DIR%FreeArkWeb\frontend
set BACKEND_DIR=%SCRIPT_DIR%FreeArkWeb\backend\freearkweb

REM 启动后端服务
start "后端服务" cmd /k "cd /d %BACKEND_DIR% && python manage.py runserver 0.0.0.0:8000"

REM 等待后端启动
ping 127.0.0.1 -n 5 >nul

REM 构建前端
echo 构建前端项目...
cd /d %FRONTEND_DIR%
call npm install > npm_install.log 2>&1
if %ERRORLEVEL% neq 0 (
    echo 前端依赖安装失败
    goto end
)

call npm run build > npm_build.log 2>&1
if %ERRORLEVEL% neq 0 (
    echo 前端构建失败
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
Backend: http://localhost:8000/
Frontend: http://localhost:8080/

:end
pause