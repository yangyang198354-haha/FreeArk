# v0.7.0 结露预警管理 — 生产部署报告

- **部署日期**：2026-05-30
- **版本**：v0.7.0-CW（结露预警管理，设备管理子项）
- **提交**：`4765cf4` feat(condensation): v0.7.0 结露预警管理（设备管理子项）
- **生产 HEAD（部署前）**：`a5a8c70` → **部署后**：`4765cf4`
- **执行人**：主控会话（Claude Code）经 SSH 亲自执行并以真实命令输出为准
- **生产环境**：树莓派 `raspberrypi`，内网 192.168.31.51，经 8.8.8.8 解析外网 IP + `HostKeyAlias` 绕过公司 DNS

## 部署步骤与结果

| # | 步骤 | 命令/对象 | 结果 |
|---|---|---|---|
| 1 | SSH 连通 | `ssh -o HostKeyAlias=et116374mm892.vicp.fun yangyang@115.236.153.170` | ✅ CONNECTED (raspberrypi) |
| 2 | 拉取范围核对 | `git diff --name-only a5a8c70 4765cf4` | ✅ 不含 `.env`/`package-lock.json`/`heartbeat_broker_config.json` |
| 3 | 生产拉取 | `git pull origin main` | ✅ Fast-forward → 4765cf4（29 files, 6048 insertions） |
| 4 | 迁移计划核对 | `migrate api 0029 --plan` | ✅ 仅 CreateModel + 1 约束 + 2 索引，**无任何 ALTER 既有表** |
| 5 | 应用迁移（**仅 0029**） | `migrate api 0029` | ✅ Applying ... OK |
| 6 | 表结构验证 | `SHOW COLUMNS FROM condensation_warning_event` | ✅ 19 列齐全（含 specific_part / device_sn / warning_type / dew_point_temp / ntc_temp / humidity / system_switch / first/last_seen_at / recovered_at / is_active 等） |
| 7 | 管理命令加载 | `manage.py help condensation_consumer` / `condensation_cleanup` | ✅ 均 OK |
| 8 | 安装 systemd 单元 | cp 3 个单元到 `/etc/systemd/system/` + `daemon-reload` | ✅ 完成 |
| 9 | 启用并启动 | `enable --now freeark-condensation-consumer` + `...cleanup.timer` | ✅ 两者 active + enabled |
| 10 | 消费者健康 | `ss -tnp` / `systemctl status` | ✅ PID 稳定运行，已建立 MQTT 连接（→171.213.194.195:8084）+ MySQL 连接（→192.168.31.98:3306），无重启 |
| 11 | 重启后端 | `systemctl restart freeark-backend` | ✅ active；`/api/health/` 返回 `{"status":"ok"}` |
| 12 | REST 端点冒烟 | `GET /api/devices/condensation-warning-events/?status=all` | ✅ HTTP 401（已注册且需鉴权，非 404） |
| 13 | 前端构建 | 备份 dist → `npm run build` | ✅ built in 19.39s；`CondensationWarningView-HeYQ-5Kz.js` 已生成 |
| 14 | SPA 服务 | `curl http://127.0.0.1:8080/` | ✅ HTTP 200 |
| 15 | 清理 timer 排程 | `list-timers` | ✅ 次次运行 2026-05-31 03:30（与 fault-cleanup 03:00 错峰） |

## 风险控制落实

- ✅ **严格只迁移到 0029**：`--plan` 先确认无 `plclatestdata.id` 等既有表 ALTER；未执行 `makemigrations`，规避 3766 万行大表锁表风险（候选 0030 未生成、未应用）。
- ✅ **未触碰生产本地修改文件**：`.env` / `package-lock.json` / `heartbeat_broker_config.json` 保持原状（fast-forward 未涉及）。
- ✅ **未误重启无关服务**：`freeark-fault-consumer`、`freeark-mqtt-consumer` 部署后仍 active，未被重启。
- ✅ **部署纪律**：全程 `ssh + git pull`，无 pscp 逐文件上传；无 Docker。

## 部署后服务状态

| 服务 | active | enabled |
|---|---|---|
| freeark-condensation-consumer | ✅ active | ✅ enabled |
| freeark-condensation-cleanup.timer | ✅ active | ✅ enabled |
| freeark-backend | ✅ active | — |
| freeark-fault-consumer（未改动） | ✅ active | — |
| freeark-mqtt-consumer（未改动） | ✅ active | — |

## 后续观察建议

1. 待真实 `condensation_alarm != 0` 上报后，核对 `condensation_warning_event` 是否按 T1/T2/T3 状态机正确写入（露点温度/NTC/湿度快照、system_switch 经 PLCLatestData 回填）。
2. 消费者日志为 journald 缓冲（单元未设 `PYTHONUNBUFFERED`），如需实时排查可临时加 `Environment=PYTHONUNBUFFERED=1` 后重启。
3. 2026-05-31 03:30 首次清理任务执行后，确认 `journalctl -u freeark-condensation-cleanup` 无异常。
