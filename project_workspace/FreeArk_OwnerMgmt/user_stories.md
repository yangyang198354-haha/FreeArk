# 用户故事

**项目名称**：FreeArk 业主管理功能  
**版本**：v1.0  
**状态**：DRAFT  
**日期**：2026-04-17

---

## US-001：查看业主列表

**As** 已登录的系统用户  
**I want to** 访问业主管理页面，查看所有业主的分页列表  
**So that** 我能快速了解小区的业主信息全貌

**验收标准（AC）**：
- **Given** 用户已登录 **When** 导航到"业主管理"页面 **Then** 显示业主列表（含专有部分、坐落、楼栋、单元、楼层、户号、绑定状态、IP地址、PLC IP），默认每页 20 条
- **Given** 列表有 634 条记录 **When** 切换到第 2 页 **Then** 显示第 21–40 条记录
- **Given** 页面加载中 **When** 数据未返回 **Then** 显示加载状态

**关联需求**：REQ-FUNC-003, REQ-FUNC-008

---

## US-002：搜索与过滤业主

**As** 已登录的系统用户  
**I want to** 按楼栋、单元、绑定状态或关键词筛选业主  
**So that** 我能快速定位特定业主信息

**验收标准（AC）**：
- **Given** 用户选择"楼栋=1栋" **When** 点击搜索 **Then** 列表仅显示 1 栋的业主
- **Given** 用户选择"绑定状态=已绑定" **When** 点击搜索 **Then** 仅显示已绑定业主
- **Given** 用户输入关键词 "201" **When** 点击搜索 **Then** 显示 specific_part 或户号含 "201" 的记录
- **Given** 用户点击"重置" **When** 重置成功 **Then** 列表恢复显示全部记录

**关联需求**：REQ-FUNC-003, REQ-FUNC-008

---

## US-003：新增业主记录

**As** 管理员用户  
**I want to** 通过弹窗表单新增业主记录  
**So that** 当有新业主入住时可以维护数据库信息

**验收标准（AC）**：
- **Given** 管理员点击"新增业主" **When** 弹窗打开 **Then** 显示包含所有字段的表单
- **Given** 管理员填写完整信息（specific_part 不重复）**When** 点击"保存" **Then** 记录写入数据库，弹窗关闭，列表刷新，显示成功提示
- **Given** specific_part 已存在 **When** 管理员点击"保存" **Then** 显示错误"该专有部分已存在"，弹窗不关闭
- **Given** 必填字段为空 **When** 管理员点击"保存" **Then** 表单内联提示必填项

**关联需求**：REQ-FUNC-005, REQ-FUNC-008

---

## US-004：编辑业主信息

**As** 管理员用户  
**I want to** 编辑已有业主的信息  
**So that** 当业主信息（如 IP 地址、绑定状态）发生变化时可以更新数据库

**验收标准（AC）**：
- **Given** 管理员点击列表中某行的"编辑"按钮 **When** 弹窗打开 **Then** 表单预填充该业主当前信息
- **Given** 管理员修改"绑定状态"为"未绑定" **When** 点击"保存" **Then** 数据库记录更新，列表刷新
- **Given** 管理员修改 specific_part 为已存在的值 **When** 点击"保存" **Then** 显示错误，不更新

**关联需求**：REQ-FUNC-006, REQ-FUNC-008

---

## US-005：删除业主记录

**As** 管理员用户  
**I want to** 删除业主记录  
**So that** 当业主退出时可清理数据库

**验收标准（AC）**：
- **Given** 管理员点击"删除"按钮 **When** 确认对话框弹出 **Then** 显示"确认删除该业主？"提示
- **Given** 管理员在对话框中点击"确认" **When** 请求成功 **Then** 记录从数据库删除，列表刷新，显示成功提示
- **Given** 管理员在对话框中点击"取消" **When** 取消操作 **Then** 记录保留，列表不变

**关联需求**：REQ-FUNC-007, REQ-FUNC-008

---

## US-006：一次性导入业主数据

**As** 系统运维人员  
**I want to** 执行 management command 将 all_owner.json 数据导入数据库  
**So that** 首次部署时能快速完成数据初始化，无需手动录入 634 条记录

**验收标准（AC）**：
- **Given** 执行 `python manage.py import_all_owners` **When** 命令完成 **Then** 输出导入成功数量，owner_info 表记录数 = all_owner.json 条目数
- **Given** 重复执行命令 **When** 记录已存在 **Then** 不重复插入，输出跳过数量
- **Given** 文件路径不存在 **When** 执行命令 **Then** 友好错误提示，进程非零退出

**关联需求**：REQ-FUNC-002

---

## US-007：权限保护

**As** 普通用户（非管理员）  
**I want to** 访问业主管理页面时只能查看，不能增删改  
**So that** 防止未授权操作破坏数据

**验收标准（AC）**：
- **Given** 普通用户访问业主管理页面 **When** 页面加载 **Then** 不显示"新增"、"编辑"、"删除"按钮（前端控制）
- **Given** 普通用户直接调用 POST /api/owners/ **When** 请求到达后端 **Then** 返回 HTTP 403
- **Given** 未登录用户访问任何 /api/owners/ 端点 **When** 请求到达后端 **Then** 返回 HTTP 401

**关联需求**：REQ-FUNC-005, REQ-FUNC-006, REQ-FUNC-007, REQ-NFN-005

---

## US-008：datacollector 隔离保障

**As** datacollector 模块  
**I want to** 继续从 all_owner.json 读取业主信息  
**So that** 新增数据库表不影响现有数据采集流程

**验收标准（AC）**：
- **Given** owner_info 表已创建且含数据 **When** datacollector 执行采集 **Then** all_owner.json 文件读取路径和内容不受影响
- **Given** 通过 Web 端删除了某条 owner_info 记录 **When** datacollector 下次运行 **Then** all_owner.json 中仍有该记录，采集正常进行

**关联需求**：REQ-FUNC-009
