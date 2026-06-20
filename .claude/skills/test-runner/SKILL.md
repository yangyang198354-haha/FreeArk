---
name: test-runner
description: FreeArk 后端测试套件分层运行参考。当需要运行后端测试、按层级（单元/集成/端到端）跑测试、验证改动是否破坏测试、复核测试结果、或查询某测试属于哪一层时使用。覆盖 Django test runner 的 @tag 分层（unit/integration/e2e）、运行命令、卫星测试（datacollection pytest）、已知"待定"失败基线、测试清单位置。
---

# FreeArk 测试运行手册（分层）

> 后端测试用 **Django test runner**（不是 pytest）。测试已按 `@tag('unit'|'integration'|'e2e')` 分层（类级标签，文件位置不变）。
> 完整脚本↔层级↔用例映射见 `docs/testing/test_inventory.md`（由 `scripts/gen_test_inventory.py` 自动生成）。

## 基线（用前以实跑为准）
- 全量：**1778** 测试，**全绿**（`OK`，0 failures / 0 errors），`19 skipped` 为合理环境跳过
  （含本地无 `python-docx` 时 `tests_rag` 的 docx 解析用例自动 skip；CI 装全量依赖后会真跑）。
- 2026-06-20：原"6 个待定失败"已逐个核对修复（实测为 **7 个**）——5 个测试侧问题
  （模块级缓存跨用例污染 / 写死他机绝对路径 / 用了 v0.5.7 已废 sub_type `room_panel` /
  docx 未装无 skip 守卫）+ 1 个过时用例删除（次日预留记录守卫，已由
  `test_daily_usage_calculator.py` 覆盖）+ 2 个分页用例改期望（device-list 上限保持 50，
  非 2000）。`views.py` 未改行为，仅同步分页 docstring。
- 已建 GitHub Actions CI（`.github/workflows/ci.yml`）：push main / PR 触发，三 job 并行
  （后端整套 `test api` / datacollection pytest / 前端 vitest+build），门控以全绿为准。

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
