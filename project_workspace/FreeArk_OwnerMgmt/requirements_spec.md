# 需求规格说明书

**项目名称**：FreeArk 业主管理功能  
**版本**：v1.0  
**状态**：DRAFT  
**日期**：2026-04-17  
**来源**：用户原始需求（Project Manager 输入）

---

## 1. 项目背景

FreeArk 是部署在树莓派（192.168.31.51）上的物理机能耗采集平台，使用 Django 5.x 后端 + Vue 3 前端。项目中存在 `resource/all_owner.json`，记录小区 634 户业主信息，目前仅被 datacollector 模块读取用于数据采集。

**用户诉求**：将该文件的业主信息持久化到数据库，并在 Web 端新增"业主管理"页面，提供完整 CRUD 操作，同时不影响 datacollector 现有流程。

---

## 2. 范围与边界

| 在范围内 | 在范围外 |
|---------|---------|
| 新增 `owner_info` 数据库表 | 修改 `all_owner.json` 文件 |
| 业主管理 CRUD Web 页面 | 修改 datacollector 任何逻辑 |
| 一次性导入 JSON 数据的 management command | 修改现有 PLC / 用量 / 用户管理功能 |
| 与现有 UI 风格一致的前端页面 | Docker 容器化 |
| Django REST Framework API 端点 | 破坏已有数据库表结构 |

---

## 3. 功能需求

### REQ-FUNC-001：业主信息数据库表
**来源**：用户需求第 1 条  
**描述**：新增数据库表 `owner_info`，持久化 all_owner.json 中的业主信息。  
**字段映射**（来自 all_owner.json 实际字段）：

| JSON 字段 | 数据库字段 | 类型 | 说明 |
|-----------|-----------|------|------|
| key（如 "1-1-2-201"） | `specific_part` | VARCHAR(20) | 专有部分标识，唯一键 |
| 专有部分坐落 | `location_name` | VARCHAR(100) | 坐落描述 |
| 楼栋 | `building` | VARCHAR(10) | 如 "1栋" |
| 单元 | `unit` | VARCHAR(10) | 如 "1单元" |
| 楼层 | `floor` | VARCHAR(10) | 如 "2楼" |
| 户号 | `room_number` | VARCHAR(10) | 如 "201" |
| 绑定状态 | `bind_status` | VARCHAR(20) | "已绑定"/"未绑定" |
| IP地址 | `ip_address` | VARCHAR(50) | 设备 IP |
| 唯一标识符 | `unique_id` | VARCHAR(50) | screenMAC，唯一键 |
| PLC IP地址 | `plc_ip_address` | VARCHAR(50) | PLC 设备 IP |
| — | `created_at` | DATETIME | 记录创建时间 |
| — | `updated_at` | DATETIME | 记录更新时间 |

**验收标准（G/W/T）**：  
- **Given** all_owner.json 包含 634 条业主记录 **When** 执行 management command 导入 **Then** owner_info 表中存在对应记录，specific_part 不重复  
- **Given** owner_info 表存在 **When** 查询任意 specific_part **Then** 返回该户完整字段信息

---

### REQ-FUNC-002：数据初始导入 Management Command
**来源**：用户需求第 1 条（持久化）  
**描述**：提供 `python manage.py import_all_owners` 命令，将 all_owner.json 批量导入 owner_info 表，支持幂等执行（已存在则跳过或更新）。  
**验收标准**：  
- **Given** owner_info 表为空 **When** 执行 import_all_owners **Then** 634 条记录全部写入，命令输出成功计数  
- **Given** 部分记录已存在 **When** 再次执行 import_all_owners **Then** 已有记录不重复插入，仅更新变化字段（upsert 语义）  
- **Given** all_owner.json 不存在 **When** 执行 import_all_owners **Then** 命令给出明确错误信息，不崩溃

---

### REQ-FUNC-003：业主列表查询 API
**来源**：用户需求第 2 条（Read）  
**描述**：`GET /api/owners/` 返回分页业主列表，支持按楼栋、单元、绑定状态过滤，支持关键词搜索（专有部分/坐落/户号）。  
**验收标准**：  
- **Given** owner_info 表有记录 **When** GET /api/owners/ **Then** 返回 JSON 列表，包含所有字段，HTTP 200  
- **Given** 请求携带 `?building=1栋&unit=1单元` **When** GET /api/owners/ **Then** 仅返回该楼栋单元的记录  
- **Given** 未登录用户 **When** GET /api/owners/ **Then** 返回 HTTP 401

---

### REQ-FUNC-004：业主详情查询 API
**来源**：用户需求第 2 条（Read）  
**描述**：`GET /api/owners/<id>/` 返回单条业主详情。  
**验收标准**：  
- **Given** owner_info 表中存在 id=5 的记录 **When** GET /api/owners/5/ **Then** 返回该条完整字段，HTTP 200  
- **Given** owner_info 表中不存在 id=9999 **When** GET /api/owners/9999/ **Then** 返回 HTTP 404

---

