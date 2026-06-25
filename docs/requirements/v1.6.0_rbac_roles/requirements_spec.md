# 需求规格说明书 — v1.6.0 三角色 RBAC 权限重构

**文档编号**: REQ-SPEC-RBAC-v160-001  
**项目名称**: FreeArk 三角色 RBAC 权限重构（v1.6.0_rbac_roles）  
**版本**: 1.0.0  
**状态**: APPROVED（用户 2026-06-24 已确认全部开放问题，按推荐答案锁定）  
**创建日期**: 2026-06-24  
**作者**: requirement-analyst (via pm-orchestrator)  
**来源锁定**: 用户简报（2026-06-24）；代码实况核查基于 models.py、views.py、router/index.js、Layout.vue

---

## 版本历史

| 版本  | 日期       | 变更摘要                                   |
|-------|------------|--------------------------------------------|
| 1.0.0 | 2026-06-24 | 初始草稿，基于用户简报 + 代码现状核查       |

---

## 0. 问题陈述

### 0.1 背景现状（代码锚定）

**后端**（`FreeArkWeb/backend/freearkweb/api/models.py:9-13`）：

```python
ROLE_CHOICES = (('admin', '管理员'), ('user', '普通用户'))
role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
```

- 仅有两种角色：`admin`（管理员）和 `user`（普通用户）。
- 自定义 `IsAdminUser`（`views.py:125-128`）：判定 `request.user.role == 'admin'`，与 Django `is_staff` 无关联。
- 后端大量接口使用 `@permission_classes([permissions.AllowAny])`（包括能耗数据接口），尚未按角色细粒度保护。

**前端**（`FreeArkWeb/frontend/src/`）：

- 路由守卫（`router/index.js:233-258`）只有两道闸：`requiresAuth`（已登录）和 `requiresAdmin`（`role==='admin'`）。
- 菜单（`Layout.vue`）中，仅"业主信息管理"、"三恒知识库管理"、"用户管理"三处加了 `v-if="userRole === 'admin'"`；其余菜单项对所有已登录用户均可见，无角色区分。

**痛点**：

1. 运维人员（现 `user` 角色）与未来的普通业主（也将叫 `user`）角色语义混淆，急需分离。
2. 缺少"普通业主/住户"角色的访问控制机制，无法在 Web 端管控其访问范围。
3. 新增角色若不同步后端强制鉴权，则单靠前端隐藏菜单存在安全越权风险。

### 0.2 本版本目标

1. 将现有两角色扩展为三角色：`admin`、`operator`（原 `user` 改名）、`user`（新，普通业主/住户）。
2. 明确定义三角色的页面/功能访问权限矩阵，并双侧落地（前端菜单隐藏 + 路由守卫 + 后端 API 强制鉴权）。
3. `user`（业主/住户）登录后只能看到一个占位页面，无业务功能访问权限——为后续专属功能开发预留位置。
4. 存量 `role='user'` 账号数据迁移为 `role='operator'`。
5. 用户创建功能支持显式选择三种角色，废弃隐式默认角色。

---

## 1. 范围与边界

### 1.1 本版本纳入范围

| 编号 | 功能域 | 摘要 |
|------|--------|------|
| REQ-FUNC-RBAC-01 | 角色模型扩展 | `CustomUser.ROLE_CHOICES` 新增 `operator` 角色，修改 `default` 值（待确认 OQ-04），添加 migration |
| REQ-FUNC-RBAC-02 | 存量数据迁移 | 一次性将数据库中所有 `role='user'` 记录更新为 `role='operator'`（待确认 OQ-05） |
| REQ-FUNC-RBAC-03 | 后端鉴权策略 | 新增 `IsOperatorOrAbove` 权限类；对现有接口按权限矩阵补充后端角色鉴权 |
| REQ-FUNC-RBAC-04 | 前端路由守卫 | 新增 `requiresOperator` meta 标记；针对 `user` 角色登录后重定向至占位页 |
| REQ-FUNC-RBAC-05 | 前端菜单权限 | 按三角色权限矩阵更新 `Layout.vue` 各菜单项的 `v-if` 条件 |
| REQ-FUNC-RBAC-06 | 用户创建/编辑表单 | 创建/编辑用户时显示三角色选项，废弃隐式默认角色 |
| REQ-FUNC-RBAC-07 | user 占位页 | 新增 `UserLandingView.vue`，`user` 角色登录后落地到此页，展示"功能开发中"提示 |
| REQ-FUNC-RBAC-08 | API 响应字段 | `/api/auth/me/` 返回的 `role` 字段支持三值（admin/operator/user） |

