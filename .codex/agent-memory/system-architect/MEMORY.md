# system-architect 项目记忆 — FreeArk

> 格式与规则见 `.codex/sdlc/shared_protocol.md` §M。"已验证"区由 kb-curator 维护；agent 只追加"待验证"区。

## 已验证
- [M-SA-001] 〔约束〕禁止 Docker/容器化：部署视图只写 systemd unit + Nginx + Python venv。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SA-002] 〔约束〕双数据库：生产 MySQL（`192.168.31.98:3306`，库 `freeark`），测试 SQLite 内存库（`freearkweb.test_settings`）；连接信息来自配置，不得硬编码。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SA-003] 〔约束〕鉴权：`User.role`（admin / operator / user），后端权限类 `api.views.IsAdminUser`、`api.views.IsOwnerUser`（不是 DRF 内置 IsAdminUser，不用 `is_staff`）。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SA-004] 〔领域模型〕设备数据挂在 `specific_part`（专有部分）之下，是查询的必填入口；`DeviceConfig.device_id`（如 `hvac-main-ctrl`）与 `PLCLatestData.specific_part`（如 `9-1-31-3104`）格式不同，不能直接 JOIN。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SA-005] 〔领域模型〕`screenMac = OwnerInfo.unique_id`。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SA-006] 〔领域模型〕`device_param_history` 是超大表（曾达 3600 万行），涉及它的设计要考虑分批删除与索引。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SA-007] 〔通信〕数据采集经 MQTT broker 与 PLC/屏端通信；小程序直连屏端用独立的共享云 broker。屏端协议细节见 requirement-analyst 知识文件。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SA-008] 〔服务影响〕改动与 systemd 服务的对应关系见 `.agents/skills/freeark-prod-deploy/SKILL.md` §6（如 `api/fault_consumer/` → `freeark-fault-consumer`）。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0

## 用户偏好与禁止项

## 待验证
