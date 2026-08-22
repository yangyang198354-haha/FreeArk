# FreeArk — 智能建筑管理平台

FreeArk 是一套面向智慧楼宇中央空调系统的运维管理平台，覆盖**设备数据采集 → 后端服务 → Web 运维后台 / 微信小程序业主端 → AI 智能体助手**的完整链路。

生产环境运行于**树莓派 5**（物理机直接部署，**全项目禁止 Docker**），数据落 MySQL，设备侧通过 MQTT + snap7 与 PLC 通信。

---

## 仓库构成

| 模块 | 目录 | 说明 |
|------|------|------|
| **Web 后端** | `FreeArkWeb/backend/freearkweb/` | Django 5.2 + DRF + Channels（ASGI），主应用 `api/` |
| **Web 前端** | `FreeArkWeb/frontend/` | Vue 3 + Vite + Pinia，管理后台（admin/operator） |
| **微信小程序** | `miniprogram/` | uni-app (Vue 3)，业主端（user 角色），赛博朋克 UI |
| **数据采集** | `datacollection/` | PLC 轮询、MQTT 收发、定时任务调度 —— **在生产运行**，非遗留代码 |
| **AI 智能体** | `FreeArkWeb/backend/freearkweb/api/langgraph_chat/` | LangGraph 编排，进程内直连 DeepSeek v4-flash |
| **智能体提示词** | `agents/` | 各专家 Agent 的 SYSTEM_PROMPT + LangGraph PoC |
| **巡检 Agent** | `FreeArkWeb/backend/freearkweb/inspection_agent/` | 自治巡检、故障事件轮询、工单生成 |
| **服务定义** | `systemctl/`、`deployment/systemd/` | systemd unit 文件与服务说明 |
| **文档** | `docs/` | 需求 / 架构 / 开发 / 测试 / 部署 / 排障，共 400+ 篇 |

---

## 核心功能

### Web 管理后台（admin / operator）

| 模块 | 说明 |
|------|------|
| 系统看板 | PLC 在线率、开机率、大屏在线率、用电量趋势、故障摘要、systemd 服务状态 |
| 设备管理 | 设备树浏览、参数实时面板（WebSocket）、设备配置读写、写操作审计与超时回执 |
| 故障管理 | 故障事件记录、按房间/设备/时间过滤、活跃故障追踪与恢复确认 |
| 结露预警 | 基于温湿度的结露风险评估，预警列表与历史查询 |
| 能耗报表 | 日用电 / 月用电统计与查询 |
| 工单与巡检 | 工单列表、巡检工作日志 |
| 知识库（RAG） | 三横知识库文档入库（docx / pdf / 图片 OCR）与检索 |
| 业主与用户 | 业主档案、三角色 RBAC（admin / operator / user）、Token 认证 + 30 min 滑动超时 |
| 方舟智能体 | 嵌入式 AI 对话，推理流式输出、多会话记忆隔离、语音输入、图片理解 |

### 微信小程序业主端（user）

以「飞船舱段」为隐喻的赛博朋克界面：舱室温控面板、子系统状态、故障抽屉、能耗图表、副官对话（独立 WS 通道 + UserScope 数据隔离）。

分包：`monitor`（PLC 状态 / 设备面板 / 参数历史）、`energy`（报表）、`ops`（故障 / 结露 / 工单 / 巡检日志）、`chat`、`game`。

后端接口：`/api/miniapp/*`（19 条路由，`IsOwnerUser` 鉴权）+ `ws/miniapp/chat/`。

---

## 架构

```
微信小程序 (uni-app)          浏览器 (Vue 3 + Vite)
        │                              │
        │ /api/miniapp/*               │ /api/*
        │ ws/miniapp/chat/             │ ws/chat/
        └──────────────┬───────────────┘
                       ▼
              nginx (反向代理，Pi)
                       ▼
        Uvicorn ASGI ── Django 5.2 + Channels  (:8000, workers=1)
                       │
        ┌──────────────┼───────────────────────────┐
        ▼              ▼                           ▼
   MySQL 8       Redis (Channel Layer + 缓存)   进程内 LangGraph
 192.168.31.98                                   └─► DeepSeek v4-flash
        ▲
        │ 入库
   mqtt-consumer / fault-consumer / condensation-consumer
        ▲
        │ MQTT (paho 2.x)
   MQTT Broker ◄──── datacollection (task-scheduler)
                            │ snap7
                            ▼
                        PLC 设备 / 屏端
```

**技术栈**

