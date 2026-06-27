<!--
file_header:
  document: implementation_plan_v1.11.1.md
  project: FreeArk
  feature: v1.11.1 微信小程序业主端·结构展示增强
  author_agent: sub_agent_software_developer
  created_at: 2026-06-27
  status: APPROVED
-->

# 实现计划 v1.11.1 — 微信小程序业主端·结构展示增强

## 实现概览

- **根因修复**：`miniapp_owner_realtime_params` 视图中 `if record is None: continue` + 尾部清理逻辑导致无 PLCLatestData 记录的面板房间被静默丢弃，生产实例 3-1-7-702 仅显示 1/4 个面板。
- **解决方案**：新增独立结构端点 `GET /api/miniapp/owner/structure/`，从 DeviceFloor → DeviceRoom → DeviceNode 设备树直接遍历，完全不依赖 PLCLatestData，保证结构完整性（REQ-FUNC-001-C）。
- **两阶段渲染**：Phase 1 拉取结构骨架（structure 端点），Phase 2 后台叠加实时值（realtime-params 端点）。
- **总模块数**：2 个模块（MOD-1111-BE-01 后端结构端点；MOD-1111-FE-01/FE-02 前端适配）。
- **总文件数**：5 个（1 新建测试文件；4 修改现有文件）。
- **实现顺序**：由依赖拓扑排序确定（后端先于前端，URL 注册先于视图消费）。

---

## 模块实现计划（按拓扑顺序）

| 序号 | MOD-ID | 模块名 | 文件路径 | 依赖前置模块 | 复杂度 | 状态 |
|------|--------|--------|---------|------------|--------|------|
| 1 | MOD-1111-BE-01 | 后端结构骨架视图 | `FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py` | IsOwnerUser（已有）、DeviceFloor/Room/Node（已有模型）、DeviceConfig（已有）、_match_panel_sub_types（已有工具函数） | H | DONE |
| 2 | MOD-1111-URL | URL 路由注册 | `FreeArkWeb/backend/freearkweb/api/urls_miniapp.py` | MOD-1111-BE-01 | L | DONE |
| 3 | MOD-1111-FE-02 | 前端 API 方法 | `miniprogram/utils/api.js` | MOD-1111-URL | L | DONE |
| 4 | MOD-1111-FE-01 | 前端两阶段渲染 | `miniprogram/subpackages/control/pages/param-settings.vue` | MOD-1111-FE-02（getOwnerStructure）、MOD-1110-FE（getOwnerRealtimeParams，已有） | H | DONE |
| 5 | MOD-1111-TEST | 端点集成测试 | `FreeArkWeb/backend/freearkweb/api/tests/test_miniapp_owner_structure_v1111.py` | MOD-1111-BE-01 | M | DONE |

---

## 各文件实现要点

### 1. `views_miniapp_device_settings.py`（+180 行）

新增内容（从原 430 行至 610 行）：

- 扩展 `import` 块：加入 `DeviceFloor`、`DeviceRoom` 两个已有模型；`_match_panel_sub_types` 工具函数。
- 常量 `_PRODUCT_CODE_TO_SUB_TYPE`：product_code → sub_type 映射（ADR-1111-02）。
- 常量 `_PANEL_PRODUCT_CODE = '120003'`。
- 私有函数 `_infer_sub_type(product_code, ori_room_name)`：面板设备调用 `_match_panel_sub_types` 推导，系统级设备查表，未知返回空字符串。
- 视图函数 `miniapp_owner_structure`（IFC-1111-BE-01）：
  - 归属校验与 `miniapp_owner_realtime_params` 完全一致（REQ-NFUNC-004）。
  - `DeviceFloor.objects.filter(owner__specific_part=...).prefetch_related('rooms__devices')`（2 次 DB 往返）。
  - 分组规则（ADR-1111-03）：`_match_panel_sub_types([room.ori_room_name])` 非空 → `rooms[]`；空 → `system_devices[]`。
  - 批量查 `DeviceConfig.filter(sub_type__in=..., is_active=True).values(...)` 填充 `params_skeleton`（OQ-1111-A Option A）；不查 PLCLatestData。
  - DeviceFloor 无记录 → `sync_status="pending"` + 空列表（OQ-E5）。
  - `device_sns` 扁平列表（ADR-1111-06，供前端 connectRoom DB 全量发现使用）。

### 2. `urls_miniapp.py`（+6 行）

```python
path('owner/structure/', views_ds.miniapp_owner_structure,
     name='miniapp-owner-structure'),
```

### 3. `api.js`（+16 行）

