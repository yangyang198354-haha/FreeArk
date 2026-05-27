# 技术栈说明

```
file_header:
  document_id: TECH-v0.5.3-FCC
  title: 设备列表「故障数量」列 + OpenClaw 故障查询工具 — 技术栈
  author_agent: sub_agent_system_architect (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: v0.5.3-fault-count-column
  created_at: 2026-05-26
  status: DRAFT
  references:
    - docs/architecture/architecture_design_v0.5.3_fault_count_column.md
    - FreeArkWeb/backend/freearkweb/freearkweb/settings.py
```

---

## 1. 沿用现有技术栈（无新增依赖）

本版本（v0.5.3-FCC）完全沿用 FreeArk 现有技术栈，**不引入任何新的第三方库或基础设施组件**。

| 层次 | 技术 | 版本/说明 | 本版本变化 |
|------|------|---------|-----------|
| 后端框架 | Django + Django REST Framework | 同现有生产版本 | 无变化 |
| 后端服务器 | Waitress（单进程多线程） | 同现有生产版本 | 无变化 |
| 后端缓存 | Django LocMemCache | Django 内置，无需安装 | **利用现有**，无新增配置 |
| 数据库 | MySQL 192.168.31.98:3306 | 同现有生产版本 | 无 schema 变更（无 migration）|
| MQTT | paho-mqtt ≥1.6.1,<2.0 | 同现有生产版本 | 无变化 |
| 前端框架 | Vue 3 + Element Plus | 同现有生产版本 | 无新增组件 |
| 前端状态管理 | 无新增 Store/Composable | — | 无变化 |
| AI 助手 | OpenClaw 2026.5.20 on Pi | DeepSeek v4-flash | 无变化（仅更新 SKILL.md）|
| 部署方式 | git pull + systemctl | — | 无变化 |
| 运行平台 | 树莓派 192.168.31.51 | — | 无变化 |

---

## 2. 关键技术选型说明

### 2.1 缓存：Django LocMemCache（进程内缓存）

Django 内置的 LocMemCache 是线程安全的进程内字典缓存，无需额外安装 Redis 或 Memcached。在 Waitress 单进程多线程部署模式下，所有请求线程共享同一缓存实例，命中率与 Redis 等价。

**缓存 TTL**：60 秒（ADR-FC-005 修订值，满足 US-FC-05 ≤60s 延迟约束；OQ-01 裁决后不采用 MQTT 事件驱动失效，完全依赖 TTL 刷新）。

**无需修改 settings.py**：Django 在未显式配置 `CACHES` 时默认使用 LocMemCache，当前生产 settings.py 未配置 `CACHES`，行为符合预期。

若后续需要确认，可在 `settings.py` 中明确添加（可选）：
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'freeark-fault-cache',
    }
}
```

**架构演进**：LocMemCache 仅适用于单进程部署，未来多进程/多机扩展时需迁移至 Redis（见 AB-001，`architecture_design_v0.5.3_fault_count_column.md` 第 12 节）。

### 2.2 数据库查询：Django ORM Q 对象

故障字段查询使用 Django ORM 的 `Q` 对象组合 OR 条件，生成单条高效 SQL，利用 `PLCLatestData` 表上已有的 `(specific_part, param_name)` 唯一索引。

无需引入原生 SQL 或额外 ORM 扩展。

### 2.3 前端颜色渲染：CSS 变量（内联样式）

颜色渲染使用全局 CSS 变量 `var(--color-success)` 和 `var(--color-danger)`，这些变量已在 `global.css` 中定义，与 `DeviceCardsView.vue` 同源，无需引入新的样式系统。

---

## 3. 无新增基础设施

| 组件 | 是否需要 | 理由 |
|------|---------|------|
| Redis | 否（v0.5.3 不需要）| v0.5.3 使用 LocMemCache，满足 Waitress 单进程多线程部署；详见 AB-001 |
| 新 Python 库 | 否 | 全部使用 Django 内置和现有依赖 |
| 新 npm 包 | 否 | Vue 3 + Element Plus 已满足需求 |
| 新 systemd service | 否 | 无需新增后台服务 |
| 数据库 migration | 否 | 无 schema 变更 |
| nginx 配置变更 | 否 | 新 API 路由由 Django urls.py 处理 |

---

## 4. 未来可能新增（架构演进，非本版本范围）

| 组件 | 引入条件 | 说明 |
|------|---------|------|
| **Redis** | AB-001 触发条件满足时（多进程部署或第二个跨进程缓存需求）| 替换 LocMemCache；切换时仅需修改 `settings.py` CACHES 配置，应用层代码无需修改。待部署期补充 Redis 连接 URL（格式：`redis://127.0.0.1:6379/1`）|
| `django-redis` | 同 Redis | Django 官方推荐的 Redis cache 后端库；或使用 Django 4.0+ 内置 Redis 后端 |

> 详见 `architecture_design_v0.5.3_fault_count_column.md` 第 12 节 AB-001。
