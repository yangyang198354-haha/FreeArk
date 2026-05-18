# CI/CD Pipeline — FreeArk PLC Write Feature

**Status**: DRAFT  
**Author**: devops-engineer  
**Date**: 2026-05-19  
**Project**: FreeArk — PLC Device Settings + Write Record (本期发布)

---

## 概述

本项目无独立 CI 平台（无 GitHub Actions / Jenkins / GitLab CI）。  
当前采用**最小可行流水线**：本地跑测试 → push → 远端 git pull → migrate → 重启服务。  
本文档记录每一步的明确命令，确保可重复执行。

禁止引入：Docker、docker-compose、Kubernetes、Helm、任何新 CI 平台。

---

## 流水线总览

```
[本地 Windows]                        [远端 树莓派 192.168.31.51]
     │
     ▼
1. 本地测试 (pytest)
     │
     ▼
2. git push origin main
     │ ──── SSH via plink ────────────▶
                                        3. git pull
                                        4. python manage.py migrate api
                                        5. systemctl restart freeark-gunicorn
                                        6. systemctl restart freeark-mqtt-consumer
                                        7. systemctl restart freeark-task-scheduler
                                        8. npm install（远端）
                                        9. npm run build（远端）
                                       10. cp -r dist/ /usr/share/nginx/html/（远端）
                                       11. systemctl reload nginx
                                       12. 健康检查
```

> **前端 build 位置说明（本期变更）**：  
> 本期改为**在树莓派上 build**（远端 build），移除了本地 Windows 的 npm 构建步骤。  
> 本地端只保留：pytest 测试、git push。  
> 远端 git pull 后，在树莓派上执行 `npm install && npm run build`，  
> 产物 `dist/` 通过远端 `cp -r` 复制到 nginx root `/usr/share/nginx/html`（无任何本地 → 远端文件传输）。  
> 详细命令见 deployment_plan.md STEP 7。

---

## 阶段 1 — 本地准备（PowerShell，Windows 开发机）

### 1.1 确认工作区干净

```powershell
cd C:\Users\yanggyan\MyProject\FreeArk
git status
git pull --rebase origin main
```

### 1.2 运行测试套件（全量，55 用例）

```powershell
cd C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend
$env:DJANGO_SETTINGS_MODULE = "freearkweb.settings"
$env:DJANGO_TEST_DB = "sqlite"
python -m pytest freearkweb/api/tests/ -v --tb=short
```

期望输出：`55 passed, 0 warnings`

如有失败，**停止**，不得 push。

### 1.3 push 到远端

```powershell
cd C:\Users\yanggyan\MyProject\FreeArk
git add .
git commit -m "release: PLC device-settings + write-record"   # 若有未提交改动
git push origin main
```

---

## 阶段 2 — 远端部署（plink，每条命令独立执行）

> 所有 plink 命令格式（复制后替换 `<RPI_PASS>`）：
> ```powershell
> $PLINK = "C:\Program Files\PuTTY\plink.exe"
> $REMOTE = "yangyang@192.168.31.51"
> $HOSTKEY = "SHA256:TfpCSrSLuK1UspD2mpikebK0bE0IFnPH8bSigERWnmk"
> $SSH_PASS = "<RPI_PASS>"
> $PLINK_OPTS = "-batch -hostkey $HOSTKEY -pw $SSH_PASS"
> ```

### 2.1 git pull

```powershell
& $PLINK $PLINK_OPTS.Split() $REMOTE "cd /home/yangyang/Freeark/FreeArk && git pull origin main 2>&1"
```

### 2.2 migrate（⚠ 需用户 CONFIRM）

```powershell
# 先干跑，确认只有 0023_plcwriterecord
& $PLINK $PLINK_OPTS.Split() $REMOTE "cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb && /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py migrate api --plan 2>&1"

# 确认无误后正式执行（⚠ 需用户 CONFIRM）
& $PLINK $PLINK_OPTS.Split() $REMOTE "cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb && /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py migrate api --no-input 2>&1"
```

### 2.3 重启 freeark-gunicorn（⚠ 需用户 CONFIRM）

