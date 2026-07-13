# FreeArk — 智能建筑管理平台

## 项目概述

FreeArk 是一个智能建筑/物业管理系统，包含 Web 管理后台、微信小程序业主端、PLC 设备数据采集、AI 聊天助手（LangGraph + DeepSeek）等模块。

## 技术栈

| 层 | 技术 |
|---|------|
| Web 后端 | Django (Python 3.12), Waitress/Gunicorn, Channels (WebSocket) |
| Web 前端 | Vue 3 + Vite + Element Plus |
| 微信小程序 | uni-app (Vue 3) |
| 数据采集 | Python (paho-mqtt, snap7) |
| AI 聊天 | LangGraph + DeepSeek v4-flash（进程内直连，非 OpenAI） |
| 生产数据库 | MySQL (192.168.31.98:3306) |
| 测试数据库 | SQLite（内存库，test_settings.py） |
| 生产服务器 | 树莓派 5 (aarch64, Debian 13, 4GB RAM) |

## 基础设施约束（所有 Agent 强制遵守）

### 禁止 Docker
整个项目采用物理机直接部署，严禁使用 Docker 或任何容器化方案。

### 生产环境
- **服务器**：树莓派 5，内网 IP `192.168.31.51`，SSH 用户 `yangyang`
- **外网访问**：阿里云 VPS `47.109.197.217` + frp 隧道（web→:18080，SSH→:57279）
- **旧外网通道**：花生壳 `et116374mm892.vicp.fun:57279`（待备案后退役）
- **数据库**：MySQL，地址 `192.168.31.98:3306`，库名 `freeark`
- **部署方式**：`git pull` + systemd 服务重启（禁止 pscp 逐文件上传）
- **代码提交**：直接提交到 `main` 分支，不需开分支+PR

### 测试环境
- 所有测试必须使用 SQLite（`--settings=freearkweb.test_settings`）
- 环境变量：`FREEARK_POC_MOCK=1`（离线导入必需），`PYTHONUTF8=1`（编码必需）
- 测试运行器：Django test runner（非 pytest，`api/` 下除外）
- ⚠️ 严禁任何测试连接生产数据库

### API 鉴权
- Admin 鉴权使用 `User.role == 'admin'`，不是 Django 的 `is_staff`
- 三角色 RBAC：admin / operator / user（业主）
- 小程序端鉴权：`/api/miniapp/` + `IsOwnerUser`

## 关键目录

```
FreeArkWeb/backend/freearkweb/    # Django 后端
  api/                             # 主 API 应用（views, models, serializers, urls）
  api/langgraph_chat/              # LangGraph AI 聊天编排
  api/migrations/                  # Django 迁移（手写 scoped，勿用 makemigrations 全产物）
  inspection_agent/                # 巡检自治 Agent
FreeArkWeb/frontend/               # Vue 3 Web 前端
miniprogram/                       # uni-app 微信小程序
datacollection/                    # MQTT 数据采集 + PLC 读写
agents/langgraph-poc/              # LangGraph PoC（非生产）
docs/                              # 项目文档
systemctl/                         # systemd 服务定义
```

## 开发约定

1. **迁移文件**：必须手写 scoped 迁移，禁止 `makemigrations` 全产物（存在迁移漂移）
2. **生产部署**：通过 `git pull`，禁止 pscp 逐文件上传
3. **代码提交**：直接 commit/push main，不要每次开分支+PR
4. **子代理核验**：test-engineer 等子代理的测试结论必须亲自复核
5. **模型修改**：子代理"只改样式"任务会越界重写/压缩代码，diff 必须用方法名集合对比核验
6. **上下文搜索**：ripgrep/Grep 遵守 `.gitignore` 可能漏扫 `docs/sdlc` 等强制跟踪文件，全仓内容核验用 `git grep` 为准
7. **聊天库版本**：`langchain-openai` pin `<0.3`（0.3.x 删了 `_convert_chunk_to_generation_chunk`，生产漂移过）

## systemd 服务清单

| 服务 | 用途 |
|------|------|
| `freeark-backend` | Django 后端（Waitress/Gunicorn） |
| `freeark-mqtt-consumer` | MQTT 消息消费（数据采集入库） |
| `freeark-task-scheduler` | 定时任务调度（含巡检、数据采集） |
| `freeark-fault-consumer` | 故障事件写入服务 |
| `freeark-dph-cleanup` | device_param_history 定期清理 |
| `freeark-gunicorn` / `nginx` | Web 服务 |

## 当前版本

- 后端：v1.12.x+（已部署）
- 小程序：v1.13.0（cyberpunk UI 重构 + main_thermostat + reorder）
- 前端：赛博朋克风格主题
