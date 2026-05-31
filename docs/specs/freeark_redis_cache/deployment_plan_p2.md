# perf-P2 生产部署计划：Redis 缓存后端

> **状态**: 待用户 CONFIRM 后执行（预测试通过后）
> **日期**: 2026-05-31
> **关联 ADR**: docs/specs/freeark_redis_cache/ADR-P2-001_redis_cache_backend.md
> **预计停机时间**: ~30 秒（`systemctl restart freeark-backend` 期间）

---

## 前提检查（执行前确认）

### 1. 预测试已通过
本地（或生产）运行预测试脚本，全 6 项通过：
- redis-py 版本 5.x
- Django RedisCache 导入正常
- cache set/get/TTL 生效
- Redis db=1 隔离有效
- Redis 宕机降级不 500
- cache_dashboard 装饰器命中/未命中正常

### 2. 本地代码已推送
```bash
# 提交
git commit -F _commit_msg_p2_impl.txt
# 推送
git push origin main
# 确认
git log -1 --oneline
```

### 3. 确认生产工作树状态
```bash
HOME=/c/fa-home ssh -i /c/fa-home/.ssh/id_ed25519 \
  -o UserKnownHostsFile=/c/fa-home/.ssh/known_hosts \
  -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=20 \
  -p 57279 yangyang@et116374mm892.vicp.fun \
  'cd /home/yangyang/Freeark/FreeArk && git status'
# 期望：只有 .env / package-lock.json / heartbeat_broker_config.json 是本地修改
```

---

## 步骤 1：确认 Redis 已运行（应已在，无需额外安装）

```bash
HOME=/c/fa-home ssh -i /c/fa-home/.ssh/id_ed25519 \
  -o UserKnownHostsFile=/c/fa-home/.ssh/known_hosts \
  -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=20 \
  -p 57279 yangyang@et116374mm892.vicp.fun \
  'systemctl is-active redis-server && redis-cli ping && ss -tlnp | grep 6379'
# 期望：active + PONG + 127.0.0.1:6379
```

如果 Redis 未运行（不应该，但作为保障）：
```bash
HOME=/c/fa-home ssh ... \
  'sudo systemctl start redis-server && redis-cli ping'
```

---

## 步骤 2：git pull 拉取代码

```bash
HOME=/c/fa-home ssh -i /c/fa-home/.ssh/id_ed25519 \
  -o UserKnownHostsFile=/c/fa-home/.ssh/known_hosts \
  -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=20 \
  -p 57279 yangyang@et116374mm892.vicp.fun \
  'cd /home/yangyang/Freeark/FreeArk && git pull origin main'
```

验证关键文件落地：
```bash
HOME=/c/fa-home ssh ... \
  'grep "redis>=5.0,<6.0" /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/requirements.txt && \
   grep "RedisCache" /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/freearkweb/settings.py && \
   grep "redis://127.0.0.1:6379/1" /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/freearkweb/settings.py && \
   echo "CODE_VERIFIED"'
# 期望：CODE_VERIFIED
```

---

## 步骤 3：安装/升级 redis-py 到 5.x

```bash
HOME=/c/fa-home ssh ... \
  'cd /home/yangyang/Freeark/FreeArk && \
   venv/bin/pip install "redis>=5.0,<6.0"'
```

验证版本：
```bash
HOME=/c/fa-home ssh ... \
  '/home/yangyang/Freeark/FreeArk/venv/bin/python -c \
   "import redis; v=redis.__version__; assert v.startswith(\"5.\"), f\"版本非 5.x: {v}\"; print(f\"redis-py {v} OK\")"'
# 期望：redis-py 5.x.x OK
```

验证 Django RedisCache 导入正常（加上 DJANGO_SETTINGS_MODULE，用非测试路径）：
```bash
HOME=/c/fa-home ssh ... \
  'cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb && \
   /home/yangyang/Freeark/FreeArk/venv/bin/python -c \
   "from django.core.cache.backends.redis import RedisCache; print(\"RedisCache import OK\")"'
# 期望：RedisCache import OK
```

---

## 步骤 4：快速缓存功能验证（可选但推荐）

在生产上直接验证 cache get/set 工作（用 Django shell）：
```bash
HOME=/c/fa-home ssh ... \
  'cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb && \
   /home/yangyang/Freeark/FreeArk/venv/bin/python manage.py shell -c \
   "from django.core.cache import cache; \
    cache.set(\"p2_pretest\", \"hello\", 60); \
    v = cache.get(\"p2_pretest\"); \
    assert v == \"hello\", f\"get 失败: {v!r}\"; \
    cache.delete(\"p2_pretest\"); \
    print(\"CACHE_OK\")"'
# 期望：CACHE_OK
# 若报 ConnectionRefusedError / RedisError → 确认 redis-server is-active 且 db=1 可访问
```

