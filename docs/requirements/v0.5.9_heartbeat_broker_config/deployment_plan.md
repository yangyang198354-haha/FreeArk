# 部署计划 — v0.5.9 心跳 Broker 配置

**版本**：v0.5.9-heartbeat-broker-config  
**日期**：2026-05-23  
**状态**：AWAITING PM CONFIRM — 不执行生产部署，等待用户最终确认后由运维/开发执行

---

## 1. 变更文件清单

| 文件路径（相对项目根） | 变更类型 | 说明 |
|----------------------|---------|------|
| `FreeArkWeb/backend/requirements.txt` | 修改 | `paho-mqtt>=1.6.1` → `paho-mqtt>=1.6.1,<2.0`（固定 1.x） |
| `FreeArkWeb/backend/heartbeat_broker_config.json` | 新建 | 初始值=现有硬编码值，升级后零行为变化 |
| `FreeArkWeb/backend/freearkweb/api/views_heartbeat_config.py` | 新建 | GET+PUT 视图，host 正则校验，原子写，subprocess restart |
| `FreeArkWeb/backend/freearkweb/api/urls.py` | 修改 | 新增 2 条路由 |
| `FreeArkWeb/backend/freearkweb/api/management/commands/screen_heartbeat_consumer.py` | 修改 | 读取配置文件，支持 mqtt/wss transport |
| `FreeArkWeb/frontend/src/views/ServicesView.vue` | 修改 | 增加「心跳中间件配置」Tab（OQ-003 方案 A） |
| `FreeArkWeb/frontend/src/utils/api.js` | 修改 | PUT 方法增加后端 JSON 错误体解析 |
| `systemctl/freeark-screen-heartbeat.service` | 修改 | 新增 StartLimitIntervalSec=300, StartLimitBurst=5 |
| `FreeArkWeb/backend/freearkweb/api/tests/test_heartbeat_broker_config.py` | 新建 | 测试套件 |

---

## 2. 生产部署前置检查

在执行部署前，请在生产服务器（树莓派，user=yangyang）上确认：

```bash
# 2.1 确认 paho-mqtt 版本（期望 >=1.6.1,<2.0）
/home/yangyang/Freeark/FreeArk/venv/bin/pip show paho-mqtt

# 2.2 确认 sudoers 白名单含 freeark-screen-heartbeat
sudo -l -U yangyang | grep freeark-screen-heartbeat

# 2.3 确认 Python ssl CA bundle 路径存在
/home/yangyang/Freeark/FreeArk/venv/bin/python3 -c "import ssl; print(ssl.get_default_verify_paths())"

# 2.4 确认现有心跳服务状态（部署前记录快照）
systemctl status freeark-screen-heartbeat
```

---

## 3. 生产部署步骤（按顺序执行）

> **重要**：所有命令在生产服务器以 yangyang 用户执行，工作目录为 /home/yangyang/Freeark/FreeArk/

### Step 1 — 拉取代码

```bash
cd /home/yangyang/Freeark/FreeArk
git pull origin main
```

### Step 2 — 升级 paho-mqtt（如需要）

```bash
/home/yangyang/Freeark/FreeArk/venv/bin/pip install 'paho-mqtt>=1.6.1,<2.0'
```

若 paho-mqtt 已是 1.6.x 版本，此命令无实际升级，仅确认版本固定。

### Step 3 — 创建配置文件并设置权限

```bash
# 若 heartbeat_broker_config.json 不存在，从代码库中的文件复制（代码库已含初始值）
# Git 拉取后文件已在正确位置，只需设置权限：
chmod 600 /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/heartbeat_broker_config.json
ls -la /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/heartbeat_broker_config.json
# 期望输出：-rw------- 1 yangyang yangyang ...
```

### Step 4 — 更新 systemd service 文件

```bash
# 复制新的 service 文件（含 StartLimitIntervalSec/Burst）
sudo cp /home/yangyang/Freeark/FreeArk/systemctl/freeark-screen-heartbeat.service \
        /etc/systemd/system/freeark-screen-heartbeat.service

# 重载 systemd daemon（必须，否则新配置不生效）
sudo systemctl daemon-reload

# 验证新配置已生效
sudo systemctl cat freeark-screen-heartbeat | grep StartLimit
# 期望输出：
# StartLimitIntervalSec=300
# StartLimitBurst=5
```

### Step 5 — 构建前端

```bash
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend
npm install
npm run build
# 构建产物在 dist/ 目录，由 Nginx 提供静态文件服务
```

