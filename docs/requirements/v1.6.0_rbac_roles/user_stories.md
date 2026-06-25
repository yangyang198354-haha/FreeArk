# 用户故事 — v1.6.0 三角色 RBAC 权限重构

**文档编号**: REQ-US-RBAC-v160-001  
**项目名称**: FreeArk 三角色 RBAC 权限重构（v1.6.0_rbac_roles）  
**版本**: 1.0.0  
**状态**: APPROVED（用户 2026-06-24 已确认全部开放问题，按推荐答案锁定）  
**创建日期**: 2026-06-24  
**作者**: requirement-analyst (via pm-orchestrator)  
**来源锁定**: 用户简报（2026-06-24）；Given/When/Then 展开自 requirements_spec.md 第 2-4 节

---

## US-1 角色扩展：三角色定义与基本区分

**作为**系统管理员，  
**我希望**系统支持 `admin`（管理员）、`operator`（运维人员）、`user`（普通业主/住户）三种角色，  
**以便**不同身份的用户获得与其职责匹配的访问权限。

### AC-1.1 运维人员（operator）可正常访问非受限页面

```
Given  一个 role='operator' 的账号已登录
When   用户访问 /home（系统看板）
Then   页面正常加载，无重定向，无 403
```

### AC-1.2 运维人员被拦截在"用户管理"页面之外

```
Given  一个 role='operator' 的账号已登录
When   用户在浏览器地址栏直接输入 /user-list（或 /create-user）
Then   路由守卫将其重定向至 /home
And    后端 GET /api/users/ 返回 HTTP 403 Forbidden
```

### AC-1.3 运维人员被拦截在"服务管理"页面之外

```
Given  一个 role='operator' 的账号已登录
When   用户在浏览器地址栏直接输入 /services
Then   路由守卫将其重定向至 /home（或按实现选择合理落地页）
And    后端服务管理相关 API 返回 HTTP 403 Forbidden
And    前端菜单中"服务管理"子菜单对 operator 不可见
```

### AC-1.4 管理员（admin）访问所有页面不受限

```
Given  一个 role='admin' 的账号已登录
When   用户访问任意页面（包括 /user-list、/create-user、/services、/admin/knowledge-base）
Then   页面正常加载，无重定向，无 403
And    前端菜单中所有菜单项均可见
```

### AC-1.5 普通业主（user）登录后落地到占位页

```
Given  一个 role='user' 的账号已登录
When   登录成功，前端完成身份信息加载
Then   路由守卫将其重定向至 /user-landing
And    /user-landing 页面展示"功能开发中，敬请期待"类提示内容
And    页面提供退出登录操作入口
And    页面不展示任何业务数据或功能按钮
```

### AC-1.6 普通业主尝试访问业务页面被拦截

```
Given  一个 role='user' 的账号已登录
When   用户在浏览器地址栏直接输入 /home（或任何其他业务路由）
Then   路由守卫将其重定向至 /user-landing
And    后端业务 API（如 GET /api/dashboard/*）返回 HTTP 403 Forbidden
```

---

## US-2 存量数据迁移：原 user 账号升级为 operator

**作为**系统运维人员，  
**我希望**数据库中原有的 `role='user'` 账号在部署后自动迁移为 `role='operator'`，  
**以便**已有运维账号无需重新创建，权限无缝延续。

### AC-2.1 migration 执行后不存在 role='user' 的旧账号（内部系统账号也迁移）

```
Given  生产数据库中存在若干 role='user' 的账号（含 openclaw-agent 等内部账号）
When   执行 python manage.py migrate（包含本版本 migration）
Then   数据库中 role='user' 的记录数为 0（旧语义的 user 已全部变为 operator）
And    所有原 role='user' 账号现在 role='operator'
And    role='admin' 账号不受影响，仍为 'admin'
```

### AC-2.2 迁移后已有 operator 账号下次登录收到正确 role 值

