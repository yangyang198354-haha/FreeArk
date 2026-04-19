# 测试计划

**项目名称**：FreeArk 业主管理功能  
**版本**：v1.0  
**状态**：DRAFT  
**日期**：2026-04-17

---

## 1. 测试目标

| 目标 | 阈值 |
|------|------|
| 单元测试通过率 | ≥ 80% |
| 集成测试通过率 | ≥ 90% |
| 所有 US-* 有对应测试用例 | 100% |
| CRITICAL Bug 数 | 0 |

---

## 2. 测试范围

**在范围内**：
- OwnerInfo 模型（字段约束、unique 约束、str 方法）
- OwnerInfoSerializer（字段校验、序列化/反序列化）
- OwnerListCreateView API（GET list、POST create、分页、过滤）
- OwnerRetrieveUpdateDestroyView API（GET detail、PATCH update、DELETE）
- import_all_owners management command
- 权限控制（IsAuthenticated / IsAdminUser）

**在范围外**：
- 前端 E2E（需要浏览器环境，本计划不含 Cypress/Playwright）
- 现有功能回归（datacollector、PLC、用量报表等）

---

## 3. 测试环境

- **数据库**：SQLite（Django 测试框架自动创建临时数据库）
- **框架**：Django TestCase + Django REST Framework APIClient
- **测试文件位置**：`FreeArkWeb/backend/freearkweb/api/tests/test_owner.py`
- **运行命令**：`python manage.py test api.tests.test_owner --verbosity=2`

---

## 4. 测试用例清单

### 4.1 模型测试（单元）

| ID | 测试描述 | 预期结果 | 关联 US |
|----|---------|---------|---------|
| TC-M-001 | 创建 OwnerInfo 记录，所有字段正确 | 记录保存，id 自动生成 | US-001 |
| TC-M-002 | specific_part 重复创建 | 抛出 IntegrityError | US-003 |
| TC-M-003 | OwnerInfo.__str__ 返回格式正确 | "1-1-2-201 - 成都乐府（二仙桥）-1-1-201" | US-001 |

### 4.2 序列化器测试（单元）

| ID | 测试描述 | 预期结果 | 关联 US |
|----|---------|---------|---------|
| TC-S-001 | 合法数据通过序列化器验证 | is_valid()=True | US-003 |
| TC-S-002 | specific_part 为空 | is_valid()=False，errors 含 specific_part | US-003 |
| TC-S-003 | specific_part 超出 20 字符 | is_valid()=False | US-003 |
| TC-S-004 | room_number 为空 | is_valid()=False | US-003 |
| TC-S-005 | created_at/updated_at 为只读 | 序列化输出包含，反序列化时忽略外部传入值 | US-001 |

### 4.3 API 集成测试

| ID | 测试描述 | 预期 HTTP 状态 | 关联 US |
|----|---------|--------------|---------|
| TC-A-001 | 未认证用户 GET /api/owners/ | 401 | US-007 |
| TC-A-002 | 普通用户 GET /api/owners/ | 200，返回分页列表 | US-001 |
| TC-A-003 | 管理员 GET /api/owners/ | 200，返回分页列表 | US-001 |
| TC-A-004 | GET /api/owners/?building=1栋 | 200，仅含 1 栋记录 | US-002 |
| TC-A-005 | GET /api/owners/?search=201 | 200，含 room_number/specific_part 含 "201" 的记录 | US-002 |
| TC-A-006 | GET /api/owners/?bind_status=已绑定 | 200，仅含已绑定记录 | US-002 |
| TC-A-007 | 管理员 POST /api/owners/ 合法数据 | 201，返回新记录 | US-003 |
| TC-A-008 | 普通用户 POST /api/owners/ | 403 | US-007 |
| TC-A-009 | 管理员 POST /api/owners/ specific_part 重复 | 400，错误信息含 specific_part | US-003 |
| TC-A-010 | 管理员 POST /api/owners/ 缺少 specific_part | 400 | US-003 |
| TC-A-011 | 管理员 GET /api/owners/{id}/ 存在 | 200，返回完整字段 | US-004 |
| TC-A-012 | GET /api/owners/9999/ 不存在 | 404 | US-004 |
| TC-A-013 | 管理员 PATCH /api/owners/{id}/ 修改 bind_status | 200，字段更新 | US-004 |
| TC-A-014 | 普通用户 PATCH /api/owners/{id}/ | 403 | US-007 |
| TC-A-015 | 管理员 DELETE /api/owners/{id}/ | 204，记录不再存在 | US-005 |
| TC-A-016 | 普通用户 DELETE /api/owners/{id}/ | 403 | US-007 |
| TC-A-017 | GET /api/owners/?page=2&page_size=5（10 条数据） | 200，返回第 6-10 条，total=10 | US-001 |

### 4.4 Management Command 测试

| ID | 测试描述 | 预期结果 | 关联 US |
|----|---------|---------|---------|
| TC-CMD-001 | 首次执行 import_all_owners（mock JSON） | owner_info 表记录数 = JSON 条目数 | US-006 |
| TC-CMD-002 | 重复执行 import_all_owners | 不重复插入，update 已有记录，total 不变 | US-006 |
| TC-CMD-003 | JSON 文件不存在时执行 | 命令以非零退出，stderr 输出友好错误信息 | US-006 |

---

## 5. 覆盖率目标

| 模块 | 目标 | 测试用例 ID |
|------|------|-----------|
| OwnerInfo Model | 100% | TC-M-001~003 |
| OwnerInfoSerializer | 100% | TC-S-001~005 |
| OwnerListCreateView | ≥ 90% | TC-A-001~010, TC-A-017 |
| OwnerRetrieveUpdateDestroyView | ≥ 90% | TC-A-011~016 |
| import_all_owners command | ≥ 80% | TC-CMD-001~003 |
