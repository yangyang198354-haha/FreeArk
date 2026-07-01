# v0.8.0 UI 修复 — 生产部署报告

- **日期**：2026-05-30
- **提交**：`3ad7afd` feat(ui): v0.8.0 UI 修复一批
- **生产 HEAD**：`4765cf4` → `3ad7afd`（fast-forward）
- **部署人**：Claude Code（用户 CONFIRM 授权）
- **类型**：纯前端，无后端/数据库迁移，无服务重启

## 需求范围（6 条）

| 需求 | 内容 |
|------|------|
| REQ-UI-001 | 结露预警状态文案"未回复/已回复"→"未恢复/已恢复" |
| REQ-UI-002 | 结露预警新增"操作"列，含"设备面板"按钮（同标签页 router.push，from=condensation-warnings） |
| REQ-UI-003 | 故障管理"查看设备面板"→"设备面板" |
| REQ-UI-004 | 设备面板返回按钮按 query.from 跳回来源页（故障管理/结露预警/设备列表）；故障与结露改为同标签页跳转 |
| REQ-UI-005-A | 返回/参数设置按钮 min-width:80px + header 左右 padding，不贴边样式统一 |
| REQ-UI-005-B | 设备面板 Tab 分两行：温控面板组(4或5随房间数)/系统设备组(新风/能耗/水力/空气) |

## 改动文件

- `FreeArkWeb/frontend/src/views/CondensationWarningView.vue`
- `FreeArkWeb/frontend/src/views/FaultManagementView.vue`
- `FreeArkWeb/frontend/src/views/DeviceCardsView.vue`

## 部署步骤

1. 本地提交 + push origin main（仅 3 vue + 4 文档，不触碰 .env/package-lock/heartbeat_broker_config.json）
2. 生产 `git pull origin main` → fast-forward 至 3ad7afd
3. 生产 `cp -r dist <备份>` + `npm run build` → `✓ built in 19.61s`，0 报错
4. nginx 直接服务 dist/，即时生效，无需重启

## 验证（生产 dist 落地核查）

| 项 | 证据 |
|----|------|
| "未恢复"文案 | `assets/CondensationWarningView-eVp0mV9g.js` 含 |
| from 来源标识 | `assets/DeviceCardsView-*.js` 含 "condensation-warnings" |
| Tab 分组 | `assets/DeviceCardsView-*.js` 含 "系统设备/温控面板" |
| 构建时间 | index.html 2026-05-30 11:54:31 +0800 |
| 路由路径匹配 | goBack 目标 /device-management/{faults,condensation-warnings,device-list} 与 router/index.js 一致 |

## 待人工验收（运行时 E2E）

项目无 Cypress/Vitest，以下需浏览器人工点验：
- 三个来源页进入设备面板后"返回"按钮各自跳回正确来源页
- 设备面板 Tab 在真实 4 房/5 房数据下两行分组渲染外观
- 结露预警"设备面板"按钮跳转正确
