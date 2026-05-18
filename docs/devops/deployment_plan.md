# Deployment Plan — FreeArk PLC Device Settings + Write Record

**Status**: DRAFT — 等待用户 CONFIRM 后由 PM 触发实际执行  
**Author**: devops-engineer  
**Date**: 2026-05-19  
**Target**: 树莓派 192.168.31.51 (yangyang)  
**DB**: MySQL 192.168.31.98:3306  
**Migration**: 0023_plcwriterecord（新增 `plc_write_record` 表）

---

## 一、前置检查清单（部署前必须逐项确认）

| # | 检查项 | 确认命令 | 期望结果 |
|---|--------|---------|---------|
| 1 | 树莓派 Python ≥ 3.10 | `plink ... "/home/yangyang/Freeark/FreeArk/venv/bin/python --version"` | `Python 3.10.x` 或更高 |
| 2 | broker TCP 32788 可达（后端/datacollection 连接） | `plink ... "nc -z 192.168.31.98 32788 && echo BROKER_TCP_OK"` | `BROKER_TCP_OK` |
| 3 | broker WebSocket 32797 可达（前端浏览器侧） | 浏览器开 DevTools，手动连 `ws://192.168.31.98:32797/mqtt` | WS 连接成功，无 ERR_CONNECTION_REFUSED |
| 4 | MySQL 用户有 CREATE TABLE 权限（0023 migrate 需要） | `plink ... "mysql -h 192.168.31.98 -P 3306 -u root -p123456 freeark -e 'SHOW GRANTS FOR CURRENT_USER;' 2>&1 \| grep -i create"` | 输出含 CREATE |
| 5 | datacollection 进程运行中（systemd unit 名已确认） | `plink ... "sudo systemctl is-active freeark-task-scheduler"` | `active` |
| 6 | 本地测试全绿（55 passed, 0 warnings） | 见 cicd_pipeline.md 阶段 1.2 | `55 passed` |
| 7 | 树莓派可用内存 ≥ 512 MB（npm run build 峰值约 400~500 MB，含 esbuild 进程） | `plink ... "free -m \| awk 'NR==2{print $7}'"` | 输出值 ≥ 512 |
| 8 | 树莓派 Node.js ≥ 18（vite@6 + @vitejs/plugin-vue@5 要求） | `plink ... "node --version"` | `v18.x` 或更高 |
| 9 | 树莓派 npm 已安装 | `plink ... "npm --version"` | 输出 npm 版本号（≥ 8 建议） |

> **前端 build 平台说明（本期变更）**：  
> 本期改为**在树莓派上 build**（远端 build）。  
> `package.json` 无 `engines` 字段，但 `vite@^6.0.1` + `@vitejs/plugin-vue@^5.2.1` 要求 Node.js ≥ 18（vite 6 官方最低要求）。  
> `vite.config.js` 的 `build.outDir` 默认为 `dist`，即产物位于  
> `/home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend/dist`，  
> nginx root 为 `/usr/share/nginx/html`，**两者路径不同，需远端 `cp -r` 复制**（步骤 7d）。  
> 整条链路**无任何本地 → 远端文件传输**（git pull 是远端从 git server 拉取，不算本地上传）。

---

## 二、部署步骤（按序执行，每步可复制命令）

> **变量约定**（在 PowerShell 会话中一次性设置）：
> ```powershell
> $PLINK   = "C:\Program Files\PuTTY\plink.exe"
> $REMOTE  = "yangyang@192.168.31.51"
> $HOSTKEY = "SHA256:TfpCSrSLuK1UspD2mpikebK0bE0IFnPH8bSigERWnmk"
> $SSH_PASS = "<RPI_PASS>"          # 不硬编码，运行时填入
> $PL_OPTS = @("-batch", "-hostkey", $HOSTKEY, "-pw", $SSH_PASS)
> $RPROJ   = "/home/yangyang/Freeark/FreeArk"
> $RBACK   = "$RPROJ/FreeArkWeb/backend/freearkweb"
> $RVENV   = "$RPROJ/venv/bin/python"
> $RFRONT  = "$RPROJ/FreeArkWeb/frontend"
> $RNGINX  = "/usr/share/nginx/html"
> ```

---

### STEP 1 — 本地确认无未提交改动

```powershell
cd C:\Users\yanggyan\MyProject\FreeArk
git status          # 期望：nothing to commit / working tree clean
git pull --rebase origin main
```

---

### STEP 2 — 本地跑测试套件

```powershell
cd C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend
$env:DJANGO_SETTINGS_MODULE = "freearkweb.settings"
$env:DJANGO_TEST_DB = "sqlite"
python -m pytest freearkweb/api/tests/ -v --tb=short
```

期望：`55 passed, 0 warnings`。若有失败，**停止部署**。

---

### STEP 3 — 本地 push

