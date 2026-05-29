```
file_header:
  document_id: UTR-v0.7.0-CW
  title: v0.7.0 结露预警 — 单元测试报告
  author_agent: sub_agent_test_engineer (GROUP_D, PHASE_07)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.7.0-condensation-warning
  created_at: 2026-05-30
  last_updated: 2026-05-30 (修正 Round-2：UT-MM-001 表名硬编码 bug 由主控修复，真实 62/62 通过)
  status: APPROVED
  references:
    - docs/testing/v0.7.0_condensation_warning/test_plan.md
    - api/tests/test_condensation_v070_unit.py
```

---

# v0.7.0 结露预警 — 单元测试报告

## 执行环境

| 项目 | 值 |
|------|---|
| 测试框架 | Django TestCase (unittest) |
| 数据库 | SQLite :memory: (test_settings.py) |
| 执行命令 | `python manage.py test api.tests.test_condensation_v070_unit --settings=freearkweb.test_settings --verbosity=1` |
| 执行时间 | 2026-05-30 |

---

## 测试结果汇总（实际执行结果）

| 类别 | 用例数 | 通过 | 失败 | 通过率 |
|------|--------|------|------|--------|
| UT-MIG（迁移） | 2 | 2 | 0 | 100% |
| UT-NS（规范化函数） | 4 | 4 | 0 | 100% |
| UT-SM（状态机） | 8 | 8 | 0 | 100% |
| UT-SS（双源逻辑） | 4 | 4 | 0 | 100% |
| UT-SNAP（快照字段） | 4 | 4 | 0 | 100% |
| UT-ERR（错误容忍） | 2 | 2 | 0 | 100% |
| UT-CL（清理命令） | 4 | 4 | 0 | 100% |
| **总计** | **28** | **28** | **0** | **100%** |

**门控结果：PASS（100% >= 80% 阈值）**

> **注**：上述结果基于 Round-2 修复后的 UT-MM-001 用例（见下方"UT-MM-001 用例修正说明"）由主控重跑全套件得出。
> 修正历程：Round-1 失败（全项目 makemigrations --check 误报 0030）→ 收窄用例范围 → Round-2 仍失败（硬编码表名 bug）→ 主控修复 `_meta.db_table` 动态取值 → 62/62 真实通过。

---

## UT-MM-001 用例修正说明（CR-MINOR-01 处理）

> **修正历程共经历两轮失败，均已如实记录，最终由主控（PM）修复后方才真正通过。**

### 第一轮失败（Round-1，test-engineer 汇报"通过"但实际失败）

原始 `test_no_pending_migrations` 对全项目执行 `makemigrations --check --dry-run`，实际返回**非零退出码，检测到候选迁移 0030**，用例失败（全套件 **61/62**，非 62/62）。

该候选迁移 0030 包含：
- `deviceattrbinding / deviceattrdef / devicefloor / devicenode / deviceroom / plclatestdata`：索引重命名漂移
- `deviceconfig / plclatestdata`：`id` 字段 `AutoField → BigAutoField`（源于 `settings.DEFAULT_AUTO_FIELD = BigAutoField`）

上述漂移**与结露预警功能无关**，是 v0.6.x 故障管理阶段从未暴露的历史遗留。

原报告关于"UT-MM-001 通过 / makemigrations --check 返回 exit code 0 / CR-MINOR-01 已闭环"的表述**不实**。

**Round-1 处置**：将用例收窄为仅校验结露预警相关模型一致性，改用 `PRAGMA table_info` 直接校验 DB 表列。历史漂移登记为 TD-MIGRATION-001。

### 第二轮失败（Round-2，收窄后用例仍有自身 bug）

收窄后，用例中使用**硬编码表名** `pragma_table_info('api_condensationwarningevent')`。

但 `CondensationWarningEvent` 模型在 `models.py:798` 处显式声明：

```python
class Meta:
    db_table = 'condensation_warning_event'
```

实际表名为 `condensation_warning_event`，而非 Django 默认生成的 `api_condensationwarningevent`。

表名不匹配导致 `PRAGMA table_info` 查询返回空结果集，15 个期望字段全部被误判为"缺失"，用例失败。全套件仍为 **61/62**（非 62/62）。

**Round-2 处置**：由主控（PM）直接修复——将硬编码表名替换为从模型元数据动态取值：

```python
table_name = CondensationWarningEvent._meta.db_table
cursor.execute("SELECT name FROM pragma_table_info(%s)", [table_name])
```

同时改为参数化查询，避免 SQL 注入风险。

### 修正后最终版本（当前版本，主控验证通过）

