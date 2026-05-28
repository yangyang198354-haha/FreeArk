# 技术栈说明

```
file_header:
  document_id: TECH-v0.6.1-FM-UX
  title: 故障管理 UX 调整 — 技术栈
  author_agent: sub_agent_system_architect (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗 / 暖通监控平台
  version: v0.6.1-FM-UX
  created_at: 2026-05-28
  status: DRAFT
  references:
    - docs/architecture/architecture_design_v0.6.1_fault_mgmt_ux.md
    - docs/architecture/module_design_v0.6.1_fault_mgmt_ux.md
    - docs/architecture/tech_stack_v0.6.0_fault_management.md
    - FreeArkWeb/backend/requirements.txt
    - FreeArkWeb/frontend/package.json
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-28 | 初始草稿，v0.6.1-FM-UX 无新增依赖，所有技术沿用现有生产栈 |

---

## 1. 技术栈总览

**v0.6.1-FM-UX 不引入任何新的第三方库或基础设施组件。** 所有新功能通过现有技术栈的组合实现。

| 层次 | 技术 | 版本/状态 | v0.6.1-FM-UX 变化 |
|------|------|----------|------------------|
| 运行平台 | 树莓派 192.168.31.51，物理机，无 Docker | — | 无变化 |
| 操作系统 | Linux（Raspberry Pi OS）| — | 无变化 |
| 服务管理 | systemd | — | **无新增服务单元**（v0.6.0-FM 已有的 freeark-backend/freeark-fault-consumer/freeark-fault-cleanup.timer 均无改动）|
| 后端语言 | Python 3.x | 同现有生产版本 | 无变化 |
| 后端框架 | Django | >=5.2.0（requirements.txt）| **无版本变更**；新增 1 个 Python 模块文件（device_name_cache.py）；修改 2 个现有文件（constants.py、serializers_fault.py）|
| REST API 框架 | Django REST Framework | 同现有生产版本 | **无版本变更**；FaultEventSerializer 新增 2 个 SerializerMethodField |
| WSGI/ASGI 服务器 | uvicorn[standard] | >=0.29.0（--workers 1）| 无变化 |
| MQTT 客户端 | paho-mqtt | >=1.6.1 | 无变化（fault_consumer 主流程不改）|
| 数据库（生产）| MySQL 9.4 @ 192.168.31.98:3306 | — | **无新 migration**；无新表；仅新增 SELECT 查询（device_name_cache 加载，量级 19 条）|
| 数据库（测试）| SQLite | Django 内置 | 无变化，所有测试 SQLite 兼容 |
| 进程内缓存 | Python 内置 dict + time.monotonic() | Python 标准库 | **新增使用方式**（device_name_cache.py）；不引入 Redis 或 LocMemCache |
| 前端框架 | Vue 3 + Vite | 同现有生产版本 | **无版本变更**；修改 3 个现有 Vue 组件（Layout.vue、FaultManagementView.vue、DeviceManagementDeviceListView.vue）|
| 前端 UI 组件库 | Element Plus | 同现有生产版本 | **无版本变更**；新增使用 `<el-radio-group>` + `<el-radio-button>`（均为 Element Plus 内置组件，已在其他页面使用）|
| 前端 HTTP 客户端 | axios | 同现有生产版本 | 无变化 |
| 前端路由 | Vue Router | 同现有生产版本 | 无变化（路由 `FaultManagement` 已存在）|
| 构建工具 | Vite | 同现有生产版本 | 无变化 |

---

## 2. 新增/变更的技术点详情

### 2.1 Python 标准库：`time.monotonic()`

用于 `device_name_cache.py` 的 TTL 计时，替代 `datetime.now()`，因为 `monotonic()` 不受系统时间回拨影响，适合 TTL 场景。

- **引入原因**：TTL 需要测量时间间隔（elapsed time），`monotonic()` 语义精确。
- **已有用法**：Python 标准库，无需安装，与现有生产环境兼容。

### 2.2 Element Plus `<el-radio-group>` + `<el-radio-button>`

用于替换 `FaultManagementView.vue` 中的 `<el-switch>`，实现三态筛选控件。

- **Element Plus 版本兼容性**：`<el-radio-group>` 和 `<el-radio-button>` 是 Element Plus 核心组件，v1.x/v2.x 均支持，现有生产版本已包含。
- **`value` prop 说明**：Element Plus v2.x 中 `<el-radio-button>` 使用 `value` prop（旧版用 `label`）；需确认当前 Element Plus 版本。若为旧版（`label` 模式），将 `value` 改为 `label` 即可，逻辑不变。

---

## 3. 明确排除的技术（v0.6.1-FM-UX 不引入）

| 排除项 | 排除原因 |
|--------|---------|
| Redis | 进程内 Python dict 满足需求（19 条，< 1 MB）；Redis 化触发条件未达（实测内存远低于 256 MB 阈值）|
| Docker | 生产环境物理机约束，禁止使用 Docker |
| LocMemCache | device_name_cache 使用纯 Python dict，不需要 Django 缓存框架 |
| DB migration | v0.6.1-FM-UX 不改 fault_event schema，无需任何 migration |
| Celery / APScheduler | 无新增定时任务需求 |
| 新 systemd 服务 | 无新增后台服务 |
| `threading.Lock` | dict 操作依赖 GIL 保障；幂等重建设计下无需显式加锁（已在 ADR-UX-06 论证）|

---

## 4. 部署技术路径

与 v0.6.0-FM 部署流程一致，无额外步骤：

```
plink 192.168.31.51 "cd /home/freeark/FreeArk && git pull origin main"
plink 192.168.31.51 "sudo systemctl restart freeark-backend"
# 前端（在开发机 build 后 commit，或在 Pi 上 build）：
# npm run build（FreeArkWeb/frontend）
```

**无 migration 执行步骤**（因为 v0.6.1-FM-UX 不新增 migration）。

**验证命令**：
```bash
# 确认后端重启正常
journalctl -u freeark-backend -n 20

# 确认 device_name_cache 加载日志（DEBUG 级别）
journalctl -u freeark-backend | grep device_name_cache
```

---

## 5. 技术债务与后续考量

| 项目 | 说明 | 优先级 |
|------|------|--------|
| `building_data.js` 缺楼层字段 | 导致无法从 CascadingSelector 输出中推导 4 段 `specific_part`；本版本用 icontains 容错，无误命中风险；若未来需要精确 4 段匹配，需在 `building_data.js` 中为每个房号添加楼层属性 | 低 |
| Element Plus `<el-radio-button>` 版本兼容 | 需确认 `value` prop（v2.x）vs `label` prop（v1.x）；开发阶段测试时注意 | 低 |
| `PRODUCT_CODE_LABELS` 维护 | 当前 7 条，硬编码；新设备接入后需手动添加；长期考虑迁移至 DB 表（AB-UX-003）| 低 |
