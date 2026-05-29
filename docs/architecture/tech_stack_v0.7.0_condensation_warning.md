# 技术选型表

```
file_header:
  document_id: TECH-v0.7.0-CW
  title: 结露预警管理页面 — 技术选型表
  author_agent: sub_agent_system_architect (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.7.0-condensation-warning
  created_at: 2026-05-30
  status: APPROVED
  references:
    - docs/architecture/architecture_design_v0.7.0_condensation_warning.md
    - docs/architecture/tech_stack_v0.6.0_fault_management.md
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 1.0.0-APPROVED | 2026-05-30 | 初始正式版本，v0.7.0-CW 技术选型（全部复用故障管理 v0.6.0 技术栈，无新增依赖） |

---

## 技术选型摘要

**本版本无新增技术依赖。** 所有技术选型与 v0.6.0-FM 故障管理保持完全一致，最大化降低生产引入风险。

---

## 技术栈详表

| 层次 | 技术/框架 | 版本约束 | 说明 | 与故障管理的差异 |
|------|---------|---------|------|----------------|
| **消息队列** | paho-mqtt | `>=1.6.1,<2.0`（已在 requirements.txt） | MQTT 消费者，WSS 协议，paho 1.x API | 无差异，直接复用 |
| **后端框架** | Django | `>=4.x`（生产已有） | Web 框架 + ORM + Management Command | 无差异 |
| **REST API** | Django REST Framework (DRF) | 生产已有 | PageNumberPagination, api_view, IsAuthenticated | 无差异 |
| **数据库（生产）** | MySQL | 9.4 @ 192.168.31.98:3306 | 新表 condensation_warning_event（migration 0029） | 无差异，同一 DB 实例 |
| **数据库（测试）** | SQLite | Django 默认 | 单元测试/CI 用 | 无差异 |
| **进程管理** | systemd | 生产已有 | 两个新服务：consumer（simple）+ cleanup（oneshot+timer） | 无差异，与 fault 服务相同模式 |
| **前端框架** | Vue 3 | 生产已有 | Composition API 或 Options API（按现有代码风格） | 无差异 |
| **UI 组件库** | Element Plus | 生产已有 | el-table, el-radio-group, el-date-picker, el-pagination | 无差异；CondensationWarningView 仅复用已有组件 |
| **HTTP 客户端（前端）** | axios + URLSearchParams | 生产已有 | 参见 BUG-FM-003（KE-PM-011）修复经验：数组参数用 URLSearchParams.append | 无差异；本版本无多值过滤参数，但编码规范一致 |
| **前端路由** | vue-router | 生产已有 | 新增 1 条路由 `/device-management/condensation-warnings` | 无差异 |
| **认证** | Django Session + CSRF | 生产已有 | IsAuthenticated 权限类 | 无差异 |
| **Python 运行时** | Python | `>=3.12`（生产已有） | 使用 dataclass, type hints `X | None` 语法 | 无差异 |
| **日志** | Python logging + journald | 生产已有 | SyslogIdentifier=freeark-condensation-consumer | 无差异 |

---

## 新增/变更依赖对照

| 依赖 | 是否新增 | 说明 |
|------|---------|------|
| paho-mqtt | 否 | 已在 requirements.txt，无需修改 |
| django | 否 | 无版本变更 |
| djangorestframework | 否 | 无版本变更 |
| mysqlclient / django-db-backends | 否 | 无变更 |
| Element Plus 组件 | 否 | 仅复用已有组件，无新增 npm 包 |
| 任何新 npm 包 | 否 | 无新增前端依赖 |

**结论：requirements.txt 和 package.json 均无需修改。**

---

## 基础设施约束确认（来自项目记忆）

| 约束 | 状态 | v0.7.0 符合性 |
|------|------|-------------|
| 禁止 Docker，物理机部署 | 有效 | 符合：systemd 服务，无容器化 |
| 生产服务器：树莓派 192.168.31.51 | 有效 | 符合：新服务部署到同一服务器 |
| 生产 DB：MySQL 192.168.31.98:3306 | 有效 | 符合：migration 0029 在此 DB 执行 |
| 部署一律 plink + git pull，禁止 pscp | 有效 | 符合：部署顺序见 architecture_design §8 |
| Restart=on-failure | 有效 | 符合：consumer.service 配置 Restart=on-failure,RestartSec=30s |
| 测试用 SQLite | 有效 | 符合：CondensationWarningEvent Model 无 MySQL 特有字段 |
