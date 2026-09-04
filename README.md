# FreeArk — 智能建筑管理平台

FreeArk 是一套面向智慧楼宇三恒（恒温/恒湿/恒氧）中央空调系统的运维管理平台，覆盖**设备数据采集 → 后端服务 → Web 运维后台 / 多端业主应用（微信小程序 + H5 + Android APK） → AI 多智能体助手**的完整链路。

生产环境运行于**树莓派 5**（物理机直接部署，**全项目禁止 Docker**），数据落 MySQL 8，设备侧通过 MQTT + snap7 与 PLC 通信。

**当前版本**：多端应用 `v1.0.4`（apk-test 分支，含微信小程序 / H5 / Android APK 三端）；后端跟随 main 持续迭代。

---

## 仓库构成

| 模块 | 目录 | 说明 |
|------|------|------|
| **Web 后端** | `FreeArkWeb/backend/freearkweb/` | Django 5.2+ + DRF + Channels（ASGI），主应用 `api/` |
| **Web 前端** | `FreeArkWeb/frontend/` | Vue 3.5 + Vite + Pinia + Element Plus，管理后台（admin/operator），27 个视图 |
| **多端业主应用** | `miniprogram/` | uni-app (Vue 3)，一套源码编译三端：微信小程序（mp-weixin）/ H5 / Android APK（app-plus）。赛博朋克"飞船舱段"UI |
| **数据采集** | `datacollection/` | PLC 轮询、MQTT 收发、定时任务调度 —— **在生产运行**，非遗留代码 |
| **AI 多智能体** | `FreeArkWeb/backend/freearkweb/api/langgraph_chat/` | LangGraph 三专家编排（系统管家 / 巡检诊断 / 三恒知识），进程内直连 DeepSeek，含作用域强制与 RBAC 数据隔离 |
| **专家提示词** | `agents/` | 三位专家的 `SYSTEM_PROMPT.langgraph.md` + `freeark-skill/` 工具能力说明 |
| **巡检 Agent** | `FreeArkWeb/backend/freearkweb/inspection_agent/` | 自治巡检、故障事件轮询、工单生成 |
| **副官推荐** | `FreeArkWeb/backend/freearkweb/api/adjutant_recommendations.py` | 聊天页副官推荐问题（安全过滤 + 意图分类） |
| **服务定义** | `systemctl/`、`deployment/systemd/` | systemd unit 文件与服务说明 |
| **文档** | `docs/` | 需求 / 架构 / 开发 / 测试 / 部署 / 排障，共 400+ 篇 |
| **发布说明** | `docs/deployment/apk_test_release/` | APK 多端版本 ReleaseNotes（MD + Word） |

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
| 方舟智能体 | 多智能体 AI 对话（系统管家 / 巡检诊断 / 三恒知识），推理流式输出、多会话记忆隔离、语音输入、图片理解、用户人格偏好、副官推荐问题 |

### 多端业主应用（user 角色）

以「飞船舱段」为隐喻的赛博朋克界面：舱室温控面板、子系统状态、故障抽屉、能耗图表、副官对话（独立 WS 通道 + UserScope 数据隔离）。

**编译目标**（一套源码，三端产物）：

| 端 | 产物 | 构建命令 |
|----|------|---------|
| 微信小程序 (mp-weixin) | `dist/build/mp-weixin/` | `npm run build:mp-weixin` → 微信开发者工具导入 |
| H5 | `dist/build/h5/` | `npm run build:h5` → 静态服务器 / WebView 内嵌 |
| Android APK (app-plus) | `.apk` | HBuilderX 发行 → 原生 App 云打包 |

分包：`monitor`（PLC 状态 / 设备面板 / 参数历史）、`energy`（报表）、`ops`（故障 / 结露 / 工单 / 巡检日志）、`chat`、`game`。

后端接口：`/api/miniapp/*`（21 条路由，`IsOwnerUser` 鉴权）+ `ws/miniapp/chat/`。

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
| 后端框架 | Django 5.2+、DRF、Django Channels 4.x |
| ASGI 服务器 | Uvicorn `[standard]`（单 worker；可回滚 Waitress） |
| 数据库 | MySQL 8（生产 `192.168.31.98:3306/freeark`）/ SQLite 内存库（测试） |
| 缓存 / Channel Layer | Redis 5.x + channels_redis 4.x |
| 消息 | MQTT（paho-mqtt 2.x，走 VERSION1 回调签名） |
| PLC 通信 | python-snap7 |
| Web 前端 | Vue 3.5、Vite、Pinia、Element Plus |
| 多端应用 | uni-app 3.0（mp-weixin / H5 / app-plus）、@qiun/ucharts、mqtt.js |
| AI 编排 | LangGraph 0.2–0.4 + langchain-core 0.3.x + langchain-openai `>=0.2.10,<0.3`（**不可升 0.3.x**）→ DeepSeek v4-flash |
| RAG | python-docx、PyMuPDF、rapidocr-onnxruntime（aarch64 已验证） |
| 运行环境 | Python 3.13（生产 Pi 5 / Debian 13 / aarch64）；本地开发 3.12+ |