```
Given  一个原 role='user' 的账号（数据已迁移为 'operator'）
When   该账号用原有凭据登录，前端获取 /api/auth/me/
Then   响应中 role='operator'
And    前端按 operator 角色显示菜单（可访问看板、设备管理等）
And    该账号无需任何手动操作，登录体验与迁移前一致（除菜单改动外）
```

### AC-2.3 migration 可正向执行且可回滚

```
Given  一个干净的测试环境（SQLite）
When   执行 python manage.py migrate（正向）
Then   migration 无报错，role 字段 choices 更新，数据迁移完成

When   执行 python manage.py migrate <app> <上一版 migration>（回滚）
Then   migration 无报错，role='operator' 记录回滚为 role='user'
And    role='admin' 记录不受影响
```

---

## US-3 前端路由与菜单按角色管控

**作为**系统管理员，  
**我希望**前端菜单和路由守卫按角色自动隐藏不可访问的入口，  
**以便**每个角色的用户看到且只能进入与其权限匹配的页面。

### AC-3.1 operator 菜单：服务管理不可见，用户管理不可见

```
Given  一个 role='operator' 的账号已登录并进入主界面
When   用户查看左侧导航菜单
Then   "服务管理"子菜单不可见
And    "用户管理"子菜单不可见
And    "系统看板"、"设备管理"、"能耗报表"、"方舟智能体"等其余菜单项正常可见
```

### AC-3.2 operator 菜单：业主信息管理可见（OQ-02 推荐方案）

```
Given  一个 role='operator' 的账号已登录（且 OQ-02 确认开放给 operator）
When   用户查看左侧导航菜单
Then   "业主信息管理"菜单项可见
And    点击进入后页面正常加载
```

### AC-3.3 admin 菜单：全部菜单项可见

```
Given  一个 role='admin' 的账号已登录
When   用户查看左侧导航菜单
Then   所有菜单项均可见（含用户管理、服务管理、业主信息管理、三恒知识库管理）
```

### AC-3.4 user 角色：不显示任何主布局菜单

```
Given  一个 role='user' 的账号已登录并被重定向至 /user-landing
When   用户查看页面
Then   左侧导航菜单不显示（或占位页为单独的无菜单布局）
And    用户无法通过点击操作进入任何业务页面
```

### AC-3.5 路由守卫：所有角色未登录时统一重定向至登录页

```
Given  一个未登录用户
When   访问任何需要认证的页面（包括 /user-landing）
Then   路由守卫将其重定向至 /login（或登录页）
```

---

## US-4 后端 API 按角色强制鉴权

**作为**系统安全要求，  
**我希望**后端 API 在接口层强制执行角色校验，不依赖前端隐藏，  
**以便**即使绕过前端直接调用 API 也无法越权访问。

### AC-4.1 operator 直接调用用户管理 API 返回 403

```
Given  一个 role='operator' 的账号，持有有效认证 Token
When   直接对 GET /api/users/ 发起请求（绕过前端菜单）
Then   后端返回 HTTP 403 Forbidden
And    响应中不包含任何用户列表数据
```

### AC-4.2 user 角色直接调用看板 API 返回 403

```
Given  一个 role='user' 的账号，持有有效认证 Token
When   直接对 GET /api/dashboard/summary/（或等价看板接口）发起请求
Then   后端返回 HTTP 403 Forbidden
And    响应中不包含任何设备数据
```

### AC-4.3 operator 可成功调用看板 API

```
Given  一个 role='operator' 的账号，持有有效认证 Token
When   直接对 GET /api/dashboard/summary/ 发起请求
Then   后端返回 HTTP 200，数据正常
```

### AC-4.4 匿名用户调用业务 API 被拒绝（能耗接口需补充鉴权）

```
Given  一个未登录用户（无 Token）
When   直接对 GET /api/usage/monthly/（或等价能耗接口）发起请求
Then   后端返回 HTTP 401 或 HTTP 403
And    不返回任何业务数据
```