### 1.2 本版本不纳入范围

- `user`（业主/住户）角色的任何专属业务功能开发——本期仅建立占位，功能另立版本。
- `OwnerInfo` 业主业务数据与 `user` 登录账号的关联逻辑——本期不做（见 OQ-07）。
- 细粒度对象级权限（如：operator 只能看自己负责的设备）——本期不做，全局角色级别。
- Django Admin 后台权限同步——本期不做，不影响业务系统。
- 角色层级下的子权限配置界面——本期不做，权限矩阵硬编码在代码中。

---

## 2. 角色定义

| 角色值 | 中文名 | 语义 | 原角色映射 |
|--------|--------|------|------------|
| `admin` | 管理员 | 拥有全部页面和功能的访问权限，包括用户管理和服务管理 | 不变 |
| `operator` | 运维人员 | 拥有除"用户管理"和"服务管理"以外的全部页面和功能访问权限 | 原 `user` 角色改名 |
| `user` | 普通业主/住户 | 登录后仅能访问占位页，不能访问任何现有业务页面和功能 | 全新角色，此前不存在 |

---

## 3. 权限矩阵

行 = 页面/功能，列 = 三种角色。标注说明：

- **✓** = 可访问/可见
- **✗** = 不可访问，前端隐藏菜单 + 路由守卫拦截 + 后端 API 强制拒绝（如适用）
- **✓(OQ)** = 存在开放问题，推荐值为 ✓，但需用户确认（见第 7 节）

### 3.1 前端页面权限矩阵

| 页面/功能 | 路由 | admin | operator | user |
|-----------|------|-------|----------|------|
| 系统看板 | /home | ✓ | ✓ | ✗ |
| 设备列表 | /device-management/device-list | ✓ | ✓ | ✗ |
| 故障管理 | /device-management/faults | ✓ | ✓ | ✗ |
| 结露预警 | /device-management/condensation-warnings | ✓ | ✓ | ✗ |
| 业主信息管理 | /owner-management | ✓ | ✓ | ✗ |
| 能耗月度用量报表 | /monthly-usage-report | ✓ | ✓ | ✗ |
| 能耗每日用量报表 | /daily-usage-report | ✓ | ✓ | ✗ |
| 用量查询 | /usage-query | ✓ | ✓ | ✗ |
| 服务管理（服务列表） | /services | ✓ | ✗ | ✗ |
| 和方舟智能体聊天 | /chat | ✓ | ✓ | ✗ |
| 巡检智能体工作日志 | /agent/inspection-worklog | ✓ | ✓ | ✗ |
| 巡检工单 | /agent/work-orders | ✓ | ✓ | ✗ |
| 三恒知识库管理 | /admin/knowledge-base | ✓ | ✗ | ✗ |
| 用户管理（创建用户/用户列表） | /create-user、/user-list | ✓ | ✗ | ✗ |
| 编辑用户 | /edit-user/:id | ✓ | ✗ | ✗ |
| 个人资料（编辑个人资料/修改密码） | /change-password | ✓ | ✓ | ✗ |
| 占位页（业主功能开发中） | /user-landing | ✗ | ✗ | ✓ |

> **注**：`user` 角色登录后跳转至 `/user-landing` 占位页，不能访问上表中 `✗` 的任何页面。管理员和运维人员不显示/不访问 `/user-landing`。

### 3.2 后端 API 权限矩阵