```powershell
& $PLINK $PLINK_OPTS.Split() $REMOTE "sudo systemctl restart freeark-gunicorn && sleep 3 && sudo systemctl is-active freeark-gunicorn && echo GUNICORN_OK"
```

### 2.4 重启 freeark-mqtt-consumer（⚠ 需用户 CONFIRM）

```powershell
& $PLINK $PLINK_OPTS.Split() $REMOTE "sudo systemctl restart freeark-mqtt-consumer && sleep 5 && sudo systemctl is-active freeark-mqtt-consumer && echo MQTT_OK"
```

### 2.5 远端前端 build + 复制 dist + reload nginx（⚠ 需用户 CONFIRM）

```powershell
$RFRONT = "/home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend"
$RNGINX = "/usr/share/nginx/html"

# 远端 npm install（复用 git pull 后的最新 package.json，首次约 5~15 分钟）
& $PLINK $PLINK_OPTS.Split() $REMOTE "cd $RFRONT && npm install 2>&1"

# 远端 npm run build（在树莓派 ARM 上 esbuild，预计 3~8 分钟）
& $PLINK $PLINK_OPTS.Split() $REMOTE "cd $RFRONT && npm run build 2>&1"

# 确认产物存在
& $PLINK $PLINK_OPTS.Split() $REMOTE "test -f $RFRONT/dist/index.html && echo BUILD_OK || echo BUILD_FAILED"

# 备份旧 dist 并清空 nginx root
& $PLINK $PLINK_OPTS.Split() $REMOTE "sudo cp -r $RNGINX /home/yangyang/FreeArk_backup/nginx_dist_bak_`$(date +%Y%m%d_%H%M%S) 2>/dev/null; sudo rm -rf ${RNGINX}/* && echo DIST_CLEARED"

# 远端复制 dist 到 nginx root（远端本地 cp，无文件上传）
& $PLINK $PLINK_OPTS.Split() $REMOTE "sudo cp -r $RFRONT/dist/. $RNGINX/ && echo DIST_COPIED"

# reload nginx
& $PLINK $PLINK_OPTS.Split() $REMOTE "sudo nginx -t 2>&1 && sudo systemctl reload nginx && echo NGINX_RELOADED"
```

### 2.6 重启 freeark-task-scheduler（⚠ 需用户 CONFIRM）

```powershell
& $PLINK $PLINK_OPTS.Split() $REMOTE "sudo systemctl restart freeark-task-scheduler && sleep 5 && sudo systemctl is-active freeark-task-scheduler && echo SCHEDULER_OK"
```

---

## 阶段 3 — 健康检查

```powershell
# API 冒烟
& $PLINK $PLINK_OPTS.Split() $REMOTE "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/device-settings/records/?page=1"

# 服务状态
& $PLINK $PLINK_OPTS.Split() $REMOTE "sudo systemctl is-active freeark-gunicorn freeark-mqtt-consumer freeark-task-scheduler nginx"

# PLCWriteSubscriber 启动日志
& $PLINK $PLINK_OPTS.Split() $REMOTE "sudo journalctl -u freeark-task-scheduler -n 30 --no-pager | grep -E 'PLCWriteSubscriber|启动|ERROR'"
```

---

## 阶段 4 — 回滚（仅在部署异常时执行，⚠ 需用户 CONFIRM）

```powershell
# DB 回滚：回退到 0022（0023 引入的 plc_write_record 表为全新表，无既有数据损失）
& $PLINK $PLINK_OPTS.Split() $REMOTE "cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb && /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py migrate api 0022_device_tree_sync --no-input 2>&1"

# 代码回滚（⚠ 需用户 CONFIRM — 确认 commit hash 后再执行）
& $PLINK $PLINK_OPTS.Split() $REMOTE "cd /home/yangyang/Freeark/FreeArk && git log --oneline -5"
# 确认 hash 后：
& $PLINK $PLINK_OPTS.Split() $REMOTE "cd /home/yangyang/Freeark/FreeArk && git reset --hard <previous_commit>"
```

---

*本文件由 devops-engineer 自动生成，实际破坏性命令均标注"需用户 CONFIRM"，等待 PM 触发。*
