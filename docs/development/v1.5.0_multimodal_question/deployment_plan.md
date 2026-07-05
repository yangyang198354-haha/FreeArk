<!--
file_header:
  project: FreeArk v1.5.0_multimodal_question
  document_type: deployment_plan
  status: READY
  created_at: 2026-06-24
  version: 1.0.0
  references:
    - .claude/skills/freeark-prod-deploy/SKILL.md（生产部署手册）
    - code_review_report.md / integration_test_report.md / unit_test_report.md
-->

# 生产部署计划 — FreeArk v1.5.0 多模态提问

## 0. 前置事实核对（部署当日实测，勿信快照）

| 项 | 期望 | 核对方式 |
|----|------|---------|
| 生产工作树干净（无会被 `git pull` 覆盖的非 `.env`/`package-lock`/`heartbeat` 改动）| 仅既有三项本地修改 | `git -C /home/yangyang/Freeark/FreeArk status --short` |
| `openai` SDK 已在 venv | 已装（经 langchain-openai 传递依赖）| `venv/bin/python -c "import openai; print(openai.__version__)"` |
| 生产 `.env` 已有 `DOUBAO_API_KEY` | 存在（RAG embedding 在用）| `grep -c '^DOUBAO_API_KEY=' FreeArkWeb/backend/.env` |

> 任一不符 → 暂停，先消解差异。

## 1. 变更范围

- **代码**：`main` 经 PR #55 合入（feat/multimodal-question-v1.5.0）
- **数据库**：无 migration
- **Python 依赖**：无新增（`from openai import AsyncOpenAI` 惰性导入，openai SDK 已随 langchain-openai 安装）
- **前端**：`ChatView.vue` / `api.js` 改动 → 需重建 `dist/`
- **服务影响**：`consumers.py` / `adapter.py` / `orchestrator.py` / `settings.py` / `urls.py` → 重启 `freeark-backend`

## 2. 部署步骤

### 2.1 拉取代码
```bash
cd /home/yangyang/Freeark/FreeArk
git status --short                 # 确认仅 .env/package-lock/heartbeat 本地改动
git pull origin main               # 应 fast-forward 到含 PR #55 的 HEAD
git log -1 --oneline               # 确认 HEAD
# 验证关键文件落地
ls FreeArkWeb/backend/freearkweb/api/vision_service.py FreeArkWeb/backend/freearkweb/api/views_chat_image.py
```

### 2.2 配置 `.env`（关键，否则 VLM 调用必失败）
在 `FreeArkWeb/backend/.env` 追加（`DOUBAO_API_KEY` 已存在，复用，不重复）：
```
DOUBAO_VISION_MODEL=doubao-vision-lite-32k
DOUBAO_VISION_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
# 以下可选，留空则用代码默认值（30s / 1 / 600s / 50MB）
DOUBAO_VISION_TIMEOUT=30
DOUBAO_VISION_MAX_RETRIES=1
VISION_UPLOAD_TTL=600
VISION_UPLOAD_MAX_TOTAL_MB=50
```
> 注：`DOUBAO_VISION_BASE_URL` 即火山方舟多模态端点，与 RAG embedding 同域。若 `.env` 已有同名行，先确认值后再决定是否覆盖。

### 2.3 依赖（按需）
```bash
venv/bin/python -c "import openai; print('openai', openai.__version__)"   # 应成功打印
# 若意外缺失才执行：venv/bin/pip install -r FreeArkWeb/backend/requirements.txt
```

### 2.4 重启后端
```bash
sudo systemctl restart freeark-backend
systemctl status freeark-backend --no-pager | grep -E "Active|uvicorn"
sudo journalctl -u freeark-backend -n 30 --no-pager   # 无 ImportError / 启动堆栈
```
> `.env` 同时被 worker 服务加载，但本次新增变量只有 backend/adapter 读取，**仅重启 backend 即可**（worker 不触碰 vision 路径）。

### 2.5 重建前端
```bash
cd /home/yangyang/Freeark/FreeArk/FreeArkWeb/frontend
cp -r dist /home/yangyang/FreeArk_backup/dist_backup_$(date +%Y%m%d%H%M%S)
npm run build        # 依赖无变化，无需 npm install
```

## 3. Smoke 验证
1. 浏览器进聊天页，选一张设备铭牌/参数图，问"请帮我分析这张图片"
2. 期望：先出 `vision_progress`（识别中），随后正常流式答复，内容引用图中文字/参数
3. 后端日志确认：`journalctl -u freeark-backend` 有 vision 调用记录，**且日志中无 base64/图片字节**
4. 健康检查：`curl -s http://127.0.0.1:8080/api/health/` → `{"status":"ok",...}`
5. 回归：发一条**纯文字**问题，确认原链路不受影响

## 4. 回滚

| 触发 | 操作 |
|------|------|
| 后端起不来 / VLM 链路异常 | `git -C /home/yangyang/Freeark/FreeArk reset --hard <部署前HEAD>` → `sudo systemctl restart freeark-backend`；前端 `cp -r <备份dist> dist` |
| 仅 VLM 失败（主链路正常）| 设计已降级：VLM 失败回纯文字重试提示，用户可不带图重发；可暂不回滚，排查 doubao 端点/密钥 |
| `.env` 配错 | 修正 `DOUBAO_VISION_*` 行 → 重启 backend |

> 回滚无需动 DB（无 migration），无需动依赖（无新增）。

## 5. 已知遗留（非阻断，见 code_review_report.md）
- FND-005：`AsyncOpenAI` 每次调用重建连接（QPS<2 可接受，v1.6 改单例）
- FND-001/003/004/006/009：MINOR（alert 提示、HEIC 常量、utcnow 弃用警告等），不影响功能
