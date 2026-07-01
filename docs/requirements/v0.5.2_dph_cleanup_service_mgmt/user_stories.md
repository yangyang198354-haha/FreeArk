# 用户故事清单

**文档编号**: REQ-US-DPH-CLEANUP-MGMT-001
**项目名称**: FreeArk DPH 清理服务管理
**版本**: 0.2.0-PENDING-GATE
**状态**: PENDING_GATE（范围已按用户答复收敛，待门控确认后升级为 APPROVED）
**创建日期**: 2026-05-20
**最后更新**: 2026-05-20
**作者**: requirement-analyst (via pm-orchestrator)

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-20 | 初始草稿，含 OQ-1 依赖的占位标注 |
| 0.2.0-PENDING-GATE | 2026-05-20 | **范围收敛修订**：按用户对 OQ-1~OQ-4 答复删除 US-DPH-07（独立卡片/清理指标），其余故事据实精简，移除所有 OQ 依赖占位符 |

---

## 说明

- 角色定义：**运维** = 已登录用户（`IsAuthenticated`，任意有效账号），与现有服务管理权限对齐。
- 每条用户故事（US）与 `requirements_spec.md` 中对应的 FR/NFR 编号交叉引用。
- 本版本已无任何 OQ 依赖占位符，所有验收标准均为最终版本。

---

## 范围收敛说明（用户故事层面）

| 故事编号 | 变更类型 | 说明 |
|---------|---------|------|
| US-DPH-01 | 保留，无改动 | 服务页查看运行/自启状态，与收敛范围完全一致 |
| US-DPH-02 | 保留，无改动 | 服务页启动操作，与收敛范围完全一致 |
| US-DPH-03 | 保留，无改动 | 服务页停止操作，与收敛范围完全一致 |
| US-DPH-04 | 保留，无改动 | 服务页重启操作，与收敛范围完全一致 |
| US-DPH-05 | 保留，无改动 | 服务页详情查看，与收敛范围完全一致 |
| US-DPH-06 | 保留，措辞据实精简 | 看板系统运行状态展示服务运行/停止，与收敛范围完全一致 |
| **US-DPH-07** | **已删除** | 原故事：看板独立"数据清理状态"卡片展示上次清理时间/删除行数。依据用户答复 OQ-1（不持久化）+ OQ-4（不新增独立卡片），整体删除 |
| US-DPH-08 | 保留，精简（移除依赖 OQ-1 的内容） | 系统按计划 03:00 自动执行清理，仅保留 systemd 层面验收标准 |
| US-DPH-09 | 保留，精简（移除 OQ 相关条件分支） | 生产安装与回滚，简化了验收标准中原 OQ-1 相关的复杂步骤 |

---

## US-DPH-01 运维查看 dph 清理服务运行状态（服务页面）

**用户故事**
作为运维人员，我希望在服务管理页面看到 `freeark-dph-cleanup` 服务的当前运行状态（active/inactive/failed）和开机自启状态（enabled/disabled），以便我能快速判断清理服务是否在正常运行。

**来源需求**: FR3-1

**验收标准（Given / When / Then）**

```
Given: 运维已登录，打开"服务管理"页面
When:  页面加载或点击"刷新"按钮
Then:  服务列表中包含 "freeark-dph-cleanup" 一行
       该行显示：服务名称、运行状态 tag（active=绿色，inactive=黄色，failed=红色）、自启动状态 tag（enabled=绿色，disabled=红色）

Given: 生产服务器上 freeark-dph-cleanup 服务处于 active 运行中
When:  运维刷新服务管理页面
Then:  freeark-dph-cleanup 行的运行状态显示"active"（绿色 tag）

Given: 生产服务器上 freeark-dph-cleanup 服务处于 inactive 或 failed 状态
When:  运维刷新服务管理页面
Then:  freeark-dph-cleanup 行的运行状态显示"inactive"或"failed"（非绿色 tag）
```

---

## US-DPH-02 运维在服务页面启动 dph 清理服务

**用户故事**
作为运维人员，我希望在服务管理页面能够启动 `freeark-dph-cleanup` 服务，以便在服务意外停止后快速恢复清理功能。

**来源需求**: FR3-2, NFR1-1, NFR1-2

**验收标准（Given / When / Then）**

