# P1-a 生产部署计划：Redis Channel Layer + 多 Worker

> **状态**: 待用户 CONFIRM 后执行  
> **日期**: 2026-05-31  
> **关联 ADR**: docs/architecture/architecture_design_p1a_redis_channel_layer.md  
> **预计停机时间**: ~2 分钟（`systemctl restart freeark-backend` 期间）

---

## 前提检查（执行前确认）

```bash
# 1. 本地测试全通过（见"本地回归验证"节）
# 2. 生产 HEAD 与本地一致（git push 已完成）
# 3. 确认不会覆盖生产本地修改

HOME=/c/fa-home ssh -i /c/fa-home/.ssh/id_ed25519 \
  -o UserKnownHostsFile=/c/fa-home/.ssh/known_hosts \
  -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=20 \
  -p 57279 yangyang@et116374mm892.vicp.fun \
  'cd /home/yangyang/Freeark/FreeArk && git status'
# 期望：只有 .env / package-lock.json / heartbeat_broker_config.json 是本地修改
```

---

## 步骤 1：安装 Redis（apt）

```bash
HOME=/c/fa-home ssh -i /c/fa-home/.ssh/id_ed25519 \
  -o UserKnownHostsFile=/c/fa-home/.ssh/known_hosts \
  -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=20 \
  -p 57279 yangyang@et116374mm892.vicp.fun \
  'sudo apt update && sudo apt install -y redis-server'
```

**验证 Redis 启动并绑 loopback**：
```bash
HOME=/c/fa-home ssh ... \
  'systemctl is-active redis-server && redis-cli ping && ss -tlnp | grep 6379'
# 期望：active + PONG + 127.0.0.1:6379
```

**设置开机自启**：
```bash
HOME=/c/fa-home ssh ... 'sudo systemctl enable redis-server'
```

**（可选）设置 maxmemory**（防止 Channel Layer 数据在内存压力时无界增长）：
```bash
HOME=/c/fa-home ssh ... \
  'grep -q "^maxmemory" /etc/redis/redis.conf || \
   echo -e "\nmaxmemory 128mb\nmaxmemory-policy allkeys-lru" | \
   sudo tee -a /etc/redis/redis.conf && \
   sudo systemctl restart redis-server && redis-cli ping'
# 期望：PONG
```

---

## 步骤 2：git pull 拉取代码

```bash
HOME=/c/fa-home ssh ... \
  'cd /home/yangyang/Freeark/FreeArk && git pull origin main'
# 验证关键文件落地
HOME=/c/fa-home ssh ... \
  'grep "channels_redis" /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/requirements.txt && \
   grep "RedisChannelLayer" /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/freearkweb/settings.py && \
   grep "workers 2" /home/yangyang/Freeark/FreeArk/systemctl/freeark-backend.service && \
   echo "CODE_VERIFIED"'
# 期望：CODE_VERIFIED
```

---

## 步骤 3：安装 Python 依赖（channels_redis）

```bash
HOME=/c/fa-home ssh ... \
  'cd /home/yangyang/Freeark/FreeArk && \
   venv/bin/pip install -r FreeArkWeb/backend/requirements.txt'
```

**验证 import**：
```bash
HOME=/c/fa-home ssh ... \
  '/home/yangyang/Freeark/FreeArk/venv/bin/python \
   -c "from channels_redis.core import RedisChannelLayer; print(\"IMPORT_OK\")"'
# 期望：IMPORT_OK
```

---

## 步骤 4：更新 systemd unit 文件

```bash
HOME=/c/fa-home ssh ... \
  'sudo cp /home/yangyang/Freeark/FreeArk/systemctl/freeark-backend.service \
   /etc/systemd/system/freeark-backend.service && \
   sudo systemctl daemon-reload'
```

**确认 unit 文件内容**：
```bash
HOME=/c/fa-home ssh ... \
  'grep -E "workers|After" /etc/systemd/system/freeark-backend.service'
# 期望：--workers 2 + After=network.target redis-server.service
```

---

## 步骤 5：重启 backend（~2 分钟停机）

```bash
HOME=/c/fa-home ssh ... \
  'sudo systemctl restart freeark-backend'
# 等待 5 秒后检查状态
HOME=/c/fa-home ssh ... \
  'sleep 5 && systemctl status freeark-backend --no-pager | head -20'
# 期望：Active: active (running)
```

