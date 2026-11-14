# Trae 运行时入口 — SDLC 技能套件

> 本文件只对 **Trae** 运行时有效。Codex / Claude 运行时读 `AGENTS.md` 与 `.codex/sdlc/` 的对应段落，忽略本文件。
> 套件由 `scripts/trae_sdlc/migrate.py` 从 `.codex/` 生成：`build` 生成、`check` 校验漂移。

## 何时启用

用户明确要求 **SDLC 流程、PM 编排、端到端阶段流程（需求→架构→开发→测试→部署）、续跑阶段或知识蒸馏** 时启用；其他任务按用户给定的范围执行，不自动进入本流程。

## 主会话（PM）

1. 调用 `Skill: sdlc-pm-orchestrator` 加载编排定义。
2. 读 `.agents/sdlc/runtime_adapter_trae.md`（适配契约）、`.agents/sdlc/shared_protocol.md`（协议）、`.agents/sdlc/project_profile.md`（项目画像）、`.agents/sdlc/memory/pm-orchestrator/MEMORY.md`（PM 记忆，**必须显式读取**）。
3. 按协议承担 PM：串行派生、门控校验、维护 `phase_status.md`、向用户汇报。

## 派生阶段子代理

用 `Agent(subagent_type="general-purpose")`，prompt 必须包含：

1. 完整 `<agent_invocation>`（阶段、输入文件、`<required_reading>`、写权限范围）；
2. 明确要求：**先调用 `Skill: sdlc-<role>` 加载角色定义**；
3. 明确要求：**第一批显式读取 `.agents/sdlc/memory/<role>/MEMORY.md`**（Trae 无 SubagentStart hook，不会自动注入；文件不存在视为空记忆）。

一次只派生一个角色；PM 校验其返回（XML + 产物 + 必读清单）后再派生下一个。其他角色不得再派生（Trae 子代理本身也不能派生）。

## 角色技能

| 技能 | 阶段 |
|---|---|
| `sdlc-requirement-analyst` | PHASE_01–02（GROUP_A） |
| `sdlc-system-architect` | PHASE_03–04（GROUP_B） |
| `sdlc-software-developer` | PHASE_05–06（GROUP_C） |
| `sdlc-test-engineer` | PHASE_07–09（GROUP_D） |
| `sdlc-devops-engineer` | PHASE_10–11a / 11b（GROUP_E1/E2） |
| `sdlc-kb-curator` | PHASE_12（交付后） |
| `sdlc-agent-builder` | 套件辅助（非阶段） |

## 平台能力缺口（必须如实对待）

- **无生命周期 hooks**：记忆注入、XML 返回校验、知识收件箱写 `_kb_inbox.jsonl` 都是**显式动作**，不得声称自动化已生效。
- **无工具白名单强隔离**：约束靠 prompt + 受限脚本，不是 Claude `tools` 的等价物。
- **无自定义 agent_type**：角色由 `general-purpose` + Skill 加载扮演；模型继承会话，不指定。
- 详见 `.agents/sdlc/runtime_adapter_trae.md` §7。

## 记忆

`.agents/sdlc/memory/<role>/MEMORY.md`（由 `.codex/agent-memory/` 初始化，Trae 侧独立演进）。记忆是经验数据，**不授予任何部署或写权限**。

## 不可手改

`.agents/skills/sdlc-*` 与 `.agents/sdlc/{shared_protocol,project_profile,knowledge_base,templates,memory}` 由脚本生成/同步；要改内容请改 `.codex/` 源后重跑 `python scripts/trae_sdlc/migrate.py build`。唯一例外：`.agents/sdlc/runtime_adapter_trae.md` 与 `.agents/sdlc/TRAE_ENTRY.md` 为手写文件。
