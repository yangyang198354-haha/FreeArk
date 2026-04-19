# 模块设计文档

**项目名称**：FreeArk 业主管理功能  
**版本**：v1.0  
**状态**：DRAFT  
**日期**：2026-04-17

---

## 1. 后端模块

### 模块 MOD-BE-001：OwnerInfo 数据模型

**文件**：`FreeArkWeb/backend/freearkweb/api/models.py`（追加）  
**覆盖需求**：REQ-FUNC-001  

```python
class OwnerInfo(models.Model):
    specific_part: CharField(max_length=20, unique=True, db_index=True)  # "1-1-2-201"
    location_name: CharField(max_length=100)                              # 专有部分坐落
    building: CharField(max_length=10, db_index=True)                    # 楼栋
    unit: CharField(max_length=10, db_index=True)                        # 单元
    floor: CharField(max_length=10)                                       # 楼层
    room_number: CharField(max_length=10)                                 # 户号
    bind_status: CharField(max_length=20, db_index=True)                 # 绑定状态
    ip_address: CharField(max_length=50, blank=True)                     # IP地址
    unique_id: CharField(max_length=50, blank=True, db_index=True)       # 唯一标识符
    plc_ip_address: CharField(max_length=50, blank=True)                 # PLC IP地址
    created_at: DateTimeField(auto_now_add=True)
    updated_at: DateTimeField(auto_now=True)
    
    Meta:
        db_table = 'owner_info'
        indexes: [building, unit, bind_status, (building, unit), (building, unit, bind_status)]
```

**接口（对外提供给序列化器/视图）**：
- `OwnerInfo.objects.filter(building=, unit=, bind_status=)`
- `OwnerInfo.objects.filter(Q(specific_part__icontains=) | Q(room_number__icontains=) | Q(location_name__icontains=))`
- `OwnerInfo.objects.get(pk=id)`
- `OwnerInfo.objects.update_or_create(specific_part=key, defaults={...})`

---

### 模块 MOD-BE-002：OwnerInfo 序列化器

**文件**：`FreeArkWeb/backend/freearkweb/api/serializers.py`（追加）  
**覆盖需求**：REQ-FUNC-003, REQ-FUNC-004, REQ-FUNC-005, REQ-FUNC-006  

```python
class OwnerInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = OwnerInfo
        fields = ['id', 'specific_part', 'location_name', 'building', 'unit',
                  'floor', 'room_number', 'bind_status', 'ip_address',
                  'unique_id', 'plc_ip_address', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    # validate_specific_part: 在 create 时检查唯一性（ModelSerializer 默认已处理 unique）
    # validate: 无跨字段业务规则，使用默认验证
```

**接口类型**（所有字段均有明确 Python 类型）：
- `id`: `int`
- `specific_part`: `str` (max 20, unique)
- `location_name`: `str` (max 100)
- `building`: `str` (max 10)
- `unit`: `str` (max 10)
- `floor`: `str` (max 10)
- `room_number`: `str` (max 10)
- `bind_status`: `str` (max 20)
- `ip_address`: `str` (max 50, optional)
- `unique_id`: `str` (max 50, optional)
- `plc_ip_address`: `str` (max 50, optional)
- `created_at`: `datetime` (ISO 8601, read-only)
- `updated_at`: `datetime` (ISO 8601, read-only)

---

### 模块 MOD-BE-003：业主 API 视图

**文件**：`FreeArkWeb/backend/freearkweb/api/views.py`（追加）  
**覆盖需求**：REQ-FUNC-003, REQ-FUNC-004, REQ-FUNC-005, REQ-FUNC-006, REQ-FUNC-007  

```
OwnerListCreateView (generics.ListCreateAPIView):
    permission_classes:
        - GET: IsAuthenticated
        - POST: IsAdminUser
    queryset: OwnerInfo.objects.all().order_by('building', 'unit', 'room_number')
    serializer_class: OwnerInfoSerializer
    pagination_class: PageNumberPagination (page_size=20)
    
    过滤逻辑（get_queryset）:
        - ?building=X  → filter(building=X)
        - ?unit=Y      → filter(unit=Y)
        - ?bind_status=Z → filter(bind_status=Z)
        - ?search=W    → filter(Q(specific_part__icontains=W) |
                                Q(location_name__icontains=W) |
                                Q(room_number__icontains=W))
    
    权限覆盖（get_permissions）:
        - GET → [IsAuthenticated]
        - POST → [IsAdminUser]

OwnerRetrieveUpdateDestroyView (generics.RetrieveUpdateDestroyAPIView):
    permission_classes:
        - GET: IsAuthenticated
        - PUT/PATCH/DELETE: IsAdminUser
    queryset: OwnerInfo.objects.all()
    serializer_class: OwnerInfoSerializer
    
    权限覆盖（get_permissions）:
        - GET → [IsAuthenticated]
        - PUT/PATCH/DELETE → [IsAdminUser]
```

