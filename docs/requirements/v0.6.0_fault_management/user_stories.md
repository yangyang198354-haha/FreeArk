# 用户故事

```
file_header:
  document_id: US-v0.6.0-FM
  title: MQTT 故障事件持久化 + 故障管理页面 — 用户故事
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.6.0-fault-management
  created_at: 2026-05-27
  status: DRAFT
  references:
    - docs/requirements/v0.6.0_fault_management/requirements_spec.md
    - FreeArkWeb/backend/freearkweb/api/fault_utils.py
    - scripts/tmp/sniff_2860fae9a34ab8a9_20260525_235217.ndjson
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-27 | 初始草稿，US-FM-01~US-FM-08，开放问题 OQ-01~OQ-14 |
| 0.2.0-DRAFT | 2026-05-27 | 落地全部 14 条 OQ 裁决/默认值；更新 US-FM-02/US-FM-08 验收标准；新增 US-FM-09（清理服务）；新增"未来增强/演进路线"章节（AB-004~AB-006 + stale 机制）；版本号更新为 v0.6.0 |

---

## 角色定义

| 角色 | 描述 |
|------|------|
| **运维人员** | 负责平台日常维护、故障响应、设备巡检的后台工作人员（主要使用 Web 管理界面） |
| **物业管理员** | 管理多户住宅的物业人员，需要快速了解哪些房间的设备存在故障 |
| **系统管理员** | 负责平台配置、服务运维（systemd 管理、日志查看）的技术人员 |
| **业主（只读）** | 住户，可查看自己房间的设备状态（本版本不新增业主专属视图，沿用现有设备面板） |

---

## 用户故事清单

---

### US-FM-01：MQTT 故障事件自动持久化

**作为** 运维人员，  
**我希望** 系统能自动从 MQTT 上报的设备状态报文中识别故障事件并保存到数据库，  
**以便** 我可以追溯任意设备的故障发生时间和持续时长，而不依赖人工记录。

**优先级**：P0（核心需求，其他故事的基础）

**验收标准**：

- **AC-FM-01-01（正常故障入库）**
  - Given：`freeark-fault-consumer` 服务正在运行，MQTT broker 连接正常
  - When：收到一条 `DeviceStatusUpdate` 报文，其中某设备的 `error_82` 值为非零（如 `"1"`）
  - Then：`fault_event` 表中新增一条记录，`fault_code="error_82"`，`fault_type="other_error"`，`severity="error"`，`is_active=True`，`first_seen_at` 记录接收时间，`specific_part` 正确映射到对应房号，`fault_message="error_82"`

- **AC-FM-01-02（重复报文不重复插入）**
  - Given：进程内内存表中已有 `(specific_part=A, device_sn=21997, fault_code=error_82) → (event_id=N, is_active=True)` 的条目
  - When：10 秒内再次收到同一设备、同一故障码的报文（故障仍未恢复）
  - Then：不插入新记录；不写 DB；仅更新内存表中的 `last_seen_at`

- **AC-FM-01-03（故障恢复更新状态）**
  - Given：`fault_event` 表中存在 `(fault_code=error_82, is_active=True)` 的记录，内存表中对应 `is_active=True`
  - When：收到同一设备的报文，`error_82` 值恢复为 `"0"`
  - Then：`fault_event` 对应记录的 `is_active` 更新为 `False`，`recovered_at` 记录本次接收时间，`last_seen_at` 写入内存中最新值；内存表中 `is_active` 更新为 `False`

- **AC-FM-01-04（comm_fault_timeout 故障识别）**
  - Given：服务正在运行
  - When：收到报文，`comm_fault_timeout` 值为非 `"normal"` 字符串（如 `"timeout"`）
  - Then：`fault_event` 新增 `fault_code="comm_fault_timeout"`, `fault_type="comm"`, `severity="error"` 的记录

- **AC-FM-01-05（新风预警识别）**
  - Given：服务正在运行
  - When：收到报文，`fresh_air_fault_bit_4` 值为非零
  - Then：`fault_event` 新增 `fault_code="fresh_air_fault_bit_4"`, `fault_type="fresh_air"`, `severity="warning"` 的记录

- **AC-FM-01-06（无故障字段不写 DB）**
  - Given：服务正在运行
  - When：收到报文，所有故障字段均为正常值
  - Then：`fault_event` 表无新增记录，无 DB 写入操作

- **AC-FM-01-07（通配符订阅覆盖所有大屏）**
  - Given：服务启动，broker ACL 允许通配符
  - When：来自任意大屏 MAC 的 DeviceStatusUpdate 报文到达 `/screen/upload/screen/to/cloud/<anyMAC>`
  - Then：服务能接收并处理该报文（无需预先注册 screenMAC 白名单）

---

### US-FM-02：进程内状态机避免频繁 DB 读写

**作为** 系统管理员，  
**我希望** 故障订阅服务在处理高频 MQTT 报文时不会造成数据库读写压力骤增，  
**以便** 避免重蹈 `device_param_history` 膨胀（36M 行 / 11.3GB）的历史问题。

**优先级**：P0（与 US-FM-01 同级，性能约束）

**验收标准**：

- **AC-FM-02-01（内存表命中不触发 DB）**
  - Given：进程内内存表中已有 `(specific_part=A, device_sn=21997, fault_code=error_82) → {event_id, is_active=True}` 的条目
  - When：收到同一设备同一故障码的重复报文（故障持续中）
  - Then：不执行任何 DB 查询或写入；仅更新内存中的 `last_seen_at`

- **AC-FM-02-02（进程重启后状态机重建）**
  - Given：`freeark-fault-consumer` 服务因重启（如 git pull 后 systemctl restart）刚刚启动
  - When：服务启动初始化
  - Then：从 `fault_event` 表查询所有 `is_active=True` 的记录（LIMIT 10000），重建进程内内存表，确保不重复插入已知活跃故障

- **AC-FM-02-03（重建后重复 INSERT 兜底）**
  - Given：进程重启后内存表重建中
  - When：收到已知活跃故障的报文，进程尝试 INSERT（极端竞态情形）
  - Then：DB unique 约束触发 IntegrityError → 服务捕获后改为 UPDATE（更新 last_seen_at），不崩溃

- **AC-FM-02-04（内存占用可接受）**
  - Given：100 楼 × 10 屏 × 9 设备 × 平均 5 故障 = 45,000 条内存表项
  - When：任意时刻
  - Then：内存占用 ≤ 10 MB（估算 9 MB），不影响树莓派正常运行

---

### US-FM-03：故障管理页面 — 多维过滤查询

**作为** 物业管理员，  
**我希望** 在「设备管理」模块下有一个专门的「故障管理」页面，可以按房号、时间段、故障类型、设备筛选历史故障记录，  
**以便** 快速定位某个房间在特定时间段内发生了什么故障、哪种故障最频繁。

**优先级**：P1

**验收标准**：

- **AC-FM-03-01（基础过滤 — 房号模糊匹配）**
  - Given：「故障管理」页面已加载，`fault_event` 表中有多个 `specific_part` 的数据
  - When：用户在房号输入框输入「160」
  - Then：表格展示所有 `specific_part` 包含 `"160"` 的故障记录（LIKE '%160%'）

- **AC-FM-03-02（基础过滤 — 时间段，默认最近 7 天）**
  - Given：页面初次加载
  - When：用户未修改时间段
  - Then：时间段默认为「今天 - 7 天」至「今天」；表格展示该区间内 `first_seen_at` 的记录
  - Note：**默认采纳 OQ-06，可改**

- **AC-FM-03-03（基础过滤 — 故障类型多选）**
  - Given：页面已加载
  - When：用户同时勾选 `comm` 和 `sensor` 两个大类
  - Then：表格展示 `fault_type IN ('comm', 'sensor')` 的记录

- **AC-FM-03-04（基础过滤 — 故障设备多选）**
  - Given：页面已加载
  - When：用户在「故障设备」下拉中同时选择「主卧温控面板」和「客厅温控面板」
  - Then：表格展示对应 sub_type 的记录

- **AC-FM-03-05（只看未恢复 toggle）**
  - Given：页面已加载，toggle 默认 OFF
  - When：用户打开「只看未恢复」toggle
  - Then：表格只展示 `is_active=True` 的记录；关闭 toggle 后恢复显示全部记录
  - Note：**默认采纳 OQ-07，可改**

- **AC-FM-03-06（组合过滤）**
  - Given：页面已加载
  - When：用户同时设置房号、时间段、故障类型、只看未恢复
  - Then：表格展示满足所有条件的交集记录（AND 逻辑）

- **AC-FM-03-07（空结果处理）**
  - Given：过滤条件下无匹配记录
  - When：过滤查询完成
  - Then：表格显示空状态提示（如「暂无故障记录」），不报错

---

### US-FM-04：故障管理页面 — 分页表格显示

**作为** 运维人员，  
**我希望** 故障管理页面的表格支持分页显示，并展示故障码、故障描述、严重级别等关键信息，  
**以便** 在存在大量历史故障记录时，页面仍能快速加载，且信息清晰可读。

**优先级**：P1

**验收标准**：

- **AC-FM-04-01（分页默认展示）**
  - Given：`fault_event` 表中有超过 20 条符合过滤条件的记录
  - When：用户进入故障管理页面
  - Then：表格默认显示第 1 页，每页 20 条，底部分页控件显示总条数和总页数

- **AC-FM-04-02（关键列展示）**
  - Given：表格已加载数据
  - When：任意时刻
  - Then：表格至少包含：房号、设备标识、故障码、故障描述（本期同故障码字符串）、故障类型、严重级别（配色）、首次发生时间、最后活跃时间、恢复时间（NULL 显示"-"）、状态（活跃/已恢复）

- **AC-FM-04-03（活跃故障视觉区分）**
  - Given：表格中混有活跃故障（`is_active=True`）和已恢复故障
  - When：表格渲染
  - Then：`severity=error` 的活跃故障行状态列使用红色；`severity=warning` 使用橙色；已恢复故障使用灰色

---

### US-FM-05：故障管理页面 — 查看设备面板

**作为** 运维人员，  
**我希望** 在故障管理表格的操作列能直接跳转到对应设备的面板页面，  
**以便** 查看该设备的实时状态，判断故障是否已真正恢复。

**优先级**：P1

**验收标准**：

- **AC-FM-05-01（跳转到设备面板）**
  - Given：故障管理表格中有一条 `specific_part="1601"` 的故障记录
  - When：用户点击该行操作列的「查看设备面板」按钮
  - Then：执行 `router.push({ name: 'DeviceCards', query: { specific_part: '1601' } })`，展示该房间的设备面板
  - Note：**用户裁决 OQ-12**：不附加子设备高亮参数

- **AC-FM-05-02（新标签页打开）**
  - Given：用户在查看故障列表
  - When：点击「查看设备面板」
  - Then：在新标签页打开设备面板，不离开故障管理页面（避免过滤条件丢失）

---

### US-FM-06：systemd 服务可靠运行

**作为** 系统管理员，  
**我希望** `freeark-fault-consumer` 服务具备自动重启和 MQTT 自动重连能力，  
**以便** 在网络抖动或服务崩溃后无需人工干预即可自动恢复。

**优先级**：P0

**验收标准**：

- **AC-FM-06-01（服务重启配置）**
  - Given：`freeark-fault-consumer.service` 已在 systemd 中注册
  - When：进程因异常退出（非零退出码）
  - Then：systemd 在 30 秒后自动重启服务（`Restart=on-failure, RestartSec=30s`）

- **AC-FM-06-02（MQTT 自动重连）**
  - Given：broker 连接因网络抖动断开
  - When：连接中断
  - Then：服务自动尝试重连（`loop_forever(retry_first_connection=True)`），不崩溃退出；重连成功后继续处理报文

- **AC-FM-06-03（日志可查）**
  - Given：服务运行中
  - When：发生故障状态变化、DB 写入、连接异常
  - Then：可通过 `journalctl -u freeark-fault-consumer -f` 实时查看对应 INFO/WARNING/ERROR 日志

---

### US-FM-07：生产部署通过 git pull

**作为** 系统管理员，  
**我希望** 新服务的生产部署通过 plink + git pull 方式完成，  
**以便** 符合 FreeArk 现有的部署规范，不引入 pscp 文件传输等不一致的部署方式。

**优先级**：P0（合规约束）

**验收标准**：

- **AC-FM-07-01（git pull 部署）**
  - Given：代码已合并到 main 分支
  - When：需要在生产服务器（192.168.31.51）部署新版本
  - Then：部署步骤为：① `plink` SSH 连接到生产服务器；② `git pull`；③ `python manage.py migrate`（执行新表 migration）；④ `sudo systemctl daemon-reload && sudo systemctl enable --now freeark-fault-consumer && sudo systemctl enable --now freeark-fault-cleanup.timer`

- **AC-FM-07-02（SQLite 用于测试）**
  - Given：本地开发环境
  - When：运行单元测试和集成测试
  - Then：测试使用 SQLite，不依赖生产 MySQL 9.4 @ 192.168.31.98

---

### US-FM-08：仅活跃故障快捷视图

**作为** 物业管理员，  
**我希望** 故障管理页面提供「只看未恢复」的快捷 toggle，  
**以便** 快速了解当前有哪些设备仍在故障状态，无需浏览历史已恢复记录。

**优先级**：P1（已采纳，**默认采纳 OQ-07，可改**）

**验收标准**：

- **AC-FM-08-01（只看未恢复 toggle）**
  - Given：故障管理页面加载完成，筛选区上方有「只看未恢复」toggle，**默认 OFF**
  - When：用户打开 toggle
  - Then：表格只展示 `is_active=True` 的记录（等价于追加 `WHERE is_active=True`）；关闭 toggle 后恢复显示全部记录

---

### US-FM-09：故障事件数据清理服务

**作为** 系统管理员，  
**我希望** 系统自动定期清理超过 90 天的历史故障记录，  
**以便** fault_event 表不会无限膨胀，避免重蹈 device_param_history 的历史问题。

**优先级**：P1（**用户裁决 OQ-08**）

**验收标准**：

- **AC-FM-09-01（定时清理执行）**
  - Given：`freeark-fault-cleanup.timer` 已在 systemd 中注册
  - When：每天 03:30 触发
  - Then：执行 `DELETE FROM fault_event WHERE first_seen_at < NOW() - INTERVAL 90 DAY AND is_active=False`（活跃故障不删除），分批执行每批 ≤ 1000 行

- **AC-FM-09-02（清理日志可查）**
  - Given：清理服务执行
  - When：每次运行
  - Then：记录 INFO 日志（删除行数、耗时）；可通过 `journalctl -u freeark-fault-cleanup` 查看

- **AC-FM-09-03（对活跃故障无影响）**
  - Given：存在 `is_active=True` 且 `first_seen_at` 超过 90 天的极端情况
  - When：清理服务执行
  - Then：该记录**不被删除**，活跃故障永远保留直至恢复

---

## 开放问题（Open Questions）— 最终落地状态

以下为 14 条 OQ 的最终裁决结果，所有问题均已在本版本落地，不再为 PENDING 状态。

| OQ | 问题简述 | 最终状态 |
|----|---------|---------|
| OQ-01 | 是否保留 `raw_payload_snippet` | **用户裁决**：不保留。fault_event 表去掉此字段 |
| OQ-02 | 故障 vs 预警的 severity 分级 | **用户裁决**：详见 FR-FM-06 完整映射表；fresh_air_fault_bit_* = warning，其余绝大多数 = error |
| OQ-03 | DB 写入节流策略 | **用户裁决**：方案 C 变体——每条 MQTT 报文更新内存 last_seen_at；仅首次出现（is_active 跳变）写 INSERT；恢复时写 UPDATE |
| OQ-04 | 前端故障类型过滤粒度 | **默认采纳**：两级——大类多选（`comm`/`sensor`/`fresh_air`/`other_error`）+ 故障码模糊搜索框；大类→字段映射由后端常量 API 暴露。**可改** |
| OQ-05 | 故障码字典来源 | **用户裁决**：无现成字典，本期 `fault_message` 直接写故障码字符串；中文字典为未来增强项 AB-004 |
| OQ-06 | 过滤项粒度与交互细节 | **用户裁决**：房号 LIKE 模糊；时间段 first_seen_at 区间，默认最近 7 天（**默认采纳，可改**）；类型多选；设备 sub_type 多选 |
| OQ-07 | 「只看未恢复」toggle | **默认采纳**：筛选区上方 toggle，默认 OFF。**可改** |
| OQ-08 | 数据保留天数 | **用户裁决**：90 天硬删除；新增 `freeark-fault-cleanup` 服务，每天 03:30 分批删除 |
| OQ-09 | 告警通知本期是否在 scope 内 | **默认采纳**（与用户意向一致）：本期 out of scope，仅做记录与查询；告警通知为未来增强项 AB-005 |
| OQ-10 | broker ACL 与通配符订阅 | **用户裁决**：broker 允许 `+` 通配符，订阅 `/screen/upload/screen/to/cloud/+`；ACL 收紧时 fallback 到按 MAC 订阅（风险 R-08） |
| OQ-11 | 多大屏支持 | **默认采纳**：OQ-10 通配符已确认，无需 screenMAC 白名单，broker 推什么订阅什么 |
| OQ-12 | 设备面板跳转是否高亮子设备 | **用户裁决**：不高亮，仅 `router.push({ name: 'DeviceCards', query: { specific_part: row.specific_part } })` |
| OQ-13 | 版本号重编 | **用户裁决**：采用 **v0.6.0**（理由见 requirements_spec.md §版本号决策记录）；目录从 `v0.5.4_fault_management` 重命名为 `v0.6.0_fault_management` |
| OQ-14 | 进程重启时状态机重建范围 | **默认采纳**（analyst 建议）：仅加载 `is_active=True` 的记录重建，LIMIT 10000 保护；DB unique 约束兜底防重复 INSERT。**可改** |

---

## 用户故事优先级矩阵

| US | 标题 | 优先级 | 依赖 |
|----|------|--------|------|
| US-FM-01 | MQTT 故障事件自动持久化 | P0 | — |
| US-FM-02 | 进程内状态机避免频繁 DB 读写 | P0 | US-FM-01 |
| US-FM-06 | systemd 服务可靠运行 | P0 | US-FM-01 |
| US-FM-07 | 生产部署通过 git pull | P0 | — |
| US-FM-03 | 故障管理页面多维过滤查询 | P1 | US-FM-01 |
| US-FM-04 | 分页表格显示 | P1 | US-FM-03 |
| US-FM-05 | 查看设备面板 | P1 | US-FM-04 |
| US-FM-08 | 只看未恢复快捷视图 | P1 | US-FM-03 |
| US-FM-09 | 故障事件数据清理服务 | P1 | US-FM-01 |

---

## 未来增强 / 演进路线

以下条目**不进入 v0.6.0 本期范围**，仅记录供后续版本规划参考。均为"架构待办（Architecture Backlog）"候选。

| 编号 | 标题 | 来源 | 说明 |
|------|------|------|------|
| **AB-004（候选）** | 故障码中文描述字典表 + 维护界面 | OQ-05 裁决 | 新增 `fault_code_dict` 表（product_code + fault_code → 中文描述 + severity）；前端提供字典维护 UI；填充数据待业务方提供 Excel |
| **AB-005（候选）** | 故障告警通知（钉钉 webhook / 短信 / 邮件） | OQ-09 裁决 | 故障发生时实时推送；支持按房号/严重级别配置通知阈值 |
| **AB-006（候选）** | 故障趋势统计（按周/月聚合） | 演进路线 | 基于 fault_event 表的统计分析；展示故障频率趋势、高发房号、高发故障类型 |
| **AB-007（候选）** | MQTT 漏消息 stale active 自动标记 | R-10 风险 | 心跳超时（如 10 分钟无同一设备任何上报）自动将 is_active 标记为 stale；前端可用不同颜色区分"确认活跃"和"可能 stale" |
| **AB-008（候选）** | broker ACL 变更 fallback 机制（逐 MAC 订阅） | R-08 风险 | 当 broker ACL 收紧不再允许通配符时，自动 fallback 到从 OwnerInfo 动态加载 MAC 列表逐个订阅；提供配置开关强制使用 MAC 列表模式 |
