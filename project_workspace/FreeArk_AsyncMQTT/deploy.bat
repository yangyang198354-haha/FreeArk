@echo off
REM ============================================================
REM FreeArk AsyncMQTT Fix — 生产部署脚本
REM 目标: 树莓派 192.168.31.51
REM 生产路径: /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/api/
REM ============================================================

set PLINK="C:\Program Files\PuTTY\plink.exe"
set PSCP="C:\Program Files\PuTTY\pscp.exe"
set HOST=yangyang@192.168.31.51
set PASSWORD=123456
set HOSTKEY=SHA256:TfpCSrSLuK1UspD2mpikebK0bE0IFnPH8bSigERWnmk
set REMOTE_DIR=/home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/api
set LOCAL_FILE=C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend\freearkweb\api\mqtt_consumer.py

echo ============================================================
echo Step 1: 备份远程文件
echo ============================================================
%PLINK% -ssh %HOST% -pw %PASSWORD% -hostkey "%HOSTKEY%" -batch "cp %REMOTE_DIR%/mqtt_consumer.py %REMOTE_DIR%/mqtt_consumer.py.bak.$(date +%%Y%%m%%d_%%H%%M%%S) && echo BACKUP_OK"
if errorlevel 1 (
    echo [ERROR] 备份失败，终止部署
    exit /b 1
)
echo [OK] 备份完成

echo ============================================================
echo Step 2: 传输新文件
echo ============================================================
%PSCP% -pw %PASSWORD% -hostkey "%HOSTKEY%" -batch "%LOCAL_FILE%" "%HOST%:%REMOTE_DIR%/mqtt_consumer.py"
if errorlevel 1 (
    echo [ERROR] 文件传输失败，终止部署
    exit /b 1
)
echo [OK] 文件传输完成

echo ============================================================
echo Step 3: 重启服务
echo ============================================================
%PLINK% -ssh %HOST% -pw %PASSWORD% -hostkey "%HOSTKEY%" -batch "sudo systemctl restart freeark-mqtt-consumer && sleep 5 && sudo systemctl is-active freeark-mqtt-consumer"
if errorlevel 1 (
    echo [ERROR] 服务重启失败
    exit /b 1
)
echo [OK] 服务重启完成

echo ============================================================
echo Step 4: 查看最新日志（验证 worker 线程启动）
echo ============================================================
%PLINK% -ssh %HOST% -pw %PASSWORD% -hostkey "%HOSTKEY%" -batch "sudo journalctl -u freeark-mqtt-consumer -n 60 --no-pager"

echo ============================================================
echo Step 5: 等待 10s 后确认无 DISCONNECT rc=16
echo ============================================================
timeout /t 10 /nobreak
%PLINK% -ssh %HOST% -pw %PASSWORD% -hostkey "%HOSTKEY%" -batch "sudo journalctl -u freeark-mqtt-consumer -n 30 --no-pager | grep -E 'DISCONNECT|rc=16|mqtt-worker|成功连接'"

echo ============================================================
echo 部署完成。请等待 600s 后执行以下命令验证 DB 数据更新：
echo %PLINK% -ssh %HOST% -pw %PASSWORD% -hostkey "%HOSTKEY%" -batch "mysql -h 192.168.31.98 -P 3306 -u root -p123456 freeark -e \"SELECT specific_part, param_name, value, collected_at FROM plclatestdata WHERE specific_part='3-1-7-702' LIMIT 5;\""
echo ============================================================
pause