**URL 接口**：

| 方法 | URL | 权限 | 返回 |
|------|-----|------|------|
| GET | /api/owners/ | IsAuthenticated | 200 分页列表 |
| POST | /api/owners/ | IsAdminUser | 201 新记录 / 400 校验失败 |
| GET | /api/owners/{id}/ | IsAuthenticated | 200 详情 / 404 |
| PUT | /api/owners/{id}/ | IsAdminUser | 200 / 400 / 404 |
| PATCH | /api/owners/{id}/ | IsAdminUser | 200 / 400 / 404 |
| DELETE | /api/owners/{id}/ | IsAdminUser | 204 / 404 |

---

### 模块 MOD-BE-004：URL 路由配置

**文件**：`FreeArkWeb/backend/freearkweb/api/urls.py`（追加两条）  
**覆盖需求**：REQ-FUNC-003 至 REQ-FUNC-007  

```python
path('owners/', views.OwnerListCreateView.as_view(), name='owner-list-create'),
path('owners/<int:pk>/', views.OwnerRetrieveUpdateDestroyView.as_view(), name='owner-detail'),
```

---

### 模块 MOD-BE-005：数据库迁移

**文件**：`api/migrations/0013_ownerinfo.py`（新建）  
**覆盖需求**：REQ-FUNC-001  
**内容**：CreateModel OwnerInfo，含所有字段定义及索引

---

### 模块 MOD-BE-006：import_all_owners Management Command

**文件**：`FreeArkWeb/backend/freearkweb/api/management/commands/import_all_owners.py`（新建）  
**覆盖需求**：REQ-FUNC-002  

```
Command.handle():
    1. 定位 all_owner.json（向上 6 级到 FreeArk 根目录，再 resource/all_owner.json）
    2. json.load()
    3. 遍历每条记录:
       OwnerInfo.objects.update_or_create(
           specific_part=key,
           defaults={
               'location_name': val['专有部分坐落'],
               'building': val['楼栋'],
               'unit': val['单元'],
               'floor': val['楼层'],
               'room_number': str(val['户号']),
               'bind_status': val['绑定状态'],
               'ip_address': val.get('IP地址', ''),
               'unique_id': val.get('唯一标识符', ''),
               'plc_ip_address': val.get('PLC IP地址', ''),
           }
       )
    4. 输出 created/updated/total 计数
    5. 异常处理：FileNotFoundError、JSONDecodeError、Exception
```

---

### 模块 MOD-BE-007：Admin 注册

**文件**：`FreeArkWeb/backend/freearkweb/api/admin.py`（追加）  
**覆盖需求**：REQ-FUNC-001（Django Admin 可管理）  

```python
@admin.register(OwnerInfo)
class OwnerInfoAdmin(admin.ModelAdmin):
    list_display = ['specific_part', 'location_name', 'building', 'unit', 'floor', 'room_number', 'bind_status']
    search_fields = ['specific_part', 'location_name', 'room_number']
    list_filter = ['building', 'unit', 'bind_status']
```

---

## 2. 前端模块

### 模块 MOD-FE-001：OwnerManagementView.vue

**文件**：`FreeArkWeb/frontend/src/views/OwnerManagementView.vue`（新建）  
**覆盖需求**：REQ-FUNC-008  

**组件结构**：
```
OwnerManagementView
├── 页面头部 (.page-header)  ← 与 UserListView 一致
├── 搜索过滤栏
│   ├── el-select: 楼栋
│   ├── el-select: 单元（联动楼栋）
│   ├── el-select: 绑定状态
│   ├── el-input: 关键词搜索
│   └── el-button: 搜索 / 重置
├── 操作栏
│   └── el-button "新增业主"（仅管理员显示）
├── 数据表格
│   └── el-table + el-table-column（含操作列：编辑/删除按钮）
├── 分页
│   └── el-pagination
└── 表单弹窗（新增/编辑共用 el-dialog）
    └── el-form + el-form-item（所有字段）
```

