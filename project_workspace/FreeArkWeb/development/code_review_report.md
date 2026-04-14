# FreeArkWeb 代码走读报告（冗余清理 + 性能优化）

<!-- file_header
author_agent: main_agent_pm
phase: CODE_REVIEW
project: FreeArkWeb
created_at: 2026-04-14
status: COMPLETED
reviewed_files: api/views.py, api/models.py, api/serializers.py, api/urls.py,
                api/mqtt_consumer.py, api/mqtt_handlers.py,
                api/daily_usage_calculator.py, api/monthly_usage_calculator.py,
                api/plc_data_cleaner.py, api/admin.py, freearkweb/settings.py,
                frontend/src/services/api.js, frontend/src/utils/api.js,
                frontend/src/router/index.js, frontend/src/views/ (全部),
                frontend/src/components/ (全部)
-->

---

## 1. 执行摘要

| 指标 | 值 |
|------|---|
| CRITICAL findings | 0 |
| MAJOR findings（已修复） | 8 |
| MAJOR findings（建议项，待决策） | 2 |
| MINOR findings（已确认，保留） | 6 |
| 直接修改文件数 | 5 |

---

## 2. 后端 — 已修复项

### M-BE-01: `views.py` — PLC 统计接口 3 次全表 COUNT 查询 [已修复]

**位置**: `get_plc_connection_status` 函数  
**问题**: 原代码为在线、离线、总数分别执行独立的 `COUNT` 查询（3 次全表扫描）。  
**修复**: 改为单次 `aggregate()` 使用 `COUNT + CASE WHEN` 一次拿到全部三个值，节省 2 次额外查询。

---

### M-BE-02: `views.py` — `get_usage_quantity_specific_time_period` 循环内冗余/重复查询 [已修复]

**位置**: `get_usage_quantity_specific_time_period` 函数，分页循环体  
**问题 1**: `combo_queryset.count()` 在 `logger.debug(...)` 中调用，每次循环额外一次 COUNT（N+1）。  
**问题 2**: `first_record` 重新构造了与 `combo_queryset` 等价的第二个 queryset 后再 `.first()`，等同于 `combo_queryset.first()`，多一次数据库访问。  
**问题 3**: `aggregate(Min(...))` 和 `aggregate(Max(...))` 分两次调用，对同一数据集发出两条 SQL。  
**修复**:  
- 移除了 `combo_queryset.count()` 的 debug 日志行。  
- 将冗余 `queryset.filter(...).first()` 改为直接 `combo_queryset.first()`。  
- 将两个 `aggregate()` 合并为一次调用。

---

### M-BE-03: `views.py` — 多处函数体内 `import` [已修复]

**位置**: 函数体内 `from django.db.models import Min, Max, F`；`from django.db.models import Count, Case, When, IntegerField`；循环体内 `import calendar`  
**问题**: 函数/循环体内执行 `import` 在每次调用时重复触发模块查找，是标准反模式。  
**修复**: 全部提升至文件顶部统一 import 区。

---

### M-BE-04: `daily_usage_calculator.py` — 无效 `select_related()` [已修复]

**位置**: `calculate_daily_usage` 方法  
**问题**: `PLCData` 模型无任何 ForeignKey/OneToOneField，`select_related()` 不产生任何 JOIN，纯冗余调用。  
**修复**: 已移除 `.select_related()`。

---

### M-BE-05: `daily_usage_calculator.py` — 未使用的 import [已修复]

**位置**: 模块顶部  
**问题**: `Subquery`, `OuterRef`, `F`, `Max`（该文件中未调用），`connection` 全部未使用。  
**修复**: 清理为仅保留实际使用的 `transaction`, `close_old_connections`。

---

### M-BE-06: `monthly_usage_calculator.py` — 重复且不可达的类型校验 [已修复]

**位置**: `calculate_monthly_usage` 方法  
**问题**: 第 27 行已提前 `return` 处理非 `date` 类型，第 37 行 try 块内再次重复同样检查，该分支永远不可达（死代码）。  
**修复**: 删除了 try 块内的重复类型校验（3 行）。

---

### M-BE-07: `monthly_usage_calculator.py` — 未使用 import + 函数体内 import [已修复]

**位置**: 模块顶部 + `except` 块  
**问题**: `Sum` 从未使用；`import traceback` 写在 `except` 块内部。  
**修复**: 移除 `Sum`，将 `import traceback` 提升至文件顶部。

---

### M-BE-08: `plc_data_cleaner.py` — 先 COUNT 再 DELETE 两次查询 [已修复]

**位置**: `clean_old_plc_data` 函数  
**问题**: 先 `count()` 获取行数再 `delete()`，触发两条 SQL。Django `QuerySet.delete()` 返回 `(deleted_count, {model: count})` 元组，无需预先 count。  
**修复**: 直接 `deleted_count, _ = PLCData.objects.filter(...).delete()`。同时移除未使用的 `from django.db.models import Q`。

