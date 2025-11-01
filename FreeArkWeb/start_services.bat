@echo off
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

REM 尝试找到npm的完整路径
for %%i in (npm.cmd) do set NPM_PATH=%%~dp$PATH:i
if not defined NPM_PATH (
    echo 警告: 未找到npm命令，请确保Node.js已正确安装并添加到系统PATH
    echo 尝试使用直接路径...
    set NPM_PATH=C:\Program Files\nodejs\
)

REM 使用绝对路径执行npm命令
echo 使用npm路径: %NPM_PATH%
call "%NPM_PATH%npm" install > npm_install.log 2>&1
if %ERRORLEVEL% neq 0 (
    echo 前端依赖安装失败，请检查npm_install.log
    goto end
)

echo 依赖安装成功，开始构建...
call "%NPM_PATH%npm" run build > npm_build.log 2>&1
if %ERRORLEVEL% neq 0 (
    echo 前端构建失败，请检查npm_build.log
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