### Step 6 — 重启后端服务

```bash
sudo systemctl restart freeark-backend
sudo systemctl status freeark-backend
# 期望：active (running)
```

### Step 7 — 重启心跳 consumer 服务

```bash
sudo systemctl restart freeark-screen-heartbeat
# 等待约 5s 后检查状态
sleep 5
sudo systemctl status freeark-screen-heartbeat
# 期望：active (running)
```

### Step 8 — 验证日志（可观测性检查）

```bash
# 查看启动日志，确认从配置文件读取（非 fallback 常量）
journalctl -u freeark-screen-heartbeat -n 30 --no-pager
# 期望包含：_load_heartbeat_config: 已加载配置文件 protocol=mqtt host=47.117.41.184 port=11883
# 期望包含：使用 mqtt TCP 传输: 47.117.41.184:11883
# 期望包含：已连接 Broker 47.117.41.184:11883
```

### Step 9 — Web 功能验证

1. 浏览器登录 admin 账号
2. 进入「服务管理」页面
3. 点击「心跳中间件配置」Tab
4. 确认页面加载出当前配置（protocol=mqtt, host=47.117.41.184, port=11883, password=空）
5. 不修改任何值，点击「保存并重启服务」→ 确认 → 应提示「配置已保存，服务重启中」

---

## 4. 回滚方案

### 情景 A：代码回滚（彻底回退）

```bash
cd /home/yangyang/Freeark/FreeArk
git revert HEAD   # 或 git reset --hard <上一个 commit SHA>
git push origin main  # 仅在确认回滚时推送

# 恢复旧 service 文件
sudo cp /etc/systemd/system/freeark-screen-heartbeat.service.bak \
        /etc/systemd/system/freeark-screen-heartbeat.service 2>/dev/null || \
    sudo systemctl edit --force freeark-screen-heartbeat  # 手动移除 StartLimit* 行

sudo systemctl daemon-reload
sudo systemctl restart freeark-screen-heartbeat
sudo systemctl restart freeark-backend
```

### 情景 B：仅恢复心跳 broker 地址（配置回滚）

```bash
# 直接编辑配置文件，将 host/port 恢复为旧值
cat > /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/heartbeat_broker_config.json << 'EOF'
{
  "protocol": "mqtt",
  "host": "47.117.41.184",
  "port": 11883,
  "path": "/mqtt",
  "username": "admin",
  "password": "public",
  "topic": "/screen/upload/screen/to/cloud/#",
  "client_id": "freeark-screen-heartbeat",
  "keepalive": 60
}
EOF
chmod 600 /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/heartbeat_broker_config.json

sudo systemctl restart freeark-screen-heartbeat
```

### 情景 C：服务进入 failed 状态（StartLimit 触发后手动恢复）

```bash
# 修正配置文件（见情景 B 或通过 Web 界面修改）
# 然后：
sudo systemctl reset-failed freeark-screen-heartbeat
sudo systemctl start freeark-screen-heartbeat
```

---

## 5. sudoers 调整说明

**不需要修改 sudoers。**

`freeark-screen-heartbeat` 已在现有 sudoers 白名单中（与 `service_management_action` 使用同一白名单）。

可通过以下命令确认：

```bash
sudo -l -U yangyang | grep freeark-screen-heartbeat
```

---

## 6. 切换到 wss broker 的操作指南（供将来使用）

部署完成后，若需切换到 `wss://www.ttqingjiao.site:8084`：

1. 登录 Web 管理界面（admin 账号）
2. 进入「服务管理」→「心跳中间件配置」Tab
3. 修改以下字段：
   - 协议：`wss`
   - Host：`www.ttqingjiao.site`
   - Port：`8084`
   - Path：`/mqtt`
   - Username / Password：按需填写（Password 留空则保留当前值）
4. 点击「保存并重启服务」→ 确认
5. 等待约 5-10 秒后查看服务状态，或通过 SSH 查看日志：
   ```bash
   journalctl -u freeark-screen-heartbeat -n 20 --no-pager
   # 期望：使用 wss 传输: www.ttqingjiao.site:8084/mqtt
   # 期望：已连接 Broker www.ttqingjiao.site:8084
   ```

---

## 7. 等待 PM CONFIRM

本文档为生产部署计划。**不执行生产部署**，所有步骤均等待用户最终 CONFIRM 后由运维/开发人员按序执行。

当用户确认后，请按 Section 3 步骤（Step 1 → Step 9）依序执行，每步完成后确认状态符合期望后再继续。