| 层 | 技术 |
|----|------|
| 后端框架 | Django 5.2、DRF、Django Channels 4.x |
| ASGI 服务器 | Uvicorn `[standard]`（单 worker；可回滚 Waitress） |
| 数据库 | MySQL 8（生产 `192.168.31.98:3306/freeark`）/ SQLite 内存库（测试） |
| 缓存 / Channel Layer | Redis 5.x + channels_redis 4.x |
| 消息 | MQTT（paho-mqtt 2.x，走 VERSION1 回调签名） |
| PLC 通信 | python-snap7 |
| Web 前端 | Vue 3、Vite、Pinia、Element Plus |
| 小程序 | uni-app 3.0（mp-weixin）、@qiun/ucharts、mqtt.js |
| AI | LangGraph 0.2–0.3 + langchain-openai `<0.3`（**不可升 0.3.x**）→ DeepSeek |
| RAG | python-docx、PyMuPDF、rapidocr-onnxruntime（aarch64 已验证） |
| 运行环境 | Python 3.12、树莓派 5 / Debian 13 / aarch64 |

---

## 目录结构

```
FreeArk/
├── FreeArkWeb/
│   ├── backend/
│   │   ├── requirements.txt
│   │   ├── DEPLOYMENT_GUIDE.md
│   │   └── freearkweb/               # Django 项目根（manage.py 在此）
│   │       ├── api/                  # 主应用
│   │       │   ├── views*.py / serializers*.py / models*.py / urls*.py
│   │       │   ├── langgraph_chat/   # AI 编排（router / experts / scope_enforcer）
│   │       │   ├── mqtt_consumer.py  # MQTT 入库
│   │       │   ├── fault_consumer/ condensation_consumer/
│   │       │   ├── migrations/       # 手写 scoped 迁移
│   │       │   ├── management/commands/   # 各 systemd 服务的入口命令
│   │       │   └── tests/ + tests_*.py
│   │       ├── inspection_agent/     # 巡检自治 Agent
│   │       └── freearkweb/           # settings / urls / asgi / test_settings
│   └── frontend/                     # Vue 3 + Vite（29 个视图）
├── miniprogram/                      # uni-app 微信小程序
│   ├── pages/ components/ composables/ store/ subpackages/ tests/
├── datacollection/                   # PLC 采集 + MQTT + 定时调度（生产运行）
├── agents/                           # Agent 提示词与 LangGraph PoC
│   ├── freeark-expert/ energy-expert/ inspection-expert/ sanheng-knowledge/
│   └── langgraph-poc/
├── docs/                             # 需求/架构/开发/测试/部署/排障/规格
├── scripts/                          # 探针、测试清单生成、标签注入
├── systemctl/                        # systemd unit + 服务说明
├── plc_config.json                   # PLC 点表配置
├── PLC与MODBUS地址对照表*.xlsx        # 硬件方权威地址表
└── .claude/skills/                   # 生产部署手册、测试运行手册
```

---

## 本地开发

### 环境要求

- Python 3.12
- Node.js 18+
- MySQL（可选，本地开发可用 SQLite）

### 后端

```bash
pip install -r FreeArkWeb/backend/requirements.txt
cd FreeArkWeb/backend/freearkweb
python manage.py migrate
python manage.py runserver          # 纯 HTTP
# 需要 WebSocket 时：
uvicorn freearkweb.asgi:application --host 0.0.0.0 --port 8000
```

> ⚠️ 迁移必须**手写 scoped 迁移**，不要用 `makemigrations` 的全量产物（仓库存在迁移漂移）。

### Web 前端

```bash
cd FreeArkWeb/frontend
npm install
npm run dev
```

### 小程序

```bash
cd miniprogram
npm install
npm run dev:mp-weixin      # 产物在 dist/，用微信开发者工具打开
npm run build:mp-weixin
```

---

## 测试

后端使用 **Django test runner**（非 pytest），全部跑 SQLite 内存库，**严禁连接生产数据库**。

```bash
cd FreeArkWeb/backend/freearkweb

# 全量
FREEARK_POC_MOCK=1 PYTHONUTF8=1 python manage.py test api --settings=freearkweb.test_settings

# 按层级（测试已打 @tag('unit'|'integration'|'e2e')）
FREEARK_POC_MOCK=1 python manage.py test api --settings=freearkweb.test_settings --tag=unit
```

- `FREEARK_POC_MOCK=1`：`fa_tools` 离线导入必需
- `PYTHONUTF8=1`：编码必需
- 分层映射见 `docs/testing/test_inventory.md`（由 `scripts/gen_test_inventory.py` 生成）

卫星测试：

```bash
cd datacollection && pytest                    # 数据采集
cd FreeArkWeb/frontend && npm run test         # 前端 Vitest
cd miniprogram && npm test                     # 小程序 Vitest
```

