# 架构设计文档

**项目名称**：FreeArk 业主管理功能  
**版本**：v1.0  
**状态**：DRAFT  
**日期**：2026-04-17

---

## 1. 系统架构概览

本次新增功能完全融入 FreeArk 现有的三层架构，无需引入新的运行时组件：

```
┌─────────────────────────────────────────────────────────┐
│                     客户端层                             │
│   Vue 3 + Element Plus + Vue Router                      │
│   新增：OwnerManagementView.vue                          │
│         路由: /owner-management                          │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP/HTTPS (REST API)
┌────────────────────────▼────────────────────────────────┐
│                     服务层                               │
│   Django 5.x + Django REST Framework                     │
│   Waitress WSGI Server (现有)                            │
│   新增：OwnerInfo Model / Serializer / ViewSet           │
│         URL: /api/owners/                                │
└────────────────────────┬────────────────────────────────┘
                         │ Django ORM
┌────────────────────────▼────────────────────────────────┐
│                     数据层                               │
│   生产: MySQL 192.168.31.98:3306                         │
│   测试: SQLite                                           │
│   新增表: owner_info                                     │
└─────────────────────────────────────────────────────────┘

（独立，不与上述架构交互）
┌─────────────────────────────────────────────────────────┐
│                  datacollector 模块                      │
│   读取 resource/all_owner.json（只读，不变）              │
└─────────────────────────────────────────────────────────┘
```

---

## 2. ADR（架构决策记录）

### ADR-001：是否为 owner_info 新建 Django App

**问题**：新模型是新建独立 App 还是复用现有 `api` App？

**方案对比**：

| 方案 | 优势 | 劣势 |
|------|------|------|
| 方案 A：复用现有 `api` App | 无需更改配置，与现有模型/序列化器/视图组织方式一致，迁移简单 | api App 规模会增大 |
| 方案 B：新建独立 App `owners` | 高内聚，代码隔离 | 需修改 INSTALLED_APPS、urls.py，增加配置风险，与现有代码组织方式不一致 |

**决策**：选择方案 A（复用现有 `api` App）。  
**理由**：项目体量较小，现有所有业务模型均在 `api` App 中（CustomUser、PLCData、UsageQuantity 等），保持一致性可降低配置变更风险。

---

### ADR-002：API 风格 — ModelViewSet vs 独立函数视图

**问题**：owner_info 的 CRUD API 使用 DRF ModelViewSet 还是独立 @api_view 函数视图？

**方案对比**：

| 方案 | 优势 | 劣势 |
|------|------|------|
| 方案 A：ModelViewSet + DefaultRouter | 代码量最少，自动生成 CRUD 端点，分页/过滤内置 | 现有代码混用函数视图与 generics，风格略有差异 |
| 方案 B：独立 @api_view 函数视图 | 与现有 get_usage_quantity 等视图风格完全一致 | 代码量大，需手动实现分页/过滤 |
| 方案 C：generics.ListCreateAPIView + RetrieveUpdateDestroyAPIView | 与现有 UserList/UserDetail 风格一致 | 稍显冗长 |

**决策**：选择方案 C（generics class-based views），与现有 `UserList`、`UserDetail` 模式完全一致。  
**理由**：方案 C 是现有代码库中已有的 CBV 模式，保持一致性最高；同时比纯函数视图更简洁，比 ModelViewSet 侵入性更小。

---

### ADR-003：前端搜索过滤 — 前端过滤 vs 后端过滤

**问题**：业主列表的搜索过滤逻辑放在前端还是后端？

**方案对比**：

| 方案 | 优势 | 劣势 |
|------|------|------|
| 方案 A：前端全量加载后过滤 | 实现简单，无需额外 API 参数 | 634 条记录一次性传输，随数据增长性能下降 |
| 方案 B：后端 Query Param 过滤 | 性能好，可扩展，符合 REST 最佳实践 | 需后端实现过滤逻辑 |

**决策**：选择方案 B（后端过滤）。  
**理由**：634 条数据量虽不大，但后端过滤符合 REST 最佳实践，且数据库表未来可能增长；同时避免前端维护过滤状态的复杂性。

---

## 3. 数据流

### 3.1 业主列表加载
```
OwnerManagementView → GET /api/owners/?building=X&unit=Y&search=Z&page=N
  → OwnerListCreateView → OwnerInfo.objects.filter(...).order_by(...)
  → OwnerInfoSerializer → JSON Response
  → 前端渲染 el-table + el-pagination
```

### 3.2 业主新增
```
管理员点击"新增" → 弹窗表单填写
  → POST /api/owners/ (携带 CSRF + Auth Token)
  → OwnerListCreateView.post → OwnerInfoSerializer.validate + save
  → HTTP 201 / 400 → 前端显示结果，刷新列表
```

### 3.3 业主编辑
```
管理员点击"编辑" → GET /api/owners/<id>/ → 表单预填充
  → PATCH /api/owners/<id>/ → OwnerRetrieveUpdateDestroyView.patch
  → HTTP 200 / 400 → 前端刷新列表
```

### 3.4 业主删除
```
管理员点击"删除" → 确认弹窗
  → DELETE /api/owners/<id>/ → OwnerRetrieveUpdateDestroyView.delete
  → HTTP 204 → 前端刷新列表
```

### 3.5 数据导入（独立流程）
```
运维执行: python manage.py import_all_owners
  → 读取 resource/all_owner.json
  → OwnerInfo.objects.update_or_create(specific_part=key, ...)
  → 输出统计结果
```

---

## 4. 安全设计

| 层 | 机制 |
|----|------|
| 认证 | Token Authentication（现有 DRF Token Auth） |
| 授权 | 自定义权限类 `IsAdminUser`（复用现有） |
| CSRF | Django CSRF middleware（现有） |
| 输入验证 | DRF Serializer 字段校验（max_length、unique） |
| SQL注入 | Django ORM 参数化查询（自动） |

---

## 5. 不变部分（零修改）

- `resource/all_owner.json`：只读，不触碰
- `datacollection/` 目录下所有文件：不修改
- 现有数据库表：不修改任何已有表结构
- 现有 API 端点：不修改任何已有路由和视图逻辑
