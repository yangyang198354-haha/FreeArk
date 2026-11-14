# test-engineer 项目记忆 — FreeArk

> 格式与规则见 `.codex/sdlc/shared_protocol.md` §M。"已验证"区由 kb-curator 维护；agent 只追加"待验证"区。

## 已验证
- [M-TE-001] 〔运行〕命令、@tag 分层标准、基线与已知既有失败：一律以 `.agents/skills/test-runner/SKILL.md` 为准（基线会变，用前实跑确认）。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-TE-002] 〔运行〕后端用 Django test runner（非 pytest）；`datacollection/` 用 pytest。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-TE-003] 〔运行〕本地缺 `mysqlclient`（MySQLdb）时，少数 import 了 MySQL 相关模块的测试会报 `ModuleNotFoundError: No module named 'MySQLdb'`——这是环境问题，归为既有/环境失败，不是改动引入。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-TE-004] 〔编写约定〕新文件一律放 `api/tests/`，命名 `test_{功能}.py`（根目录的 `api/tests_*.py` 是旧文件，不再新增）；测试类加 `@tag('unit'|'integration'|'e2e')`（漏标 tag 的测试会被 `--tag` 过滤静默漏跑）。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-TE-005] 〔编写约定〕继承 `django.test.TestCase`；API 用 DRF `APITestCase` / `APIClient`。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-TE-006] 〔编写约定〕**权限类测试要用真实 Token 头**（`client.credentials(HTTP_AUTHORIZATION='Token <key>')`），不要只用 `force_authenticate`：后者在中间件之后才生效，会绕过全局的 `api.middleware.UserRoleApiGuardMiddleware`（它负责拦截 user 角色访问非小程序接口），测不到真实的 401/403 路径。（来源：UserRoleStats 实测提案，2026-10-22） — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-TE-007] 〔编写约定〕模块级缓存会跨用例污染：在 `tearDown` 中重置。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-TE-008] 〔编写约定〕不写死本机绝对路径；可选依赖（如 python-docx）缺失时用 skip 守卫。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-TE-009] 〔编写约定〕涉及 LangGraph/DeepSeek 的路径必须 mock，不得打真实 LLM。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-TE-010] 〔纪律〕没有运行输出就不能标 PASS。报告里贴命令与输出尾部，PM 会复跑核对。 — conf 0.9 · 证据 人工维护知识库迁移 · 首见 2026-10-22 · 命中 0
- [M-TE-011] 〔编写约定〕小程序组件层（`.vue`）用例必须用非 `.spec.js` 扩展名（当前实测用 `.spec.mjs`）**且**在 `miniprogram/vitest.component.config.mjs` 的硬编码 `include` 名单里点名登记：默认 `vitest.config.mjs:16` 的 `include` 只匹配 `tests/**/*.spec.js` 且不含 `@vitejs/plugin-vue`（用 `.spec.js` 会被默认层收集并报 SFC 解析错误），而组件层 `include` 是点名名单——**漏登记不会报错，只会静默跳过**，必须核对"实际收集到的文件数"。 — conf 0.8 · 证据 GR-D-1-F01（实测报错）+ GR-C-1 CR-002（GROUP_C 独立发现）+ 复核 `vitest.config.mjs:16`、`vitest.component.config.mjs:16-23` · 首见 2026-11-01 · 命中 1
- [M-TE-012] 〔编写约定〕回首页看板的 `useBridgeDashboard.start()` 会经 `PagePoller.start()`（`utils/poller.js:16-19`：先立即执行一次再 `setInterval`）**立刻多发一轮请求**；断言轮数/调用次数前先 `await` 一个 `setTimeout(0)` 的 flush，否则计数系统性偏移一轮。 — conf 0.8 · 证据 复核 `utils/poller.js:16-19` + `tests/bridge-dashboard-network-alert.integration.spec.js:87,101` + GR-D-1 复跑 17 files/215 tests 全通过 · 首见 2026-11-01 · 命中 1
- [M-TE-013] 〔编写约定〕既要 fake 轮询定时器又要真实 promise 结算时，用 `vi.useFakeTimers({ toFake: ['setInterval','clearInterval'] })`；全量 fake 会让启动阶段的 `setTimeout(0)` flush 永不 resolve（实测 5s 用例超时）。 — conf 0.6 · 证据 GR-D-1-F04（TC-INT-010 首轮失败→改写法后通过）+ 最终写法 `tests/bridge-dashboard-network-alert.integration.spec.js:296` · 首见 2026-11-01 · 命中 1

## 用户偏好与禁止项

## 待验证

