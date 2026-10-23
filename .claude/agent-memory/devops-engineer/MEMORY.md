# devops-engineer 项目记忆 — FreeArk

> 格式与规则见 `.claude/agents/shared_protocol.md` §M。"已验证"区由 kb-curator 维护；agent 只追加"待验证"区。

## 已验证
- [M-DE-001] 〔部署纪律〕生产仓库 `/home/yangyang/Freeark/FreeArk/`，只 `git pull origin main`，**禁止 `git stash`**：生产工作树长期有本地修改（`FreeArkWeb/backend/.env`、`FreeArkWeb/frontend/package-lock.json`、`FreeArkWeb/backend/heartbeat_broker_config.json`），stash 会把生产配置藏起来导致服务起不来。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-DE-002] 〔部署纪律〕pull 前先 `git diff --name-only HEAD origin/main`，确认不触碰上述三个文件；若触碰，停止并上报。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-DE-003] 〔部署纪律〕前端：`npm run build`；**不要随手 `npm install`**（会改动生产 `package-lock.json`），只有 package.json 变化时才需要，且要人工确认。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-DE-004] 〔部署纪律〕禁止 pscp/scp 逐文件上传；禁止 Docker。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-DE-005] 〔部署纪律〕记录 pull 前的 HEAD 作为回滚锚点。**不要 `git reset --hard`**（会冲掉已跟踪文件的生产本地修改）。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-DE-006] 〔部署纪律〕回滚首选：开发机 `git revert` + push → 生产 `git pull --ff-only` → 重启服务。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-DE-007] 〔部署纪律〕紧急止血才用 `git checkout <锚点> -- <修改过的文件>`（`--diff-filter=M`，新增文件不要列入，否则命令报错）；事后必须收尾：revert 推送后 `git checkout HEAD -- <同一列表>` → `git pull --ff-only` → `git status --short` 只剩三个已知本地修改。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-DE-008] 〔远端命令引号〕在开发机上通过 `ssh ... '<命令>'` 执行时，**单引号里的 `$VAR` 不会在本地展开**，到生产机上通常是空值。命令里要用开发机的本地变量（如回滚锚点 `$ANCHOR`、文件列表 `$MFILES`）时，用双引号，或先 `echo` 出完整命令核对后再执行。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-DE-009] 〔远端命令引号〕后果示例：`ssh $PROD 'git checkout $ANCHOR -- $MFILES'` 中 `$ANCHOR` 为空 → 变成 `git checkout -- <files>`，从索引恢复的仍是新代码，紧急回滚静默失效。（来源：UserRoleStats E1 重跑，门控 GR-E1-002 MAJOR，2026-10-22） — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-DE-010] 〔远端命令引号〕执行回滚前先核验变量：锚点是 40 位哈希且 `git cat-file -t $ANCHOR` 返回 `commit`；执行后用 `git diff --cached --name-only` 确认恢复的文件正确。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-DE-011] 〔服务〕重启哪些服务按 skill §6 精确列出。易漏：改 `api/fault_consumer/` 必须重启 `freeark-fault-consumer`（与 `freeark-mqtt-consumer` 是两个服务）。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-DE-012] 〔服务〕服务清单不止 CLAUDE.md 列出的 6 个（另有 plc-connection-monitor、screen-heartbeat、usage 统计、fault-cleanup.timer、redis 等），以 skill §3 和生产实际 `systemctl list-units 'freeark*'` 为准。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-DE-013] 〔服务〕部分服务的 `Restart=` 已调整（如 mqtt-consumer 改为 `always`，commit a3bd3445），以 `systemctl cat <svc>` 为准。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-DE-014] 〔访问〕SSH：`ssh -p 57279 yangyang@47.109.197.217`（VPS + frp，密钥认证），主机密钥指纹 `SHA256:TfpCSrSLuK1UspD2mpikebK0bE0IFnPH8bSigERWnmk`；Web `https://ai-freeark.xin`。花生壳已退役。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-DE-015] 〔CI〕`.github/workflows/ci.yml`：三个 job（后端全量 `test api` / datacollection pytest / 前端 vitest+build），`.claude/**` 与文档变更不触发。基线存在既有失败时 CI 会红，判断回归要对比基线。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0

## 用户偏好与禁止项

## 待验证
