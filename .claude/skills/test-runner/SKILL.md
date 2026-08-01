---
name: test-runner
description: FreeArk 后端测试套件分层运行参考。当需要运行后端测试、按层级（单元/集成/端到端）跑测试、验证改动是否破坏测试、复核测试结果、判断某个失败是不是自己引入的、或查询某测试属于哪一层时使用。覆盖 Django test runner 的 @tag 分层（unit/integration/e2e）、运行命令、卫星测试（datacollection pytest）、当前基线与 3 项已知既有失败（含一个会打真实 DeepSeek 的 flaky 用例）、对照实验为何不能用 git worktree（.env 差异导致假阳性）、测试清单位置。
---

# FreeArk 测试运行手册（分层）

> 后端测试用 **Django test runner**（不是 pytest）。测试已按 `@tag('unit'|'integration'|'e2e')` 分层（类级标签，文件位置不变）。
> 完整脚本↔层级↔用例映射见 `docs/testing/test_inventory.md`（由 `scripts/gen_test_inventory.py` 自动生成）。

## 基线（用前以实跑为准）

**当前基线（2026-08-01，生产树莓派实跑）：全量 `test api` = 2137 测试 / 291s，
3 failures / 0 errors / 46 skipped。**

⚠️ **这 3 项是既有失败，与被测改动无关**，不要当成自己引入的回归。每项都已用
「主目录临时 `git checkout <改动前提交> -- <改的文件>` → 跑 → 还原」做过受控复核：

| 失败用例 | 性质 |
|---|---|
| `test_device_management.TC_U_003_ScreenConnectivityChecker.test_probe_single_returns_false_on_oserror` | 既有失败 |
| `test_device_management.TC_U_003_ScreenConnectivityChecker.test_probe_single_returns_false_on_timeout` | 既有失败 |
| `test_langgraph_phase_a.OrchestratorShortCircuitTests.test_sticky_disabled_falls_to_default` | **flaky**：会打真实 DeepSeek（单条耗时 40~80s），断言路由结果为 `freeark-expert`，实跑常返回 `inspection-expert` |

### ⚠️ 对照实验的坑：不要用 `git worktree` 比基线

`FreeArkWeb/backend/.env` 在仓库里有一份**已提交的 771 字节版本**（无真实
`DEEPSEEK_API_KEY`），而生产主目录那份是 2044 字节含真实 key 的**本地修改版**。
在 worktree 里跑，LangGraph 相关用例会因为拿不到 key 而直接短路 → 秒过；
主目录跑则真打 LLM → 慢且结果不确定。

**后果**：用 worktree 对比「改动前 vs 改动后」会得到假阳性——
2026-08-01 实测就出现过 worktree 里 0.47s `OK`、主目录 78s `FAIL` 的假象，
差点把一个 flaky 测试误判成新引入的回归。

**正确做法**：在**同一个工作目录**里临时回退被改文件再跑，保证 `.env` 一致：
```bash
F="path/to/changed1.py path/to/changed2.py"
git checkout <改动前提交> -- $F
FREEARK_POC_MOCK=1 PYTHONUTF8=1 venv/bin/python .../manage.py test <目标用例> --settings=freearkweb.test_settings
git checkout HEAD -- $F      # 务必还原
```
（清 `DEEPSEEK_API_KEY` 环境变量**没用**——key 从 `.env` 文件读，不走进程环境变量。）

### 历史
- 2026-06-20：全量 **1778** 测试全绿，`19 skipped`。原"6 个待定失败"已逐个核对修复
  （实测为 **7 个**）——5 个测试侧问题（模块级缓存跨用例污染 / 写死他机绝对路径 /
  用了 v0.5.7 已废 sub_type `room_panel` / docx 未装无 skip 守卫）+ 1 个过时用例删除
  （次日预留记录守卫，已由 `test_daily_usage_calculator.py` 覆盖）+ 2 个分页用例改期望
  （device-list 上限保持 50，非 2000）。`views.py` 未改行为，仅同步分页 docstring。
- skipped 从 19 增至 46：含本地无 `python-docx` 时 `tests_rag` 的 docx 解析用例自动 skip
  （CI 装全量依赖后会真跑），其余为环境相关跳过。
- 已建 GitHub Actions CI（`.github/workflows/ci.yml`）：push main / PR 触发，三 job 并行
  （后端整套 `test api` / datacollection pytest / 前端 vitest+build）。
  ⚠️ 门控写的是「以全绿为准」，但当前基线并非全绿——上述 3 项会让 CI 红。
  修 flaky/既有失败前，别把 CI 结果当作改动质量的唯一判据。

## 运行命令

工作目录与环境变量对所有命令通用：
- 目录：`FreeArkWeb/backend/freearkweb`
- `FREEARK_POC_MOCK=1`：fa_tools 离线导入所必需。
- `--settings=freearkweb.test_settings`：自动切 SQLite 内存库，**不连生产 DB**。

```bash
cd FreeArkWeb/backend/freearkweb

# 全量
FREEARK_POC_MOCK=1 python manage.py test api --settings=freearkweb.test_settings

# 仅单元
FREEARK_POC_MOCK=1 python manage.py test api --settings=freearkweb.test_settings --tag=unit

# 仅集成
FREEARK_POC_MOCK=1 python manage.py test api --settings=freearkweb.test_settings --tag=integration

# 仅端到端
FREEARK_POC_MOCK=1 python manage.py test api --settings=freearkweb.test_settings --tag=e2e

# 组合（OR 关系：unit 或 integration）
FREEARK_POC_MOCK=1 python manage.py test api --settings=freearkweb.test_settings --tag=unit --tag=integration

# 排除某层（例：跑除 e2e 外的全部）
FREEARK_POC_MOCK=1 python manage.py test api --settings=freearkweb.test_settings --exclude-tag=e2e
```

> Windows PowerShell 设环境变量：`$env:FREEARK_POC_MOCK=1`，再跑同样的 `python manage.py test ...`。

## 卫星测试（不在 `manage.py test api` 范围内）

```bash
# datacollection（pytest 风格）
cd datacollection && python -m pytest tests/ -v

# datacollection 独立 unittest
cd datacollection && python -m unittest test_log_config_manager -v
```

`test_dashboard_perf.py` 是性能基准脚本（需生产 token），手动运行，不进套件。

## 分层判定标准（新增测试时遵循，保持一致）
- **unit**：纯函数 / 纯逻辑 / 模型 / 管理命令；mock 掉外部与（多数）DB 交互。
- **integration**：走 DRF `APIClient` / 真实路由 / WebSocket（`channels.testing`）/ ORM 查询行为 / SQL 计数 / 完整 handler 管道。
- **e2e**：完整用户故事多步端到端（类名常含 `E2E`）。
- **共享基类不打层级 tag**：`@tag` 会经继承传播给子类，导致跨层重复计数。若一个基类被不同层级的子类共用（如 `RoomFilterTestBase`），**基类不打 tag**，由各子类自带正确层级。

## 维护工具
- `scripts/inject_tags.py` / `scripts/inject_tags_extra.py`：当初注入 @tag 的可复现脚本（仅加 `@tag` 与 `from django.test import tag`，原子校验后写入）。
- `scripts/gen_test_inventory.py`：改 @tag 后重新生成 `docs/testing/test_inventory.md`。

## 复核纪律
本项目历史上子代理多次虚报"测试通过"。任何"通过/数量"结论必须附**真实命令 + 真实输出尾部**（`Ran N tests` 与 `OK`/`FAILED (...)` 行）；重组测试结构后必须对比 `Ran N tests` 的 N 未无故下降。
