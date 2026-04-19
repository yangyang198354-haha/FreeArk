# 部署计划

**项目名称**：FreeArk 业主管理功能  
**版本**：v1.0  
**状态**：DRAFT  
**日期**：2026-04-17  
**目标环境**：树莓派（192.168.31.51），生产 MySQL（192.168.31.98:3306）

---

## 1. 部署变更清单

| 变更类型 | 文件/对象 | 说明 |
|---------|---------|------|
| 新增数据库表 | `owner_info` | 通过 migration 0013_ownerinfo 创建 |
| 新增 Python 文件 | `api/models.py`（OwnerInfo 类） | 追加 |
| 新增 Python 文件 | `api/serializers.py`（OwnerInfoSerializer） | 追加 |
| 新增 Python 文件 | `api/views.py`（OwnerListCreateView, OwnerRetrieveUpdateDestroyView） | 追加 |
| 修改 Python 文件 | `api/urls.py` | 新增 2 条路由 |
| 修改 Python 文件 | `api/admin.py` | 注册 OwnerInfoAdmin |
| 新增 Python 文件 | `api/migrations/0013_ownerinfo.py` | 迁移文件 |
| 新增 Python 文件 | `api/management/commands/import_all_owners.py` | 数据导入命令 |
| 新增 Python 文件 | `api/tests/test_owner.py` | 测试文件（不影响生产） |
| 新增 Vue 文件 | `frontend/src/views/OwnerManagementView.vue` | 业主管理页面 |
| 修改 Vue 文件 | `frontend/src/router/index.js` | 新增路由 |
| 修改 Vue 文件 | `frontend/src/components/Layout.vue` | 新增菜单项 |

---

## 2. 影响范围分析

| 已有功能 | 受影响 | 说明 |
|---------|-------|------|
| datacollector 读取 all_owner.json | 否 | 文件未修改，逻辑未触碰 |
| PLC 监控 / 用量报表 / 用户管理 | 否 | 无相关文件修改 |
| 现有 API 端点 | 否 | 仅新增 /api/owners/ 路由 |
| 现有数据库表 | 否 | 仅新增 owner_info 表 |

---

## 3. 部署顺序

```
1. 代码更新（git pull）
2. 后端：python manage.py migrate          ← 建表
3. 后端：python manage.py import_all_owners ← 导入 634 条数据（一次性）
4. 后端：systemctl restart freeark-backend  ← 重启后端
5. 前端：npm run build                      ← 重新构建
6. 前端：systemctl restart freeark-frontend ← 重启前端
7. 健康验证（见 cicd_pipeline.md 第 6 节）
```

---

## 4. 部署时间窗口

- **建议时间**：业务低峰期（凌晨 2:00–4:00）
- **预计停机时间**：约 2–5 分钟（后端重启 + 前端重启）
- **数据导入时间**：634 条记录，预计 < 10 秒

---

## 5. 验证标准（deployment_report）

| 验证项 | 预期 |
|-------|------|
| `python manage.py showmigrations api` | 0013_ownerinfo 显示 [X] |
| `OwnerInfo.objects.count()` | = all_owner.json 条目数（约 634） |
| `GET /api/health/` | {"status": "ok"} |
| `GET /api/owners/?page=1` | 200, total ≥ 1 |
| 前端访问 /owner-management | 页面正常渲染，列表有数据 |

**deployment_report 字段**：`DEPLOYED_SUCCESSFULLY`（所有验证项通过后标注）
