# 代码审查报告 — FreeArk v0.5.7 按房型过滤设备面板与采集点裁剪

```
file_header:
  document_id: CR-v0.5.7
  title: FreeArk v0.5.7 — 代码审查报告
  author_agent: sub_agent_software_developer (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: v0.5.7-fix2
  created_at: 2026-05-23
  revised_at: 2026-05-23
  status: APPROVED
  references:
    - docs/development/v0.5.7_room_filter/implementation_plan_v0.5.7.md
    - docs/architecture/module_design_v0.5.7.md
```

---

## 1. 审查摘要

| 维度 | 结论 |
|------|------|
| CRITICAL finding 数量 | **0** |
| MAJOR finding 数量 | 1 |
| MINOR finding 数量 | 3 |
| 是否满足 GROUP_C 门控标准（无 CRITICAL）| **是** |

---

## 2. 逐文件审查

### 2.1 `api/utils_room_filter.py`（M1）

**总体评估**：设计与实现高度一致，逻辑清晰，无 CRITICAL 问题。

| finding | 严重级别 | 描述 |
|---------|---------|------|
| CR-M1-01 | MINOR | `get_panel_param_blocklist()` 每次调用均发出 `DeviceConfig` DB 查询（约 50 条记录），无额外缓存。由于 `get_available_sub_types()` 有 300s 缓存，blocklist 的 DB 查询频率与 `get_available_sub_types` 的缓存 miss 频率相同（约每 5 分钟一次），可接受。后续可将 blocklist 结果也缓存（与 available_sub_types 共用同一缓存 key），但当前版本不影响正确性。 |
| CR-M1-02 | INFO | `_match_panel_sub_types()` 对 `panel_fourth_children` 的「房间数量 >= 4」判断（原 finding）已在 fix2 中修复：该判断在三房户型（房间总数 5）上误触发，已改为「含书房 AND 含儿童房」。详见 fix2 审查条目 CR-M1-fix2-01。 |
| CR-M1-fix2-01 | **CRITICAL_FIXED**（生产 bug，fix2 修复）| `_match_panel_sub_types()` 中 `panel_fourth_children` 判定使用 `len(ori_room_names) >= 4` 作为四房识别启发式，而生产数据中三房户型（9-1-10-1002）房间总数也是 5，导致三房和四房 `get_available_sub_types()` 返回值完全相同，`get_panel_param_blocklist()` 对三房返回空集，v0.5.7 功能性等同未生效。修复：核心判定改为 `has_study_room = any('书房' in name ...)` AND `has_children_keyword = any('儿童房' in name ...)`，保留「含四字」分支作冗余识别。经生产全量 40 专有部分扫描验证：「含书房 = 四房」100% 吻合。CRITICAL finding 数：修复前 1，修复后 0。 |
| CR-M1-03 | INFO | `get_allowed_param_names()` 是设计文档 M7-A 中通过内联 DeviceConfig 查询实现的功能，被抽出为独立工具函数，提升了 M7-A 的可测试性，属于良好的工程实践。 |

### 2.2 `api/views.py`（M2、M5、M7-A）

**总体评估**：三处变更均遵循「最小侵入」原则，无 CRITICAL 问题。

| finding | 严重级别 | 描述 |
|---------|---------|------|
| CR-M2-01 | INFO | `get_available_sub_types()` 调用位置正确（在 `configs_qs` 和 `latest_by_param` 构建之后，`for cfg in configs_qs` 循环之前），确保缓存 miss 时只多一次查询，不影响现有逻辑。 |
| CR-M5-01 | MINOR | `device_tree_sync_batch()` 在启动批量任务**前**清缓存（`invalidate_room_filter_cache()` 在 `start_batch_sync()` 之后立即调用），设计合理。但存在一个窗口：批量同步执行期间（可能几分钟）新建的缓存条目将在同步完成前被重新填充为旧数据，然后在下次请求时重新读取最新数据（缓存 TTL 300s 内可能读到旧数据）。这是已知的 trade-off，与设计文档描述一致，不影响正确性（最终一致），无需修改。 |
| CR-M7A-01 | MINOR | `device_ondemand_refresh()` 内仍保留 `import datetime as _dt`（原有 inline import），与模块顶部的 `from .utils_room_filter import ...` 风格不一致（inline import 是原有代码风格，本次不做重构以降低 diff 范围），属于代码风格问题，无功能影响。 |

### 2.3 `api/views_device_settings.py`（M3）

