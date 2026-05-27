# v0.6.0 故障管理生产部署报告

| 项 | 值 |
|---|---|
| 部署日期 | 2026-05-27 23:14 ~ 23:23 CST |
| 部署人 | Yang Yang（Claude Code 协助） |
| 目标主机 | 树莓派 Raspberry Pi 5，`192.168.31.51` |
| 部署前 HEAD | `6dc05a1 fix(chat-stream)` |
| 部署后 HEAD | `bf666f9 fix(fault-mgmt): 修正 systemd venv 路径 (MINOR-5)` |
| 涉及 commits | `537c5a7 feat(fault-management)`、`bf666f9 fix(fault-mgmt)` |

## 部署步骤与结果

| # | 操作 | 结果 |
|---|---|---|
| 1 | 本地 rebase + commit + push | OK，单一 commit `537c5a7` |
| 2 | 修正 unit venv 路径（`Freeark/venv` → `Freeark/FreeArk/venv`）+ 推送 `bf666f9` | OK |
| 3 | 生产 `git pull` | Fast-forward 6dc05a1 → bf666f9，26 文件，+6226 行 |
| 4 | 验证 paho-mqtt 已装 | OK (`venv/lib/python3.13/site-packages/paho/mqtt/client.py`) |
| 5 | 应用 migration 0026_add_fault_event | `Applying api.0026_add_fault_event... OK` |
| 6 | 前端备份 + `npm run build` | OK，19.25s，dist 输出含 FaultManagementView |
| 7 | 部署 3 个 systemd unit | OK（fault-consumer.service / fault-cleanup.service / fault-cleanup.timer） |
| 8 | `daemon-reload` + `enable --now` | OK，consumer + timer 立即启用 |
| 9 | 重启 `freeark-backend` | OK，Uvicorn 重新监听 :8000 |
| 10 | API smoke：`/api/devices/fault-events/` 等 | HTTP 401（无 token，预期；说明路由生效） |
| 11 | TCP 验证 fault-consumer 实际连 MQTT broker | ESTAB → `171.213.194.195:8084`（EMQX）+ `192.168.31.98:3306`（MySQL） |
| 12 | 全 freeark 服务状态 | 9 service active running + 1 timer active waiting |

## 部署期发现并修复的问题

| # | 问题 | 解决 |
|---|---|---|
| **D1** | systemd unit 文件 venv 路径推断错误（`/home/yangyang/Freeark/venv/` 不存在，实际是 `Freeark/FreeArk/venv/`）| commit `bf666f9` 修正后重 push |
| **D2** | DNS `et116374mm892.vicp.fun` 间歇性解析失败 | 等待 DNS 恢复后重连，3 次出现 |

## 服务状态快照

```
freeark-backend.service                active running   FreeArk backend Service
freeark-daily-usage.service            active running   FreeArk daily-usage Service
freeark-dph-cleanup.service            active running   FreeArk DPH Cleanup Service
freeark-fault-consumer.service         active running   FreeArk Fault Event MQTT Consumer (v0.6.0-FM)  ★新增
freeark-monthly-usage.service          active running   FreeArk monthly-usage Service
freeark-mqtt-consumer.service          active running   FreeArk mqtt-consumer Service
freeark-plc-connection-monitor.service active running   FreeArk PLC Connection Monitor
freeark-screen-heartbeat.service       active running   FreeArk Screen Heartbeat Consumer
freeark-task-scheduler.service         active running   FreeArk Task Scheduler
freeark-fault-cleanup.timer            active waiting   FreeArk Fault Cleanup Timer (next: Thu 03:30)  ★新增
```

## 验证清单

- [x] Migration 0026 应用成功（`device_fault_event` 表建立，2 索引 + 1 UNIQUE 约束）
- [x] fault-consumer TCP ESTAB → EMQX broker（订阅生效）
- [x] fault-consumer MySQL 连接已建立
- [x] backend 重启后 ASGI 正常监听 :8000
- [x] `/api/devices/fault-events/` 路由生效（HTTP 401 表示已挂载）
- [x] fault-cleanup.timer 启用，next trigger Thu 2026-05-28 03:30
- [x] 前端 `dist/` 含新增 `FaultManagementView` 入口

## 待观察

- [ ] **首批真实 MQTT 故障数据流入**——需等待真实故障上报（或测试环境主动推一条）
- [ ] **首次 fault-cleanup 触发**（2026-05-28 03:30）——查 `journalctl -u freeark-fault-cleanup`
- [ ] **内存占用**——consumer 长期运行后实测 RSS（设计估算 9 MB）

## 回滚预案

如需回滚：
```bash
sudo systemctl disable --now freeark-fault-consumer freeark-fault-cleanup.timer
sudo rm /etc/systemd/system/freeark-fault-{consumer.service,cleanup.service,cleanup.timer}
sudo systemctl daemon-reload
cd /home/yangyang/Freeark/FreeArk
git reset --hard 6dc05a1     # 回到部署前
cd FreeArkWeb/backend/freearkweb
venv/bin/python manage.py migrate api 0025  # 回滚 migration
cd ../../frontend
cp -r /home/yangyang/FreeArk_backup/dist_backup_v060_<TIMESTAMP> dist
sudo systemctl restart freeark-backend
```

## 已知技术债（不阻断验收）

- **MINOR-1 ~ MINOR-4**（views_fault.py 时间格式校验、icontains 全表扫等）：表规模小，暂可接受
- **AB-001**：进程内 dict → Redis 迁移阈值 >256 MB（当前 9 MB 估算）
- **AB-004**：故障码 → 中文描述字典（目前 `fault_message = fault_code`）
- **AB-007**：基于 heartbeat 的故障自愈检测（仅在收到 MQTT 显式恢复消息时写 UPDATE）
