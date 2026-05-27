# 架构设计文档 — 设备列表故障筛选

```
file_header:
  document_id: ARCH-FFF-001
  project: FreeArk — freeark_device_list_fault_filter
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_system_architect (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-27
  depends_on:
    - REQ-SPEC-FFF-001
    - US-FFF-001
    - BUG-FCC-001 RCA (docs/troubleshooting/BUG-FCC-001_list_vs_panel_mismatch.md)
  context_snapshot: >
    FreeArk v0.5.3-FCC，Django DRF，Vue 3 + Element Plus，
    GET /api/device-management/device-list/ 现有过滤机制：
      - room_no/system_switch/plc_status/operation_mode → DB 层 ORM 过滤
      - screen_status → Python 层全量拉取后过滤（因 ORM annotate 层无法表达在线状态逻辑）
    fault_count 来自 get_fault_count_batch_cached（分页后批量查 PLCLatestData，缓存 60s），
    在 step 9a 中为当页 page_rows 获取，结果在 results 序列化循环中使用
```

---

## 0. 设计原则

本期为**最小侵入性增量改动**。FreeArk 设备列表已有成熟的多维过滤机制，
故障筛选遵循现有模式，不引入新架构元素，不新增 API 端点，不修改 `fault_utils.py` 核心逻辑。

---

## 1. 架构变更总览

### 1.1 变更范围

本期仅涉及两个文件，**不新增文件、不引入新依赖**：

| 文件 | 当前版本 | 变更性质 | 改动量估计 |
|------|---------|---------|-----------|
| `FreeArkWeb/backend/freearkweb/api/views.py` | v0.5.3-FCC | 增量：`device_management_device_list` 函数内新增 `fault_status` 过滤逻辑 | ~30 行 |
| `FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue` | v0.5.3-FCC | 增量：过滤栏新增 `el-select`，`fetchList` 新增参数透传，`handleReset` 新增清空 | ~25 行 |

### 1.2 不变更的内容

| 内容 | 理由 |
|------|------|
| `fault_utils.py` | BUG-FCC-001 hotfix 已验证，不触碰 |
| `/api/devices/fault-count/` 端点 | 独立端点，用途不同（单设备详情） |
| `/api/devices/fault-summary/` 端点 | 独立端点，用途不同（汇总视图） |
| `DeviceCardsView.vue` | 设备面板详情页，不在本期范围 |
| ORM 查询结构 | 故障过滤在 Python 层进行，无需改变 annotate 结构 |

---

## 2. 架构决策记录（ADR）

### ADR-FFF-001：故障过滤层级选择

**决策问题**：`fault_status` 过滤应在 DB 层（ORM annotate + filter）还是 Python 层执行？

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A — DB 层 ORM | 在 `OwnerInfo` queryset 上 annotate `fault_count`（子查询 SUM） | 天然支持 DB 层分页，`total` 正确 | PLCLatestData 故障数计算包含位域 popcount 和 Python 层 sub_type 过滤，无法纯 SQL 表达；需新增复杂 annotate；破坏 fault_utils 缓存层 |
| B — Python 层全量过滤（选用） | 拉取全量 `OwnerInfo` 行，批量查故障数，按 `fault_status` 在 Python 层过滤后再分页 | 与 `screen_status` 过滤完全同构，复用现有模式；不破坏 `fault_utils` 缓存层；逻辑清晰 | 需拉取全量设备数据（可接受，业主总数有限，现有 screen_status 已走此路径） |
| C — 前端纯客户端过滤 | 前端只过滤当前页的展示数据 | 零后端改动 | 分页 `total` 错误，翻页结果不准确；违反 AC-FFF-03-01 |

**决策：方案 B**

**理由**：
1. 与 `screen_status` 过滤完全同构（`views.py` step 8 已有全量拉取→Python 过滤→分页的完整模式）。
2. 不破坏 `fault_utils` 的缓存层（`get_fault_count_batch_cached`），故障数计算逻辑集中不分散。
3. `fault_count` 的计算包含位域 popcount 和 `_is_param_visible_for_section` 的 Python 逻辑，无法纯 SQL 表达。
4. 业主总数有限（单小区通常数百套），全量拉取代价可接受。

**风险**：若未来业主数量超过数千，方案 B 的全量拉取可能产生性能瓶颈。届时可考虑方案 A（引入专门的故障数 annotate），但本期规模无此需要。

---

### ADR-FFF-002：fault_status 过滤与 screen_status 过滤的执行顺序

**决策问题**：当 `fault_status` 和 `screen_status` 同时存在时，两者的 Python 层全量过滤如何叠加？

**分析**：
- `screen_status` 过滤：step 8 全量拉取 `qs`，Python 过滤后得到 `filtered` 列表，再切页得 `page_rows`。
- `fault_status` 过滤：step 9a 只对 `page_rows` 的 `specific_part` 批量查故障数。

**问题**：若 `screen_status` 过滤后再做 `fault_status` 过滤，需要在 step 8 和 step 9a 之间插入 `fault_status` 过滤逻辑；若在 step 9a 之后过滤，会导致 `page_rows` 已切页，`total` 无法反映实际过滤后总数。

**决策**：重构 step 8 的过滤路径，将 `fault_status` 与 `screen_status` 在同一 Python 层"全量过滤"阶段处理：

