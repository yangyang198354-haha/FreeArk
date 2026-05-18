# 技术栈说明

**文档编号**: ARCH-TECH-DEVICE-SETTINGS-001  
**项目名称**: FreeArk 设备参数设置功能  
**版本**: 0.3.0-APPROVED  
**状态**: APPROVED（v0.3.0：2026-05-19 broker WebSocket 端口确认为 32797）  
**创建日期**: 2026-05-19  
**最后更新**: 2026-05-19  
**作者**: system-architect (via pm-orchestrator)  
**审核**: pm-orchestrator（v0.3.0 端口确认审核通过）

---

## 1. 现有技术栈（无需改动）

| 层次 | 技术 | 版本（来自代码/配置） | 角色 |
|------|------|---------------------|------|
| 后端框架 | Django | 5.2.x | Web 框架 |
| 后端 API | Django REST Framework | 已安装（views.py 中导入） | RESTful API |
| 后端认证 | DRF Token Auth | 已配置 | Token 鉴权 |
| 后端 WSGI | Waitress | 已使用（start_waitress_server.py） | 生产 HTTP 服务器 |
| 后端 MQTT 客户端 | paho-mqtt | 已使用（mqtt_consumer.py） | 消息发布/订阅 |
| 后端 ORM | Django ORM | — | 数据库访问 |
| 数据库（生产） | MySQL | 192.168.31.98:3306 | 持久化存储 |
| 数据库（测试） | SQLite | 内置 | 单元测试 |
| PLC 通信 | python-snap7 | 已使用（plc_write_manager.py） | S7 协议写 PLC |
| 前端框架 | Vue 3 | ^3.5.13（package.json） | SPA 框架 |
| 前端 UI 库 | Element Plus | ^2.8.7（package.json） | UI 组件（按钮/弹窗/表单）|
| 前端构建 | Vite | ^6.0.1（package.json） | 打包工具 |
| 前端 HTTP 客户端 | Axios | ^1.7.9（package.json） | API 调用 |
| 前端路由 | Vue Router | ^4.4.5（package.json） | SPA 路由 |
| 部署方式 | git + plink + Waitress | — | 物理机部署（树莓派）|

---

## 2. 本次新增依赖

| 层次 | 技术 | 版本建议 | 用途 | 引入理由 |
|------|------|---------|------|---------|
| 前端 NPM | `mqtt`（mqtt.js） | ^5.x | MQTT-over-WebSocket 客户端 | 前端直连 broker WebSocket 实现实时回执推送（ADR-01）|

**mqtt.js 评估**：
- 包大小：约 200KB gzip，不影响首屏加载（按需 import，仅设置面板组件引用）
- ESM 支持：v5.x 原生 ESM，与 Vite 构建兼容
- 浏览器 WebSocket 支持：原生支持，无需 polyfill
- 安装命令：`npm install mqtt --save`
- 无需新增 devDependency

**后端新增 Python 包**：无（paho-mqtt 已存在，uuid 为标准库，无额外依赖）

---

## 3. 明确不引入的技术

| 技术 | 原因 |
|------|------|
| Docker / Docker Compose | 基础设施约束：物理机部署，禁止 Docker |
| Django Channels | 会要求替换 Waitress 为 Daphne/Uvicorn（ASGI），改动量大；ADR-01 选择前端直连 broker WebSocket 替代 |
| Redis | Django Channels 方案的依赖，一并排除 |
| Celery | 异步任务量小（单次 MQTT publish），不值得引入 Celery broker |
| WebSocket Proxy（Nginx WebSocket upstream） | 若 broker 直接支持 WebSocket 端口，无需反向代理 |
| GraphQL | 现有 REST API 已满足需求 |
| TypeScript | 现有前端全为 JS，本次保持一致 |

---

## 4. 基础设施约束合规检查

| 约束条件 | 合规状态 | 说明 |
|---------|---------|------|
| 物理机部署，禁止 Docker | 合规 | 所有组件均在物理机进程中运行 |
| 生产服务器：树莓派 192.168.31.51 | 合规 | Django + datacollection 均部署在树莓派；mqtt.js 运行在浏览器端 |
| 生产 DB：MySQL@192.168.31.98:3306 | 合规 | `plc_write_record` 表在 MySQL 中创建，Django ORM 自动处理 |
| 测试 DB：SQLite | 合规 | `settings.py` 中 `_RUNNING_TESTS` 自动切换 SQLite |
| 部署通过 plink + git pull | 合规 | 部署脚本见 architecture_design.md 第 7 节 |

---

## 5. MQTT Broker WebSocket 端口（关键前置条件）

本架构方案要求 broker（192.168.31.98）开启 WebSocket 监听端口。

**已确认**（2026-05-19 用户确认）：
- TCP 端口 32788（datacollection 发布）、32795（Django 后端默认 fallback）均已在使用
- **WebSocket 端口已确认为 32797**，前端连接地址：`ws://192.168.31.98:32797/mqtt`

在 `src/config/mqtt.js` 中配置：
```javascript
export const MQTT_BROKER_WS_URL = import.meta.env.VITE_MQTT_WS_URL 
  || 'ws://192.168.31.98:32797/mqtt'
```

此前置条件已关闭，无需降级方案。

---

## 6. 版本兼容性矩阵

| 组件 | 当前版本 | 本次变更 | 兼容性 |
|------|---------|---------|-------|
| Django | 5.2.x | 新增 views、models、urls | 完全兼容，标准 Django 功能 |
| Vue 3 | ^3.5.13 | 新增组件、composable | 完全兼容，Composition API |
| Element Plus | ^2.8.7 | 新增 el-dialog、el-collapse 用法 | 完全兼容，已有组件 |
| Vite | ^6.0.1 | 新增 npm 包 mqtt | 兼容（mqtt.js ESM 支持）|
| paho-mqtt | 现有版本 | 新增 publish 调用路径 | 无版本变更 |
| python-snap7 | 现有版本 | 通过 PLCWriteSubscriber 调用现有 write_db_data() | 无版本变更 |
| MySQL | 生产版本 | 新增 plc_write_record 表（migration 自动创建）| 完全兼容 |