> **说明**：该 AC 针对当前使用 `AllowAny` 的能耗/PLC 状态接口，要求在本期升级为至少 `IsOperatorOrAbove`（已登录且角色为 admin 或 operator）。

---

## US-5 用户创建与角色选择

**作为**系统管理员，  
**我希望**创建和编辑用户时能明确选择三种角色之一，  
**以便**避免误分配角色，清楚区分运维人员与普通业主账号。

### AC-5.1 创建用户表单展示三个角色选项

```
Given  管理员已进入创建用户页面（/create-user）
When   用户查看角色选择字段
Then   下拉菜单包含三个选项：管理员（admin）、运维人员（operator）、普通业主（user）
And    没有预设默认选中项（或推荐默认为"运维人员"，视 OQ-04 确认结果）
And    角色字段为必选，不填写时提交报错
```

### AC-5.2 创建 user 角色账号成功，后端存储 role='user'

```
Given  管理员在创建用户表单中选择"普通业主（user）"角色，填写其他必填信息
When   管理员提交表单
Then   后端 POST /api/users/ 返回 HTTP 201
And    新建账号在数据库中 role='user'
And    前端用户列表中该账号角色显示为"普通业主"
```

### AC-5.3 创建 operator 角色账号成功，后端存储 role='operator'

```
Given  管理员在创建用户表单中选择"运维人员（operator）"角色，填写其他必填信息
When   管理员提交表单
Then   后端 POST /api/users/ 返回 HTTP 201
And    新建账号在数据库中 role='operator'
And    前端用户列表中该账号角色显示为"运维人员"
```

### AC-5.4 用户列表展示正确的角色中文名

```
Given  用户列表中包含三种角色的账号
When   管理员访问 /user-list
Then   各账号角色列展示对应中文名：管理员 / 运维人员 / 普通业主
And    不显示原始字段值（不显示 'admin'/'operator'/'user' 等英文值）
```

### AC-5.5 后端拒绝非法角色值

```
Given  任意调用方（管理员或绕过前端的 API 调用）
When   POST /api/users/ 请求体中 role='superuser'（或其他非法值）
Then   后端返回 HTTP 400 Bad Request
And    响应中包含角色字段校验错误信息
```

---

## US-6 /api/auth/me/ 正确返回三种角色值

**作为**前端应用，  
**我希望** `/api/auth/me/` 返回的 `role` 字段能正确区分三种角色，  
**以便**前端路由守卫和菜单逻辑基于准确的角色信息进行判断。

### AC-6.1 operator 账号登录后 me 接口返回 role='operator'

```
Given  一个 role='operator' 的账号（由存量迁移或新建而来）
When   账号登录成功，前端调用 GET /api/auth/me/
Then   响应中 role='operator'
And    前端 localStorage 缓存的 userInfo.role='operator'
And    前端菜单按 operator 角色渲染
```

### AC-6.2 user 账号登录后 me 接口返回 role='user'

```
Given  一个新建的 role='user' 账号
When   账号登录成功，前端调用 GET /api/auth/me/
Then   响应中 role='user'
And    前端路由守卫触发重定向至 /user-landing
```

### AC-6.3 admin 账号不受影响

```
Given  一个 role='admin' 的账号
When   账号登录成功，前端调用 GET /api/auth/me/
Then   响应中 role='admin'（与迁移前完全相同）
And    前端行为与迁移前完全一致
```

---

## US-7 占位页体验（user 角色登录落地）

**作为**普通业主/住户（user 角色），  
**我希望**登录后看到一个清晰友好的提示页面，  
**以便**知道系统正在为我准备专属功能，不产生困惑或白屏感受。

### AC-7.1 user 登录后跳转至占位页，不出现白屏