```
[全量 qs 拉取]
  ↓
[step 7: DB 层过滤：system_switch / plc_status / operation_mode]
  ↓
[step 8: Python 全量拉取 → 先计算 screen_status → 再叠加 fault_status → 分页]
```

具体：当 `fault_status` 参数存在时，强制走"全量拉取"路径（即使 `screen_status` 未设置），
批量查全量设备的故障数，在 Python 层按 `fault_status` 过滤，再分页。

**附加说明**：
- 若两者均存在，顺序为：先 `screen_status` 过滤，再 `fault_status` 过滤（AND 语义）。
- `total` 始终等于所有 Python 层过滤完毕后的列表长度。

---

### ADR-FFF-003：fault_count=None 的语义界定

**决策问题**：PLCLatestData 无记录的设备（`fault_count=None`）在过滤时如何处理？

| 方案 | 描述 |
|------|------|
| A — 视为"无故障"（选入 no_fault） | 简单，但语义不准确：数据缺失 ≠ 无故障 |
| B — 两侧均排除（选用） | 准确：只有有明确数据的设备参与判断 |
| C — 单独的"未知"选项 | 超出本期用户诉求，过度设计 |

**决策：方案 B**

**理由**：与 BUG-FCC-001 的设计原则一致——"不存在的数据不参与判断"。
用户需要的是"确定有故障"和"确定无故障"的设备，`None` 设备归类为任一侧均会产生误导。

---

## 3. 数据流图

```
用户操作"故障状态"下拉
        |
        v
[前端 filterFaultStatus = 'has_fault' | 'no_fault' | '']
        |
        | @change → handleSearch → currentPage = 1
        v
fetchList() → params.fault_status = filterFaultStatus.value (若非空)
        |
        v
GET /api/device-management/device-list/?fault_status=has_fault&page=1&page_size=20
        |
        v
[后端 views.device_management_device_list]
  step 1: 解析 fault_status 参数
  step 7: DB 层过滤（system_switch / plc_status / operation_mode）
  step 8: 是否需要全量拉取？
    - screen_status 存在 OR fault_status 存在 → 走全量拉取路径
      a. 全量拉取 all_rows = list(qs)
      b. 计算每行 screen_status（若需过滤）
      c. fault_status 存在 → 全量查故障数 get_fault_count_batch_cached(all_specific_parts)
      d. Python 层 AND 叠加过滤 → filtered 列表
      e. total = len(filtered)，切页 page_rows = filtered[start:start+page_size]
    - 两者均不存在 → DB 层直接切页（现有逻辑不变）
  step 9: 序列化
    - fault_status 存在时：fault_counts 已在 step 8c 获取，直接复用
    - fault_status 不存在时：现有逻辑（仅查 page_rows 的故障数）
        |
        v
响应：{"count": N, "page": 1, "page_size": 20, "results": [...]}
        |
        v
[前端 tableData = results, total = count]
分页控件 :total="total" 展示过滤后总数
```

---

## 4. 架构约束

| 编号 | 约束 | 来源 |
|------|------|------|
| ARCH-FFF-C-001 | 禁止查询 `device_param_history` 表（3766 万行 / 11.3 GB），故障数必须来自 `PLCLatestData` | fault_utils.py 文件头注释 |
| ARCH-FFF-C-002 | 故障数计算必须经过 `get_fault_count_batch_cached`，不得绕过缓存 | ADR-FC-001（LocMemCache，TTL=60s） |
| ARCH-FFF-C-003 | `fault_utils.py` 核心逻辑不得修改（BUG-FCC-001 hotfix 已验证，69/69 测试通过） | 稳定性约束 |
| ARCH-FFF-C-004 | 不新增 API 端点，在现有 device-list 上增量扩展 | 契约稳定性 |
| ARCH-FFF-C-005 | 前端过滤参数非空时才传入 query string（与现有其他参数行为一致） | 现有前端约定 |

---

## 5. 影响评估

### 5.1 性能影响

| 场景 | 现有行为 | 新增行为 | 净影响 |
|------|---------|---------|-------|
| 无 fault_status 过滤 | page_rows 批量查故障数（≤50 条） | 无变化 | 0 |
| 有 fault_status 过滤 | — | 全量查故障数（数百条，带缓存） | +1 SQL（首次），后续命中缓存 |
| screen_status + fault_status 同时 | 全量拉取 + 全量 screen 计算 | 额外加全量故障数查询 | +1 SQL（首次），后续命中缓存 |

缓存 TTL=60s，批量查询单次 SQL，预估全量设备（300 套）场景下延迟增加 < 20ms。

### 5.2 向后兼容性

- 无 `fault_status` 参数时：代码路径 100% 与 v0.5.3-FCC 相同，无破坏性变更。
- 前端响应字段结构不变（仍为 `{count, page, page_size, results}`）。
- 现有测试（69/69）不受影响。

### 5.3 测试覆盖要求

开发阶段需新增单元测试，覆盖：
1. `fault_status=has_fault` 返回 fault_count>0 设备
2. `fault_status=no_fault` 返回 fault_count==0 设备
3. `fault_count=None` 设备在两侧均不出现
4. `fault_status` 与 `screen_status` AND 叠加
5. `fault_status` 非法值静默忽略
（注：GROUP_D 测试工程师执行，本文档仅列出覆盖要求）
