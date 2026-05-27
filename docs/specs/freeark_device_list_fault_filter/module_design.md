# 模块与接口设计 — 设备列表故障筛选

```
file_header:
  document_id: MOD-FFF-001
  project: FreeArk — freeark_device_list_fault_filter
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_system_architect (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-27
  depends_on:
    - ARCH-FFF-001
    - REQ-SPEC-FFF-001
```

---

## 1. 模块清单

| 模块 ID | 文件 | 变更类型 | 覆盖需求 |
|---------|------|---------|---------|
| MOD-BE-DL | `FreeArkWeb/backend/freearkweb/api/views.py` 函数 `device_management_device_list` | 增量修改 | REQ-FUNC-FFF-02, REQ-FUNC-FFF-03, REQ-NFR-FFF-01 |
| MOD-FE-DL | `FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue` | 增量修改 | REQ-FUNC-FFF-01, REQ-NFR-FFF-02 |

---

## 2. MOD-BE-DL：后端设备列表 API 扩展

### 2.1 接口变更

**端点**：`GET /api/device-management/device-list/`（无变化）

**新增 Query 参数**：

| 参数名 | 类型 | 必选 | 取值 | 说明 |
|--------|------|------|------|------|
| `fault_status` | string | 否 | `has_fault` \| `no_fault` | 故障状态过滤；未传或非法值视为不过滤 |

**响应结构**：无变化（`{count, page, page_size, results}`）

**文档更新**：函数 docstring 的"Query 参数"节追加 `fault_status` 说明。

### 2.2 实现逻辑（伪代码）

```python
# step 1（已有）: 解析已有过滤参数
fault_status_filter = request.GET.get('fault_status', '').strip().lower()
# 仅接受合法值，其他静默忽略
if fault_status_filter not in ('has_fault', 'no_fault'):
    fault_status_filter = ''

# step 7（已有）: DB 层过滤（system_switch / plc_status / operation_mode）
# ...（不变）

# step 8（修改）: 全量拉取路径判断
need_full_scan = (
    screen_status_filter in ('online', 'offline', 'unknown')
    or fault_status_filter in ('has_fault', 'no_fault')
)

if need_full_scan:
    all_rows = list(qs)

    # 8a. screen_status 过滤（若存在）
    if screen_status_filter in ('online', 'offline', 'unknown'):
        all_rows = [r for r in all_rows
                    if _compute_screen_status(r._screen_last_seen_at) == screen_status_filter]

    # 8b. fault_status 过滤（若存在）
    if fault_status_filter in ('has_fault', 'no_fault'):
        all_specific_parts = [r.specific_part for r in all_rows]
        all_fault_counts = get_fault_count_batch_cached(all_specific_parts)
        if fault_status_filter == 'has_fault':
            all_rows = [r for r in all_rows
                        if (all_fault_counts.get(r.specific_part) or 0) > 0
                        and all_fault_counts.get(r.specific_part) is not None]
        else:  # no_fault
            all_rows = [r for r in all_rows
                        if all_fault_counts.get(r.specific_part) == 0]

    total = len(all_rows)
    start = (page - 1) * page_size
    page_rows = all_rows[start:start + page_size]
else:
    # 现有逻辑：DB 层直接切页
    total = qs.count()
    start = (page - 1) * page_size
    page_rows = list(qs[start:start + page_size])

# step 9a（修改）: 序列化时获取故障数
if fault_status_filter in ('has_fault', 'no_fault'):
    # 已在 step 8b 查过，复用 all_fault_counts
    fault_counts = {r.specific_part: all_fault_counts.get(r.specific_part)
                    for r in page_rows}
else:
    # 现有逻辑：仅查 page_rows
    page_specific_parts = [owner.specific_part for owner in page_rows]
    fault_counts = get_fault_count_batch_cached(page_specific_parts)
```

**关键实现细节**：

1. `has_fault` 判断条件：`fault_counts.get(sp) is not None and fault_counts.get(sp) > 0`
   （`None` 设备排除，`0` 设备排除）
2. `no_fault` 判断条件：`fault_counts.get(sp) == 0`
   （严格等于 0，`None` 和正整数均排除）
3. `fault_status` 非法值（如 `'invalid'`）：`fault_status_filter = ''`，不过滤
4. step 9a 中当 `fault_status_filter` 存在时，直接从 step 8b 的 `all_fault_counts` 中取 `page_rows` 的子集，**不重复查询**

### 2.3 需求覆盖矩阵

