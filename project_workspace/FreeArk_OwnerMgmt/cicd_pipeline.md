# CI/CD 流水线说明

**项目名称**：FreeArk 业主管理功能  
**版本**：v1.0  
**状态**：DRAFT  
**日期**：2026-04-17

---

## 1. 概述

本项目为物理机部署（树莓派），无 Docker，无自动化 CI 平台（Jenkins/GitHub Actions）。以下为手动部署流水线的规范步骤，运维人员按顺序执行。

---

## 2. 部署前检查

| 检查项 | 命令 | 预期结果 |
|-------|------|---------|
| 确认代码已推送到生产服务器 | `git log --oneline -3` | 最新 commit 包含业主管理功能 |
| 确认测试通过 | `python manage.py test api.tests.test_owner --verbosity=2` | 28 个测试全部 PASS |
| 确认数据库连接 | `python manage.py dbshell` | 能连接到 MySQL 192.168.31.98:3306 |
| 确认 all_owner.json 存在 | `ls resource/all_owner.json` | 文件存在，大小 > 0 |

---

## 3. 后端部署步骤

```bash
# Step 1: 进入项目后端目录
cd /path/to/FreeArk/FreeArkWeb/backend/freearkweb

# Step 2: 执行数据库迁移（建 owner_info 表）
python manage.py migrate
# 回滚方案：python manage.py migrate api 0012_specificpartinfo

# Step 3: 验证迁移成功
python manage.py showmigrations api
# 期望：0013_ownerinfo [X]

# Step 4: 导入业主数据（一次性）
python manage.py import_all_owners
# 期望输出：新建：634（或接近）, 错误：0

# Step 5: 验证数据导入
python manage.py shell -c "from api.models import OwnerInfo; print(OwnerInfo.objects.count())"
# 期望：634

# Step 6: 重启 Waitress 后端服务
sudo systemctl restart freeark-backend
sudo systemctl status freeark-backend
# 期望：active (running)

# Step 7: 部署后 API 验证（需要有效 Token）
curl -H "Authorization: Token <your_admin_token>" http://localhost:8000/api/owners/
# 期望：HTTP 200, {"success": true, "total": 634, ...}
```

---

## 4. 前端部署步骤

```bash
# Step 1: 进入前端目录
cd /path/to/FreeArk/FreeArkWeb/frontend

# Step 2: 安装依赖（若有新增，本次无新增）
# npm install  # 本次无需执行

# Step 3: 构建生产包
npm run build
# 回滚方案：恢复上一次 dist/ 备份

# Step 4: 将 dist/ 内容复制到 Nginx 静态文件目录（或重启前端服务）
# 具体路径依据实际 Nginx 配置
sudo systemctl restart freeark-frontend
sudo systemctl status freeark-frontend
# 期望：active (running)
```

---

## 5. 回滚方案

| 步骤 | 回滚操作 |
|------|---------|
| 数据库迁移 | `python manage.py migrate api 0012_specificpartinfo`（回退到上一版本迁移） |
| 前端构建 | 恢复上一次 dist/ 备份 |
| 后端代码 | `git revert` 或 `git checkout` 到上一个稳定 tag |
| 业主数据 | owner_info 表可直接 `TRUNCATE`（不影响其他表） |

---

## 6. 健康检查（部署后验证）

```bash
# API 健康
curl http://localhost:8000/api/health/
# 期望：{"status": "ok"}

# owners API
curl -H "Authorization: Token <token>" http://localhost:8000/api/owners/?page=1&page_size=5
# 期望：200，total=634（或已导入数量）

# 前端页面
curl -I http://localhost:5173/owner-management
# 期望：200（或重定向到 /login，正常鉴权流程）
```
