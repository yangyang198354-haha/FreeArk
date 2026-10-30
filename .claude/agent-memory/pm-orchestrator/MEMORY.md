# pm-orchestrator 项目记忆 — FreeArk

> 格式与规则见 `.claude/agents/shared_protocol.md` §M。"已验证"区由 kb-curator 维护；agent 只追加"待验证"区。

## 已验证
- [M-PM-001] 〔领域〕楼宇/物业数据都挂在 **specific_part（专有部分/住宅单元）** 之下；设备相关 API 以 specific_part 为必填入口，不能由后端从设备 ID 反推。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-PM-002] 〔领域〕`DeviceConfig.device_id`（如 `hvac-main-ctrl`）与 `PLCLatestData.specific_part`（如 `9-1-31-3104`）不是同一种东西，混用导致"面板永远为空"。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-PM-003] 〔领域〕曾有设计写 GenericDeviceHandler、实际实现为 PLCLatestDataHandler；曾有 `/device-cards` 路由无入口且无法自动携带 `specific_part`。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-PM-004] 〔门控〕GROUP_D 复跑：后端全量约 2–5 分钟；改动涉及 models / urls / settings / 中间件时跑全量，否则跑相关模块。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-PM-005] 〔门控〕生产部署一切以 `.claude/skills/freeark-prod-deploy/SKILL.md` 为准。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-PM-006] 〔门控·交付完整性〕前端新页面必须核对"导航入口"：全部应用里是否存在可达的按钮/链接；需要上下文参数的页面，入口要放在能自然提供该参数的页面（如专有部分详情页），并自动携带参数；只注册路由等于未交付。 — conf 0.9 · 证据 旧知识库 KE-PM-004 迁移（/device-cards 无任何入口） · 首见 2026-10-30 · 命中 0

## 用户偏好与禁止项

## 待验证
