# 用户故事 v2 — 方舟龙虾 API 通道与知识增强

```
file_header:
  document_id: US-LOBSTER-002
  project: FreeArk — lobster-agent-api-channel
  version: 2.0.0
  status: APPROVED
  author_agent: requirement-analyst (PM-orchestrated, SDLC 第二轮修订)
  created_at: 2026-05-25
  supersedes: US-LOBSTER-001
  depends_on: REQ-SPEC-LOBSTER-002, PROBES-LOBSTER-001
  change_summary: >
    v1 → v2 变更：
    (1) 新增 US-010 PoC 最小 Skill 验证（REQ-NFR-006 落地）
    (2) 所有 US 中 "Skill" 的实现描述由 "Node.js tool function" 更新为
        "SKILL.md + CLI 子进程"（不影响 AC 验收标准，只影响内部实现描述）
    (3) 角色定义新增"部署工程师"（PoC 验证场景）
    (4) US-001 至 US-009 的 AC 验收标准不变（用户视角不受实现方式影响）
```

---

## 角色定义

| 角色 | 说明 |
|------|------|
| 运维工程师 | FreeArk 日常运维人员，通过 Web 界面监控三恒系统 |
| 暖通工程师 | HVAC 专业人员，负责设备参数调试和问题诊断 |
| 系统管理员 | FreeArk 管理员（role=admin），拥有所有写权限 |
| 方舟龙虾 | OpenClaw main agent，本次改造的目标 AI Agent |
| 部署工程师 | 负责在 Pi 上部署和验证 Skill 的工程师（新增，PoC 场景）|

---

## US-001 至 US-009（完整保留，AC 不变）

US-001 至 US-009 的内容与 v1（US-LOBSTER-001）完全一致，AC 验收标准不变。
用户故事描述的是用户视角的行为和预期，与 Skill 内部实现方式（Node.js/Python/Bash CLI）无关。

以下简要索引（完整内容见 US-LOBSTER-001）：

| US 编号 | 标题 | 优先级 |
|---------|------|--------|
| US-001 | 查询设备实时状态 | P0 |
| US-002 | 查询近期能耗数据 | P0 |
| US-003 | 诊断三恒系统故障 | P0 |
| US-004 | 下发设备参数（Tier-2 写操作） | P1 |
| US-005 | 查询 PLC 连接状态 | P0 |
| US-006 | 查看系统服务状态 | P1 |
| US-007 | 触发按需数据采集 | P2 |
| US-008 | 查看写操作历史记录 | P1 |
| US-009 | Agent 知识问答（无 API 调用） | P0 |

---

## US-010（新增）：PoC 最小 Skill 加载验证

**As** 部署工程师，
**I want** 在扩展到 19 个 tool 之前，先验证最小 Skill（1 个 tool）能够被 OpenClaw 成功加载和调用，
**So that** 确保 SKILL.md 格式和 CLI 调用协议正确，避免重蹈第一轮架构假设错误的覆辙。

**优先级**：P0（开发阶段第一里程碑，阻塞后续 tool 实现）

**关联需求**：REQ-NFR-006（PoC 强制前置验证）

**验收标准**：

- Given：`agents/freeark-skill/SKILL.md` 仅实现 1 个只读 tool（`freeark_get_realtime_params`），
  配套 CLI 脚本已在 Pi 本地可执行
- When：在 Pi 上运行 `systemctl --user restart openclaw-gateway.service`
- Then：
  - Gateway 启动日志无 "Invalid config" 或 "Invalid input" 错误
  - `openclaw skills list`（或等效命令）显示 freeark-skill 已加载
  - 通过 Web 聊天界面，用户问"3号楼1单元702室温度？"，Agent 调用该 tool，
    返回 `GET /api/devices/realtime-params/` 的真实数据

- Given：PoC 验证通过
- When：部署工程师记录验证结果
- Then：`code_review_report_v2.md` 中有明确的"PoC PASS"记录，作为进入完整 19 tool 开发的门控证据

---

## US-011（新增）：Token 脱敏合规

**As** 系统管理员，
**I want** 在部署脚本或管理命令输出 Token 时，Token 值被自动脱敏为 `[REDACTED-40HEX]`，
**So that** 避免 Token 出现在 AI 对话上下文或日志中，防止 RISK-3 复发。

**优先级**：P0（安全合规）

**关联需求**：REQ-NFR-007（Token 脱敏强制规范）

**验收标准**：

- Given：执行 `create_openclaw_agent_user --force-regenerate-token` 或类似命令
- When：命令输出（stdout + stderr 全部）经过管道处理
- Then：输出中的所有 40 字符 hex 字符串（`[a-f0-9]{40}`）被替换为 `[REDACTED-40HEX]`
- Then：Claude 对话上下文中不出现任何明文 Token

- Given：deployment_plan_v2.md §4 中的账号操作步骤
- When：工程师按照 SOP 操作
- Then：每条可能输出 Token 的命令后面都有 `| sed -E 's/[a-f0-9]{40}/[REDACTED-40HEX]/g'` 管道