```
Given  一个 role='user' 的账号
When   账号凭密码登录成功
Then   前端在 100ms 内完成重定向至 /user-landing（无白屏或闪烁）
And    /user-landing 页面渲染"功能开发中"类提示文本
And    不显示任何设备数据、图表或业务功能
```

### AC-7.2 占位页提供退出登录入口

```
Given  role='user' 账号已在 /user-landing 页面
When   用户点击退出登录按钮
Then   前端清除 Token 和用户信息（localStorage）
And    页面跳转至登录页
And    再次访问 /user-landing 被重定向至登录页（因已登出）
```

### AC-7.3 admin/operator 误入占位页被重定向

```
Given  一个 role='admin' 或 role='operator' 的账号已登录
When   用户访问 /user-landing
Then   路由守卫将其重定向至 /home
And    不显示占位页内容
```

---

## 附录：用户故事追踪矩阵

| 用户故事 | 关联需求编号 | 优先级 | 估算复杂度 | 前置依赖 |
|----------|-------------|--------|------------|----------|
| US-1 角色扩展：三角色定义与基本区分 | REQ-FUNC-RBAC-01、04、07 | P0 | 中（model/migration + 守卫/占位页）| 无 |
| US-2 存量数据迁移 | REQ-FUNC-RBAC-02 | P0 | 低（RunPython migration） | US-1（模型扩展先就绪） |
| US-3 前端路由与菜单按角色管控 | REQ-FUNC-RBAC-04、05 | P0 | 中（守卫逻辑 + 菜单 v-if 全量梳理） | US-1、US-2 |
| US-4 后端 API 按角色强制鉴权 | REQ-FUNC-RBAC-03 | P0 | 中（新权限类 + 接口逐一升级）| US-1 |
| US-5 用户创建与角色选择 | REQ-FUNC-RBAC-06、08 | P1 | 低（表单 UI 改动 + serializer）| US-1、US-2 |
| US-6 /api/auth/me/ 正确返回三种角色值 | REQ-FUNC-RBAC-08 | P0 | 低（me 接口已返回 role，模型迁移后自动生效） | US-2 |
| US-7 占位页体验 | REQ-FUNC-RBAC-07 | P0 | 低（新建简单 Vue 页面） | US-1 |

**优先级说明**：US-1/2/3/4 是核心安全基础（P0），US-5/7 是用户体验（P0/P1）。US-6 依赖后端迁移，逻辑上会自动满足。

---

## 附录：测试环境约束

- **后端测试**：`python manage.py test`（自动切 SQLite），需加 `PYTHONUTF8=1` 绕 cp1252。
- **角色 fixture**：测试用例中用 `User.objects.create_user(role='operator')` 和 `role='user'` 分别构造，验证权限类行为。
- **migration 测试**：用 `call_command('migrate')` 在 SQLite 上验证正向执行，再用 `call_command('migrate', 'api', '<上一 migration 编号>')` 验证回滚。
- **可复核原则**：test-engineer 必须提供可被主控直接复制执行的完整命令（含工作目录和环境变量），不得虚报通过。

---

## 附录：开放问题摘要（同 requirements_spec.md 第 7 节）

| 编号 | 核心问题 | 推荐答案 |
|------|---------|----------|
| OQ-01 | "服务管理"范围确认 | 菜单"服务管理"子菜单 + /services |
| OQ-02 | operator 是否可访问"业主信息管理" | 推荐：是 |
| OQ-03 | operator 是否可访问"三恒知识库管理" | 推荐：否（仍限 admin） |
| OQ-04 | 新建用户默认角色 | 推荐：无默认，强制选择 |
| OQ-05 | 存量 user → operator 全量迁移 | 推荐：是 |
| OQ-06 | user 登录落地体验 | 推荐：/user-landing 占位页 + 退出按钮 |
| OQ-07 | user 账号与 OwnerInfo 关联 | 推荐：本期不做 |
| OQ-08 | 创建管理员是否需二次确认 | 推荐：不需要 |
