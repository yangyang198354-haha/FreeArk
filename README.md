# FreeArk

FreeArk 是一套面向智慧楼宇中央空调系统的 Web 运维管理平台。后端基于 Django 5.2 + Django Channels ASGI，前端基于 Vue 3 + Vite，通过 MQTT 实时接收 PLC 设备数据，提供系统看板、设备管理、故障管理、结露预警和方舟智能体 AI 助手等功能。

> 历史桌面数据采集工具（`datacollection/`）仍保留于此仓库，但主体产品已演进为 FreeArkWeb。

---

## 核心功能

| 功能模块 | 说明 |
|---------|------|
| 系统看板 | 实时展示 PLC 在线率、开机率、大屏在线率、用电量趋势、故障摘要、系统服务状态 |
| 设备管理 | 设备树浏览、设备参数实时面板（WebSocket）、设备配置读写、凝露预警标记 |
| 故障管理 | 故障事件记录、按房间/设备/时间段过滤、活跃故障追踪与恢复确认 |
| 结露预警 | 基于温湿度数据的结露风险评估，支持预警列表与历史查询 |
| 业主信息 | 业主档案管理，含房间与联系方式 |
| 方舟智能体 AI 助手 | 嵌入式 AI 对话助手（LangGraph 编排），支持推理流式输出、多会话记忆隔离、语音输入 |
| 用户与认证 | Token 认证 + 滑动窗口会话超时（30 min）、CSRF 保护、角色权限 |

---

## 架构概述

```
浏览器 (Vue 3 + Vite)
   │  HTTP/REST ────────────────────────────────────┐
   │  WebSocket (Django Channels)                   │
   └──────────────────────────────────────────────► Django 5.2 (ASGI / Waitress)
                                                     │
                               ┌─────────────────────┤
                               │                     │
                        MySQL (生产)           SQLite (测试)
                               │
              MQTT Broker ◄────┤◄──── PLC 设备 (snap7)
              (paho 2.x)       │
                         task-scheduler (定时采集)
                         mqtt-consumer  (消息入库)
```

**关键技术栈**

| 层 | 技术 |
|----|------|
| 后端框架 | Django 5.2, Django REST Framework, Django Channels |
| ASGI 服务器 | Waitress（生产单 worker）|
| 数据库 | MySQL 8（生产）/ SQLite（测试）|
| 消息队列 | MQTT (paho-mqtt 2.x) |
| PLC 通信 | snap7 |
| 前端框架 | Vue 3, Vite, Pinia |
| AI 集成 | LangGraph (方舟智能体) |

---

## 目录结构

```
FreeArk/
├── FreeArkWeb/
│   ├── backend/
│   │   ├── freearkweb/            # Django 项目根（manage.py 在此）
│   │   │   ├── api/               # 主应用（models/views/serializers/tests）
│   │   │   │   ├── tests/         # 测试包（test_*.py）
│   │   │   │   ├── tests_*.py     # 独立测试模块
│   │   │   │   └── management/commands/  # 管理命令
│   │   │   └── freearkweb/        # Django settings/urls/asgi/wsgi
│   │   └── requirements.txt
│   └── frontend/                  # Vue 3 + Vite 前端
│       ├── src/
│       └── API_CONFIGURATION.md
├── datacollection/                # 历史桌面 PLC 采集工具（遗留）
├── docs/                          # 项目文档（按版本与子目录组织）
│   ├── requirements/              # 需求规格（各版本子目录）
│   ├── architecture/              # 架构与模块设计
│   ├── development/               # 实现计划与代码评审
│   ├── testing/                   # 测试计划与报告
│   ├── deployment/                # 部署计划与报告
│   ├── bugfix/                    # Bug 修复记录
│   ├── troubleshooting/           # 故障排查记录
│   ├── analysis/                  # 专项分析报告
│   └── specs/                     # 功能规格（含 AI 助手各特性）
├── scripts/
│   └── analysis/                  # 调试探针脚本
├── systemctl/                     # systemd 服务配置说明
└── .claude/skills/freeark-prod-deploy/SKILL.md  # 生产部署手册
```

---

## 本地开发与测试

### 环境要求

- Python 3.11+
- Node.js 18+（前端）
- pip 依赖：`pip install -r FreeArkWeb/backend/requirements.txt`

### 启动后端（开发模式）

```bash
cd FreeArkWeb/backend/freearkweb
python manage.py migrate
python manage.py runserver
```

### 启动前端（开发模式）

```bash
cd FreeArkWeb/frontend
npm install
npm run dev
```

### 运行测试

所有测试使用内存 SQLite，无需连接生产数据库。在 `FreeArkWeb/backend/freearkweb/` 目录下执行：

```bash
# 运行全部测试
python manage.py test api --settings=freearkweb.test_settings

# 运行特定测试模块
python manage.py test api.tests_session_timeout --settings=freearkweb.test_settings -v 2
python manage.py test api.tests.test_csrf_relogin --settings=freearkweb.test_settings --verbosity=2
python manage.py test api.tests.test_v100_dashboard_redesign --settings=freearkweb.test_settings --verbosity=2
python manage.py test api.tests_fault_event --settings=freearkweb.test_settings -v 2
```

---

## 生产部署

生产环境运行于树莓派，通过 systemd 管理多个服务。完整部署流程、SSH 连接方式、服务重启命令详见：

[`.claude/skills/freeark-prod-deploy/SKILL.md`](.claude/skills/freeark-prod-deploy/SKILL.md)

后端也提供参考：[`FreeArkWeb/backend/DEPLOYMENT_GUIDE.md`](FreeArkWeb/backend/DEPLOYMENT_GUIDE.md)

---

## 文档索引

| 目录 | 内容 |
|------|------|
| `docs/requirements/` | 各版本需求规格与用户故事 |
| `docs/architecture/` | 架构设计与模块设计 |
| `docs/development/` | 实现计划与代码评审报告 |
| `docs/testing/` | 测试计划与测试报告 |
| `docs/deployment/` | 部署计划与部署报告 |
| `docs/bugfix/` | Bug 分析与修复记录 |
| `docs/troubleshooting/` | 生产故障排查记录 |
| `docs/analysis/` | 专项技术分析报告 |
| `docs/specs/` | 方舟智能体 AI 助手各特性规格 |

---

## 联系与支持

如有问题，请联系项目维护团队。
