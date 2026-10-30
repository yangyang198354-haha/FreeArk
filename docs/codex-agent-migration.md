# Claude SDLC → Codex 迁移记录

核对日期：2026-10-30。源版本：SDLC Agent Suite **v3.7**，提交 `69ff6a11729e562c9b9ef6a437ab4f0d45a761bf`。

> 版本号不再是脚本里的常量：`migrate.py` 从 `.claude/agents/INSTALL.md` 的 `SDLC Agent Suite vX.Y` 解析，并写入 `migration_manifest.json` 与 `.codex/hooks.json`，避免清单声称的版本与正文脱节（2026-10-30 之前硬编码为 3.5.1）。

**状态：文件与离线适配已完成；严格的“机制不退化”运行时验收尚未通过。** 本机实际用户上下文已加载项目配置、识别全部 6 个 hook，没有加载错误；6 个 hook 均为 `untrusted`。此外，Codex 原生托管网页搜索不经过工具 hook，不能把本迁移描述为与 Claude `tools` 白名单完全相同的强隔离。

## 这次上游变化

首次迁移（2026-10-23）是 `a3bd344..185691f`，共 40 个文件发生变化、增加 2220 行；不是 40 个文件全是新增。2026-10-30 重新以 `185691f..69ff6a1`（v3.5.2 → v3.7）为增量重建，此前 Codex 侧停在 v3.5.1 内容。

| 版本 / 提交 | 主要变化 |
|---|---|
| v3.3 / `95e46e1` | 套件纳入版本管理；统一 shared_protocol、FreeArk 项目画像、项目记忆、通用知识和收件箱；新增 kb-curator；加入 SubagentStop 与派生前目录检查；配置命令 ask/deny |
| v3.4 / `01f8562` | agent-builder 重写为六维百分制评分、生成/评分/局改/优化流程；独立模板库；纳入响应协议、记忆和 hooks；显式写入/覆盖/返工授权 |
| v3.4.1 / `ebd4a25` | 通用经验去除 FreeArk 专有事实，项目事实和经验分别归入画像与项目记忆 |
| v3.5 / `00a13ef` | agent-builder 仅允许读取指定官方页面，禁止搜索；新增 WebFetch guard；更新平台事实、目录定位要求 |
| v3.5.1 / `185691f` | 修正各角色的澄清、错误状态、输出、自检和证据要求；知识蒸馏 pending/committed、重试与回读；PM 复跑范围、评审算术与报告冻结点等 |
| v3.5.2 / `c68d4b2` | 修复评分遗留的内部一致性 MINOR |
| v3.6 / `137eeca` | PM 子代理模式（检查点 `<checkpoints>`、RUN 事件、跨调用续跑）与 hook 修复 |
| v3.7 / `69ff6a1` | 项目画像新增 **P11 领域与外部依赖**；协议补充 P11 的必读分发、门控与 `[STALE]` 复核；PM 对缺 P11 的旧画像按"无"处理，出现信号时先拟补充稿 |

相对旧 Codex 角色，保留并迁入的关键机制包括：FULL_FLOW / INCREMENTAL / PARTIAL_FLOW；A→B→C→D→E1 串行门控；E1 计划与 E2 授权执行分离；测试阈值/基线两种判定；缺陷回流与有限重试；结构化 XML 调用/响应；状态与审计持久化；交付后的 PHASE_12 知识蒸馏；记忆三区、置信度公式、150 行索引与主题文件。

## 文件与机制对应

| 内容 | Codex 落点 | 验证/状态 |
|---|---|---|
| 8 个角色 | `.codex/agents/*.toml` | name/description/developer_instructions；保留全部编号章节，TOML 可解析 |
| PM 主会话入口 | `AGENTS.md`、`.codex/sdlc/pm-orchestrator.md` | 在当前主会话执行；没有虚构 `codex --agent` |
| 协议、项目画像、模板、通用/历史知识 | `.codex/sdlc/` | 迁移源文件和 SHA-256 在 migration_manifest.json 中逐项登记 |
| 角色项目记忆 | `.codex/agent-memory/{role}/` | 7 份既有记忆迁入，agent-builder 空记忆初始化；主题文件保留；重复迁移保留现有 Codex 记忆 |
| 记忆加载 | SessionStart / SubagentStart → `hook_runtime.py memory` | 注入前 200 行；缺失时显式读取；尚待信任后真实触发验收 |
| 派生 cwd 检查 | PreToolUse → `hook_runtime.py pre-agent` | Codex spawn_agent / Agent 两种名字；脚本根定位；离线通过 |
| 响应与知识提案 | SubagentStop → `hook_runtime.py stop` | XML 检查、每轮最多补齐一次、脱敏、加锁和幂等写入；支持 Codex transcript fallback |
| 工具与联网限制 | PreToolUse → web / tools；角色关闭 apps/plugins | 仅对受 hook 覆盖且可识别角色的路径有效；不是全工具强隔离 |
| agent-builder 官方文档 | `scripts/codex_sdlc/fetch_docs.py` | 页面 key 白名单；检查 URL 与重定向；不接受自定义 URL、查询参数或搜索词 |
| ask/deny | `.codex/rules/sdlc.rules` | 37 个源规则用原生 `codex execpolicy check` 逐条核对；Windows exe/cmd 别名 |
| 测试/部署 skills | `.agents/skills/` | 同步较新的源内容；修复旧全绿基线、已退役花生壳通道等信息；格式校验通过 |
| 运行时差异 | `.codex/sdlc/runtime_adapter.md` | 工具映射、Windows/POSIX 命令、真实时间、权限继承、记忆与 hook 兜底 |