**检查 journald（无 ERROR / traceback）**：
```bash
HOME=/c/fa-home ssh ... \
  'sudo journalctl -u freeark-backend -n 30 --no-pager'
# 注意：
# - "ASGI 'lifespan' protocol appears unsupported." 无害
# - 不应见 "ConnectionRefusedError" / "No module named channels_redis"
# - 应见类似 "Started server process [PID]" × 2（2 个 worker）
```

---

## 步骤 6：验证（健康检查 + WS + 看板）

**6-1. HTTP 健康检查**：
```bash
HOME=/c/fa-home ssh ... \
  'curl -s http://127.0.0.1:8080/api/health/'
# 期望：{"status":"ok",...}
```

**6-2. Redis 连接验证（Channel Layer 是否已用 Redis）**：
```bash
HOME=/c/fa-home ssh ... \
  'redis-cli monitor &
   sleep 2;
   curl -s http://127.0.0.1:8080/api/health/ > /dev/null;
   sleep 1;
   kill %1 2>/dev/null; true'
# 期望：redis monitor 期间看到 channels_redis 写入的 channel 数据（如 asgi.*）
# 注：也可接受无输出（健康检查不触发 WS，Channel Layer 惰性连接）
```

**6-3. WebSocket 聊天链路（按 SKILL.md §11 排查清单）**：
```bash
# 检查 1: OpenClaw Gateway
HOME=/c/fa-home ssh ... \
  'systemctl --user is-active openclaw-gateway.service && \
   curl -s http://127.0.0.1:18789/health'

# 检查 2: ALLOWED_HOSTS 含 Pi IP
HOME=/c/fa-home ssh ... \
  'grep "^ALLOWED_HOSTS" /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/.env'

# 检查 3: backend 无 "Unsupported upgrade request"
HOME=/c/fa-home ssh ... \
  'sudo journalctl -u freeark-backend -n 50 --no-pager | grep -i "unsupported\|error\|traceback" | head -20'
```

**6-4. 看板接口缓存**（验证 cache 仍工作，非 500）：
```bash
# 需要有效 token，用已有测试账号的 Token 头
HOME=/c/fa-home ssh ... \
  'curl -s -H "Authorization: Token <TEST_TOKEN>" http://127.0.0.1:8080/api/your-dashboard-endpoint/'
# 期望：200 OK（非 500/502）
```

---

## 回滚步骤（如需）

```bash
# 1. 编辑 unit 文件（--workers 2 → 1，BACKEND 改回 InMemoryChannelLayer）
HOME=/c/fa-home ssh ... \
  'sudo nano /etc/systemd/system/freeark-backend.service'

# 或者用 sed 快速改（确认 sed 表达式后执行）：
HOME=/c/fa-home ssh ... \
  'sudo sed -i "s/--workers 2/--workers 1/" /etc/systemd/system/freeark-backend.service && \
   sudo systemctl daemon-reload && \
   sudo systemctl restart freeark-backend'

# settings.py 的 CHANNEL_LAYERS 在 git 里的版本已改为 RedisChannelLayer；
# 回滚需要同时回滚代码（git revert 或手动改 settings.py 后 git pull）
# 最简单的回滚：仅改 --workers 1，settings.py 里 RedisChannelLayer 在 Redis 存在时
# 功能正确，不会导致错误。单 worker 下 RedisChannelLayer vs InMemoryChannelLayer 行为等价。
```

---

## 成功标准

| 验证项 | 期望结果 |
|--------|---------|
| `systemctl is-active freeark-backend` | `active` |
| `systemctl is-active redis-server` | `active` |
| `journalctl -u freeark-backend` 无 ERROR traceback | 通过 |
| `curl http://127.0.0.1:8080/api/health/` | `{"status":"ok",...}` |
| WebSocket 聊天链路（SKILL.md §11 checklist）| TOKEN_MATCH + 18789 LISTEN |
| 看板 API HTTP 200 | 通过 |

---

## 注意事项

1. **生产 .env 无需修改**：CHANNEL_LAYERS 配置在 settings.py 中读取 Redis 默认地址
   （127.0.0.1:6379），不需要新增 .env 变量。
2. **git pull 不会覆盖 .env / package-lock.json / heartbeat_broker_config.json**
   （本次改动不涉及这三个文件）。
3. **redis-server 默认 bind 127.0.0.1**：Debian trixie 的 redis-server 包默认配置
   已绑 loopback，安装后确认一次 `grep "^bind" /etc/redis/redis.conf` 即可。
4. **停机窗口约 2 分钟**：`systemctl restart freeark-backend` 期间 uvicorn 重启，
   现有 WebSocket 连接中断（前端会自动重连），HTTP 请求短暂 502（Nginx 等待）。
   建议在低峰期（深夜）执行。
