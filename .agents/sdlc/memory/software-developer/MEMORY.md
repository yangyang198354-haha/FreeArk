# software-developer 项目记忆 — FreeArk

> 格式与规则见 `.codex/sdlc/shared_protocol.md` §M。"已验证"区由 kb-curator 维护；agent 只追加"待验证"区。

## 已验证
- [M-SD-001] 〔迁移〕仓库存在迁移漂移：`makemigrations` 会夹带无关的 id/索引变更 → 只能手写 scoped 迁移。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SD-002] 〔迁移〕编号接续 `api/migrations/` 最新编号，依赖指向最新迁移；并行开发易撞号，合并前核对。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SD-003] 〔迁移〕已应用到生产的迁移不得修改；字段重命名用 `migrations.RenameField`；带索引字段先 RemoveIndex 再 AddIndex。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SD-004] 〔鉴权〕管理员判断用 `User.role == 'admin'`，不是 `is_staff`（二者无联动；`/api/auth/me/` 不返回 is_staff；v1.4.0 知识库页打不开即因误用 is_staff，commit 9cf65d1）。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SD-005] 〔鉴权〕视图权限类用 `api.views.IsAdminUser` / `api.views.IsOwnerUser`。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SD-006] 〔测试命令〕见画像 P4 与 `.agents/skills/test-runner/SKILL.md`；基线以实跑为准。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SD-007] 〔样式任务防越界〕"只改样式/UI"任务里子代理会顺带把 JS 压成单行、删内联样式，diff 出现大额净删除。派活时写明"只改 CSS、不动任何 JS 逻辑"；提交前用方法名集合对比核验（`git diff main -- . | grep -oE '(function|const|class)\s+\w+' | sort -u` 前后比对），有越界就逐行复核。 — conf 0.9 · 证据 旧知识库 KE-SD-003 迁移（用户警告 + 实际越界案例） · 首见 2026-10-30 · 命中 0
- [M-SD-008] 〔自验证〕无测试写权限时在**仓库外**取证：`npx vite-node --config vitest.config.mjs`（mock `globalThis.uni` + 改 `api.*` 方法名）验证 composable 接线；`@vue/compiler-sfc` 的 parse + compileScript + compileTemplate 做 SFC 语法检查；脚本放 `%TEMP%` 不落仓库，报告里贴命令与断言计数（实测 31/31 与 21/21 全通过）。 — conf 0.6 · 证据 GR-C-1 受审的 `development/code_review_report.md:88-90`（SFC_OK ×2 / WIRING_ALL_PASS 21/21）+ PM 另跑 190+56 全绿 · 首见 2026-11-01 · 命中 1

## 用户偏好与禁止项

## 待验证

- [P-SD-002] 〔自评一致性〕implementation_plan 的开放问题/自评描述必须与最终代码逐字一致：本轮 OQ-A3 写"try/finally"，实际为 try/catch + 尾部赋值，被门控记 MINOR（GR-C-1-F03）。 — 自记 2026-11-01 · 证据 GR-C-1-F03（单处门控记录，conf 0.5）