```powershell
cd C:\Users\yanggyan\MyProject\FreeArk
git push origin main
```

---

### STEP 4 — 远端 git pull（⚠ 需用户 CONFIRM）

```powershell
& $PLINK $PL_OPTS $REMOTE "cd $RPROJ && git pull origin main 2>&1"
```

期望输出含：新增文件列表（0023_plcwriterecord.py、plc_write_subscriber.py、views_device_settings.py 等）

---

### STEP 5 — Django migrate（⚠ 需用户 CONFIRM）

**5a. 干跑确认（先看计划，不写 DB）：**

```powershell
& $PLINK $PL_OPTS $REMOTE "cd $RBACK && $RVENV manage.py migrate api --plan 2>&1"
```

期望输出：仅 `Run migrations: api.0023_plcwriterecord`（CREATE TABLE plc_write_record）

**5b. 正式执行（⚠ 需用户 CONFIRM）：**

```powershell
& $PLINK $PL_OPTS $REMOTE "cd $RBACK && $RVENV manage.py migrate api --no-input 2>&1"
```

期望输出含：`Applying api.0023_plcwriterecord... OK`

---

### STEP 6 — 重启 freeark-gunicorn（⚠ 需用户 CONFIRM）

```powershell
& $PLINK $PL_OPTS $REMOTE "sudo systemctl restart freeark-gunicorn && sleep 3 && sudo systemctl is-active freeark-gunicorn && echo GUNICORN_OK"
```

若失败，查看日志：

```powershell
& $PLINK $PL_OPTS $REMOTE "sudo journalctl -u freeark-gunicorn -n 30 --no-pager"
```

---

### STEP 7 — 远端前端 build + 复制 dist + reload nginx（⚠ 需用户 CONFIRM）

> 所有子步骤均通过 `plink` 在树莓派上远端执行，**无任何本地 → 远端文件传输**。  
> `vite.config.js` 的 `build.outDir` 默认为 `dist`，产物位于 `$RFRONT/dist`；  
> nginx root 为 `/usr/share/nginx/html`，两者不同，需远端 `cp -r` 复制（见 7d）。

**7a. 远端 npm install（首次约 5~15 分钟，复用 git pull 后的最新 package.json）：**

```powershell
& $PLINK $PL_OPTS $REMOTE "cd $RFRONT && npm install 2>&1"
```

若树莓派可用内存紧张（< 512 MB），在 7b 中追加 `NODE_OPTIONS=--max-old-space-size=512`。

**7b. 远端 npm run build（在树莓派 ARM 上执行 esbuild，预计 3~8 分钟）：**

```powershell
& $PLINK $PL_OPTS $REMOTE "cd $RFRONT && npm run build 2>&1"
```

确认产物存在：

```powershell
& $PLINK $PL_OPTS $REMOTE "test -f $RFRONT/dist/index.html && echo BUILD_OK || echo BUILD_FAILED"
```

**7c. 备份远端旧 nginx dist：**

