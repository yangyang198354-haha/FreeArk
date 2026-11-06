# TRAE SDLC 套件运行时配置（等效 `.claude/settings.json`）

> 本文件是 `.claude/settings.json` 的 TRAE 对应物：TRAE 没有 hook 运行时，也没有
> `permissions.ask` 配置项，因此把「拦截」改为「**强制脚本 + 提示词约束 + 主控复核**」。
> 源套件（`.claude/**`）保持只读，本文件不修改它。

## 1. Hook 映射

| Claude Code hook | 原文件 | TRAE 等效 | 调用时机 |
|---|---|---|---|
| `PreToolUse` (Agent) | `.claude/hooks/sdlc_pre_agent.py` | `python .trae/sdlc/scripts/sdlc_preflight.py --check-cwd` | PM 在**每次**调用 `sdlc-*` 子技能前 |
| `SubagentStop` | `.claude/hooks/sdlc_subagent_stop.py` | `python .trae/sdlc/scripts/kb_inbox.py --check-response --text-file <reply>` | 子技能返回后、PM 门控前（**必须**） |
| `PreToolUse` (WebFetch/WebSearch) | `.claude/hooks/sdlc_webfetch_guard.py` | `python .trae/sdlc/scripts/webfetch_guard.py --url <u>` / `--search` | agent-builder 联网前 |
| 收件箱自动收集 | 同上 SubagentStop | `python .trae/sdlc/scripts/kb_inbox.py --agent <a> --text-file <reply>` | 每次子技能返回后 |
| `permissions.ask`（ssh/scp/git push/安装依赖） | `.claude/settings.json` | TRAE 工具审批（用户可见的权限确认）+ 画像 P9 规则 | 执行前 |

## 2. 关键差异与补偿

| 能力 | Claude Code | TRAE | 补偿方式 |
|---|---|---|---|
| 子代理 | `Agent` 工具 + 独立上下文 | `Skill` 工具 + **共享上下文** | PM 必须在同一轮内完成落盘校验与门控；禁止并行加载多个角色技能 |
| 项目记忆 | `memory: project` **自动注入**前 200 行 | **不自动注入** | 每个 `sdlc-*` 技能的第 1 步必须 Read `.trae/sdlc/agent-memory/{agent}/MEMORY.md` |
| 通用知识库 | `knowledge_base/generic/*.md` 必读 | 同（已迁移到 `.trae/sdlc/knowledge_base/generic/`） | 必读清单中列全路径 |
| 记忆写权限 | 运行时按 agent 隔离 | 由协议 §A 约束 | PM 门控时抽查 |
| 时间 | `date -Iseconds` | Windows: `Get-Date -Format o`；Linux/macOS: `date -Iseconds` | 文件头与 phase_status 必须使用**真实**输出 |
| 禁用写 `report*.md` | 运行时拦截 | 无拦截 | 协议 §M-4 提示词约束；PM 门控核对文件名 |

## 3. 目录约定（TRAE）

```
.trae/
├── skills/sdlc-*/SKILL.md          ← 9 个技能（1 编排 + 1 协议 + 6 角色 + kb-curator + agent-builder）
│   └── sdlc-agent-builder/templates/agent_builder_templates.md
└── sdlc/
    ├── project_profile.md          ← 画像（PM 生成；status=DRAFT→APPROVED）
    ├── project_profile.template.md
    ├── knowledge_base/
    │   ├── generic/{agent}.md      ← 通用知识（跨项目）
    │   └── README.md
    ├── agent-memory/{agent}/MEMORY.md
    ├── scripts/                     ← hook 等效脚本
    └── suite_config.md              ← 本文件
```

工作区（`{DOCS}`）与代码目录由画像 P2/P3 决定；缺省仍是
`project_workspace/{project_name}/`（nested）+ `{DOCS}/src`。

## 4. 启动方式

1. 在主会话中调用 `Skill: sdlc-orchestrator`；
2. PM 先跑 `sdlc_preflight.py --check-all`；
3. 画像缺失或 `status=DRAFT` → 先生成/确认画像，再进入流程。

## 5. 安全

- 本文件与 `.claude/**` 都不得写入任何凭据；
- `agent-builder` 即使获得 `WRITE_TARGET` 授权，也不得修改 `.claude/**` 与
  `.trae/sdlc/scripts/**`、`.trae/sdlc/suite_config.md`；
- 远程操作（ssh/scp/git push）与依赖安装一律需要用户当轮确认（画像 P9）。
