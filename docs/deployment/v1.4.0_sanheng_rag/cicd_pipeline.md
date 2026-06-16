# CI/CD 流水线 — v1.4.0 三恒知识专家 RAG 检索增强

**文档编号**: CICD-RAG-v140-001
**版本**: 1.0.0
**状态**: APPROVED
**创建日期**: 2026-06-16
**作者**: sub_agent_devops_engineer (via pm-orchestrator)

---

## 1. FreeArk 当前 CI/CD 模式

FreeArk 当前采用**手动 + git pull 模式**（无 GitHub Actions/Jenkins）：

1. 开发者本地完成开发和本地测试
2. git push 到 main
3. 通过 plink SSH 远程 git pull 到 Pi 生产机
4. 手动执行 migrate、pip install、重启服务

本文档定义 v1.4.0 发布的手动 CI/CD 检查流程。

---

## 2. 发布前本地 CI 检查流程

**在开发机执行（Windows PowerShell）**：

```powershell
# 进入工作目录
cd C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend\freearkweb

# 步骤 1: 运行 RAG 专项测试（必须全通过）
$env:FREEARK_POC_MOCK="1"
python manage.py test api.tests_rag --verbosity=2
# 预期：Ran N tests in X.XXXs  OK

# 步骤 2: 运行完整测试集（回归检查）
python manage.py test api --verbosity=1
# 预期：OK（含 skipTest 不计失败）

# 步骤 3: migration 检查（确认无冲突）
python manage.py migrate --run-syncdb --check
# 预期：无报错

# 步骤 4: migration showmigrations（确认 0036 在列表）
python manage.py showmigrations api | Select-String "0036"
# 预期：[ ] 0036_add_rag_tables
```

---

## 3. 发布检查清单（git push 前）

```
[ ] 所有新增文件已 git add
[ ] 测试通过（api.tests_rag ALL PASS）
[ ] requirements.txt 中 OCR 行保持注释（aarch64 未验证前）
[ ] .env 文件不在 git 追踪范围（.gitignore 确认）
[ ] RAG_EMBEDDING_API_KEY 未出现在任何代码文件中
[ ] commit message 格式：feat(rag): v1.4.0 三恒知识专家 RAG 检索增强
[ ] SYSTEM_PROMPT.langgraph.md 已包含 RAG 工具使用约定
[ ] migration 0036 依赖 0035（Migration.dependencies 已设置）
```

---

## 4. 生产部署流水线（plink 手动执行）

### 4.1 SSH 连接配置

```powershell
# 内网直连
$PI_HOST = "192.168.31.51"
$PI_USER = "pi"
$PROD_DIR = "/home/pi/freeark-prod"

# 若公司 DNS 不解析 vicp.fun，先解析 IP
# nslookup et116374mm892.vicp.fun 8.8.8.8

# plink 连接测试
plink -ssh ${PI_USER}@${PI_HOST} "echo 'SSH 连接正常'"
```

### 4.2 一键部署脚本（PowerShell，生产执行）

```powershell
# deploy_v1.4.0_rag.ps1
$PI_HOST = "192.168.31.51"
$PI_USER = "pi"
$PROD_DIR = "/home/pi/freeark-prod"
$BACKEND_DIR = "$PROD_DIR/FreeArkWeb/backend"
$DJANGO_DIR = "$BACKEND_DIR/freearkweb"
$FRONTEND_DIR = "$PROD_DIR/FreeArkWeb/frontend"

Write-Host "=== v1.4.0 RAG 部署开始 ===" -ForegroundColor Cyan

# Step 1: 拉取代码
Write-Host "[1/6] git pull..." -ForegroundColor Yellow
plink -ssh ${PI_USER}@${PI_HOST} "cd $PROD_DIR && git pull origin main"
if ($LASTEXITCODE -ne 0) { Write-Host "git pull 失败" -ForegroundColor Red; exit 1 }

# Step 2: 安装依赖
Write-Host "[2/6] pip install..." -ForegroundColor Yellow
plink -ssh ${PI_USER}@${PI_HOST} "cd $BACKEND_DIR && pip install -r requirements.txt"
if ($LASTEXITCODE -ne 0) { Write-Host "pip install 失败" -ForegroundColor Red; exit 1 }

# Step 3: 执行 Migration
Write-Host "[3/6] migrate 0036..." -ForegroundColor Yellow
plink -ssh ${PI_USER}@${PI_HOST} "cd $DJANGO_DIR && python manage.py migrate api 0036_add_rag_tables"
if ($LASTEXITCODE -ne 0) { Write-Host "migration 失败" -ForegroundColor Red; exit 1 }

# Step 4: 构建前端
Write-Host "[4/6] 前端构建..." -ForegroundColor Yellow
plink -ssh ${PI_USER}@${PI_HOST} "cd $FRONTEND_DIR && npm install && npm run build"
if ($LASTEXITCODE -ne 0) { Write-Host "前端构建失败" -ForegroundColor Red; exit 1 }

# Step 5: 重启后端服务
Write-Host "[5/6] 重启 freeark-backend..." -ForegroundColor Yellow
plink -ssh ${PI_USER}@${PI_HOST} "sudo systemctl restart freeark-backend"
Start-Sleep -Seconds 5
plink -ssh ${PI_USER}@${PI_HOST} "sudo systemctl is-active freeark-backend"

# Step 6: Smoke Test
Write-Host "[6/6] Smoke Test..." -ForegroundColor Yellow
plink -ssh ${PI_USER}@${PI_HOST} "cd $DJANGO_DIR && FREEARK_POC_MOCK=1 python manage.py test api.tests_rag --verbosity=1 2>&1 | tail -5"

Write-Host "=== v1.4.0 RAG 部署完成 ===" -ForegroundColor Green
Write-Host "请执行 deployment_plan.md §5 手工验收清单" -ForegroundColor Cyan
```

