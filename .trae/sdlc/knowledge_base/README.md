# 知识库（TRAE 版；规则见共享协议 §M 与 §T-3）

三层：
- `generic/{agent}.md` —— **通用经验**，与项目无关，随套件分发；技能开工时必读。只有 sdlc-kb-curator 在用户确认后写入。
- `.trae/sdlc/agent-memory/{agent}/MEMORY.md` —— **项目记忆**。TRAE 不自动注入：每个技能第 1 步显式 Read（不存在视为空）。"已验证"区由 kb-curator 维护，agent 只能追加"待验证"区。
- `project_workspace/_kb_inbox.jsonl` —— **经验收件箱**。PM 在每次子技能返回后运行 `python .trae/sdlc/scripts/kb_inbox.py --agent <agent> --text-file <reply>` 收集 `<kb_proposals>`（共享协议 §T-2）。

蒸馏：PM 交付后加载 `Skill: sdlc-kb-curator`（PHASE_12），也可在主会话中单独加载。报告与日志在 `project_workspace/_kb_distillation/`。

项目事实（目录、命令、环境、禁用项）放 `../project_profile.md`，不放知识库或记忆。