```
Given: 运维已登录，服务管理页面中 freeark-dph-cleanup 处于 inactive 状态
When:  运维点击该行的"启动"按钮，并在确认弹窗中点击"确认"
Then:  后端调用 sudo systemctl start freeark-dph-cleanup
       操作成功后，该行运行状态更新为"active"（无需手动刷新）
       页面弹出成功提示（ElMessage.success）

Given: 运维未登录（session 已过期）
When:  访问服务管理页面或发送 POST /api/services/freeark-dph-cleanup/action/
Then:  HTTP 401，前端跳转至登录页或弹出认证提示

Given: sudo systemctl start 执行失败（如进程启动错误）
When:  运维点击"启动"并确认
Then:  前端弹出错误提示，显示后端返回的错误信息；运行状态不更新（保持 inactive/failed）
```

---

## US-DPH-03 运维在服务页面停止 dph 清理服务

**用户故事**
作为运维人员，我希望在服务管理页面能够停止 `freeark-dph-cleanup` 服务，以便在需要临时暂停清理操作时（如 DB 压力过大或数据保留策略变更期间）安全停止服务。

**来源需求**: FR3-3, NFR1-1, NFR1-4

**验收标准（Given / When / Then）**

```
Given: 运维已登录，freeark-dph-cleanup 处于 active 状态
When:  运维点击"停止"按钮，弹窗显示"确认对服务 freeark-dph-cleanup 执行停止操作？"，运维点击"确认"
Then:  后端调用 sudo systemctl stop freeark-dph-cleanup
       Django logger 记录审计日志："用户 <username> 对服务 freeark-dph-cleanup 执行 stop"
       操作成功后，该行运行状态更新为"inactive"
       页面弹出成功提示

Given: 运维点击"停止"按钮后，在确认弹窗中点击"取消"
When:  弹窗关闭
Then:  不执行任何 systemctl 操作，服务状态不变
```

---

## US-DPH-04 运维在服务页面重启 dph 清理服务

**用户故事**
作为运维人员，我希望在服务管理页面能够重启 `freeark-dph-cleanup` 服务，以便在配置或代码更新后无中断地应用变更。

**来源需求**: FR3-4, NFR1-4

**验收标准（Given / When / Then）**

```
Given: 运维已登录，freeark-dph-cleanup 处于 active 或 inactive 状态
When:  运维点击"重启"按钮并在确认弹窗中确认
Then:  后端调用 sudo systemctl restart freeark-dph-cleanup
       Django logger 记录审计日志
       操作完成后，前端查询并更新服务新状态（active/failed）
       若重启成功，显示成功提示；若失败，显示错误信息

Given: systemctl restart 超时（超过 30 秒）
When:  运维执行重启操作
Then:  后端返回 HTTP 504，前端弹出提示"systemctl 操作超时（30s），请稍后重试"
```

---

## US-DPH-05 运维查看 dph 清理服务详情

**用户故事**
作为运维人员，我希望在服务管理页面点击"详情"后，能看到 `freeark-dph-cleanup` 的完整 systemd 状态输出（active_state、sub_state、PID、内存占用、raw systemctl status），以便深入排查服务异常。

**来源需求**: FR3-5

**验收标准（Given / When / Then）**

```
Given: 运维已登录，服务管理页面已加载 freeark-dph-cleanup 行
When:  运维点击该行的"详情"链接按钮
Then:  弹窗打开，标题显示"服务详情 — freeark-dph-cleanup"
       弹窗中展示：运行状态（active_state tag）、子状态（sub_state）、PID、内存占用
       弹窗底部展示 systemctl status 原始文本输出（黑色背景，等宽字体）

Given: 请求服务详情时后端调用 systemctl status 超时
When:  弹窗打开
Then:  弹窗内显示错误提示"systemctl status 超时"，不崩溃
```

---

## US-DPH-06 看板展示 dph 清理服务运行状态（系统运行状态卡片）

**用户故事**
作为系统用户，我希望在看板的"系统运行状态"卡片中能看到 `freeark-dph-cleanup` 的 active/inactive 状态 tag，以便与其他服务统一浏览系统健康度，无需进入服务管理页面。

**来源需求**: FR2-1, FR2-2

**说明**: 此功能通过将 `freeark-dph-cleanup` 加入后端 `MONITORED_SERVICES` 白名单实现，无需新增接口或前端改动。看板"系统运行状态"卡片的渲染逻辑已由现有代码处理。