---

## 5. 回滚流水线

```powershell
# rollback_v1.4.0_rag.ps1
$PI_HOST = "192.168.31.51"
$PI_USER = "pi"
$PROD_DIR = "/home/pi/freeark-prod"
$DJANGO_DIR = "$PROD_DIR/FreeArkWeb/backend/freearkweb"

Write-Host "=== v1.4.0 RAG 回滚 ===" -ForegroundColor Yellow

# Step 1: 回滚 migration
plink -ssh ${PI_USER}@${PI_HOST} "cd $DJANGO_DIR && python manage.py migrate api 0035_workorder_proposed_write"

# Step 2: 回滚代码（revert commit）
$COMMIT_MSG = "revert: 回滚 v1.4.0 三恒知识专家 RAG 检索增强"
plink -ssh ${PI_USER}@${PI_HOST} "cd $PROD_DIR && git revert HEAD --no-edit -m '$COMMIT_MSG' && git push origin main"

# Step 3: 重新安装（去除 RAG 依赖）
plink -ssh ${PI_USER}@${PI_HOST} "cd $PROD_DIR/FreeArkWeb/backend && pip install -r requirements.txt"

# Step 4: 重启
plink -ssh ${PI_USER}@${PI_HOST} "sudo systemctl restart freeark-backend"

Write-Host "=== 回滚完成 ===" -ForegroundColor Green
```

---

## 6. 监控与告警

### 6.1 部署后监控点

```bash
# 后端日志（RAG 入库任务）
sudo journalctl -u freeark-backend -f | grep rag_service

# 向量缓存加载日志
sudo journalctl -u freeark-backend -n 100 | grep "向量缓存加载"

# RAG 入库失败告警（生产中监控此模式）
sudo journalctl -u freeark-backend | grep "rag_service.*入库失败"
```

### 6.2 关键日志模式

| 日志模式 | 含义 | 处理 |
|---------|------|------|
| `rag_service: 向量缓存加载完成，共 N 条` | 启动时缓存加载成功 | 正常 |
| `rag_service: 文档 N 入库成功` | 文档成功入库 | 正常 |
| `rag_service: 文档 N 入库失败` | 入库异常 | 检查 DB / embedding API |
| `rag_service: search_rag 失败（降级）` | RAG 降级（聊天不受影响） | 检查 embedding API 可达性 |
| `rapidocr-onnxruntime 未安装` | OCR 未启用 | 正常（等待 aarch64 验证） |

### 6.3 WiFi 省电影响的 embedding API 可达性

由于 Pi 生产公网出口通过 wlan0（已知 WiFi 省电间歇性问题），embedding API 调用可能间歇失败：

```bash
# 检查 WiFi 省电状态
iwconfig wlan0 | grep Power

# 若为 on（省电开启），关闭
sudo iwconfig wlan0 power off

# 永久关闭（写入 /etc/rc.local 或 systemd 服务）
echo "sudo iwconfig wlan0 power off" | sudo tee -a /etc/rc.local
```

fail-open 设计确保 embedding 不可达时聊天不报错（专家返回降级提示），不阻断业务。