---

## AI 多智能体（LangGraph）

聊天助手由 **LangGraph 状态图** 编排，在 `freeark-backend` 进程内直连 DeepSeek v4-flash（v1.7.0 起退役 OpenClaw，无独立服务/端口）。

### 三位专家（`agents/<name>/SYSTEM_PROMPT.langgraph.md`）

| 专家 | 职责 | 持有工具 |
|------|------|---------|
| **系统管家** `freeark-expert` | 能耗看板、设备实时参数、确认式写控制、业主人格偏好 | 能耗查询 / 实时参数 / 设备写 / 写状态 / 人格读写 |
| **巡检诊断** `inspection-expert` | PLC 状态、故障汇总、传感器诊断与修复建议 | PLC 状态 / 故障汇总 / 故障详情 |
| **三恒知识** `sanheng-knowledge` | 三恒原理概念、设备说明书/技术文档（RAG 检索） | RAG 知识库检索（无实时数据工具） |

三位专家均可**子委托**同侪（阶段 G：`delegate_read` / `delegate_write` / `delegate_knowledge`），系统管家为默认兜底专家。

### 编排状态图（`orchestrator.py`）

```
user input → route（LLM 分类 + 关键词 + sticky 路由）
    ├─ 命中专家 → expert（工具调用循环，scope_enforcer 强制作用域）
    │     └─ 写操作 → gate（确认式中断，verify_write_scope 二次校验）→ execute_write
    ├─ 多专家 → 并行 fan-out → aggregate（LLM 聚合）
    └─ 跑题/闲聊 → general（通用回复）
```

### 安全与数据隔离（`scope_enforcer.py` + `user_scope.py`）

- **三角色 RBAC**：admin（全量）/ operator（运维范围）/ user（仅绑定的 `specific_part`）
- **作用域强制**：工具按类别（豁免 / 单 sp / 全局看板 / 过滤汇总 / scoped 查询 / owner self / 写）在调用前注入 `_bound_specific_parts` / `_user_id` 过滤，越权直接拒绝
- **写操作二次校验**：`gate` 节点对所有 pending write 再次 `verify_write_scope`，通过后才 `interrupt` 等待用户确认
- **人格偏好**：`set_persona` / `get_persona` 严格 `OWNER_SELF_TOOLS`，且值经提示注入防护（控制字符剔除 + 注入模式黑名单）

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
│   │       │   ├── adjutant_recommendations.py  # 副官推荐问题
│   │       │   ├── langgraph_chat/   # AI 多智能体编排
│   │       │   │   ├── orchestrator.py   # 状态图：route / expert / gate / aggregate / general
│   │       │   │   ├── router.py         # LLM 分类 + 关键词 + sticky 路由
│   │       │   │   ├── experts.py        # 专家注册表（单一真源）
│   │       │   │   ├── scope_enforcer.py # 作用域强制 + RBAC 数据隔离
│   │       │   │   ├── fa_tools.py       # 工具集（能耗/设备/写操作/persona）
│   │       │   │   ├── user_scope.py     # UserScope 构建
│   │       │   │   ├── adapter.py        # WebSocket 适配器 + 流式输出
│   │       │   │   └── routing_eval/     # 路由评测数据集与 harness
│   │       │   ├── mqtt_consumer.py  # MQTT 入库
│   │       │   ├── fault_consumer/ condensation_consumer/
│   │       │   ├── migrations/       # 手写 scoped 迁移
│   │       │   ├── management/commands/   # 各 systemd 服务的入口命令
│   │       │   └── tests/ + tests_*.py
│   │       ├── inspection_agent/     # 巡检自治 Agent
│   │       └── freearkweb/           # settings / urls / asgi / test_settings
│   └── frontend/                     # Vue 3.5 + Vite（27 个视图）
├── miniprogram/                      # uni-app 多端应用（mp-weixin / H5 / app-plus）
│   ├── pages/ components/ composables/ store/ subpackages/ tests/ utils/
├── datacollection/                   # PLC 采集 + MQTT + 定时调度（生产运行）
├── agents/                           # 三位正式专家的运行时提示词
│   ├── freeark-expert/  inspection-expert/  sanheng-knowledge/
│   │   └── SYSTEM_PROMPT.langgraph.md
│   └── freeark-skill/                # 工具能力说明（SKILL.md + scripts/）
├── docs/                             # 需求/架构/开发/测试/部署/排障/规格
├── docs/deployment/apk_test_release/ # APK 多端版本 ReleaseNotes（MD + Word，apk-test 分支）
├── scripts/                          # 探针、测试清单生成、标签注入
├── systemctl/                        # systemd unit + 服务说明（10 个服务）
├── deployment/systemd/               # 巡检/故障/结露等附加 systemd unit（5 个服务）
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

