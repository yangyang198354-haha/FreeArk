# 部署计划 — v1.4.0 三恒知识专家 RAG 检索增强

**文档编号**: DEPLOY-PLAN-RAG-v140-001
**版本**: 1.0.0
**状态**: APPROVED（待人类 CONFIRM 执行）
**创建日期**: 2026-06-16
**作者**: sub_agent_devops_engineer (via pm-orchestrator)
**目标环境**: 树莓派 Pi 5 (aarch64)，192.168.31.51，内网 + 花生壳公网

---

## 1. 部署约束（硬性）

| 约束 | 说明 |
|------|------|
| 禁 Docker | 物理机部署，不使用容器 |
| 部署方式 | git pull（plink SSH + git pull + 重启服务），禁止 pscp 逐文件上传 |
| 生产代码路径 | `FreeArkWeb/backend/freearkweb/api/langgraph_chat/`（非 agents/langgraph-poc） |
| DB | 生产 MySQL 192.168.31.98:3306 freeark 数据库 |
| 网络 | 公网出口 wlan0（WiFi，需注意省电模式间歇性断连）；eth0 仅 PLC 子网 |
| OCR 依赖 | aarch64 验证通过前不安装 rapidocr；代码降级运行 |

---

## 2. 部署前置检查清单（阻塞性）

**以下所有检查项必须在生产部署前确认通过，否则不得上线。**

### 2.1 aarch64 OCR 验证（阻塞性）

在树莓派 Pi 5 上执行以下命令，验证通过后方可取消 requirements.txt 注释：

```bash
# SSH 到 Pi（使用生产 SSH 凭据）
# 1. 尝试安装
pip install rapidocr-onnxruntime onnxruntime

# 2. 验证 import
python3 -c "from rapidocr_onnxruntime import RapidOCR; ocr = RapidOCR(); print('OCR import OK')"

# 3. 准备一张含中文的测试图片（如系统截图），保存为 /tmp/test_zh.png
# 4. 验证真实 OCR
python3 -c "
from rapidocr_onnxruntime import RapidOCR
ocr = RapidOCR()
result, _ = ocr('/tmp/test_zh.png')
print('OCR 结果:', result[:3] if result else '（空）')
print('验证通过' if result else '警告：OCR 结果为空')
"
```

**验证通过判断标准**：
- 无 ImportError / ImportWarning
- OCR 结果含可读中文字符（非空）
- 无段错误（segfault）或 onnxruntime 版本不兼容报错

**验证通过后操作**：
1. 取消 requirements.txt 中 `# rapidocr-onnxruntime>=1.3.0` 和 `# onnxruntime>=1.17.0` 的注释
2. 提交并推送
3. 在 Pi 上 `pip install -r requirements.txt` 安装新依赖
4. 重启 freeark-backend 服务

**验证失败处理**：
- 保持 requirements.txt 中 OCR 行注释状态（不安装）
- 代码层 `_HAS_OCR=False` 确保 OCR 跳过，文字内容正常入库
- 在部署报告中记录"OCR 未验证，图片内容无法检索"

### 2.2 Python 依赖可安装性验证（阻塞性）

```bash
# 在 Pi 上验证新增依赖可安装
pip install python-docx PyMuPDF

# 验证 import
python3 -c "
from docx import Document
import fitz
import numpy as np
from langchain_openai import OpenAIEmbeddings
print('python-docx:', Document.__module__)
print('PyMuPDF (fitz):', fitz.__version__)
print('numpy:', np.__version__)
print('langchain-openai: OK')
print('所有依赖验证通过')
"
```

### 2.3 embedding API 可达性验证（阻塞性）

在 Pi 上验证 wlan0 出口可达硅基流动 API：

```bash
# 测试基本网络连通性
curl -s --connect-timeout 5 https://api.siliconflow.cn/v1/models -H "Authorization: Bearer ${RAG_EMBEDDING_API_KEY}" | python3 -c "import sys,json; d=json.load(sys.stdin); print('API 可达, 模型数:', len(d.get('data',[])) )"

# 或用 Python 测试（需要 .env 中已配置 RAG_EMBEDDING_API_KEY）
python3 -c "
import os
from langchain_openai import OpenAIEmbeddings
emb = OpenAIEmbeddings(
    base_url=os.environ.get('RAG_EMBEDDING_BASE_URL', 'https://api.siliconflow.cn/v1'),
    model=os.environ.get('RAG_EMBEDDING_MODEL', 'BAAI/bge-m3'),
    api_key=os.environ.get('RAG_EMBEDDING_API_KEY', ''),
    timeout=10.0,
)
vec = emb.embed_query('测试')
print(f'embedding 成功，维度: {len(vec)}')
assert len(vec) == 1024, f'预期 1024 维，实际 {len(vec)} 维'
print('embedding API 验证通过')
"
```

