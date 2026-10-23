# software-developer 项目记忆 — FreeArk

> 格式与规则见 `.claude/agents/shared_protocol.md` §M。"已验证"区由 kb-curator 维护；agent 只追加"待验证"区。

## 已验证
- [M-SD-001] 〔迁移〕仓库存在迁移漂移：`makemigrations` 会夹带无关的 id/索引变更 → 只能手写 scoped 迁移。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SD-002] 〔迁移〕编号接续 `api/migrations/` 最新编号，依赖指向最新迁移；并行开发易撞号，合并前核对。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SD-003] 〔迁移〕已应用到生产的迁移不得修改；字段重命名用 `migrations.RenameField`；带索引字段先 RemoveIndex 再 AddIndex。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SD-004] 〔鉴权〕管理员判断用 `User.role == 'admin'`，不是 `is_staff`（二者无联动；`/api/auth/me/` 不返回 is_staff；v1.4.0 知识库页打不开即因误用 is_staff，commit 9cf65d1）。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SD-005] 〔鉴权〕视图权限类用 `api.views.IsAdminUser` / `api.views.IsOwnerUser`。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-SD-006] 〔测试命令〕见画像 P4 与 `.claude/skills/test-runner/SKILL.md`；基线以实跑为准。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0

## 用户偏好与禁止项

## 待验证
