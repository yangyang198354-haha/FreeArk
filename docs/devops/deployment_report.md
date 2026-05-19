# Deployment Report — FreeArk PLC Device Settings + Write Record

**Status**: READY_FOR_DEPLOYMENT — 等待用户 CONFIRM 后由 PM 触发实际执行  
**Author**: devops-engineer  
**Date**: 2026-05-19  
**Release**: PLC 设备设置面板 + 写入记录（含 PLCWriteSubscriber MQTT 回路）

---

## 部署就绪状态

| 检查项 | 状态 |
|--------|------|
| 部署文档已完成（cicd_pipeline.md + deployment_plan.md） | DONE |
| 本地测试 55 passed, 0 warnings（用户已确认） | DONE |
| migration 文件已就绪（0023_plcwriterecord.py） | DONE |
| 前端新依赖已在 package.json 声明（mqtt ^5.10.1） | DONE |
| 所有破坏性命令均标注"⚠ 需用户 CONFIRM" | DONE |
| 回滚方案已记录（DB + 代码 + 前端） | DONE |
| 禁止技术审查：无 Docker / k8s / pscp 逐文件 / 明文密码 | PASS |

---

## 实际部署动作（待用户 CONFIRM 后由 PM 触发）

以下为本次发布需要在生产环境执行的完整动作清单，**当前均未执行**：

| 步骤 | 动作 | 执行位置 | 等待状态 |
|------|------|---------|---------|
| 1 | `git push origin main` | 本地 Windows | 等待用户 CONFIRM |
| 2 | `git pull origin main` | 远端树莓派 | 等待用户 CONFIRM |
| 3 | `python manage.py migrate api --plan`（干跑） | 远端树莓派 | 等待用户 CONFIRM |
| 4 | `python manage.py migrate api --no-input`（正式） | 远端树莓派 | 等待用户 CONFIRM |
| 5 | `systemctl restart freeark-backend` | 远端树莓派 | 等待用户 CONFIRM |
| 6 | 远端 `npm install && npm run build`（在树莓派上执行） | 远端树莓派 | 等待用户 CONFIRM |
| 7 | 远端 `cp -r dist/ /usr/share/nginx/html/` + `systemctl reload nginx` | 远端树莓派 | 等待用户 CONFIRM |
| 8 | `systemctl restart freeark-task-scheduler` | 远端树莓派 | 等待用户 CONFIRM |
| 9 | `systemctl restart freeark-mqtt-consumer` | 远端树莓派 | 等待用户 CONFIRM |

---

## 部署后验收记录（部署执行后填写）

| 健康检查项 | 期望 | 实际结果 | 时间 |
|-----------|------|---------|------|
| GET /api/device-settings/records/?page=1 | 200 或 401 | — | — |
| 设备设置面板页面渲染 | 无 console error | — | — |
| WebSocket ws://192.168.31.98:32797/mqtt | OPEN | — | — |
| Django 日志无新 ERROR | 0 new errors | — | — |
| datacollection 含 PLCWriteSubscriber 启动日志 | 日志存在 | — | — |

---

## 系统服务说明（经脚本 Read 确认）

从 `deploy_device_management.bat` 和 `deploy_v2_operation_mode.bat` 确认的 systemd unit 名：

| 服务 | Unit 名 | 作用 |
|------|---------|------|
| Django (waitress) | `freeark-backend` | 提供 REST API，端口 8000（入口 `start_waitress_server.py`，非 gunicorn）|
| MQTT Consumer | `freeark-mqtt-consumer` | 订阅 PLC 数据写入 MySQL |
| 数据采集调度 | `freeark-task-scheduler` | 含 PLCWriteSubscriber 订阅写命令线程 |
| Web Server | `nginx` | 反向代理 + 静态前端，端口 80 |

---

## MQTT 端口说明（经源码 Read 确认）

| 端口 | 协议 | 用途 | 来源 |
|------|------|------|------|
| 192.168.31.98:32788 | TCP (MQTT) | 后端 mqtt_consumer + PLCWriteSubscriber 连接 broker | `FreeArkWeb/backend/mqtt_config.json` + `improved_data_collection_manager.py:100` |
| 192.168.31.98:32797 | WebSocket (MQTT over WS) | 前端浏览器 useMqttWebSocket.js 连接 broker | 用户提供，nginx.conf 无代理（浏览器直连） |

---

## 最终状态

**READY_FOR_DEPLOYMENT**

部署文档准备完毕，所有破坏性动作均已明确标注，等待用户 CONFIRM 后 PM 触发实际执行。

*本文档由 devops-engineer 产出，当前轮次不执行任何生产动作。*