### 多端应用

> **分支说明**：微信小程序（mp-weixin）构建脚本在 `main` 可用；**H5 与 Android APK 构建配置（`build:h5` / `dev:h5` / `index.html` / 版本号同步）维护在 `apk-test` 分支**，多端发布从该分支出包。

```bash
cd miniprogram
npm install

# 微信小程序（main 可用）
npm run dev:mp-weixin        # 开发，产物在 dist/dev/mp-weixin
npm run build:mp-weixin      # 构建，产物在 dist/build/mp-weixin（微信开发者工具导入）

# H5（需切到 apk-test 分支）
npm run dev:h5               # 开发服务器
npm run build:h5             # 构建，产物在 dist/build/h5

# 单元测试
npm test                      # Vitest
```

> Android APK 需用 HBuilderX（发行 → 原生 App-云打包 → Android），命令行不支持。详见 `docs/deployment/apk_test_release/ReleaseNotes.md`（`apk-test` 分支）。

---

## 测试

后端使用 **Django test runner**（非 pytest），全部跑 SQLite 内存库，**严禁连接生产数据库**。

```bash
cd FreeArkWeb/backend/freearkweb

# 全量（Windows PowerShell 环境变量写法）
$env:PYTHONDONTWRITEBYTECODE='1'; $env:FREEARK_POC_MOCK='1'; $env:PYTHONUTF8='1'; `
  python manage.py test api --settings=freearkweb.test_settings