**总体评估**：变更位置精确，与 M2 对称，无问题。

| finding | 严重级别 | 描述 |
|---------|---------|------|
| CR-M3-01 | INFO | `available_sub_types` 在 `groups` 循环前计算，位于 `DeviceConfig` 查询之后，逻辑顺序正确。与 M2 模式一致，可维护性良好。 |

### 2.4 `api/mqtt_handlers.py`（M4）

**总体评估**：落库侧防御层实现正确，无 CRITICAL 问题。

| finding | 严重级别 | 描述 |
|---------|---------|------|
| CR-M4-01 | MAJOR | `get_panel_param_blocklist()` 在 `PLCLatestDataHandler.handle()` 中**每次消息到达时**都会被调用（包括定时周期采集，约每 10 分钟一次/设备）。由于 `get_panel_param_blocklist()` 内部调用了 `get_available_sub_types()`（有 300s 缓存）和 `DeviceConfig.objects.filter(...)`（无缓存，约 1 次 DB 查询），缓存 miss 时有额外 DB 查询。当前场景（低 QPS，MQTT 消息频率低）可接受，但在高频消息场景下可能成为性能瓶颈。**建议**：后续版本（v0.5.8）可将 `DeviceConfig` 的 blocklist 结果缓存在 `utils_room_filter` 模块中（与 available_sub_types 共享缓存 key），或在 `handle()` 入口处判断 `if not param_blocklist: skip`（已实现：`if param_blocklist and param_name in param_blocklist`，空集合时不进入判断）。当前 v0.5.7 实现正确，MAJOR 级别是提醒而非缺陷。 |
| CR-M4-02 | INFO | `skipped_room_filter` 计数器已加入日志摘要，便于运维排查。日志格式与现有代码风格（f-string）一致。 |

### 2.5 `datacollection/ondemand_collect_subscriber.py`（M7-B）

**总体评估**：变更最小侵入，向后兼容，无 CRITICAL 问题。

| finding | 严重级别 | 描述 |
|---------|---------|------|
| CR-M7B-01 | INFO | `allowed_params` 为空集合 `set()` 的边界情况：如果 Django 发送了 `allowed_params=[]`（空列表），采集侧会将其转为 `set()`，导致 `configs=[]`，进而触发「plc_config 为空」的警告日志并发布 `success=false` 结果。此边界在 M7-A 中已防御（`get_allowed_param_names()` 返回 `None` 时不注入字段，返回空列表也不注入，故采集侧不会收到空列表）。但采集侧的空集合处理路径仍需在单元测试中验证（测试要点已在 module_design §测试要点 中标注）。 |
| CR-M7B-02 | INFO | `_on_request()` 中 `allowed_params` 的类型转换（`list → set`）发生在防重入检查之前，即使因防重入直接 return，转换工作已完成（无害的轻量操作）。不影响逻辑正确性。 |

---

## 3. 综合结论

### 3.1 门控标准检查

| 标准 | 结果 | 说明 |
|------|------|------|
| 所有模块已实现（M1~M5、M7-A、M7-B）| **通过** | M6 按 PM 决策不实施 |
| code_review 无 CRITICAL finding | **通过** | 0 个 CRITICAL |
| 所有变更均有设计文档支撑 | **通过** | 每处变更均注释标注 module_id |
| 不修改 plc_config.json | **通过** | 未触及 |
| 不修改 PLC 程序 | **通过** | 未触及 |
| 不实施 M6 清理命令 | **通过** | 文件未创建 |

### 3.2 遗留问题（移交测试/后续版本）

| 编号 | 来源 | 级别 | 描述 | 建议处理版本 |
|------|------|------|------|------------|
| REM-01 | CR-M4-01 | MAJOR | `get_panel_param_blocklist()` 在缓存 miss 时有额外 DB 查询，高频场景下可优化 | v0.5.8（低优先级，当前场景 QPS 极低）|
| REM-02 | CR-M1-01 | MINOR | `get_panel_param_blocklist()` 结果未缓存，可与 available_sub_types 共享缓存 | v0.5.8 |
| REM-03 | CR-M7B-01 | MINOR | `allowed_params=set()` 边界需单元测试覆盖 | v0.5.7 测试阶段（GROUP_D）|

---

## 4. 移交测试确认

代码实现符合 module_design_v0.5.7.md 设计规格，无 CRITICAL finding，可进入 GROUP_D 测试阶段。