```javascript
// IFC-1111-FE-02-1: getOwnerStructure
getOwnerStructure: (specificPart) =>
  http.get('/api/miniapp/owner/structure/', { specific_part: specificPart }),
```
含完整 JSDoc 说明响应格式（sync_status="ok"/"pending" 两种分支）。

### 4. `param-settings.vue`（全页重构，+~400 行净增）

**Template 层：**
- `structureLoading` guard → "加载中…" spinner。
- `sync_status="pending"` → "设备结构初始化中" + 刷新按钮（调用 `loadStructure(sp, true)`）。
- `structure.rooms` 循环：`resolveRoomName(room)` + `room.devices` 迭代。
- 每个 device → `device.params`（骨架）迭代，叠加 `getOverlayValue(realtimeData, device.sub_type, param.param_name, ps.loading)`。
- `structure.system_devices` → "全屋系统" section。

**Script 层：**
- `_initPartState` 增加 `structureLoading: false`、`structure: null`。
- `connectRoom`（v1.11.1）：DB-full SN 发现路径优先（从 `structure.device_sns`），废弃 probeNeighbors ±8 范围扫描（DEPRECATED 注释保留向后）。
- 缓存：`writeStructureCache(sp, data)`（24h TTL；pending 降级 5min）、`readStructureCache(sp)`（TTL 检测 + 过期丢弃）。
- Phase 1：`loadStructure(sp, forceRefresh?)`。
- Phase 2：`getParamsForSubType(realtimeData, subType)`、`getOverlayValue(realtimeData, subType, paramName, isLoading)`（ADR-1111-05：sub_type + param_name 作为叠加键）。
- `resolveRoomName(room)` → `room.room_name || room.ori_room_name || '未知房间'`（OQ-E2）。
- `toggleExpand(sp)` 重写：await loadStructure → 读 realtime 缓存展示 → 后台 loadRealtimeParams。

**CSS 层（新增类）：**
- `.sync-pending`、`.sync-pending-text`（降级状态样式）。
- `.system-block`、`.device-name-system`（"全屋系统"区块）。
- `.no-params-placeholder`（骨架未覆盖参数占位）。

### 5. `test_miniapp_owner_structure_v1111.py`（488 行，25 个测试用例）

测试类清单：
| 类名 | 用例数 | 覆盖内容 |
|------|--------|---------|
| `StructurePermissionsTest` | 3 | 权限矩阵（user 200/operator 403/anon 401）|
| `StructureAuthFilterTest` | 3 | 归属过滤（自己 200/他人 403/缺参 400）|
| `StructureSyncPendingTest` | 1 | DeviceFloor 无记录 → sync_status=pending |
| `StructureGroupingTest` | 5 | panel/system 分组、device_sns、sub_type 推导、sync_status=ok |
| `StructureParamsSkeletonTest` | 4 | params 字段存在、无 value 字段、inactive 排除、display_name 正确 |
| `StructureNoPlcDataTest` | 4 | REQ-FUNC-001-C 核心：无 PLCLatestData 4 房全返回 |
| `StructureMultiDeviceTypeTest` | 2 | 5 种系统设备 sub_type 映射、未知 product_code 不崩溃 |
| `StructureRoomNameTest` | 2 | room_name + ori_room_name 字段 |

---

## 架构偏差记录

无架构偏差。所有实现均严格遵循预决策（OQ-E1 至 OQ-E5、OQ-1111-A 至 OQ-1111-C）和 ADR-1111-01 至 ADR-1111-06。

---

## 关键设计约束符合性

| 约束 | 实现方式 | 状态 |
|------|---------|------|
| REQ-FUNC-001-C：无 PLCLatestData 也返回完整房间结构 | 视图完全不查 PLCLatestData | DONE |
| REQ-NFUNC-004：归属过滤越权 403 | OwnerUserBinding.filter(user, active=True) 校验 | DONE |
| OQ-E5：无 DeviceFloor → sync_status=pending | floors 查询为空时降级 | DONE |
| OQ-1111-A Option A：params_skeleton 来自 DeviceConfig | DeviceConfig 批量查，无 PLCLatestData | DONE |
| ADR-1111-04：两阶段渲染 | Phase 1 await loadStructure + Phase 2 后台 loadRealtimeParams | DONE |
| ADR-1111-05：sub_type+param_name 叠加键 | getOverlayValue 签名 | DONE |
| ADR-1111-06：DB-full SN 发现 | connectRoom 优先读 structure.device_sns | DONE |
| 无新增 DB 模型/迁移 | 无 | DONE |
| 停留 main 分支，无 commit/push | 无 git 操作 | DONE |
