# Deployment Plan — FreeArk AsyncMQTT Fix
<!-- file_header: author_agent=sub_agent_devops_engineer, status=APPROVED, version=1.0 -->

## 部署目标

将异步化改造后的 `mqtt_consumer.py` 部署到生产服务器，消除 EMQX rc=16 断连。

## 环境信息

| 参数 | 值 |
|------|----|
| 生产服务器 | 树莓派 192.168.31.51 |
| SSH 用户 | yangyang |
| SSH 密码 | 123456 |
| hostkey | SHA256:TfpCSrSLuK1UspD2mpikebK0bE0IFnPH8bSigERWnmk |
| 目标文件 | /home/yangyang/FreeArk/FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py |
| systemd 服务 | freeark-mqtt-consumer |

## 部署步骤

### Step 1: 备份现有文件（含回滚）
```bash
"C:\Program Files\PuTTY\plink.exe" -ssh yangyang@192.168.31.51 -pw 123456 \
  -hostkey "SHA256:TfpCSrSLuK1UspD2mpikebK0bE0IFnPH8bSigERWnmk" \
  "cp /home/yangyang/FreeArk/FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py \
      /home/yangyang/FreeArk/FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py.bak.$(date +%Y%m%d_%H%M%S)"
```
**回滚命令（若验证失败）**:
```bash
"C:\Program Files\PuTTY\plink.exe" -ssh yangyang@192.168.31.51 -pw 123456 \
  -hostkey "SHA256:TfpCSrSLuK1UspD2mpikebK0bE0IFnPH8bSigERWnmk" \
  "cp /home/yangyang/FreeArk/FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py.bak.* \
      /home/yangyang/FreeArk/FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py && \
   sudo systemctl restart freeark-mqtt-consumer"
```

### Step 2: 传输新文件（使用 pscp）
```bash
"C:\Program Files\PuTTY\pscp.exe" -pw 123456 \
  -hostkey "SHA256:TfpCSrSLuK1UspD2mpikebK0bE0IFnPH8bSigERWnmk" \
  "C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend\freearkweb\api\mqtt_consumer.py" \
  "yangyang@192.168.31.51:/home/yangyang/FreeArk/FreeArkWeb/backend/freearkweb/api/mqtt_consumer.py"
```

### Step 3: 重启服务
```bash
"C:\Program Files\PuTTY\plink.exe" -ssh yangyang@192.168.31.51 -pw 123456 \
  -hostkey "SHA256:TfpCSrSLuK1UspD2mpikebK0bE0IFnPH8bSigERWnmk" \
  "sudo systemctl restart freeark-mqtt-consumer && sleep 3 && sudo systemctl status freeark-mqtt-consumer"
```

### Step 4: 验证日志（连接成功，无 rc=16）
```bash
"C:\Program Files\PuTTY\plink.exe" -ssh yangyang@192.168.31.51 -pw 123456 \
  -hostkey "SHA256:TfpCSrSLuK1UspD2mpikebK0bE0IFnPH8bSigERWnmk" \
  "sudo journalctl -u freeark-mqtt-consumer -n 50 --no-pager"
```

### Step 5: 验证 worker 线程启动
在日志中查找：
- `[mqtt-worker-0] Worker 线程启动`
- `[mqtt-worker-1] Worker 线程启动`
- `[mqtt-worker-2] Worker 线程启动`
- `[mqtt-worker-3] Worker 线程启动`
- `成功连接到MQTT代理`

### Step 6: 验证 DB 数据更新（600s 后）
```bash
"C:\Program Files\PuTTY\plink.exe" -ssh yangyang@192.168.31.51 -pw 123456 \
  -hostkey "SHA256:TfpCSrSLuK1UspD2mpikebK0bE0IFnPH8bSigERWnmk" \
  "mysql -h 192.168.31.98 -P 3306 -u root -p123456 freeark -e \
  \"SELECT specific_part, param_name, value, collected_at FROM plclatestdata WHERE specific_part='3-1-7-702' LIMIT 5;\""
```

## 验证标准

| 标准 | 验证方法 | 通过条件 |
|------|---------|---------|
| 无 rc=16 | journalctl 过滤 DISCONNECT | 24h 内无 DISCONNECT rc=16 |
| worker 线程启动 | 日志搜索 mqtt-worker | 4 个 worker 日志出现 |
| DB 更新 | MySQL 查询 plclatestdata | collected_at 在 600s 内 |
| 优雅关闭 | systemctl stop 计时 | 30s 内 inactive |

## 回滚计划

每个步骤均可独立回滚：
- Step 1 备份确保原文件保留
- 任何验证失败时执行 Step 1 中的回滚命令

## 部署状态

PRODUCTION_DEPLOY_CONFIRM: 待用户授权