# 按层级（测试已打 @tag('unit'|'integration'|'e2e')）
$env:FREEARK_POC_MOCK='1'; python manage.py test api --settings=freearkweb.test_settings --tag=unit
```

- `PYTHONDONTWRITEBYTECODE=1`：防止 `.pyc` 文件沙箱/权限冲突
- `FREEARK_POC_MOCK=1`：`fa_tools` 离线导入必需
- `PYTHONUTF8=1`：编码必需
- 分层映射见 `docs/testing/test_inventory.md`（由 `scripts/gen_test_inventory.py` 生成）

卫星测试：

```bash
cd datacollection && pytest                    # 数据采集
cd FreeArkWeb/frontend && npm run test         # 前端 Vitest
cd miniprogram && npm test                     # 小程序 Vitest
```

**当前基线（2026-09-04，Python 3.14 + test_settings + SQLite 内存库）**：
Ran **2254 tests in 75.142s** — **OK (skipped=14)**。14 skips 全部是环境依赖导致（2 个 MySQL 并发测试需真实 MySQL、12 个 bash/sha256sum 外壳脚本在 Windows 不支持），非功能缺陷。

> ⚠️ 不要用 `git worktree` 做改动前后对照 —— 仓库内已提交的 `.env` 不含真实 `DEEPSEEK_API_KEY`，worktree 里 LangGraph 用例会短路秒过，产生假阳性。正确做法是在同一工作目录里临时 `git checkout <旧提交> -- <改的文件>` 再跑。

### CI

`.github/workflows/ci.yml`：push main / PR 触发，三 job 并行（后端 Django 全量、datacollection pytest、前端 Vitest + build）。CI 无需任何外部服务（SQLite + DummyCache + InMemoryChannelLayer + mock）。

---

## 生产部署

- **服务器**：树莓派 5，内网 `192.168.31.51`，用户 `yangyang`
- **外网**：阿里云 VPS `47.109.197.217` + frp 隧道（web → `:18080`，SSH → `:57279`）；旧花生壳通道 `et116374mm892.vicp.fun` 待备案后退役
- **部署方式**：`git pull` + `systemctl restart`（**禁止 pscp 逐文件上传**）
- **分支策略**：
  - `main`：后端 + Web 前端 + 小程序源码主干，生产后端从 main 拉取
  - `apk-test`：多端应用发布分支（mp-weixin / H5 / Android APK 构建产物与版本号统一管理），APK 打包从该分支出包，ReleaseNotes 见 `docs/deployment/apk_test_release/`
  - 多端构建相关改动先在 apk-test 验证，再视情况合并回 main

完整流程（SSH、构建、按改动决定重启哪个服务、数据库与日志、已知坑）见
[`.claude/skills/freeark-prod-deploy/SKILL.md`](.claude/skills/freeark-prod-deploy/SKILL.md)。

### systemd 服务

| 服务 | 用途 | 位置 |
|------|------|------|
| `freeark-backend` | Uvicorn ASGI（Django + Channels，:8000） | `systemctl/` |
| `freeark-mqtt-consumer` | MQTT 消息消费入库 | `systemctl/` |
| `freeark-fault-consumer` | 故障事件写入 | `deployment/systemd/` |
| `freeark-condensation-consumer` | 结露事件消费 | `deployment/systemd/` |
| `freeark-task-scheduler` | 定时调度（跑 `datacollection/run_task_scheduler.py`） | `systemctl/` |
| `freeark-screen-heartbeat` | 屏端心跳消费 | `systemctl/` |
| `freeark-plc-connection-monitor` | PLC 连接监控 | `systemctl/` |
| `freeark-plc-write-timeout` | PLC 写超时清理 | `systemctl/` |
| `freeark-daily-usage` / `freeark-monthly-usage` | 日 / 月用电统计 | `systemctl/` |
| `freeark-dph-cleanup` / `freeark-plc-cleanup` / `freeark-fault-cleanup` / `freeark-condensation-cleanup` | 历史数据定期清理 | `systemctl/` + `deployment/systemd/` |
| `freeark-inspection-agent` | 自治巡检 Agent | `deployment/systemd/` |
| `nginx` | 反向代理 + 前端静态资源 | 系统 |

聊天 AI **没有独立服务/端口** —— v1.7.0 起 LangGraph 在 `freeark-backend` 进程内运行（已退役 OpenClaw）。

---

## 项目约定

1. **禁止 Docker** —— 全项目物理机直接部署。`datacollection/` 下残留的 `Dockerfile` / `docker-compose.yml` 为历史产物，不在生产使用。
2. **迁移手写** —— 禁止 `makemigrations` 全量产物。
3. **分支策略** —— 后端/前端/小程序源码改动走 `main`；多端构建（H5 产物、APK 打包配置、版本号同步、ReleaseNotes）走 `apk-test`，验证后合并回 main。
4. **测试只连 SQLite** —— 任何测试不得连生产库。
5. **鉴权用 `User.role == 'admin'`** —— 不是 Django 的 `is_staff`。
6. **全仓内容核验用 `git grep`** —— ripgrep 遵守 `.gitignore`，会漏扫 `docs/sdlc` 等强制跟踪文件。
7. **`langchain-openai` pin `<0.3`** —— 0.3.x 删了 `_convert_chunk_to_generation_chunk`，生产漂移过。
8. **子代理结论必须亲自复核** —— 尤其测试结论与"只改样式"类改动（diff 用方法名集合对比）。
9. **测试运行必须 `PYTHONDONTWRITEBYTECODE=1`** —— 避免 `.pyc` 写入被沙箱拦截导致测试中断。

---

## 文档索引

| 目录 | 内容 |
|------|------|
| `docs/requirements/` | 各版本需求规格与用户故事（v0.5.0 ~ v1.12.0+，26+ 版本规格） |
| `docs/architecture/` | 架构决策记录（ADR）与模块设计（含 Redis Channel Layer、RAG、多模态等） |
| `docs/development/` `docs/implementation/` | 实现计划与代码评审（按版本归档） |
| `docs/testing/` | 测试计划、报告、`test_inventory.md`（版本级测试报告） |
| `docs/deployment/` `docs/devops/` | 部署计划与报告、CI/CD（`apk_test_release/` ReleaseNotes 真源在 `apk-test` 分支） |
| `docs/specs/` | 功能规格（含 AI 助手 lobster 系列：记忆隔离 / 推理框 / 语音输入、Redis 缓存等） |
| `docs/bugfix/` `docs/troubleshooting/` | Bug 修复与生产排障记录（含 BUG-FM-001 ~ 008、事故 RCA、性能分析） |
| `docs/analysis/` `docs/design/` | 专项分析（PLC 冻结、心跳、热供回水、数据查看器等）与 UI 设计规格 |
| `docs/sdlc/` | SDLC 流程产物 |

同时参考仓库根 [`CLAUDE.md`](CLAUDE.md)（Agent 强制约束）与 `.claude/skills/` 下的运行手册（生产部署、测试运行等）。

---

## 变更日志（快速入口）

- 聚合版变更日志：`CHANGELOG.md`（`apk-test` 分支）
- 多端应用（APK / 小程序 / H5）各版本发布详情 + APK 网盘下载链接 + Word 版 ReleaseNote：
  `docs/deployment/apk_test_release/ReleaseNotes.md`（`apk-test` 分支）
