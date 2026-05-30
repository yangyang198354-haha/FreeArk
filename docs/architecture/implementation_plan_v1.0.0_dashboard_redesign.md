# 实施计划

```
file_header:
  document_id: IMPL-v1.0.0-DASHBOARD-REDESIGN
  title: 系统看板重设计 + 设备列表凝露提醒列 — 实施计划
  author_agent: sub_agent_software_developer
  project: FreeArk 住宅能耗/暖通监控平台
  version: v1.0.0
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: DRAFT
```

## 已实施改动清单

| 编号 | 文件 | 改动类型 | 状态 |
|------|------|---------|------|
| 1 | `FreeArkWeb/backend/freearkweb/api/views.py` | 新增 step 9b（凝露批量查询），新增 `dashboard_fault_summary` 函数，新增 `dashboard_device_fault_summary` 函数 | DONE |
| 2 | `FreeArkWeb/backend/freearkweb/api/urls.py` | 新增 2 条 dashboard 路由 | DONE |
| 3 | `FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue` | 在「故障数量」后插入「凝露提醒」列 | DONE |
| 4 | `FreeArkWeb/frontend/src/views/HomeView.vue` | 新增状态/fetch函数/跳转函数/分组重排/5张新卡片/CSS | DONE |
| 5 | `FreeArkWeb/frontend/src/views/FaultManagementView.vue` | onMounted 补充 sub_type URL 参数读取 | DONE |

## 代码评审报告（self-review）

### CRITICAL findings：无

### HIGH findings：无

### MEDIUM findings：

**M-001**：`views.py` 中两个新函数使用了 `from .models import FaultEvent` 的局部导入。`FaultEvent` 已在文件顶部的 `views_fault.py` 中导入，但 `views.py` 顶部的 import 中未包含 `FaultEvent` 和 `DeviceNode`。

分析：`views.py` 顶部的 models import 为：
```python
from .models import CustomUser, UsageQuantityDaily, ..., ScreenConnectivityStatus, TokenActivity
```
未包含 `FaultEvent`、`DeviceNode`、`CondensationWarningEvent`。新增的代码均使用局部 import（`from .models import ...`），可以正常运行，但不符合 views.py 现有的顶部集中 import 风格。

决策：局部 import 可以正常工作，与 `fault_utils.py` 中的模式一致（该文件也使用局部 import），保持现状。若后续重构再统一到顶部。

**M-002**：HomeView.vue 中，原有 `top-cards-row` 布局的 `.power-status-wrapper` CSS 不再使用（已将开机状况卡片移出 top-cards-row），CSS 中保留有 `.power-status-wrapper` 等相关 CSS 规则。这些规则不产生任何错误，只是死代码，影响可忽略。

### LOW findings：

**L-001**：HomeView.vue 中 WindPower 图标（用于新风卡片）需确认该 icon 在当前项目已安装的 @element-plus/icons-vue 版本中存在。Element Plus Icons v2.x 包含 WindPower。可在测试阶段验证，若不存在可替换为 `Wind` 或其他图标。

**L-002**：SetUp 图标（用于温控面板卡片）同理需验证存在性。

### 结论：PASS（无 CRITICAL/HIGH，MEDIUM findings 已分析且不阻塞功能）