| 需求 ID | 覆盖方式 |
|---------|---------|
| REQ-FUNC-FFF-02 | 新增 `fault_status` 参数解析与 Python 层过滤（step 1 + step 8b） |
| REQ-FUNC-FFF-03 | `total = len(all_rows)` 在所有 Python 层过滤完成后计算 |
| REQ-NFR-FFF-01 | step 8b 与 step 9a 共享同一次 `get_fault_count_batch_cached` 调用，无额外 DB 查询 |
| AC-FFF-02-05 | `None` 设备在 has_fault / no_fault 两侧均排除（显式判断） |
| AC-FFF-02-06 | 非法 `fault_status` 值 → `fault_status_filter = ''`，不过滤 |

---

## 3. MOD-FE-DL：前端设备列表视图扩展

### 3.1 模板变更（过滤栏）

在"运行模式" `el-select` 之后，"搜索"按钮之前，插入：

```html
<!-- REQ-FUNC-FFF-01: 故障状态过滤 -->
<el-select
  v-model="filterFaultStatus"
  placeholder="故障状态"
  clearable
  style="width: 140px"
  @change="handleSearch"
>
  <el-option label="仅有故障" value="has_fault" />
  <el-option label="仅无故障" value="no_fault" />
</el-select>
```

### 3.2 Script 变更

**新增响应式状态**（在 `filterOperationMode` 之后）：

```javascript
const filterFaultStatus = ref('')
```

**`fetchList` 中新增参数传入**（在 `filterOperationMode` 参数处理之后）：

```javascript
if (filterFaultStatus.value) {
  params.fault_status = filterFaultStatus.value
}
```

**`handleReset` 中新增清空**（与其他 filter 变量同步）：

```javascript
filterFaultStatus.value = ''
```

**`return` 中新增暴露**：

```javascript
filterFaultStatus,
```

### 3.3 需求覆盖矩阵

| 需求 ID | 覆盖方式 |
|---------|---------|
| REQ-FUNC-FFF-01 | 新增 `el-select`（`clearable`，`@change="handleSearch"`，`style="width: 140px"`）|
| REQ-NFR-FFF-02 | `style="width: 140px"`，`clearable`，`@change="handleSearch"` 与现有控件一致 |
| AC-FFF-01-04 | `handleReset` 中 `filterFaultStatus.value = ''` |
| AC-FFF-03-02 | `handleSearch` 已有 `currentPage.value = 1`，`filterFaultStatus` 触发 `handleSearch` 即满足 |

---

## 4. 完整需求覆盖矩阵

| 需求 ID | 覆盖模块 | 覆盖方式 |
|---------|---------|---------|
| REQ-FUNC-FFF-01 | MOD-FE-DL | `el-select` + `filterFaultStatus` 状态 + `fetchList` 参数传入 |
| REQ-FUNC-FFF-02 | MOD-BE-DL | `fault_status` 参数解析 + Python 层全量过滤 |
| REQ-FUNC-FFF-03 | MOD-BE-DL + MOD-FE-DL | 后端 `total = len(all_rows)`；前端 `total.value = response.count` |
| REQ-NFR-FFF-01 | MOD-BE-DL | step 8b 与 step 9a 共享同一次 `get_fault_count_batch_cached` |
| REQ-NFR-FFF-02 | MOD-FE-DL | `el-select` 样式与现有控件一致 |
| REQ-NFR-FFF-03 | — | 本期不实现（技术债记录，与现有过滤项一致） |

**所有 REQ-FUNC-FFF-* 均有模块覆盖。无需求未覆盖项。**

---

## 5. 接口依赖图

```
MOD-FE-DL
  └── 调用 GET /api/device-management/device-list/?fault_status=...
        └── MOD-BE-DL (views.device_management_device_list)
              ├── 复用 fault_utils.get_fault_count_batch_cached [不修改]
              │     └── PLCLatestData 表 [不修改]
              └── 复用 OwnerInfo queryset [不修改]
```

**单向依赖，无循环依赖。**

---

## 6. 开放问题

| 编号 | 问题 | 状态 |
|------|------|------|
| OQ-ARCH-FFF-001 | 若 screen_status 和 fault_status 同时过滤，`all_fault_counts` 在 screen 过滤之后的 `all_rows` 上批量查询；若 screen 过滤大幅缩小 rows 集合，可以节省查询量，但需确保 `all_specific_parts = [r.specific_part for r in all_rows]` 在 screen 过滤后执行。实现人员须注意步骤顺序（8a 先于 8b）。 | 已在伪代码中明确（8a→8b 顺序） |
| OQ-ARCH-FFF-002 | 若未来单小区设备数量超过 1000 套，全量拉取 + 全量故障数查询的性能可能成为瓶颈。长期方案是 ADR-FFF-001 方案 A（DB 层 annotate）。 | 技术债，本期不处理 |