| API 端点 | 当前权限类 | 目标权限类 | admin | operator | user | 说明 |
|----------|-----------|-----------|-------|----------|------|------|
| POST /api/auth/login/ | AllowAny | AllowAny | ✓ | ✓ | ✓ | 登录不限制 |
| GET /api/auth/me/ | IsAuthenticated | IsAuthenticated | ✓ | ✓ | ✓ | 获取自身信息不限制 |
| POST /api/auth/logout/ | IsAuthenticated | IsAuthenticated | ✓ | ✓ | ✓ | 登出不限制 |
| GET /api/users/ | IsAdminUser | IsAdminUser | ✓ | ✗ | ✗ | 用户列表 |
| POST /api/users/ | IsAdminUser | IsAdminUser | ✓ | ✗ | ✗ | 创建用户 |
| GET/PUT/DELETE /api/users/:id/ | IsAdminUser | IsAdminUser | ✓ | ✗ | ✗ | 用户详情/编辑/删除 |
| GET /api/services/ 及相关 | （待确认 OQ-01）| IsAdminUser | ✓ | ✗ | ✗ | 服务管理接口 |
| GET /api/dashboard/*(看板类) | IsAuthenticated | IsOperatorOrAbove | ✓ | ✓ | ✗ | 看板数据 |
| GET /api/usage/*(能耗报表类) | AllowAny（当前！） | IsOperatorOrAbove | ✓ | ✓ | ✗ | 需补充鉴权 |
| GET /api/plc/*(PLC状态类) | AllowAny（当前！） | IsOperatorOrAbove | ✓ | ✓ | ✗ | 需补充鉴权 |
| POST /api/rag/documents/ 等 | IsAdminUser | IsAdminUser（待确认 OQ-03） | ✓ | ✗(OQ-03) | ✗ | 三恒知识库管理 |
| GET/POST/DELETE /api/owner/* | （待确认 OQ-02） | （待确认 OQ-02） | ✓ | ✓(OQ-02) | ✗ | 业主信息管理 |
| POST /api/chat/* | IsAuthenticated | IsOperatorOrAbove | ✓ | ✓ | ✗ | 智能体聊天 |

> **安全说明**：当前多个接口（能耗、PLC状态）使用 `AllowAny`，历史上可能基于内网安全假设。本期 RBAC 重构应至少将这些接口升级为 `IsOperatorOrAbove`（已登录且角色为 admin 或 operator），确保 `user` 角色和匿名用户无法调取设备数据。具体接口清单由开发阶段 code review 最终确认，需求层面强制要求"后端强制鉴权，不得只依赖前端隐藏"。

---

## 4. 功能需求

### 4.1 角色模型扩展（REQ-FUNC-RBAC-01）

修改 `FreeArkWeb/backend/freearkweb/api/models.py`：

```python
ROLE_CHOICES = (
    ('admin', '管理员'),
    ('operator', '运维人员'),   # 原 'user' 改名
    ('user', '普通业主/住户'),  # 新增
)
role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='operator')
# default 值待 OQ-04 用户确认
```

**Migration 要求**：

- 新建 migration 文件，仅修改 `role` 字段的 `choices` 和 `default`，**不改变列类型**（VARCHAR(20) 不变，仅 choices 是代码级约束，不影响 DB schema）。
- migration 中嵌入数据迁移操作（`RunPython`），将所有 `role='user'` 的记录更新为 `role='operator'`（REQ-FUNC-RBAC-02，待 OQ-05 确认）。
- migration 命名建议：`0037_rbac_add_operator_role_and_migrate_data`（在最新 migration 编号基础上递增，开发阶段确认实际编号）。

### 4.2 存量数据迁移（REQ-FUNC-RBAC-02）

**迁移逻辑（嵌入 migration 的 RunPython）**：

```python
def migrate_user_to_operator(apps, schema_editor):
    CustomUser = apps.get_model('api', 'CustomUser')
    updated = CustomUser.objects.filter(role='user').update(role='operator')
    # 建议 migration 执行日志记录更新数量，方便审计

def reverse_operator_to_user(apps, schema_editor):
    CustomUser = apps.get_model('api', 'CustomUser')
    CustomUser.objects.filter(role='operator').update(role='user')
```

**验收要求**：

- migration 执行后，数据库中不存在任何 `role='user'` 的旧账号（openclaw-agent 账号同样需要迁移，其原 `role='user'` 应变为 `role='operator'`，因其是内部 AI Agent 账号，语义上属于运维侧）。
- migration 可回滚（reverse 函数存在且逻辑正确）。

### 4.3 后端鉴权策略（REQ-FUNC-RBAC-03）

**新增权限类**（在 `views.py` 或独立的 `permissions.py` 中）：

```python
class IsOperatorOrAbove(permissions.BasePermission):
    """允许 admin 和 operator 角色访问，拒绝 user 角色和匿名用户"""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in ('admin', 'operator')
        )
```

**现有 `IsAdminUser` 不变**，继续用于仅 admin 可访问的接口（用户管理、服务管理、知识库管理等）。

**接口升级要求**（开发阶段逐一落地）：

- 所有当前使用 `AllowAny` 的业务接口（看板、能耗、PLC 状态等），评估是否需要升级为 `IsOperatorOrAbove`——凡是 `user` 角色不应访问的，必须升级，不得只靠前端隐藏。
- 具体接口清单见第 3.2 节权限矩阵，开发阶段按矩阵逐一落地并在 code review 中核验。

### 4.4 前端路由守卫更新（REQ-FUNC-RBAC-04）

修改 `FreeArkWeb/frontend/src/router/index.js`：

**新增 meta 标记**：在需要 `operator` 及以上角色访问的路由上，添加 `requiresOperator: true`（或等价机制）。

**路由守卫逻辑**（在现有守卫中新增分支）：

```javascript
// 已登录但角色为 user，且目标路由非占位页，统一重定向至 /user-landing
if (isLoggedIn && userInfo.role === 'user' && to.path !== '/user-landing') {
  next({ path: '/user-landing' })
  return
}
```

**`user-landing` 路由**：

```javascript
{
  path: '/user-landing',
  name: 'UserLanding',
  component: () => import('../views/UserLandingView.vue'),
  meta: { requiresAuth: true }
  // 不需要 requiresAdmin 或 requiresOperator
}
```

**防止二次重定向**：`admin` 和 `operator` 角色访问 `/user-landing` 时，重定向至 `/home`。

### 4.5 前端菜单权限更新（REQ-FUNC-RBAC-05）

修改 `FreeArkWeb/frontend/src/components/Layout.vue`：

按第 3.1 节权限矩阵，对每个菜单项的 `v-if` 条件进行更新。涉及变更的菜单项：

| 菜单项 | 当前 `v-if` | 目标 `v-if` |
|--------|------------|------------|
| 业主信息管理 | `userRole === 'admin'` | `userRole === 'admin' \|\| userRole === 'operator'`（待 OQ-02 确认） |
| 服务管理（整个子菜单） | 无限制（所有登录用户可见） | `userRole === 'admin'` |
| 三恒知识库管理 | `userRole === 'admin'` | `userRole === 'admin'`（待 OQ-03，如放开则改为含 operator） |
| 用户管理（整个子菜单） | `userRole === 'admin'` | `userRole === 'admin'`（不变） |

> **注**：`user` 角色登录后不进入主布局（直接落地到占位页），因此 Layout.vue 菜单的 `v-if` 主要影响 admin 和 operator 的区分。对 `user` 角色的拦截由路由守卫完成。

### 4.6 用户创建/编辑表单更新（REQ-FUNC-RBAC-06）

修改创建用户和编辑用户相关前端组件：

**要求**：

- 角色选择字段（`role`）改为下拉菜单，明确展示三个选项：管理员（admin）、运维人员（operator）、普通业主（user）。
- 废弃隐式默认角色，表单提交前必须用户明确选择角色（见 OQ-04 关于默认值的讨论）。
- 用户列表页（`/user-list`）展示 `role` 字段时，显示中文名称：管理员/运维人员/普通业主。

**后端**：`UserSerializer` / `UserCreateSerializer` 更新 `role` 字段的 `choices` 校验，接受 `admin`、`operator`、`user` 三值，拒绝其他值。

### 4.7 user 角色占位页（REQ-FUNC-RBAC-07）

新增 `FreeArkWeb/frontend/src/views/UserLandingView.vue`：

**页面内容**：

- 标题：欢迎使用自由方舟（或等价标题）
- 正文：您的专属功能正在开发中，敬请期待。
- 提供"退出登录"操作入口（避免用户无法退出）。
- 不显示任何业务数据、菜单导航或功能按钮。

**路由**：`/user-landing`，`meta: { requiresAuth: true }`

**访问控制**：

- 未登录访问 `/user-landing` → 重定向至登录页（复用现有 `requiresAuth` 守卫）。
- `admin`/`operator` 角色访问 `/user-landing` → 重定向至 `/home`。
- `user` 角色访问任何其他业务页面 → 重定向至 `/user-landing`。

### 4.8 API 响应字段兼容（REQ-FUNC-RBAC-08）

`/api/auth/me/` 返回的用户信息中，`role` 字段值将出现三种：`admin`、`operator`、`user`。

**兼容性要求**：

- 前端所有引用 `userInfo.role` 的地方，凡是做 `=== 'user'` 判断表示"运维用户"语义的，都必须改为 `=== 'operator'`。
- 前端现有的 `role === 'admin'` 判断不受影响。
- `localStorage` 中缓存的 `userInfo.role` 会在下次登录时刷新。对于已登录的旧 `user` 账号，下次登录后将收到 `role='operator'`（因为后端数据已迁移）。

---

## 5. 非功能需求

### 5.1 向后兼容

- 存量 `admin` 账号不受任何影响，权限、登录体验完全不变。
- 存量 `user`（即将成为 `operator`）账号数据迁移后，下次登录时前端收到 `role='operator'`，权限与原来基本相同（能访问的页面范围不变，因为原来 `user` 就能访问除 admin-only 以外的所有页面；本期 `operator` 权限与之对齐）。
- migration 可回滚，回滚后恢复原始 role 值分布。

### 5.2 安全

- **后端强制鉴权原则**：前端菜单隐藏和路由守卫只是 UX 层保护，不构成安全边界。所有按角色限制的功能，必须在后端 API 层也强制执行角色校验，防止通过直接调用 API 越权访问。
- **`IsAdminUser` 判定逻辑不变**：仍使用 `request.user.role == 'admin'`，不引入 `is_staff` 依赖。
- **新 `user` 角色不得访问任何设备数据**：即使通过直接构造 API 请求，也应被后端拒绝（HTTP 403）。

### 5.3 数据一致性

- migration 在数据库事务中执行（Django migration 默认行为），失败时自动回滚，不产生部分迁移状态。
- migration 执行完毕后，不得存在 `role` 字段值不在 `('admin', 'operator', 'user')` 范围内的账号记录。

### 5.4 部署约束

- 物理机部署，生产服务器为树莓派（aarch64），无 Docker。
- 部署一律通过 `plink + git pull + 重启相关服务`，禁止 pscp 逐文件上传。
- migration 通过 `python manage.py migrate` 执行，上线前需在测试环境（SQLite）先验证 migration 可正向执行、可回滚。
- 前端需重新构建（`npm run build`）并部署 dist 目录。

### 5.5 测试约束

- 后端测试用 SQLite + `FREEARK_POC_MOCK=1` 环境（不依赖生产 MySQL）。
- 本机测试需 `PYTHONUTF8=1` 绕过 cp1252 编码问题（参见项目记忆）。
- test-engineer 必须提供可被主控直接复制执行的完整命令，不得虚报通过。

---

## 6. 文件影响范围汇总

### 6.1 后端修改文件

| 文件路径 | 改动摘要 |
|----------|----------|
| `FreeArkWeb/backend/freearkweb/api/models.py` | `ROLE_CHOICES` 新增 `operator`；修改 `default`（待 OQ-04） |
| `FreeArkWeb/backend/freearkweb/api/migrations/0037_rbac_*.py` | 新增 migration；含 `RunPython` 数据迁移（待 OQ-05） |
| `FreeArkWeb/backend/freearkweb/api/views.py` | 新增 `IsOperatorOrAbove` 权限类；按权限矩阵升级相关接口的 `permission_classes` |
| `FreeArkWeb/backend/freearkweb/api/serializers.py` | `UserCreateSerializer` 的 `role` 字段 choices 更新为三值 |

### 6.2 前端修改文件

| 文件路径 | 改动摘要 |
|----------|----------|
| `FreeArkWeb/frontend/src/router/index.js` | 新增 `/user-landing` 路由；守卫新增 `user` 角色拦截逻辑 |
| `FreeArkWeb/frontend/src/components/Layout.vue` | 按权限矩阵更新菜单项 `v-if` 条件（服务管理加 admin 限制等） |
| `FreeArkWeb/frontend/src/views/CreateUserView.vue` | 角色选择改为三选项下拉，废弃隐式默认 |
| `FreeArkWeb/frontend/src/views/EditUserView.vue` | 角色选择改为三选项下拉 |
| `FreeArkWeb/frontend/src/views/UserListView.vue` | 展示 role 字段时显示中文名称（管理员/运维人员/普通业主） |

### 6.3 前端新增文件

| 文件路径 | 说明 |
|----------|------|
| `FreeArkWeb/frontend/src/views/UserLandingView.vue` | `user` 角色登录后的占位落地页 |

---

## 7. 开放问题（Open Questions）——✅ 已确认（2026-06-24）

> **结论**：用户于 2026-06-24 通过交互式确认，对 OQ-01～OQ-08 **全部按推荐答案**锁定。
> 其中 OQ-02=operator 可访问业主信息管理；OQ-03=三恒知识库仍仅 admin；OQ-06=新建 /user-landing 占位页；其余按推荐。

每条原始推荐答案如下（均为最终决定）。

| 编号 | 问题 | 推荐答案 | 影响范围 |
|------|------|----------|----------|
| OQ-01 | "服务管理"的确切范围 | 菜单中"服务管理"子菜单 + 其下的"服务列表 /services" | 权限矩阵第 3.1、3.2 节 |
| OQ-02 | `operator` 是否可访问"业主信息管理 /owner-management" | 推荐：**是**，业主信息是运维工作的重要依据，且需求原文"除用户管理和服务管理外都给 operator"字面上支持此结论 | Layout.vue 菜单条件；后端业主相关接口权限类 |
| OQ-03 | `operator` 是否可访问"三恒知识库管理 /admin/knowledge-base" | 推荐：**否**，知识库文档上传/删除是内容管理职能，建议仍限 admin；operator 只使用知识库（通过聊天），不管理文档 | Layout.vue 菜单条件；RAG 接口权限类 |
| OQ-04 | 新建用户时的默认角色 | 推荐：**无默认值（强制选择）**，废弃当前 `default='user'`（语义已混乱），表单提交时必须明确选择角色，避免误创建错误角色账号 | models.py default；CreateUserView.vue 表单 |
| OQ-05 | 存量数据迁移：`role='user'` → `role='operator'` | 推荐：**是，全量迁移**，因旧 `user` 语义即现在的运维人员；新 `user` 语义是业主账号，此前不存在，无需单独处理 | migration RunPython |
| OQ-06 | `user`（业主）登录后落地体验 | 推荐：**显示占位页 `/user-landing`**，内容为"功能开发中，敬请期待" + 退出登录按钮；不允许访问任何业务页面；不产生白屏或无限重定向 | UserLandingView.vue；路由守卫 |
| OQ-07 | `user` 账号是否关联 `OwnerInfo` 业主业务数据 | 推荐：**本期不关联**，留给后续版本；本期仅建立角色，不做账号与业主数据的映射逻辑 | 本期不涉及 |
| OQ-08 | 用户创建/编辑表单是否对 `admin` 账号特殊提示（如：创建管理员账号需二次确认）| 推荐：**不需要**，当前系统简单，管理员不多，额外确认步骤意义不大 | CreateUserView.vue |

---

## 附录 A：代码现状核查摘要（不得推翻，作为需求输入锚点）

| 文件 | 关键现状 |
|------|---------|
| `models.py:9-13` | `ROLE_CHOICES = (('admin','管理员'),('user','普通用户'))` |
| `views.py:125-128` | `IsAdminUser` 判定 `user.role == 'admin'`，不依赖 `is_staff` |
| `router/index.js:233-258` | 守卫仅两道闸：`requiresAuth` + `requiresAdmin`（`role==='admin'`） |
| `Layout.vue:65,96,99` | 仅三处 `v-if="userRole === 'admin'"`：业主管理、三恒知识库管理、用户管理 |
| `Layout.vue:80-86` | 服务管理子菜单**无任何 v-if**，所有已登录用户均可见（当前缺陷） |
| `views.py:303-365` | 能耗/PLC状态接口使用 `AllowAny`（内网假设，需本期补充角色鉴权） |

---

## 附录 B：实现决策与偏差说明（开发阶段补充，2026-06-25）

实现时对需求做了如下工程化落地决策，均不改变已确认的功能语义：

1. **user 角色后端兜底用中间件而非逐接口改 permission_classes。**
   本项目 DRF 仅启用 Token 认证（已移除 SessionAuthentication），普通 Django 中间件 `request.user` 对 API 恒为匿名；业务接口分散在 10+ 文件、40+ 端点。故新增 `api/middleware.py::UserRoleApiGuardMiddleware`，自行解析 `Authorization: Token` 后，对 `role='user'` 拦截白名单外所有 `/api/`（403）。白名单：login/logout/me/get-csrf-token/change-password/health。
   - 代价：每个带 Token 的业务请求多一次 token 表 SELECT（O(1) 常量，已在 owner 设备树 N+1 测试阈值 9→10 中记录）。
   - 另对明确按角色区分的接口仍显式声明权限类：`IsOperatorOrAbove`（业主接口、原 AllowAny 的能耗/PLC/设备参数）、`IsAdminUser`（服务管理 services/*）。
2. **模型 `role` 默认值 = `'operator'`，但公开注册强制 `'user'`。**
   模型 default='operator'：泛化创建的账号（内部/工具）默认得运维级，与旧 'user'（=现运维）语义一致，避免大面积破坏既有逻辑。两个例外显式处理：① 管理员创建表单强制选择角色（`UserCreateSerializer.role` 必填）；② **公开自助注册 `UserRegistrationSerializer.create` 强制 `role='user'`，忽略客户端传入 role**——这同时关闭了"自助注册即可自选 admin/operator"的越权口子（见下）。
3. **openclaw-agent 服务账号 role 由 'user' 改为 'operator'。**
   该 AI Agent 通过 Token 调用设备/能耗业务 API，新 'user'=业主会被中间件拦截，故服务账号必须为 operator。已同步更新 `create_openclaw_agent_user` 命令；存量账号由数据迁移 user→operator 自动覆盖。
4. **前端 user-mgmt 与 services 路由补 `requiresAdmin`。**
   `/services`、`/create-user`、`/user-list`、`/edit-user/:id` 增加 `meta.requiresAdmin`，使 operator 直接输 URL 也被守卫弹回 /home（后端另有 IsAdminUser 兜底）。
5. **能耗/PLC/设备参数/计费 9 个原 `AllowAny` 只读接口收紧为 `IsOperatorOrAbove`（用户 2026-06-25 确认）。**
   落实 AC-4.4——匿名与业主均被拒（仅 admin/operator 可读）。代价：存量约 13 个 test_main 能耗/PLC/计费测试类（改用 `_authed_client()` helper 带 operator Token）、`test_device_cards`、`test_room_filter_v057` 需补认证，2 个 `test_unauthenticated_access_allowed` 翻转为断言 401。仅 csrf/login/register/health 保持 `AllowAny`。
   - 聊天 WebSocket 不经 HTTP 中间件，已在 `ChatConsumer.connect` 显式拒绝 `role='user'`。

### 顺带修复的安全发现

- **自助注册自选角色越权**：`user_register`（POST /api/auth/register/，AllowAny）原 `UserRegistrationSerializer` 允许请求方自带 `role` 字段——任何人可自助注册为 admin/operator，绕过 RBAC。本期已修复：`create()` 强制 `role='user'`（最小权限业主），忽略客户端传入的 role。
  - 注：是否进一步**下线**该公开注册端点（项目可能不需要自助注册），留给用户决定。
