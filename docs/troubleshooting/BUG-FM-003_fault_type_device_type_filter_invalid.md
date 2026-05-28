# BUG-FM-003 RCA：故障管理页"故障类型"和"设备类型"过滤器完全无效

| 项 | 值 |
|---|---|
| Bug 编号 | BUG-FM-003 |
| 发现日期 | 2026-05-28 |
| 影响版本 | v0.6.0-FM、v0.6.1-FM-UX（均受影响） |
| 修复版本 | v0.6.1-FM-UX patch（本次提交） |
| 严重级别 | HIGH（过滤器完全失效，用户无法按故障类型/设备类型缩小结果集） |
| 影响范围 | 前端单文件：`FreeArkWeb/frontend/src/views/FaultManagementView.vue` |
| 后端影响 | 无（后端逻辑完全正确） |

---

## 现象描述

用户在故障管理页（`/device-management/faults`）的过滤栏中选择"故障类型"（如"通信故障"）或"设备类型"（如"新风机"）后，点击查询或触发 `@change`，列表不发生任何变化，返回的数据与不选择过滤器时完全相同。

---

## 根因分析

### 直接原因

`FaultManagementView.vue` 的 `fetchFaultEvents()` 函数（v0.6.1 修复前第 324-331 行）将数组参数直接赋值给 axios `params` 对象：

```js
// 修复前（错误代码）
if (filters.fault_types.length > 0) {
  // 注释声称 axios 会序列化为重复参数：fault_type=comm&fault_type=sensor
  // 实际上 axios 1.x 生成的是：fault_type[]=comm&fault_type[]=sensor（带方括号）
  params.fault_type = filters.fault_types
}
if (filters.sub_types.length > 0) {
  params.sub_type = filters.sub_types
}
```

代码注释本身说明了意图（期望生成重复参数名），但 axios 1.x 的实际默认行为与注释描述不符。

### axios 1.x 实际序列化行为

axios 1.x（项目使用 `^1.7.9`）对数组参数的默认序列化格式为**带方括号**的形式：

```
// axios 实际生成（错误）：
fault_type[]=comm&fault_type[]=sensor

// 或带索引（取决于配置）：
fault_type[0]=comm&fault_type[1]=sensor
```

### 后端期望的格式

`views_fault.py` 使用 Django REST Framework 的 `request.query_params.getlist('fault_type')` 接收多值参数：

```python
fault_types = request.query_params.getlist('fault_type')
```

DRF/Django 的 `getlist()` 识别的是**无方括号的重复参数名**格式：

```
// 后端能正确识别（正确格式）：
fault_type=comm&fault_type=sensor
```

方括号形式（`fault_type[]`）被视为一个不同的参数名，`getlist('fault_type')` 返回空列表 `[]`，导致过滤器逻辑跳过：

```python
fault_types = request.query_params.getlist('fault_type')
if fault_types:   # 空列表 → 条件不成立，不过滤
    ...
```

### 根因小结

| 层 | 期望 | 实际 | 差异 |
|---|---|---|---|
| 前端注释 | `fault_type=comm&fault_type=sensor` | axios 生成 `fault_type[]=comm&...` | 注释描述的行为与 axios 1.x 实际行为不符 |
| 后端接收 | `getlist('fault_type')` 返回 `['comm']` | 返回 `[]`（空列表） | key 不匹配 |
| 过滤效果 | 按类型过滤 | 条件不触发，返回全量 | 完全失效 |

`sub_type` 参数同理。

---

## 修复方案

**最小改动，仅修改前端 `fetchFaultEvents()` 函数。**

将 axios `params` 对象改为手动构建 `URLSearchParams`，对数组参数逐一调用 `append()`，保证生成无方括号的重复参数名格式。

```js
// 修复后（FaultManagementView.vue，fetchFaultEvents 函数）
const qs = new URLSearchParams()
// ... 其他参数 ...

// 故障类型多值过滤（BUG-FM-003 修复：逐一 append，生成重复参数名）
for (const ft of filters.fault_types) {
  qs.append('fault_type', ft)
}

// 设备类型多值过滤（BUG-FM-003 修复：同上）
for (const st of filters.sub_types) {
  qs.append('sub_type', st)
}

const resp = await axios.get('/api/devices/fault-events/?' + qs.toString())
```

生成的 URL 示例：
```
/api/devices/fault-events/?page=1&page_size=20&fault_type=comm&fault_type=sensor
```

---

## 变更文件清单

| 文件 | 类型 | 变更描述 |
|---|---|---|
| `FreeArkWeb/frontend/src/views/FaultManagementView.vue` | 前端修复 | `fetchFaultEvents` 改用 `URLSearchParams` 构建多值参数 |
| `FreeArkWeb/backend/freearkweb/api/tests_fault_event.py` | 测试新增 | `TestFaultTypeFilterFrontendCompat` 类，验证重复参数名格式的过滤效果 |

---

## 未变更确认

| 项 | 状态 |
|---|---|
| 后端 `views_fault.py` | 无需修改（逻辑正确） |
| 后端 `serializers_fault.py` | 无需修改 |
| DB migration | 无 |
| systemd unit | 无 |
| nginx 配置 | 无 |

---

## 验证方案

1. 本地运行后端测试（见下方测试章节），验证 `fault_type=comm&fault_type=sensor` 格式能正确过滤。
2. 前端构建后浏览器 Network 面板确认请求 URL 不含方括号：`fault_type=comm&fault_type=sensor`（而非 `fault_type[]=comm`）。
3. 故障管理页选择"通信故障"后，列表仅显示 `fault_type=comm` 的记录。
4. 选择"新风机"后，列表仅显示 `fresh_air_fault_bit_*` 和 `fresh_air_unit_*` 相关故障。
5. 两者组合选择，验证 AND 语义正确（后端对 `fault_type` 和 `sub_type` 各自独立过滤后取交集）。

---

## 关联文档

- 上游功能实现：`docs/implementation/v0.6.1_fault_mgmt_ux/`
- 部署报告：`docs/deployment/v0.6.1_fault_mgmt_ux/deployment_report_2026-05-28.md`
