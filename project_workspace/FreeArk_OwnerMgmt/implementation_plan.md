# 实现计划

**项目名称**：FreeArk 业主管理功能  
**版本**：v1.0  
**状态**：DRAFT  
**日期**：2026-04-17

---

## 实现步骤顺序

1. `api/models.py` — 追加 OwnerInfo 模型
2. `api/migrations/0013_ownerinfo.py` — 生成迁移文件
3. `api/serializers.py` — 追加 OwnerInfoSerializer
4. `api/views.py` — 追加 OwnerListCreateView + OwnerRetrieveUpdateDestroyView
5. `api/urls.py` — 追加 owners 路由
6. `api/admin.py` — 注册 OwnerInfoAdmin
7. `api/management/commands/import_all_owners.py` — 新建导入命令
8. `frontend/src/views/OwnerManagementView.vue` — 新建前端页面
9. `frontend/src/router/index.js` — 追加路由
10. `frontend/src/components/Layout.vue` — 追加菜单项

## 部署步骤（生产）

```bash
cd FreeArkWeb/backend/freearkweb
python manage.py migrate                      # 建表
python manage.py import_all_owners            # 导入数据（一次性）
# 前端构建
cd ../../../frontend
npm run build
# 重启 Waitress 服务
systemctl restart freearkweb
```