**注意 WiFi 省电模式**：若测试失败，先执行：
```bash
sudo iwconfig wlan0 power off  # 关闭 WiFi 省电
# 再重试 API 测试
```

### 2.4 Migration 安全检查

```bash
# 在 Pi 上检查 migration 状态（确认 0035 已 applied，0036 尚未 applied）
cd /home/pi/freeark-prod/FreeArkWeb/backend/freearkweb
python manage.py showmigrations api | tail -5

# 预期输出中应有：
# [X] 0035_workorder_proposed_write
# [ ] 0036_add_rag_tables   ← 待应用
```

### 2.5 .env 配置检查

确认生产 .env 文件（`/home/pi/freeark-prod/FreeArkWeb/backend/freearkweb/.env` 或等价路径）已添加：

```ini
# RAG 知识库（v1.4.0_sanheng_rag）
RAG_EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
RAG_EMBEDDING_MODEL=BAAI/bge-m3
RAG_EMBEDDING_API_KEY=sk-xxxx  # 实际密钥，不入 git
RAG_TOP_K=5
RAG_SCORE_THRESHOLD=0.3
RAG_CHUNK_SIZE=500
RAG_CHUNK_OVERLAP=50
```

验证变量已加载：
```bash
python manage.py shell -c "from django.conf import settings; print('BASE_URL:', settings.RAG_EMBEDDING_BASE_URL[:20]+'...'); print('MODEL:', settings.RAG_EMBEDDING_MODEL); print('KEY:', 'SET' if settings.RAG_EMBEDDING_API_KEY else 'EMPTY')"
```

---

## 3. 部署步骤（生产执行序列）

**执行方式**：通过 plink SSH 远程执行，不使用 pscp 传文件。

### Step 1：推送代码（本地开发机执行）

```bash
# 确认在 main 分支
git status
git add FreeArkWeb/backend/freearkweb/api/models_rag.py
git add FreeArkWeb/backend/freearkweb/api/migrations/0036_add_rag_tables.py
git add FreeArkWeb/backend/freearkweb/api/serializers_rag.py
git add FreeArkWeb/backend/freearkweb/api/views_rag.py
git add FreeArkWeb/backend/freearkweb/api/rag_service.py
git add FreeArkWeb/backend/freearkweb/api/urls.py
git add FreeArkWeb/backend/freearkweb/api/langgraph_chat/fa_tools.py
git add FreeArkWeb/backend/freearkweb/freearkweb/settings.py
git add FreeArkWeb/backend/requirements.txt
git add FreeArkWeb/backend/freearkweb/api/models.py
git add agents/sanheng-knowledge/SYSTEM_PROMPT.langgraph.md
git add FreeArkWeb/frontend/src/views/KnowledgeBaseView.vue
git add FreeArkWeb/frontend/src/router/index.js
git add FreeArkWeb/frontend/src/components/Layout.vue
git add FreeArkWeb/backend/freearkweb/api/tests_rag.py
git commit -m "feat(rag): v1.4.0 三恒知识专家 RAG 检索增强"
git push origin main
```

### Step 2：Pi 上拉取代码

```bash
# 通过 plink 执行（替换 PI_HOST/PI_USER/PI_KEY 为实际值）
plink -ssh PI_USER@PI_HOST -i PI_KEY "cd /home/pi/freeark-prod && git pull origin main"
```

或直接 SSH：
```bash
ssh pi@192.168.31.51
cd /home/pi/freeark-prod
git pull origin main
```

### Step 3：安装新 Python 依赖

```bash
# 在 Pi 上执行
cd /home/pi/freeark-prod/FreeArkWeb/backend
pip install -r requirements.txt

# 若 OCR 已验证通过，此步骤会安装 rapidocr-onnxruntime + onnxruntime
# 若未验证，OCR 行注释，不安装（代码降级运行）
```

### Step 4：执行 Migration（新增 RAG 两表）

```bash
cd /home/pi/freeark-prod/FreeArkWeb/backend/freearkweb
python manage.py migrate api 0036_add_rag_tables

# 验证 migration 已应用
python manage.py showmigrations api | grep 0036
# 预期：[X] 0036_add_rag_tables
```

**回滚命令**（如 migration 失败）：
```bash
python manage.py migrate api 0035_workorder_proposed_write
# 将回滚到 0035，删除 rag_document 和 rag_chunk 表
```

### Step 5：构建前端