**验收标准（Given / When / Then）**

```
Given: 用户已登录，打开看板首页
When:  "系统运行状态"卡片加载完成
Then:  卡片中的服务列表包含 "freeark-dph-cleanup" 条目
       active 时显示绿色"运行中" tag，inactive/failed 时显示非绿色"已停止"或"失败" tag

Given: freeark-dph-cleanup 服务处于 failed 状态
When:  用户打开看板
Then:  "系统运行状态"卡片中 freeark-dph-cleanup 显示非绿色 tag，与 active 服务的绿色 tag 形成视觉对比
```

---

## US-DPH-08 系统按计划（每天 03:00）自动执行清理

**用户故事**
作为系统管理员，我希望 `freeark-dph-cleanup` 以 systemd 服务的方式在生产服务器上开机自启，并每天凌晨 03:00 自动执行一次清理，无需人工干预，以保持 `device_param_history` 表维持在可控大小。

**来源需求**: FR1-1, FR1-5, NFR3-1

**验收标准（Given / When / Then）**

```
Given: 生产服务器已通过 git pull + sudo cp + systemctl enable 安装 freeark-dph-cleanup.service
When:  执行 systemctl is-enabled freeark-dph-cleanup
Then:  输出 "enabled"，确认开机自启已注册

Given: freeark-dph-cleanup 服务运行中，系统时间到达 03:00
When:  服务内 schedule 触发
Then:  dph_cleanup_service._run_cleanup 执行，按 batch_size=5000、sleep_ms=200 分批删除 7 天前的数据
       每批次结果写入 dph_cleanup_service.log（INFO 级别，格式含 batch 号和删除行数）
       最终写入一条"完成，共删除 N 行，共 M 批次"日志

Given: 清理过程中服务进程因异常崩溃（如内存不足）
When:  systemd 检测到进程退出
Then:  systemd 在 30 秒后自动重启该服务（Restart=on-failure，RestartSec=30s）
       运维次日可通过 journalctl -u freeark-dph-cleanup 查看崩溃和重启记录

Given: 某天 device_param_history 中无超过 7 天的数据
When:  03:00 清理任务执行
Then:  任务输出"无需删除（保留窗口内没有超期数据）"并正常退出，不报错
```

---

## US-DPH-09 生产安装与回滚（运维操作）

**用户故事**
作为运维人员，我希望有明确的生产安装步骤和回滚方法，以便在部署 dph 清理服务时有据可查，出错时能快速恢复。

**来源需求**: FR1-1, FR2-1, C2（plink + git pull 约束）

**验收标准（Given / When / Then）**

```
Given: 部署 runbook 已提供以下步骤
When:  运维按步骤执行
Then:  步骤应包含：
       1. plink 远程执行 git pull（主分支，生产目录）
       2. sudo cp systemctl/freeark-dph-cleanup.service /etc/systemd/system/
       3. sudo systemctl daemon-reload
       4. sudo systemctl enable freeark-dph-cleanup
       5. sudo systemctl start freeark-dph-cleanup
       6. 验证：systemctl is-active freeark-dph-cleanup 输出 "active"
       7. 验证：systemctl is-enabled freeark-dph-cleanup 输出 "enabled"
       8. Django 后端重启（freeark-backend），使 MONITORED_SERVICES 白名单变更生效
       9. 验证：GET /api/services/list/ 响应中包含 freeark-dph-cleanup 条目

Given: 安装后发现服务异常，需要回滚
When:  运维执行回滚
Then:  回滚步骤：
       sudo systemctl stop freeark-dph-cleanup
       sudo systemctl disable freeark-dph-cleanup
       sudo rm /etc/systemd/system/freeark-dph-cleanup.service
       sudo systemctl daemon-reload
       回滚后 systemctl status freeark-dph-cleanup 返回 "Unit not found" 或 "inactive"
       若需同步回滚后端白名单代码：git revert 对应提交后重启 freeark-backend

Given: 后端白名单（MONITORED_SERVICES）代码变更已 git pull 至生产
When:  运维重启 Django 服务（freeark-backend）
Then:  /api/services/list/ 接口响应中包含 freeark-dph-cleanup 条目
       /api/dashboard/services/ 接口响应中包含 freeark-dph-cleanup 的状态条目
```
