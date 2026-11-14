# pm-orchestrator 项目记忆 — FreeArk

> 格式与规则见 `.codex/sdlc/shared_protocol.md` §M。"已验证"区由 kb-curator 维护；agent 只追加"待验证"区。

## 已验证
- [M-PM-001] 〔领域〕楼宇/物业数据都挂在 **specific_part（专有部分/住宅单元）** 之下；设备相关 API 以 specific_part 为必填入口，不能由后端从设备 ID 反推。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-PM-002] 〔领域〕`DeviceConfig.device_id`（如 `hvac-main-ctrl`）与 `PLCLatestData.specific_part`（如 `9-1-31-3104`）不是同一种东西，混用导致"面板永远为空"。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-PM-003] 〔领域〕曾有设计写 GenericDeviceHandler、实际实现为 PLCLatestDataHandler；曾有 `/device-cards` 路由无入口且无法自动携带 `specific_part`。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-PM-004] 〔门控〕GROUP_D 复跑：后端全量约 2–5 分钟；改动涉及 models / urls / settings / 中间件时跑全量，否则跑相关模块。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-PM-005] 〔门控〕生产部署一切以 `.agents/skills/freeark-prod-deploy/SKILL.md` 为准。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-PM-006] 〔门控·交付完整性〕前端新页面必须核对"导航入口"：全部应用里是否存在可达的按钮/链接；需要上下文参数的页面，入口要放在能自然提供该参数的页面（如专有部分详情页），并自动携带参数；只注册路由等于未交付。 — conf 0.9 · 证据 旧知识库 KE-PM-004 迁移（/device-cards 无任何入口） · 首见 2026-10-30 · 命中 0
- [M-PM-007] 〔仓库配置〕`.gitignore:146` 的 `sdlc/` 规则会让 **`.agents/sdlc/` 整目录**（协议、画像、记忆、通用知识、技能）被判为忽略对象，只有 `.codex/sdlc/` 在 148-149 行被豁免；另 `.gitignore:66` 的 `output/*` 使放在 `output/` 下的沙箱 `{DOCS}` 全部不可入库。派活前用 `git check-ignore -v <路径>` 定位到具体规则行，再决定是否补精确豁免（`!.agents/sdlc/` + `!.agents/sdlc/**`）。 — conf 0.8 · 证据 `git check-ignore -v` 实测（→ `.gitignore:146:sdlc/` 与 `.gitignore:66:output/*`）+ PM 本次 clarification 独立发现 · 首见 2026-11-01 · 命中 1
- [M-PM-008] 〔门控·口径冲突〕需求 AC 与 `module_design` 的数值口径冲突时（本轮 AC-11-04"失败计数继续累加" vs 设计 clamp"到阈值不再累加"），不静默取舍：按设计口径实现，在交付报告"口径差异"表与用例断言中显式固化，并写清单处修改点（`utils/networkAlert.js:62`）。 — conf 0.6 · 证据 GR-C-1-F02 + `delivery_report.md:51` + 复核 `miniprogram/utils/networkAlert.js:62`（`Math.min`） · 首见 2026-11-01 · 命中 1
- [M-PM-009] 〔调用契约〕给子代理下发写权限时表述必须与协议 §A 一致：§A 与 §M-2 允许 agent 自记"待验证"区，因此写"不可写 `.agents/`"会自相矛盾（本轮 GROUP_C 照协议写记忆，门控只能记 MINOR）。要沙箱纯净就精确写"禁止写 `.agents/sdlc/memory/**`"。 — conf 0.6 · 证据 GR-C-1-F01 + `delivery_report.md:52` + 协议 §A 写权限表末行 · 首见 2026-11-01 · 命中 1

## 用户偏好与禁止项

## 待验证