### REQ-FUNC-005：业主信息创建 API
**来源**：用户需求第 2 条（Create）  
**描述**：`POST /api/owners/` 创建一条新业主记录，仅管理员可操作。  
**验收标准**：  
- **Given** 管理员用户已登录，请求体包含所有必填字段 **When** POST /api/owners/ **Then** 记录成功创建，返回 HTTP 201 及新记录 ID  
- **Given** specific_part 已存在 **When** POST /api/owners/ **Then** 返回 HTTP 400，错误信息指明重复  
- **Given** 普通用户已登录 **When** POST /api/owners/ **Then** 返回 HTTP 403

---

### REQ-FUNC-006：业主信息更新 API
**来源**：用户需求第 2 条（Update）  
**描述**：`PUT/PATCH /api/owners/<id>/` 更新业主信息，仅管理员可操作。  
**验收标准**：  
- **Given** 管理员用户已登录，id 存在 **When** PATCH /api/owners/5/ 携带 `{"bind_status": "未绑定"}` **Then** 字段更新成功，HTTP 200  
- **Given** 普通用户 **When** PATCH /api/owners/5/ **Then** HTTP 403

---

### REQ-FUNC-007：业主信息删除 API
**来源**：用户需求第 2 条（Delete）  
**描述**：`DELETE /api/owners/<id>/` 删除业主记录，仅管理员可操作。  
**验收标准**：  
- **Given** 管理员用户，id 存在 **When** DELETE /api/owners/5/ **Then** 记录删除，HTTP 204  
- **Given** 普通用户 **When** DELETE /api/owners/5/ **Then** HTTP 403

---

### REQ-FUNC-008：业主管理 Web 页面
**来源**：用户需求第 2 条（Web 端）  
**描述**：在 Vue 3 前端新增 `/owner-management` 路由及 `OwnerManagementView.vue`，提供：
1. 分页列表（显示：专有部分、坐落、楼栋、单元、楼层、户号、绑定状态、IP地址、PLC IP、操作按钮）
2. 搜索/过滤栏（按楼栋、单元、绑定状态、关键词）
3. 新增业主弹窗表单
4. 编辑业主弹窗表单（点击编辑按钮触发）
5. 删除确认操作
6. 左侧菜单新增"业主管理"入口（管理员可见）  
**验收标准**：  
- **Given** 管理员进入业主管理页面 **When** 页面加载 **Then** 显示业主列表，与数据库一致  
- **Given** 管理员输入搜索条件 **When** 点击搜索 **Then** 列表按条件过滤  
- **Given** 管理员点击新增 **When** 填写表单并提交 **Then** 记录保存，列表刷新  
- **Given** 管理员点击编辑 **When** 修改并保存 **Then** 记录更新，列表刷新  
- **Given** 管理员点击删除 **When** 确认对话框确认 **Then** 记录删除，列表刷新  
- **Given** 页面风格 **When** 视觉比较 **Then** 与现有 UserListView 等页面一致（同样使用 Element Plus 组件）

---

### REQ-FUNC-009：datacollector 隔离
**来源**：用户约束（不得破坏 datacollector 现有逻辑）  
**描述**：datacollector 继续从 `resource/all_owner.json` 读取数据，不依赖数据库表，两者完全独立。  
**验收标准**：  
- **Given** 新增 owner_info 表后 **When** datacollector 执行采集任务 **Then** 其读取 all_owner.json 的行为不受影响  
- **Given** owner_info 表数据有变更 **When** datacollector 运行 **Then** 其使用的 all_owner.json 文件内容无变化

---

## 4. 非功能需求

| ID | 需求 | 来源 |
|----|------|------|
| REQ-NFN-001 | 生产数据库使用 MySQL（192.168.31.98:3306），测试使用 SQLite | 用户约束 |
| REQ-NFN-002 | 禁止 Docker，物理机部署（树莓派） | 用户约束 |
| REQ-NFN-003 | 业主列表页支持至少 634 条记录的分页展示，每页默认 20 条 | 用户需求 |
| REQ-NFN-004 | API 响应时间 < 2s（正常负载下） | 行业惯例 |
| REQ-NFN-005 | 管理员权限控制：创建/更新/删除仅管理员可操作 | 用户需求 |

---

## 5. 约束

- `all_owner.json` 文件只读，不可修改
- 不得修改 datacollector 任何现有代码
- 新页面须与现有 Web UI（Element Plus 组件库）风格一致
- 后端沿用 Django 5.x + Django REST Framework 技术栈
- 前端沿用 Vue 3 + Element Plus 技术栈

---

## 6. 词汇表

| 术语 | 定义 |
|------|------|
| specific_part | 专有部分标识符，格式 "楼-单-层-户"，如 "1-1-2-201" |
| owner_info | 新增的业主信息数据库表 |
| datacollector | 现有的数据采集模块，读取 all_owner.json |
| screenMAC / 唯一标识符 | 设备屏幕 MAC 地址，与 specific_part_info 表中字段同义 |
