# requirement-analyst 项目记忆 — FreeArk

> 格式与规则见 `.codex/sdlc/shared_protocol.md` §M。"已验证"区由 kb-curator 维护；agent 只追加"待验证"区。

## 已验证
- [M-RA-001] 〔增量需求写法〕对已有基线的增量需求，每条标注 `新增 / 变更 / 继承`；继承项只写引用，变更项写"变更前 → 变更后"；约束编号接续基线（基线 C-01~C-05，新增从 C-06 起）；非功能需求同样标注。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-RA-002] 〔小程序业主端（截至 v1.12.0，引用前用 `git grep` 核实仍有效）〕业主角色 `role=user`，接口在 `/api/miniapp/` 下，权限类 `IsOwnerUser`。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-RA-003] 〔小程序业主端（截至 v1.12.0，引用前用 `git grep` 核实仍有效）〕设备标识：`screenMac = OwnerInfo.unique_id`。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-RA-004] 〔小程序业主端（截至 v1.12.0，引用前用 `git grep` 核实仍有效）〕productCode → 角色：270001 主机/集中供暖，130004 新风，260001 主温控，120003 末端温控/房间级。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-RA-005] 〔小程序业主端（截至 v1.12.0，引用前用 `git grep` 核实仍有效）〕接口：骨架 `GET /api/miniapp/owner/structure/?specific_part=`；配置 `GET /api/miniapp/device-settings/config/`；实时值 `GET /api/miniapp/owner/realtime-params/?specific_part=`（5 分钟缓存）；审计 `POST /api/miniapp/device-settings/audit/`（尽力而为）。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-RA-006] 〔小程序业主端（截至 v1.12.0，引用前用 `git grep` 核实仍有效）〕可写 attrTag 白名单：switch、system_switch、temp_set、out_temp_set、mode、energy_supply_mode、energy_saving_sign。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-RA-007] 〔小程序业主端（截至 v1.12.0，引用前用 `git grep` 核实仍有效）〕骨架缓存：TTL 24h（sync_status=pending 时 5min）；两阶段渲染（骨架 ≤300ms → MQTT 值叠加）；网络失败用过期缓存并提示"数据可能已过时"；key `owner_structure_{specific_part}`；骨架缓存不作为可写性的权威来源。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-RA-008] 〔屏端 MQTT 协议（v1.10.0 抓包实测）〕写命令主题 `/screen/service/cloud/to/screen/{screenMac}`，报文 `DeviceWrite`。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-RA-009] 〔屏端 MQTT 协议（v1.10.0 抓包实测）〕值推送主题 `/screen/upload/screen/to/cloud/{screenMac}`（是 upload 不是 service），报文 `DeviceStatusUpdate`。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-RA-010] 〔屏端 MQTT 协议（v1.10.0 抓包实测）〕无独立写回执：写确认 = 8s 内监听到 `DeviceStatusUpdate` 中 attrTag 变为目标值。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-RA-011] 〔屏端 MQTT 协议（v1.10.0 抓包实测）〕值为语义串（on/off、cold/hot/wind/dehumidification、"26.0" 不 ×10）；`deviceSn` 在 DeviceWrite 中是字符串、在 DeviceStatusUpdate 中是整数，需双向兼容。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0

## 用户偏好与禁止项

## 待验证