```bash
# 在 Pi 上执行（或在开发机构建后推送 dist/）
cd /home/pi/freeark-prod/FreeArkWeb/frontend
npm install
npm run build
# 若使用 Nginx 服务前端静态文件，确认 dist/ 已更新
```

### Step 6：重启后端服务

```bash
# 重启 freeark-backend（Django/uvicorn）
sudo systemctl restart freeark-backend
sudo systemctl status freeark-backend

# 确认服务正常（无报错）
sudo journalctl -u freeark-backend -n 30 --no-pager
```

### Step 7：部署后验证（Smoke Test）

```bash
# 7.1 检查 migration 状态
python manage.py showmigrations api | grep 0036

# 7.2 检查 RAG 路由注册
python manage.py shell -c "
from django.test import RequestFactory
from django.urls import reverse
print('RAG list URL:', reverse('rag-document-list'))
print('路由注册成功')
"

# 7.3 API 端点检查（需有效 admin Token）
# 替换 TOKEN 为实际管理员 Token
curl -s -H "Authorization: Token TOKEN" http://192.168.31.51/api/rag/documents/ | python3 -m json.tool

# 7.4 检查向量缓存加载（日志）
sudo journalctl -u freeark-backend -n 50 | grep "rag_service"

# 7.5 后端测试（SQLite，不影响生产 DB）
cd /home/pi/freeark-prod/FreeArkWeb/backend/freearkweb
FREEARK_POC_MOCK=1 python manage.py test api.tests_rag --verbosity=1
```

---

## 4. 回滚方案

### 4.1 完整回滚步骤

```bash
# Step A: 回滚 migration（删除 RAG 两表）
cd /home/pi/freeark-prod/FreeArkWeb/backend/freearkweb
python manage.py migrate api 0035_workorder_proposed_write

# Step B: 回滚代码（回到上一个 commit）
cd /home/pi/freeark-prod
git log --oneline -5  # 找到 v1.4.0 前的 commit hash
git revert HEAD       # 或 git reset --hard PREV_HASH（谨慎）
git push origin main

# Step C: 重启服务
sudo systemctl restart freeark-backend
sudo systemctl status freeark-backend

# Step D: 验证聊天功能正常（SANHENG_TOOLS 回到空列表）
```

### 4.2 部分回滚（保留 migration，仅回滚 SANHENG_TOOLS）

若需要紧急关闭 RAG 工具但保留 DB 表：
```bash
# 临时禁用：在 fa_tools.py 将 SANHENG_TOOLS 改回空列表
# 重启服务即可（无需回滚 migration）
```

---

## 5. 部署后手工验收清单（PHASE_09 条件项）

**部署完成后，由人类执行以下手工验收**：

| 验收项 | 步骤 | 预期结果 |
|-------|------|---------|
| AC-1.3 前端拦截非法文件类型 | 浏览器登录管理员账号，进入知识库管理页，选择 .xlsx 文件 | el-message 弹出"仅支持 .docx 和 .pdf 文件"，未调用接口 |
| AC-1.4 前端拦截超大文件 | 选择超过 50MB 的文件 | el-message 弹出"文件不能超过 50MB" |
| AC-1.7 入库成功后状态变 indexed | 上传一份小 PDF，等待 180 秒 | 列表中该文档状态变绿色"已入库"，chunk_count > 0 |
| AC-2.3 失败原因可见可重试 | （需 embedding API key 无效时测试）或手动触发 | 状态红色"失败"，"查看原因"按钮可见，"重试"按钮可见 |
| 知识库导航 admin only | 用普通用户登录 | 侧边栏"方舟智能体"下无"三恒知识库管理"选项 |
| 知识库导航 admin 可见 | 用管理员登录 | 侧边栏可见"三恒知识库管理"，点击跳转到正确页面 |
| 路由守卫 | 普通用户直接访问 /admin/knowledge-base | 重定向到 /home |
| 聊天降级 | 未配置 RAG_EMBEDDING_API_KEY 时向三恒专家提问 | 回复含"目前未接入知识资料库"，无报错弹窗 |

---

## 6. 服务影响分析

| 服务 | 影响 | 重启需要 |
|------|------|---------|
| freeark-backend | 新增 RAG API，需重启加载新代码 | 是 |
| freeark-fault-consumer | 无影响 | 否 |
| 其他 systemd 服务 | 无影响 | 否 |
| 前端 Nginx | 新增 KnowledgeBaseView.vue 路由，需重新构建 | 是（前端构建） |

---

## 7. 生产部署状态

**当前状态**: 等待人类 CONFIRM

本部署计划已通过门控评审，所有步骤均有回滚方案，部署后验证覆盖所有 AC。

**生产部署需人类明确授权（PRODUCTION_DEPLOY_CONFIRM=true）后方可执行。**
