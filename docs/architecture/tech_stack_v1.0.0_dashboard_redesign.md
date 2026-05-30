# 技术栈说明

```
file_header:
  document_id: TECH-v1.0.0-DASHBOARD-REDESIGN
  title: 系统看板重设计 + 设备列表凝露提醒列 — 技术栈
  author_agent: sub_agent_system_architect
  project: FreeArk 住宅能耗/暖通监控平台
  version: v1.0.0
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: DRAFT
```

---

## 技术栈变更说明

本次变更**不引入任何新技术栈组件**，完全复用现有技术栈。

| 层级 | 现有技术 | 本次新增 | 说明 |
|------|---------|---------|------|
| 后端框架 | Django 4.x + DRF | 无 | 新增 2 个视图函数，复用现有 @api_view 装饰器 |
| 数据库 | 测试用 SQLite / 生产用 MySQL 8.0 | 无 | 无新 migration |
| 缓存 | Django LocMemCache | 无 | 新增查询不使用缓存（见 ADR-v100-01/02） |
| 前端框架 | Vue 3 + Element Plus | 无 | 修改现有 Vue 文件 |
| 前端路由 | Vue Router 4 | 无 | 复用现有 router.push 和 useRoute/useRouter |
| HTTP 客户端 | axios（封装为 api.js） | 无 | 复用现有 api.get() 调用 |
| 图标库 | @element-plus/icons-vue | 可能新增 `Warning`、`Odometer` | 从现有已安装包中导入，无新依赖 |
| 部署方式 | 物理机 systemd，git pull 部署 | 无 | 遵循现有部署规范 |
| 测试 | Django TestCase + SQLite（测试 DB） | 无 | 沿用现有测试基础设施 |

## 受影响服务

| 服务 | 是否需要重启 | 原因 |
|------|------------|------|
| freeark-backend（gunicorn/uwsgi） | 是 | views.py + urls.py 修改 |
| freeark-fault-consumer | 否 | 仅读取其写入的 FaultEvent 数据，无逻辑改动 |
| freeark-condensation-consumer | 否 | 仅读取其写入的 CondensationWarningEvent 数据 |
| 前端（nginx static） | 是（需重新 npm build） | Vue 文件修改 |