**当前基线（2026-08-01，生产 Pi 实跑）**：`test api` = 2137 测试 / 291s，**3 failures / 0 errors / 46 skipped**。这 3 项为既有失败（2 个 `ScreenConnectivityChecker` 用例 + 1 个会真打 DeepSeek 的 flaky 路由用例），**不要误判为自己引入的回归**。详见 `.claude/skills/test-runner/SKILL.md`。

> ⚠️ 不要用 `git worktree` 做改动前后对照 —— 仓库内已提交的 `.env` 不含真实 `DEEPSEEK_API_KEY`，worktree 里 LangGraph 用例会短路秒过，产生假阳性。正确做法是在同一工作目录里临时 `git checkout <旧提交> -- <改的文件>` 再跑。

### CI

`.github/workflows/ci.yml`：push main / PR 触发，三 job 并行（后端 Django 全量、datacollection pytest、前端 Vitest + build）。CI 无需任何外部服务（SQLite + DummyCache + InMemoryChannelLayer + mock）。门控写的是"全绿"，但上述 3 项既有失败会让 CI 红。

---

## 生产部署

- **服务器**：树莓派 5，内网 `192.168.31.51`，用户 `yangyang`
- **外网**：阿里云 VPS `47.109.197.217` + frp 隧道（web → `:18080`，SSH → `:57279`）；旧花生壳通道 `et116374mm892.vicp.fun` 待备案后退役
- **部署方式**：`git pull` + `systemctl restart`（**禁止 pscp 逐文件上传**）
- **代码流程**：直接 commit / push `main`，不开分支 PR

完整流程（SSH、构建、按改动决定重启哪个服务、数据库与日志、已知坑）见
[`.claude/skills/freeark-prod-deploy/SKILL.md`](.claude/skills/freeark-prod-deploy/SKILL.md)。

### systemd 服务

| 服务 | 用途 |
|------|------|
| `freeark-backend` | Uvicorn ASGI（Django + Channels，:8000） |
| `freeark-mqtt-consumer` | MQTT 消息消费入库 |
| `freeark-fault-consumer` | 故障事件写入 |
| `freeark-task-scheduler` | 定时调度（跑 `datacollection/run_task_scheduler.py`） |
| `freeark-screen-heartbeat` | 屏端心跳消费 |
| `freeark-plc-connection-monitor` | PLC 连接监控 |
| `freeark-plc-write-timeout` | PLC 写超时清理 |
| `freeark-daily-usage` / `freeark-monthly-usage` | 日 / 月用电统计 |
| `freeark-dph-cleanup` / `freeark-plc-cleanup` | 历史数据定期清理 |
| `nginx` | 反向代理 + 前端静态资源 |

聊天 AI **没有独立服务/端口** —— v1.7.0 起 LangGraph 在 `freeark-backend` 进程内运行（已退役 OpenClaw）。

---

## 项目约定

1. **禁止 Docker** —— 全项目物理机直接部署。`datacollection/` 下残留的 `Dockerfile` / `docker-compose.yml` 为历史产物，不在生产使用。
2. **迁移手写** —— 禁止 `makemigrations` 全量产物。
3. **提交直推 main** —— 不开分支 + PR。
4. **测试只连 SQLite** —— 任何测试不得连生产库。
5. **鉴权用 `User.role == 'admin'`** —— 不是 Django 的 `is_staff`。
6. **全仓内容核验用 `git grep`** —— ripgrep 遵守 `.gitignore`，会漏扫 `docs/sdlc` 等强制跟踪文件。
7. **`langchain-openai` pin `<0.3`** —— 0.3.x 删了 `_convert_chunk_to_generation_chunk`，生产漂移过。
8. **子代理结论必须亲自复核** —— 尤其测试结论与"只改样式"类改动（diff 用方法名集合对比）。

---

## 文档索引

| 目录 | 内容 |
|------|------|
| `docs/requirements/` | 各版本需求规格与用户故事 |
| `docs/architecture/` | 架构决策记录（ADR）与模块设计 |
| `docs/development/` `docs/implementation/` | 实现计划与代码评审 |
| `docs/testing/` | 测试计划、报告、`test_inventory.md` |
| `docs/deployment/` `docs/devops/` | 部署计划与报告、CI/CD |
| `docs/specs/` | 功能规格（含 AI 助手各特性） |
| `docs/bugfix/` `docs/troubleshooting/` | Bug 修复与生产排障记录 |
| `docs/analysis/` `docs/design/` | 专项分析与设计 |
| `docs/sdlc/` | SDLC 流程产物 |

同时参考仓库根 [`CLAUDE.md`](CLAUDE.md)（Agent 强制约束）与 `.claude/skills/` 下的运行手册。