---

## 3. 前端 + 后端 — 建议项（需用户决策，未修改）

### R-01: `services/api.js` 实际未被任何视图使用，应考虑删除

**位置**: `frontend/src/services/api.js`  
**问题**:  
- 所有 `.vue` 视图文件全部 `import api from '@/utils/api.js'`，`services/api.js` 中定义的 `authApi`/`userApi`/`usageApi` 实际未被任何视图文件导入。  
- `services/api.js` 中 `usageApi.getDailyUsage` 指向的 URL 是 `/usage/daily/`，但后端实际端点是 `/usage/quantity/`，若被调用将返回 404（逻辑死代码）。  
**建议**: 确认无其他引用后删除 `services/api.js`，保留 `utils/api.js` 为唯一 API 层。

---

### R-02: `MonthlyUsageReportView.vue` 月份范围参数名与后端不匹配，过滤无效

**位置**: `MonthlyUsageReportView.vue` `searchMonthlyUsageData` 方法  
**问题**: 前端发送 `start_time`/`end_time`，后端 `get_usage_quantity_monthly` 读取 `start_month`/`end_month`。  
导致：月份范围过滤在前端点击查询时实际上始终无效，每次返回全量数据（受分页限制）。  
**建议**: 将前端发送的两个参数名改为 `start_month` 和 `end_month`。这是一个前端单行改动，风险低。

---

### R-03: `specificPart` 构建逻辑在前端重复 4 次（建议提取 composable）

**位置**: `DailyUsageReportView.vue`（2处）、`UsageQueryView.vue`（2处）、`MonthlyUsageReportView.vue`（2处）  
**问题**: 从 DOM 元素读取 `building/unit/room` 并组合 `specificPart` 字符串（含楼层提取规则）的逻辑出现多次，完全相同。  
**建议**: 提取为 `useSpecificPartBuilder()` composable 函数，供三个视图复用。

---

### R-04: `mqtt_handlers.py` + `daily_usage_calculator.py` — `parse_specific_part` 逻辑三处重复

**位置**: `ConnectionStatusHandler._parse_building_info`、`PLCDataHandler.batch_save_plc_data` 内嵌解析、`DailyUsageCalculator.parse_specific_part`  
**问题**: 三处均实现"从 specific_part 提取 building/unit/room_number"（处理3段和4段格式），未来一处逻辑调整需同步修改三处。  
**建议**: 提取为 `api/utils.py` 的共享函数，三处调用。

---

## 4. MINOR 问题（已确认，保留不动）

| 编号 | 位置 | 问题 | 理由 |
|------|------|------|------|
| m-01 | `views.py` `user_logout` | `if request.user.is_authenticated:` 永远为 True（已有 IsAuthenticated 装饰器） | 不影响功能，改动引入风险 > 收益 |
| m-02 | `views.py` `AdminUserCreate.create` | `print(...)` 替代 `logger.error(...)` | 建议改，但不属于本次性能/冗余清理范围 |
| m-03 | `views.py` `UserDetail.update` | `logger.debug` 记录含敏感字段的请求数据 | 生产环境日志级别默认 INFO，暂不触发 |
| m-04 | `mqtt_consumer.py` | 方法名 `_db_maintenance_thread` 与属性名 `self.db_maintenance_thread` 命名混淆 | 可读性问题，不影响功能 |
| m-05 | `PlcStatusView.vue` | 楼栋/单元选项硬编码 | 属业务功能缺口，非冗余/性能问题 |
| m-06 | `utils/api.js` | `exportToExcel` 挂在通用 API 对象上语义不一致 | 设计风格问题，不影响功能 |

---

## 5. 修改文件清单

| 文件 | 变更内容 |
|------|----------|
| `api/views.py` | 提升 imports 至顶部；PLC 统计 3 次 COUNT 改为 1 次 aggregate；合并双 aggregate；移除循环内冗余查询 |
| `api/daily_usage_calculator.py` | 移除无效 `select_related()`；移除未使用的 `Max`, `Subquery`, `OuterRef`, `F`, `connection` |
| `api/monthly_usage_calculator.py` | 移除重复类型校验；移除 `Sum`；提升 `import traceback` 到顶部 |
| `api/plc_data_cleaner.py` | delete() 返回值获取行数；移除未使用 `Q` import |

---

## 6. 测试验证

所有修改均为冗余清理和查询优化，不涉及任何业务逻辑变更。

```bash
cd C:\Users\yanggyan\MyProject\FreeArk\FreeArkWeb\backend\freearkweb
python manage.py test api
```

预期：116 tests, OK
