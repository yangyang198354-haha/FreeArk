# v1.0.0 部署报告 — 系统看板重排 + 子设备故障卡片 + 设备列表凝露提醒列

- **日期**：2026-05-30
- **提交**：`5c51fa8`（main）
- **部署人**：Claude Code（主控亲自执行测试与部署验证）
- **生产**：树莓派 `/home/yangyang/Freeark/FreeArk`，HEAD 由 `8d9fd46` → `5c51fa8`（fast-forward）

## 变更内容
- 设备列表新增「凝露提醒」列（有/无，有则橙色），数据源 `CondensationWarningEvent`（按页批量 IN 查询）
- 系统看板按 4 组重排 + 5 张卡片（当前故障总数 / 空气品质传感器 / 温控面板 / 新风 / 水力模块），可点击跳转故障管理并预选过滤
- 新增接口 `dashboard/fault-summary/`、`dashboard/device-fault-summary/`
- `device_management_device_list` 注入 `has_active_condensation`
- `FaultManagementView` onMounted 支持 `sub_type` 多值 URL 参数初始化过滤

## 部署步骤
1. 本地 `git pull`（fast-forward 合并远端 CSRF 修复 8d9fd46）→ 提交 5c51fa8 → push
2. 生产 `git pull`（fast-forward，未触碰 .env/package-lock.json/heartbeat_broker_config.json）
3. 前端 `npm run build`（dist 已备份；✓ built in 19.28s）
4. `sudo systemctl restart freeark-backend`（views.py/urls.py 为 REST 视图）
5. 无 model 变更（无需迁移）、无新增 Python 依赖、未改 fault_consumer/（无需重启 freeark-fault-consumer）

## 生产验证（真实数据，MySQL）
- `freeark-backend`：active；`/api/health/` → `{"status":"ok"}`
- 两个新接口未认证返回 **401**（路由已注册）
- `dashboard/fault-summary/` → 200：`active_fault_count=473, affected_unit_count=75`
- `dashboard/device-fault-summary/` → 200：空气品质 634/49、温控面板 2954/206、新风 634/66、水力 634/61
- 设备列表凝露字段：生产唯一 1 条活跃凝露事件（`7-1-5-502`）在第 8 页正确显示 `has_active_condensation=True`，全列表 True 总数=1，吻合

## 测试
- 新增 `test_v100_dashboard_redesign.py` 16 用例全通过（修正了测试内 tz-aware 时间与 USE_TZ=False 冲突的 bug，生产代码未动）
- 回归无新增失败

## 已知遗留（非本次引入，未处理）
- 设备列表 API `page_size` 被硬 cap 到 50（即便请求更大值），对应历史失败用例 `TC_I_005_DeviceListAPIPagination`（期望 cap=2000）。看板卡片走独立聚合接口，不受此 cap 影响。
- `test_dashboard_power_status_v053.py:555` docstring 语法错误（来自 v0.5.3 提交 072e373），导致该测试文件无法被收集。
- 工作区遗留未提交：`package-lock.json`（生产 ARM 依赖树本地修改，按纪律不入仓）、`.claude/skills/freeark-prod-deploy/SKILL.md`（手册文档更新，与本次功能无关）。
