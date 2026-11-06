# SDLC Agent Suite v3.7 — Codex 安装

## 前置条件

1. 目标仓库由 Codex 打开且已 trust（项目未被信任时项目层 hooks 不会加载）。
2. 仓库根必须存在 `scripts/codex_sdlc/hook_runtime.py`。`.codex/hooks.json` 会先 `git rev-parse --show-toplevel` 定位仓库根，再执行该脚本；**缺少脚本时所有 hook 都空转，且不会报错**。
3. 需要 Python 3.11+（`migrate.py` 使用 `tomllib`）；`test_hooks.py` 只用标准库。

## 安装步骤

1. 把以下内容复制到目标仓库根：
   - `.codex/`：`agents/*.toml`、`sdlc/`、`rules/sdlc.rules`、`hooks.json`、`config.toml`
   - `scripts/codex_sdlc/`：至少 `hook_runtime.py`、`fetch_docs.py`；需要重新生成或校验时再带 `migrate.py`、`verify_migration.py`、`test_hooks.py`、`probe_runtime.py`
   - `AGENTS.md`（可把标题改成项目名）
2. 确认 `.codex/config.toml` 中 `features.hooks = true`、`agents.enabled = true`（随分发提供，勿在 agent TOML 里写权限字段）。
3. 在仓库根启动 Codex，打开 `/hooks`，审阅并**信任** `.codex/hooks.json` 里的 6 个定义（SessionStart / SubagentStart / PreToolUse ×3 / SubagentStop）。未信任前，记忆注入、cwd 守卫、联网与工具限制都不会生效——此时按 `.codex/sdlc/runtime_adapter.md` 显式读取记忆并人工核对返回。
4. 项目画像：没有 `.codex/sdlc/project_profile.md` 时，PM 会先扫描仓库生成初稿，逐项请你确认后再开始。已有旧画像没有 P11 时按“无”处理；仓库出现专用硬件、领域算法或闭源 API 迹象时，PM 先拟 P11 补充稿请你确认。
5. 项目记忆：`.codex/agent-memory/{role}/MEMORY.md`。分发里可能为空或不存在；首次运行由 hook 注入，未收到时角色必须显式 Read，不存在视为空。已有记忆重跑迁移不会被覆盖。
6. 权限规则：`.codex/rules/sdlc.rules` 由 `.claude/settings.json` 的 `permissions.ask/deny` 生成。仓库没有 `.claude/settings.json` 时，先复制 `.claude/settings.example.json` 为 `.claude/settings.json`，再执行：

   ```text
   python scripts/codex_sdlc/migrate.py build
   python scripts/codex_sdlc/migrate.py install
   ```

   分发自带的 `sdlc.rules` 可能含原项目的 `docker / docker-compose = forbidden`，复用到其他项目时按需删除或调整。
7. 启动 PM：
   - 主会话模式：`codex "按 .codex/sdlc/pm-orchestrator.md 执行任务"`，可当场澄清、可当轮授权部署。
   - 子代理模式：普通会话里 `@pm-orchestrator <需求>`，跑到检查点返回问题清单；回答后再 @ 一次续跑，止于部署计划（E1），不执行部署。
8. 评审或生成 agent：在主会话中说明要评审/生成的对象。默认只在回复中给结果；需要落盘时在请求里写 `WRITE_TARGET: <路径>`，覆盖已有文件另加 `OVERWRITE_AUTHORIZED: <路径>`。
9. 知识蒸馏：PM 交付后自动调用 kb-curator；也可直接 `codex "调用 kb-curator 整理项目经验"`。报告在 `project_workspace/_kb_distillation/`。
10. 从旧版升级：SubagentStop 的 matcher 自 v3.6 起包含 `pm-orchestrator`；hook 定义变更后必须重新在 `/hooks` 审阅信任。

## 验证安装

```text
python scripts/codex_sdlc/test_hooks.py            # 20 项离线行为测试，无需 codex CLI
python scripts/codex_sdlc/verify_migration.py      # 需要 PATH 上的 codex + .claude/settings.json
python scripts/codex_sdlc/probe_runtime.py --output output/codex-runtime-probe.json
```

`probe_runtime.py` 只读查询 hook 加载情况，不信任 hook、不启动模型。**以上都不能证明 hook 已在真实会话中触发**；真实生命周期验收步骤见 `docs/codex-agent-migration.md`。

## 已知限制

- 没有与 Claude `tools` 等价的完整工具白名单；托管 WebSearch 不经过 PreToolUse。
- 角色身份依赖宿主提供的 `agent_type` / transcript 元数据；缺失时工具 hook 无法可靠判定角色。
- hook 异常是 fail-open 并给出可见提示，不是 fail-closed 安全边界。
- `.codex/sdlc/migration_manifest.json` 的 `runtime_activation` 在完成真实会话验收前保持 `PENDING_USER_HOOK_TRUST_AND_REAL_SESSION_VALIDATION`。