**数据状态**：
```javascript
data() {
    ownerList: [],        // 当前页业主数组
    total: 0,             // 总记录数
    currentPage: 1,
    pageSize: 20,
    loading: false,
    searchForm: { building: '', unit: '', bind_status: '', search: '' },
    dialogVisible: false,
    dialogMode: 'create' | 'edit',
    ownerForm: { specific_part, location_name, building, unit, floor, room_number, bind_status, ip_address, unique_id, plc_ip_address },
    editingId: null,
    userRole: ''          // 从 localStorage 读取，控制按钮显示
}
```

**方法**：
- `loadOwners()` — GET /api/owners/?page=N&building=X&...
- `handleSearch()` — 重置 currentPage=1，调用 loadOwners
- `handleReset()` — 清空 searchForm，调用 loadOwners
- `openCreateDialog()` — 清空 ownerForm，dialogMode='create'，dialogVisible=true
- `openEditDialog(row)` — GET /api/owners/{row.id}/，填充 ownerForm，dialogMode='edit'，dialogVisible=true
- `submitForm()` — 根据 dialogMode 调用 POST 或 PATCH
- `deleteOwner(id)` — ElMessageBox.confirm + DELETE /api/owners/{id}/
- `handlePageChange(page)` — 更新 currentPage，调用 loadOwners

---

### 模块 MOD-FE-002：路由注册

**文件**：`FreeArkWeb/frontend/src/router/index.js`（追加一条路由）  
**覆盖需求**：REQ-FUNC-008  

```javascript
{
    path: '/owner-management',
    name: 'OwnerManagement',
    component: () => import('../views/OwnerManagementView.vue'),
    meta: { requiresAuth: true }
}
```

---

### 模块 MOD-FE-003：左侧菜单新增入口

**文件**：`FreeArkWeb/frontend/src/components/Layout.vue`（追加菜单项）  
**覆盖需求**：REQ-FUNC-008  

在"用户管理"子菜单（`el-sub-menu index="user"`，v-if="userRole === 'admin'"）内追加：
```html
<el-menu-item index="/owner-management">
  <el-icon><House /></el-icon>
  业主管理
</el-menu-item>
```
同时在 import 中引入 `House` 图标。

---

## 3. 需求覆盖矩阵

| 需求 ID | 覆盖模块 |
|---------|---------|
| REQ-FUNC-001 | MOD-BE-001, MOD-BE-005 |
| REQ-FUNC-002 | MOD-BE-006 |
| REQ-FUNC-003 | MOD-BE-002, MOD-BE-003, MOD-BE-004 |
| REQ-FUNC-004 | MOD-BE-002, MOD-BE-003, MOD-BE-004 |
| REQ-FUNC-005 | MOD-BE-002, MOD-BE-003, MOD-BE-004 |
| REQ-FUNC-006 | MOD-BE-002, MOD-BE-003, MOD-BE-004 |
| REQ-FUNC-007 | MOD-BE-003, MOD-BE-004 |
| REQ-FUNC-008 | MOD-FE-001, MOD-FE-002, MOD-FE-003 |
| REQ-FUNC-009 | 架构隔离设计（无代码修改） |
| REQ-NFN-001 | MOD-BE-005（迁移兼容 MySQL/SQLite） |
| REQ-NFN-002 | 物理机部署，无 Docker 依赖 |
| REQ-NFN-003 | MOD-BE-003（分页 page_size=20），MOD-FE-001（el-pagination） |
| REQ-NFN-004 | MOD-BE-001（索引设计） |
| REQ-NFN-005 | MOD-BE-003（IsAdminUser 权限），MOD-FE-001（前端按钮控制） |

---

## 4. 模块依赖关系（无循环依赖）

```
MOD-BE-001 (Model)
    ↓
MOD-BE-002 (Serializer) ← 依赖 MOD-BE-001
    ↓
MOD-BE-003 (Views) ← 依赖 MOD-BE-001, MOD-BE-002
    ↓
MOD-BE-004 (URLs) ← 依赖 MOD-BE-003
    ↓
MOD-BE-005 (Migration) ← 依赖 MOD-BE-001（makemigrations 自动生成）
MOD-BE-006 (Command) ← 依赖 MOD-BE-001
MOD-BE-007 (Admin) ← 依赖 MOD-BE-001

MOD-FE-001 (View) ← 依赖 /api/owners/ REST API
MOD-FE-002 (Router) ← 依赖 MOD-FE-001
MOD-FE-003 (Layout) ← 依赖 MOD-FE-002（路由路径）
```

依赖方向：单向，无循环。