```powershell
& $PLINK $PL_OPTS $REMOTE "sudo cp -r $RNGINX /home/yangyang/FreeArk_backup/nginx_dist_bak_`$(date +%Y%m%d_%H%M%S) 2>/dev/null; sudo rm -rf ${RNGINX}/* && echo DIST_CLEARED"
```

**7d. 远端复制 dist 到 nginx root（远端本地 cp，无文件上传）：**

```powershell
& $PLINK $PL_OPTS $REMOTE "sudo cp -r $RFRONT/dist/. $RNGINX/ && echo DIST_COPIED"
```

**7e. 检测 nginx 配置并 reload（⚠ 需用户 CONFIRM）：**

```powershell
& $PLINK $PL_OPTS $REMOTE "sudo nginx -t 2>&1 && sudo systemctl reload nginx && echo NGINX_RELOADED"
```

---

### STEP 8 — 重启 freeark-task-scheduler（启动 PLCWriteSubscriber）（⚠ 需用户 CONFIRM）

```powershell
& $PLINK $PL_OPTS $REMOTE "sudo systemctl restart freeark-task-scheduler && sleep 5 && sudo systemctl is-active freeark-task-scheduler && echo SCHEDULER_OK"
```

确认 PLCWriteSubscriber 日志：

```powershell
& $PLINK $PL_OPTS $REMOTE "sudo journalctl -u freeark-task-scheduler -n 30 --no-pager | grep -E 'PLCWriteSubscriber|启动|ERROR'"
```

期望含：`PLCWriteSubscriber 线程已启动` 或 `PLCWriteSubscriber 已订阅`

---

### STEP 9 — 重启 freeark-mqtt-consumer（⚠ 需用户 CONFIRM）

```powershell
& $PLINK $PL_OPTS $REMOTE "sudo systemctl restart freeark-mqtt-consumer && sleep 5 && sudo systemctl is-active freeark-mqtt-consumer && echo MQTT_OK"
```

---

## 三、健康检查（部署后 5 分钟内完成）

| # | 检查项 | 命令 / 操作 | 期望结果 |
|---|--------|------------|---------|
| 1 | API 冒烟 | `plink ... "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/device-settings/records/?page=1"` | `200` 或 `401`（401 表示接口存在但需认证，正常） |
| 2 | 设备列表 → 设置面板 | 浏览器打开设备列表页，点"设置"按钮 | DeviceSettingsPanelView 面板渲染，无 console error |
| 3 | WebSocket 连接 | 浏览器 DevTools Console：检查 `ws://192.168.31.98:32797/mqtt` | 连接状态 OPEN，无 ERR_CONNECTION_REFUSED |
| 4 | Django 日志 | `plink ... "sudo journalctl -u freeark-gunicorn -n 50 --no-pager \| grep -i error"` | 无新增 ERROR |
| 5 | datacollection 启动日志 | `plink ... "sudo journalctl -u freeark-task-scheduler -n 30 --no-pager \| grep -E 'PLCWriteSubscriber\|启动'"` | 含 `PLCWriteSubscriber 线程已启动` |

---

## 四、回滚方案（仅在部署异常时执行）

### DB 回滚（⚠ 需用户 CONFIRM）

```powershell
& $PLINK $PL_OPTS $REMOTE "cd $RBACK && $RVENV manage.py migrate api 0022_device_tree_sync --no-input 2>&1"
```

> 数据安全说明：`plc_write_record` 表为本期全新创建，回退 schema 不损失任何既有业务数据。

### 代码回滚（⚠ 需用户 CONFIRM — 用户确认 commit hash 后才执行）

```powershell
# 先查看历史，确认 hash
& $PLINK $PL_OPTS $REMOTE "cd $RPROJ && git log --oneline -5"

# 用户确认 hash 后执行（⚠ 需用户 CONFIRM）
& $PLINK $PL_OPTS $REMOTE "cd $RPROJ && git reset --hard <previous_commit>"
```

### 前端回滚（⚠ 需用户 CONFIRM）

```powershell
& $PLINK $PL_OPTS $REMOTE "sudo cp -r /home/yangyang/FreeArk_backup/nginx_dist_bak_<TIMESTAMP>/* $RNGINX/ && sudo systemctl reload nginx && echo FRONTEND_ROLLBACK_OK"
```

---

## 五、风险与已知问题

| # | 风险 | 影响 | 缓解措施 |
|---|------|------|---------|
| 1 | broker WebSocket 32797 被防火墙拦截 | 前端 MQTT WS 连接失败，FR5（写入回执推送）失效，页面显示超时 | 健康检查第 3 项验证；若失败联系网络管理员开放端口 |
| 2 | 树莓派 ARM 上 `npm install` + `npm run build` 首次耗时长（约 5~15 分钟），内存峰值约 400~500 MB | 延长部署窗口；若内存不足进程被 OOM Kill | 执行前确认可用内存 ≥ 512 MB（前置检查项 7）；内存不足时可加 `NODE_OPTIONS=--max-old-space-size=512` 限制 V8 堆 |
| 3 | migrate 期间 Django 短暂不可用（预计 < 5 秒） | 极短暂 API 中断 | 安排在低负载时段（如夜间）执行；gunicorn 重启后自动恢复 |

---

## 六、本期变更文件汇总

### 后端 Django

| 类型 | 文件路径 |
|------|---------|
| 新增 | `FreeArkWeb/backend/freearkweb/api/migrations/0023_plcwriterecord.py` |
| 新增 | `FreeArkWeb/backend/freearkweb/api/serializers_device_settings.py` |
| 新增 | `FreeArkWeb/backend/freearkweb/api/views_device_settings.py` |
| 修改 | `FreeArkWeb/backend/freearkweb/api/models.py` |
| 修改 | `FreeArkWeb/backend/freearkweb/api/urls.py` |
| 修改 | `FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py` |

### datacollection

| 类型 | 文件路径 |
|------|---------|
| 新增 | `datacollection/plc_write_subscriber.py` |
| 修改 | `datacollection/improved_data_collection_manager.py` |

### 前端 Vue

| 类型 | 文件路径 |
|------|---------|
| 新增 | `FreeArkWeb/frontend/src/composables/useMqttWebSocket.js` |
| 新增 | `FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue` |
| 新增 | `FreeArkWeb/frontend/src/views/PlcWriteRecordView.vue` |
| 修改 | `FreeArkWeb/frontend/package.json`（新增 mqtt ^5.10.1） |
| 修改 | `FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue` |
| 修改 | `FreeArkWeb/frontend/src/router/index.js` |

---

*所有标注"⚠ 需用户 CONFIRM"的步骤，等待用户明确授权后由 PM 触发，devops 不自行执行。*