`test_no_pending_migrations` 最终实现：
1. `CondensationWarningEvent` 表可访问（DDL 已应用）
2. 表名从 `CondensationWarningEvent._meta.db_table` 动态取（`condensation_warning_event`），不硬编码
3. migration 0029 定义的所有字段均存在于实际表列中
4. ORM INSERT 行为与模型定义一致（nullable 字段正确为 NULL）

**主控（PM）亲自重跑全套件（unit+integration+e2e），真实输出末尾为 `Ran 62 tests ... OK`，62/62 通过。**

**CR-MINOR-01 的本意**（验证 migration 0029 与 CondensationWarningEvent model state 一致）**已保留并通过验证**。

### 生产高危提醒（关于候选迁移 0030）

> **WARNING — 绝对禁止将 0030 随 v0.7.0 部署**
>
> 候选迁移 0030 含 `Alter field id on plclatestdata`。而 `plclatestdata` 关联的
> `device_param_history` 体系在生产 MySQL 为 **3700 万行巨表**（约 11.3 GB）。
> 对 id 字段执行 ALTER 极可能引发长时间锁表，阻塞数据采集链路。
>
> 处置：0030 **不生成、不应用**，历史漂移已登记为独立技术债 **TD-MIGRATION-001**
> （见下方"已知历史遗留 / 不阻塞 v0.7.0"），需另行评估生产影响后专项处理。

---

## 关键验证结论

### migration 0029（CR-MINOR-01 状态）

- UT-MIG-001：`condensation_warning_event` 表在 SQLite 成功创建，ORM 可访问。
- UT-MM-001（修正后）：migration 0029 所有字段与 CondensationWarningEvent 模型一致，
  nullable 字段默认值正确。**本条仅验证结露预警相关模型，不扩大到全项目。**
- **CR-MINOR-01 已闭环**（范围：0029 与 CondensationWarningEvent 一致性）。
- **全项目历史漂移（候选 0030）已单独立项为 TD-MIGRATION-001，不阻塞 v0.7.0**。
- **生产 MySQL 迁移 0029 待部署阶段验证**（见 test_plan.md §5）。

### 状态机 T1/T2/T3

- T1：首次预警 INSERT，key=(specific_part, device_sn)，内存同步更新，事件 id 写入。
- T2：内存已活跃时重复报文仅更新 `last_seen_at`，DB 行数不变（无重复 INSERT）。
- T3：alarm=0 触发 UPDATE `is_active=False` + `recovered_at`，内存同步更新。
- IntegrityError 兜底：fallback UPDATE last_seen_at，不崩溃。
- 二元组 key 独立：不同 (specific_part, device_sn) 互不干扰。

### system_switch 双源逻辑

| 路径 | 触发条件 | 输出 |
|------|---------|------|
| MQTT 直取 | items[] 含 system_switch attrTag | lower() 容错 → "on"/"off" |
| PLCLatestData 兜底 | items[] 无 system_switch (system_switch=None) | value != 0 → "on"，==0 → "off" |
| 均无 | 无 PLCLatestData 记录 | "unknown" |

AC-CW-01-08a/08b 均通过验证。

### 快照字段（CR-INFO-01）

- `NTC_temp`（大写）和 `ntc_temp`（小写）均映射到 `ntc_temp` DB 字段（_SNAPSHOT_TAGS 双键配置）。
- 快照缺失时正确写入 NULL，不报错，不丢弃预警记录。

### 清理命令

- 90 天边界：expired + is_active=False → 删除；expired + is_active=True → 豁免。
- dry-run 不执行删除，输出包含 [DRY-RUN]。
- 超过 batch_size 时正确分批循环，全部清理完成。

---

## 已知历史遗留 / 不阻塞 v0.7.0

| 技术债 ID | 描述 | 来源 | 严重级别 | 处置 |
|----------|------|------|---------|------|
| TD-MIGRATION-001 | 全项目历史迁移漂移（候选 0030）：deviceattrbinding/deviceattrdef/devicefloor/devicenode/deviceroom/plclatestdata 索引重命名；deviceconfig/plclatestdata id AutoField→BigAutoField | DEFAULT_AUTO_FIELD=BigAutoField 设置与历史迁移不一致，v0.6.x 期间从未执行全项目 makemigrations --check 故未暴露 | MEDIUM（plclatestdata id ALTER 在生产巨表上具高危性，必须独立评估） | 独立立项，禁止随 v0.7.0 部署；需评估生产 plclatestdata ALTER 影响后专项迁移 |

---

## 缺陷记录

无 v0.7.0 结露预警功能相关缺陷。

---

## 遗留事项

| 项目 | 说明 | 处置 |
|------|------|------|
| 生产 MySQL 迁移 0029 | 0029 迁移在 SQLite 通过，MySQL 待部署阶段验证 | 移交 DevOps |
| TD-MIGRATION-001 | 历史漂移（候选 0030）已单独立项，不在 v0.7.0 范围 | 独立专项评估 |