源 agent 的 opus/sonnet 不直接映射到未经用户选择的 Codex 模型；模型与推理强度继承当前会话。颜色等源元数据保存在清单中，不冒充受支持的 TOML 配置。

原始 `.claude` 文件保持不变（知识库的旧格式 XML 除外，见下）。2026-10-30 起旧格式 `kb_full.xml` 的内容已按 §M 去重后并入项目记忆，原文件与 Codex 侧副本均已删除——其中两条含生产明文密码和过期外网通道，不能再留在磁盘上；逐条去向见 `project_workspace/_kb_distillation/legacy_kb_import_2026-10-30.md`（本地，未入库）。

## 验证结果

- `python -m unittest discover -s scripts/codex_sdlc -p test_hooks.py -v`：**20 项通过**。覆盖错误 cwd、角色边界、记忆位置/截断、响应校验、补齐次数、转义、去重、脱敏、transcript fallback、URL/重定向拒绝和异常输出。
- `python scripts/codex_sdlc/verify_migration.py`：**38 文件 / 8 角色 / 37 个原生规则检查通过**。核对源/目标 hash、TOML、编号章节、结构化返回及实际路径引用。（首次 v3.5.1 迁移时为 62 文件；差额是旧格式 XML 知识副本与指针文件，已按上节删除。）
- 两个 skill 的 `quick_validate.py` 均通过。
- 受限读取脚本的 8 个官方页面均实际读取成功；白名单外 URL 与重定向由离线测试覆盖。
- 6 条 `commandWindows` 均在 PowerShell 中从仓库子目录启动成功，返回有效 JSON。这是命令启动验证，不等于生命周期事件已实际触发。
- 实际用户上下文 app-server `config/read` / `hooks/list`：`features.hooks=true`，项目层启用，6 个 hook，0 errors、0 warnings，均 `untrusted`。未调用信任写入接口、未启动模型回合。
- `git diff --check` 通过。未运行 FreeArk 后端/前端业务测试：本次改动为 agent 运行配置及其脚本，不涉及业务实现。

本地详细结果保存在 `output/codex-migration-verification.json`、`output/codex-hook-launch-verification.json`、`output/codex-runtime-probe-user.json`。`output/` 被 Git 忽略；持久化摘要为本文。沙箱账号 `CodexSandboxOffline` 的项目 trust 与实际用户不同，因此不能用沙箱下“0 hooks”的结果判断桌面加载失败。

## 未完成的运行时验收

1. **信任**：在仓库根运行 Codex CLI，打开 `/hooks`，审阅 `.codex/hooks.json` 中的 6 个定义并信任。重新加载/开启会话以读取最新角色定义。本步骤是 Codex 的原生安全机制，不应通过脚本修改全局 trust 或绕过。
2. **真实生命周期**：在新的会话中调用一个阶段子代理，用最小非生产任务核验 SubagentStart 记忆、PreToolUse 目录拒绝、SubagentStop 响应补齐和收件箱写入。需要检验该宿主实际提供的角色字段/transcript 元数据；不得仅凭模拟事件宣称通过。
3. **工具强隔离缺口**：当前 Codex 自定义角色没有 Claude `tools` 的等价完整白名单字段，托管 WebSearch 不走 PreToolUse。需求/架构保留公开搜索能力；其他角色与 agent-builder 的约束由提示词、能力开关、受覆盖工具 hook 和受限读取脚本共同实施，但不能保证所有特殊路径都被拦截。如果必须得到严格角色级网络隔离，需要经用户选择的独立会话/受控联网工具架构，再进行端到端验收；本迁移没有擅自把整个项目的搜索关闭或替换为低质量搜索服务。
4. **失败行为**：沿用上游 hook 异常不阻断全部工作的策略，并新增可见失败提示；这不是 fail-closed 安全边界。PM 仍须检查返回、必读清单和收件箱。内置沙箱、命令规则和组织策略继续适用。

因此，**可确认源职责与工作流已迁入；无法确认“当前已经完整激活且所有硬权限无退化”**。这两类结论必须分别报告。

## 使用、维护与回退

桌面/CLI 主会话可说：“按 `.codex/sdlc/pm-orchestrator.md` 处理这个增量需求……”。角色以原名调用，新增 `kb-curator`；调用方式和工具名称以当前运行时为准。

迁移脚本两步执行：

```text
python scripts/codex_sdlc/migrate.py build
python scripts/codex_sdlc/migrate.py install
python scripts/codex_sdlc/verify_migration.py
```

build 仅生成 `output/codex-migration/`；install 逐文件检查源/目标 hash，备份旧文件再安装，不删除目录，不改全局设置。不要把未来的 Codex 独立定制不加审阅地重新覆盖；知识库/画像/模板改变时应先人工合并。现有 Codex 项目记忆不会被重跑覆盖。

首次迁移前的旧配置备份在 `output/codex-migration-backups/20261023T220733133874/`，后续修正各有时间戳备份；v3.7 重建前的 Codex 记忆快照在 `output/codex-migration-backups/legacy-memory-2026-10-30/`（记忆随后由源重新生成，以便新条目同步到 Codex 侧）。回退按清单恢复对应旧文件，新增文件按需逐项移除；保留后来产生的记忆和知识收件箱。未提交 Git，也未修改用户已有的 `miniprogram/vite.config.js` 改动。

平台依据：[自定义子代理](https://learn.chatgpt.com/docs/agent-configuration/subagents)、[hooks 与信任/覆盖边界](https://learn.chatgpt.com/docs/hooks)、[命令规则](https://learn.chatgpt.com/docs/agent-configuration/rules)。
