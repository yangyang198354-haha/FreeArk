# 技术选型表（Tech Stack）

**版本**：v1.8.0_miniprogram_owner_account  
**日期**：2026-06-25  
**状态**：DRAFT  
**作者**：system-architect (SDLC Agent)

---

## 原则

本版本无新增第三方依赖（除微信登录的 HTTP 调用用现有 `requests` 库外），所有实现均复用已有技术栈。保持零新依赖是该版本的明确目标，避免在生产树莓派环境引入安装风险。

---

## 后端技术选型

| 技术/组件 | 版本/来源 | 用途 | 是否新增 |
|---------|---------|------|---------|
| Django | 现有（生产已部署） | ORM、中间件、视图 | 否 |
| Django REST Framework | 现有 | API 视图、权限类、序列化器 | 否 |
| `rest_framework.authtoken` | 现有 | Token 签发（微信登录复用） | 否 |
| `requests` | 现有（已安装） | 调用微信 code2session HTTP API | 否（复用） |
| Django Channels | 现有 | WebSocket（MiniAppChatConsumer 继承） | 否 |
| LangGraph | 现有 | 编排图（State 扩展，user_scope 字段） | 否 |
| LangChain | 现有 | @tool 装饰器（fa_tools 扩展） | 否 |
| MySQL（生产） | 现有 | 新增两张表（WechatBinding、OwnerUserBinding） | 否（复用） |
| SQLite（测试） | 现有 | 同上 | 否（复用） |

**新增依赖**：无

---

## 前端技术选型

### 微信小程序（uni-app）

| 技术/组件 | 版本/来源 | 用途 | 是否新增 |
|---------|---------|------|---------|
| uni-app | 现有（v1.5.0 已建立） | 框架 | 否 |
| Vue 3（uni-app 内） | 现有 | 页面组件 | 否 |
| 微信原生 API `wx.login()` | 小程序 SDK | 获取临时 code（微信登录） | 否（SDK 已有） |
| 微信原生 API `wx.scanCode()` | 小程序 SDK | 扫描二维码获取 unique_id | 否（SDK 已有） |

**新增依赖**：无（`wx.login()` 和 `wx.scanCode()` 均为微信小程序 SDK 原生 API，无需安装额外包）

### Web 端（Element Plus + Vue 3）

| 技术/组件 | 版本/来源 | 用途 | 是否新增 |
|---------|---------|------|---------|
| Vue 3 | 现有 | 组件框架 | 否 |
| Element Plus | 现有 | `<el-table-column>`、`<el-tag>` | 否 |
| Axios | 现有 | 新增 `/api/miniapp/admin/owner-bindings/` 请求 | 否 |

---

## 微信开放平台配置需求（非代码，运维层面）

| 配置项 | 说明 | 注入方式 |
|--------|------|---------|
| `WECHAT_MINIAPP_APPID` | 微信小程序 AppID | 生产 `.env` 文件，`python-dotenv` 加载 |
| `WECHAT_MINIAPP_SECRET` | 微信小程序 AppSecret | 同上 |

**已有基础**：需求文档确认 AppID/Secret 已有，注入方式与现有 `DEEPSEEK_API_KEY` 一致（`.env` + `django.conf.settings`），无新的凭证管理机制需要引入。

---

## 基础设施约束回顾（与本版本的关系）

| 约束 | 内容 | 本版本影响 |
|------|------|---------|
| 禁 Docker | 物理机树莓派部署 | 无影响：零新增服务/容器 |
| 生产 DB | MySQL 192.168.31.98:3306 | 迁移 0041 新建 2 张表，纯 CREATE TABLE，锁最小 |
| 测试 DB | SQLite（FREEARK_POC_MOCK 环境） | 同样支持新增表迁移，无差异 |
| 部署方式 | git pull + systemd 重启 | 不变：无新 systemd 服务需要创建 |
| 微信 code2session | 需访问 `api.weixin.qq.com` | 需确认树莓派到外网微信 API 的 HTTPS 连通性 |

**潜在风险**：生产环境树莓派的公网出口为 wlan0（已知 WiFi 省电模式偶发劣化），微信 code2session API 调用若网络超时（5s）会返回 503。已在视图设计中处理（REQ-AUTH-002 场景 3）。

---

## 新增文件清单（供 software-developer 参考）

| 文件路径 | 类型 | 说明 |
|---------|------|------|
| `api/views_miniapp.py` | Python（新建） | /api/miniapp/ 所有视图 |
| `api/urls_miniapp.py` | Python（新建） | miniapp 路由表 |
| `api/langgraph_chat/user_scope.py` | Python（新建） | UserScope dataclass + build_user_scope() |
| `api/langgraph_chat/scope_enforcer.py` | Python（新建） | ScopeEnforcer（工具调用拦截） |
| `api/migrations/0041_*.py` | Python（新建） | 数据库迁移 |
| `miniprogram/pages/register/register.vue` | Vue（新建） | 小程序注册页 |
| `miniprogram/pages/bind/bind.vue` | Vue（新建） | 小程序绑定页 |
| `miniprogram/pages/bind/unbind.vue` | Vue（新建） | 小程序解绑页 |

## 改动文件清单

| 文件路径 | 改动性质 | 行数估计 |
|---------|---------|---------|
| `api/models.py` | 末尾追加 2 个模型类 | +80 行 |
| `api/middleware.py` | `_should_block()` 新增 3 行 | +3 行 |
| `api/consumers.py` | 末尾追加 MiniAppChatConsumer 类 | +80 行 |
| `api/langgraph_chat/orchestrator.py` | State 字段 + _expert/_gate/_fan_out 各改动块 | +30 行 |
| `api/langgraph_chat/fa_tools.py` | 2 个工具签名扩展 | +8 行 |
| `api/langgraph_chat/adapter.py` | stream_chat 签名 + payload 注入 | +8 行 |
| `api/views.py` | 末尾追加 IsOwnerUser 权限类 | +8 行 |
| `freearkweb/urls.py` | include miniapp 路由 | +2 行 |
| `freearkweb/settings.py` | WECHAT_MINIAPP_APPID/SECRET 配置读取 | +4 行 |
| `freearkweb/routing.py` | 新增 ws/miniapp/chat/ 路由 | +2 行 |
| `frontend/src/views/OwnerManagementView.vue` | 新增列 + 数据加载逻辑 | +40 行 |
| `miniprogram/pages/login/login.vue` | 新增微信登录按钮 | +20 行 |

**净新增**：约 300 行新代码 + 120 行改动（不含前端 Vue 页面）

---

*文档结束*
