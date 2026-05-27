# 技术栈说明 — 设备列表故障筛选

```
file_header:
  document_id: TECH-FFF-001
  project: FreeArk — freeark_device_list_fault_filter
  version: 1.0.0-DRAFT
  status: DRAFT
  author_agent: sub_agent_system_architect (PM-orchestrated, PARTIAL_FLOW)
  created_at: 2026-05-27
  depends_on: ARCH-FFF-001
```

---

## 技术栈（继承现有，无新增依赖）

| 层 | 技术 | 版本（现有）| 本期变化 |
|----|------|-----------|---------|
| 后端框架 | Django + Django REST Framework | 现有 | 无 |
| 缓存 | Django LocMemCache | 现有 | 无（故障数缓存 TTL=60s 已配置） |
| 前端框架 | Vue 3 | 现有 | 无 |
| UI 组件库 | Element Plus | 现有 | 新增一个 `el-select` 控件（与现有用法相同） |
| HTTP 客户端 | `@/utils/api.js`（axios 封装） | 现有 | 无，query string 构建沿用 `URLSearchParams` |

**无新增 npm 包、Python 包、数据库表、migration、环境变量。**
