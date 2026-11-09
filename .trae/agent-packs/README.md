# TRAE 单文件注册包（SDLC Agent Suite v3.9）

> 由 `.trae/sdlc/scripts/port_from_claude.py` 从 `.claude/agents/*.md` 生成。
> 每个 pack 的正文与对应 `.trae/skills/<skill>/SKILL.md` 的正文**逐字一致**（不含 frontmatter），
> `python .trae/sdlc/scripts/suite_selftest.py` 会断言该一致性。
> 源套件 `.claude/**` 保持只读，不被本生成器修改。

| Pack | Skill | 用途 |
|---|---|---|
| `01-pm-orchestrator.md` | `sdlc-orchestrator` | sdlc-orchestrator 的单文件提示词 |
| `02-requirement-analyst.md` | `sdlc-requirement-analyst` | sdlc-requirement-analyst 的单文件提示词 |
| `03-system-architect.md` | `sdlc-system-architect` | sdlc-system-architect 的单文件提示词 |
| `04-software-developer.md` | `sdlc-software-developer` | sdlc-software-developer 的单文件提示词 |
| `05-test-engineer.md` | `sdlc-test-engineer` | sdlc-test-engineer 的单文件提示词 |
| `06-devops-engineer.md` | `sdlc-devops-engineer` | sdlc-devops-engineer 的单文件提示词 |
| `07-agent-builder.md` | `sdlc-agent-builder` | sdlc-agent-builder 的单文件提示词 |
| `08-kb-curator.md` | `sdlc-kb-curator` | sdlc-kb-curator 的单文件提示词 |

## 使用方式

1. **TRAE 会话**：优先 `Skill: sdlc-*`（技能会加载运行时脚本、记忆与知识库路径）。
2. **无 skills 的平台**：把对应 pack 全文作为该角色的系统提示；须同时把 `.trae/skills/sdlc-shared-protocol/SKILL.md` 作为参考资料提供——pack 不含协议全文，TRAE 适配在协议 §T。
3. **不要在 pack 或 SKILL.md 上手改**：重跑生成器即可同步。角色内容由套件维护者改 `.claude/agents/*.md`；TRAE 专属适配改 `.trae/sdlc/scripts/port_from_claude.py`。运行中的 agent 不得修改两者（共享协议 §T-5）。
