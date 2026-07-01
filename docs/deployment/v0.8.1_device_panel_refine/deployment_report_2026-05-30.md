# v0.8.1 设备面板修正与新增 — 生产部署报告

- **日期**：2026-05-30
- **提交**：`eb19665`
- **生产 HEAD**：`3ad7afd` → `eb19665`（fast-forward）
- **部署人**：Claude Code（用户 CONFIRM 授权）
- **类型**：纯前端，唯一文件 DeviceCardsView.vue，无后端/数据库迁移，无服务重启

## 需求范围（5 条）

| 需求 | 内容 |
|------|------|
| REQ-UI-006 | 撤销 v0.8.0 导航栏两行拆分，复原单行 Tab + 历史数据链接（保留 goBack 来源跳转、按钮 min-width） |
| REQ-UI-007 | 下方详细数据面板分两行：第一行温控面板(panel_*)，第二行系统设备(新风/能耗/水力/空气) |
| REQ-UI-008 | 两行各自可折叠，默认展开，切换 specific_part 时重置展开 |
| REQ-UI-009 | 故障值由红色字体 → 红底白字徽章（框起来） |
| REQ-UI-010 | 温控面板凝露提醒 0→"无"、1→"告警"（黄底#faad14 深色字徽章），仅匹配 *_condensation_alert 字段 |

## 部署步骤

1. 本地提交 + push origin main（1 vue + 2 文档，不触碰 .env/package-lock/heartbeat_broker_config.json）
2. ⚠️ 公司 DNS 偶发无法解析 vicp.fun，采用绕过：8.8.8.8 解析得 IP 115.236.153.170，ssh + HostKeyAlias=域名 直连
3. 生产 `git pull origin main` → fast-forward 至 eb19665
4. 生产 `cp -r dist <备份>` + `npm run build` → `✓ built in 18.88s`，0 报错
5. nginx 直接服务 dist/，即时生效，无需重启

## 验证（生产 dist 落地核查）

| 项 | 证据 |
|----|------|
| 凝露映射 | `assets/DeviceCardsView-B0YcoOcw.js` 含 "告警" + "status-condensation-alert" |
| 导航栏复原 | assets/*.js 无 "nav-row--thermostat" 残留 |
| 构建时间 | index.html 2026-05-30 13:51:32 +0800 |
| 本地 build | ✓ built in 10.29s，0 报错 |

## 待人工验收（运行时 E2E，自动化覆盖不到外观）

- 凝露提醒"告警"黄框、"无"显示
- 故障值红底白字框
- 温控/系统设备两行折叠展开（默认展开）
- 4 房 / 5 房真实数据下两行布局
- 导航栏复原为单行 + 历史数据链接，goBack 来源跳转仍正常