验证 Redis db=1 键存在（KEY_PREFIX=fa_cache）：
```bash
HOME=/c/fa-home ssh ... \
  'redis-cli -n 1 keys "fa_cache*" | head -5'
# 注：manage.py shell 执行后可能有残留键；若 CACHE_OK 则至少短暂存在过
```

---

## 步骤 5：重启 backend（约 30 秒停机）

```bash
HOME=/c/fa-home ssh ... \
  'sudo systemctl restart freeark-backend'
# 等待后检查
HOME=/c/fa-home ssh ... \
  'sleep 5 && systemctl status freeark-backend --no-pager | head -15'
# 期望：Active: active (running)
```

检查 journald（无 ERROR traceback，无 RedisError）：
```bash
HOME=/c/fa-home ssh ... \
  'sudo journalctl -u freeark-backend -n 30 --no-pager'
# 注意：
#   - "ASGI 'lifespan' protocol appears unsupported." 无害
#   - 不应见 "redis.exceptions" / "ConnectionRefusedError"
#   - 应见 "Started server process [PID]"
```

---

## 步骤 6：生产验证

**6-1. HTTP 健康检查**：
```bash
HOME=/c/fa-home ssh ... \
  'curl -s http://127.0.0.1:8080/api/health/'
# 期望：{"status":"ok",...}
```

**6-2. 看板接口缓存命中验证**：
```bash
# 使用有效 Token（从生产测试账号获取），调用两次，观察 Redis db=1 键增加
HOME=/c/fa-home ssh ... \
  'redis-cli -n 1 dbsize'
# 第一次调用看板接口后
HOME=/c/fa-home ssh ... \
  'curl -s -H "Authorization: Token <TEST_TOKEN>" \
   http://127.0.0.1:8080/api/dashboard/power-status/ | head -c 100'
# 期望：{"success":true,...} 而非 500

HOME=/c/fa-home ssh ... \
  'redis-cli -n 1 keys "fa_cache*"'
# 期望：出现 fa_cache:1:dash:dashboard_power_status 等键
```

**6-3. redis-py 版本 + channels_redis 兼容性检查**：
```bash
HOME=/c/fa-home ssh ... \
  '/home/yangyang/Freeark/FreeArk/venv/bin/python -c \
   "import redis; import channels_redis; \
    print(f\"redis-py {redis.__version__}, channels_redis {channels_redis.__version__}\")"'
# 期望：redis-py 5.x.x, channels_redis 4.x.x（无 ImportError）
```

**6-4. Redis db 隔离确认**：
```bash
HOME=/c/fa-home ssh ... \
  'echo "=db0 fa_cache keys="; redis-cli -n 0 keys "fa_cache*"; \
   echo "=db1 fa_cache keys="; redis-cli -n 1 keys "fa_cache*"'
# 期望：db0 无 fa_cache 键；db1 有 fa_cache 键
```

---

## 回滚步骤（如需）

只需改 settings.py 的生产分支 CACHES（不影响 Redis 服务和 channels）：

```bash
# 方法 1：直接编辑
HOME=/c/fa-home ssh ... \
  'nano /home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/freearkweb/freearkweb/settings.py'
# 将 RedisCache 分支改回 LocMemCache，LOCATION='freeark-dashboard-cache'

# 方法 2：git revert（若提交已推送）
HOME=/c/fa-home ssh ... \
  'cd /home/yangyang/Freeark/FreeArk && git revert <commit_hash> --no-edit'

# 重启 backend
HOME=/c/fa-home ssh ... \
  'sudo systemctl restart freeark-backend'
```

回滚后验证：
```bash
HOME=/c/fa-home ssh ... \
  'curl -s http://127.0.0.1:8080/api/health/'
# 期望：{"status":"ok",...}
```

---

## 成功标准

| 验证项 | 期望结果 |
|--------|---------|
| `systemctl is-active freeark-backend` | `active` |
| `systemctl is-active redis-server` | `active` |
| `journalctl -u freeark-backend` 无 redis ERROR | 通过 |
| `curl http://127.0.0.1:8080/api/health/` | `{"status":"ok",...}` |
| 看板接口 HTTP 200 | 通过 |
| `redis-cli -n 1 keys 'fa_cache*'` | 调用后出现缓存键 |
| `redis-cli -n 0 keys 'fa_cache*'` | 无结果（db 隔离有效）|
| redis-py 版本 | 5.x.x |

---

## 注意事项

1. **不改 .env**：CACHES 配置在 settings.py 中硬编码 Redis 地址（127.0.0.1:6379/1），不需要新增 .env 变量。
2. **git pull 不会覆盖 .env / package-lock.json / heartbeat_broker_config.json**（本次改动不涉及这三个文件）。
3. **redis-py 版本固定是关键操作**：必须确认 pip install 成功且版本为 5.x，否则 channels_redis 可能在将来 P1 多 worker 时再次遇到兼容问题。
4. **停机窗口约 30 秒**：`systemctl restart freeark-backend` 期间看板 HTTP 请求短暂 502（Nginx 等待），WebSocket 连接中断（前端自动重连）。建议低峰期执行。
