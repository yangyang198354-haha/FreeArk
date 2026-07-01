# v0.6.1-FM-UX 故障管理 UX 调整 — 生产部署报告

| 项 | 值 |
|---|---|
| 部署日期 | 2026-05-28 |
| 部署人 | Yang Yang（Claude Code 协助执行 SSH 步骤） |
| 目标主机 | 树莓派 Raspberry Pi 5，`192.168.31.51`（外网 `et116374mm892.vicp.fun:57279`） |
| 部署前 HEAD | `1554e8f fix(dph-cleanup): _run_cleanup 前 close_old_connections() (BUG-DPH-003)` |
| 部署后 HEAD | `c7aa7fd feat(fault-mgmt): v0.6.1 UX 调整（导航/房号控件/设备名/默认筛选）` |
| 部署方式 | plink+ssh 手工 + `git pull origin main`（密钥认证，无密码） |
| 部署结果 | ✅ **SUCCESS** |

## 部署步骤实际执行

| # | 操作 | 实际结果 | 状态 |
|---|---|---|---|
| 0 | cicd_pipeline.md + deployment_plan.md 产出 | 文件存在 | ✅ DONE |
| 1 | git status 前置检查 | 仅 3 个长期本地修改（`.env` / `heartbeat_broker_config.json` / `package-lock.json`），与 skill 文档一致；HEAD = `1554e8f` | ✅ PASS |
| 2 | git pull origin main | Fast-forward 19 文件 +3751/-49 行；HEAD → `c7aa7fd`；无 CONFLICT；3 个本地修改未受影响 | ✅ PASS |
| 3 | 落地验证 | `device_name_cache.py` 存在（4171 字节）；`PRODUCT_CODE_LABELS` grep 命中 1；`device_name` 在 `serializers_fault.py` 出现 9 次 | ✅ PASS |
| 4 | 前端备份 + `npm run build` | 备份至 `dist_backup_$(date)`；构建耗时 **20.17s**；产物 6 个新 chunk（FaultManagementView / CascadingSelector 等）；building_data.js + favicon.png 已复制到 dist/ | ✅ PASS |
| 5 | `systemctl restart freeark-backend` | `is-active = active`；启动日志含 `Application startup complete`、`Uvicorn running on http://0.0.0.0:8000`；无 Traceback | ✅ PASS |
| 6a | `curl /api/health/` | `{"status":"ok","message":"FreeArk Web API 服务正常运行"}` | ✅ PASS |
| 6b | Django shell 序列化器字段验证 | 8 条活跃故障样本 device_name **全部命中**，无 fallback | ✅ PASS |
| 7 | 覆盖度统计 | 活跃 468/468 = **100% 主路径命中**；全部历史前 500 条 **100% 命中**；兜底一/双重 miss 均为 0 | ✅ PASS |

## 烟测样本（生产实测）

```
FaultEvent total = 1560
FaultEvent active = 468

sp=5-2-14-1401    sn=22157  pc=100007  fault=error_265              | device_name='空气品质'   device_type_label='空气品质'
sp=7-1-11-1104    sn=22157  pc=100007  fault=error_265              | device_name='空气品质'   device_type_label='空气品质'
sp=8-1-14-1403    sn=21998  pc=100007  fault=comm_fault_timeout     | device_name='空气品质'   device_type_label='空气品质'
sp=8-1-14-1403    sn=21999  pc=250001  fault=comm_fault_timeout     | device_name='能耗表'     device_type_label='能耗表'
sp=8-1-14-1403    sn=22550  pc=120003  fault=comm_fault_timeout     | device_name='温控面板'   device_type_label='温控面板'
sp=8-1-14-1403    sn=22001  pc=260001  fault=comm_fault_timeout     | device_name='主温控'     device_type_label='主温控'
sp=8-1-14-1403    sn=21996  pc=10016   fault=comm_fault_timeout     | device_name='自由方舟'   device_type_label='自由方舟（主机）'
sp=8-1-14-1403    sn=21997  pc=270001  fault=comm_fault_timeout     | device_name='水力模块'   device_type_label='水力模块'
```

**结论**：用户最初问到的 SN 21997 / 22001 现在分别正确显示为「水力模块」和「主温控」，全部 468 条活跃故障不再出现数字 SN。

## 变更范围确认

- [x] 无 DB migration
- [x] 无 systemd unit 变更（仅重启 freeark-backend，未新增/修改 unit）
- [x] 无 nginx 配置变更
- [x] `.env` / `package-lock.json` / `heartbeat_broker_config.json` 未包含在 c7aa7fd，git pull 未触碰它们

## 部署过程中的事件

1. **SSH 瞬态中断 1 次**（Step 2 首次 git pull）：`kex_exchange_identification: read: Software caused connection abort` — frp/动态 DNS 隧道偶发，立即重试成功，无数据损失。
2. **deploy_v061_fm_ux.py 安全事件**：上一轮 devops 子代理误生成一个带硬编码 `PASSWORD = "123456"` 的部署脚本（违反 skill"SSH 用密钥认证、本文件不含任何密码"准则），已在执行前删除，未提交到 git。
3. **bundle size warning（非阻塞）**：vite build 提示 `index-*.js > 500kB`，是项目历史问题与 v0.6.1 无关。

## 待用户在浏览器手工 E2E

需要您在浏览器实际访问生产环境完成 5 条 `manual_e2e_checklist.md` 中的检查项：

1. 左侧"设备管理"展开应含「设备列表」+「故障管理」二级菜单
2. 设备列表页头**无**右上角"故障管理"按钮
3. 故障管理选房号（楼栋 8 / 单元 1 / 房号 1403）→ Network 请求含 `specific_part=8-1-1403`
4. 表格"设备名称"列显示中文名（21997=水力模块 等）
5. 默认筛选 = "未恢复"；URL `?is_active=false` 时高亮"已恢复"；点重置后恢复"未恢复"

## 回滚预案（如发现 E2E 问题）

```bash
ssh -p 57279 yangyang@et116374mm892.vicp.fun
cd /home/yangyang/Freeark/FreeArk
git revert c7aa7fd --no-edit
# 推到 GitHub（开发机 commit）：git push origin main 后再到 prod git pull
sudo systemctl restart freeark-backend
# 前端回滚：
# cp -r /home/yangyang/FreeArk_backup/dist_backup_<新备份时间戳> FreeArkWeb/frontend/dist
```

回滚成本：约 2 分钟（git revert + 一次 restart + 可选 dist 还原）。

## 关联文档

- 需求：`docs/requirements/v0.6.1_fault_mgmt_ux/{requirements_spec,user_stories}.md`
- 架构：`docs/architecture/{architecture_design,module_design,tech_stack}_v0.6.1_fault_mgmt_ux.md`
- 实施：`docs/implementation/v0.6.1_fault_mgmt_ux/{implementation_plan,code_review_report}.md`
- 测试：`docs/testing/v0.6.1_fault_mgmt_ux/{test_plan,unit_test_report,integration_test_report,manual_e2e_checklist}.md`
- 本期 commit：`c7aa7fd`
