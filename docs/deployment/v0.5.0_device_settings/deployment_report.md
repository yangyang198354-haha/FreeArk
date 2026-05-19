<file_header>
  <author_agent>sub_agent_devops_engineer</author_agent>
  <timestamp>2026-05-20T00:00:00+08:00</timestamp>
  <project_name>FreeArk-DeviceSettings-v0.5.0</project_name>
  <version>1.0.0</version>
  <input_files>
    <file>docs/deployment/v0.5.0_device_settings/deployment_plan.md</file>
    <file>docs/deployment/v0.5.0_device_settings/production_runbook_192.168.31.51.md</file>
    <file>docs/deployment/v0.5.0_device_settings/verify_deployment.sh</file>
    <file>docs/deployment/v0.5.0_device_settings/rollback.sh</file>
  </input_files>
  <phase>PHASE_11</phase>
  <status>DRAFT</status>
</file_header>

---

# 部署报告

**文档编号**：DEPLOY-REPORT-v0.5.0-device-settings  
**项目名称**：FreeArk 设备设置页面增量变更  
**目标版本**：v0.5.0  
**基线版本**：v0.4.7（回滚 commit：b714db1）  
**部署目标**：`192.168.31.51`（内网生产服务器）  
**计划部署日期**：2026-05-20  
**状态**：`PENDING_USER_EXECUTION`

---

## 1. 部署状态

```
deployment_status: PENDING_USER_EXECUTION
```

> 说明：所有 Runbook 文档、验证脚本、回滚脚本已生成完毕，等待操作人员按
> `production_runbook_192.168.31.51.md` 逐步执行并回填本报告留空字段。

---

## 2. 风险接受记录

以下风险已由用户在本次会话中明确授权接受：

| 风险编号 | 风险描述 | 风险等级 | 缓解措施 | 授权人 | 授权日期 |
|---------|---------|---------|---------|-------|---------|
| RISK_ACCEPTED_001 | 跳过 Staging 验证，直接部署生产环境（无 Staging 环境验证结果作为门控）| 高 | 执行 verify_deployment.sh 脚本做部署后自动验证；保留完整数据库备份和前端 dist 快照用于快速回滚 | 用户（本次会话授权） | 2026-05-20 |
| RISK_ACCEPTED_002 | SSH 密码认证模式，Runbook 需操作人员手动逐步执行，无法自动化端到端部署 | 中 | Runbook 每步附有预期输出和失败处理说明；verify_deployment.sh 提供 5 项自动化验证覆盖关键路径 | 用户（本次会话授权） | 2026-05-20 |

**生产部署授权记录**：

```
PRODUCTION_DEPLOY_CONFIRM = true
授权方式：用户在 PM Orchestrator 本次会话中明确发出
授权范围：FreeArk v0.5.0 生产环境部署（192.168.31.51），本次 SDLC 运行唯一有效
授权日期：2026-05-20
本次授权不可跨会话/跨部署运行复用
```

---

## 3. 变更范围摘要

本次部署涉及以下变更（详见 `deployment_plan.md` §1）：

| 文件 | 变更类型 | 关联需求 |
|------|---------|---------|
| `api/views_device_settings.py` | `WRITABLE_SUFFIXES` 追加 `_mode`；新增 `WRITABLE_PARAM_NAMES` 白名单（`away_energy_saving`） | REQ-FUNC-002、REQ-FUNC-003 |
| `api/param_value_label.py` | 新增 `operation_mode`、`away_energy_saving` 值映射 | REQ-FUNC-002、REQ-FUNC-003 |
| `api/management/commands/seed_device_config.py` | `system_switch(main_thermostat)` 设为 `is_active=False`；水力模块新增 3 条可写记录 | REQ-FUNC-001、CHG-01 |
| `frontend/src/views/DeviceSettingsPanelView.vue` | 新增 `dirtyFields` Set 脏值追踪；`markDirty` 含 FR-001 hotfix（undefined 清空保护） | REQ-FUNC-004、ADR-10、FR-001 |

**数据库变更**：无 Schema 变更（无需 `migrate`），仅 seed 数据层变更（`is_active`、新增行）。

---

## 4. 部署执行记录（待回填）

> 以下字段由操作人员执行完毕后回填，回填后将 `deployment_status` 更新为最终状态。

```
实际执行开始时间：____________________（格式：YYYY-MM-DD HH:MM:SS +08:00）
实际执行完成时间：____________________
执行人员：____________________
备份产物路径：
  - 数据库备份：/opt/freeark/backup/<BACKUP_TS>/db.sqlite3.bak
  - 前端快照：/opt/freeark/backup/<BACKUP_TS>/nginx_html_v0.4.7/
  - 服务状态快照：/opt/freeark/backup/<BACKUP_TS>/service_snapshot.txt
  - 备份时间戳（BACKUP_TS）：____________________
```

---

## 5. verify_deployment.sh 执行结果（待回填）

> 执行 `bash verify_deployment.sh` 后，将完整输出粘贴至此处。

```
（执行完毕后粘贴 verify_deployment.sh 输出，包含 5 项 [PASS]/[FAIL] 结果及最终 DEPLOYMENT_VERIFIED=true/false）

____________________
```

| 检查项 | 预期 | 实际结果 |
|-------|------|---------|
| 检查 1：后端健康检查（HTTP 200） | PASS | |
| 检查 2：设备设置 API 路由可达（HTTP 401） | PASS | |
| 检查 3：前端静态资源（HTTP 200） | PASS | |
| 检查 4：bundle 包含 markDirty（FR-001 hotfix） | PASS | |
| 检查 5：system_switch is_active=False（seed 验证） | PASS | |
| **整体结论** | **DEPLOYMENT_VERIFIED=true** | |

---

## 6. 手动功能验收记录（待回填）

> 对应 `deployment_plan.md` §9.4 及 Runbook Step 8。

| 编号 | 验收项 | 预期结果 | 实际结果 | 通过？ |
|------|-------|---------|---------|-------|
| AC-01 | 主温控分组 | 系统开关字段消失 | | |
| AC-02 | 水力模块：工作模式字段 | 出现 operation_mode，下拉可选 | | |
| AC-03 | 水力模块：离家节能字段 | 出现 away_energy_saving，下拉可选 | | |
| AC-04 | 脏值追踪功能 | 修改未提交时显示脏值数量 | | |
| AC-05 | 仅提交已修改字段 | payload 只含已修改参数 | | |
| AC-06 | operation_mode 写入 | 后端返回 HTTP 202，无 400 | | |

---

## 7. 异常记录（待回填）

```
部署过程中遇到的异常或偏差（如无则填"无"）：
____________________
```

---

## 8. 回滚记录（待回填）

```
是否触发回滚：[ 是 / 否 ]
回滚触发原因（如触发）：____________________
回滚执行时间：____________________
回滚使用快照时间戳：____________________
回滚后验证结果：____________________
```

---

## 9. 最终状态（待回填）

```
final_status: ____________________
（可选值：DEPLOYED_SUCCESSFULLY / FAILED_ROLLED_BACK / PARTIAL_DEPLOYED）
```

> 回填规则：
> - `DEPLOYED_SUCCESSFULLY`：verify_deployment.sh 全部 PASS + 所有 AC 通过 + 未触发回滚
> - `FAILED_ROLLED_BACK`：触发回滚并成功恢复至 v0.4.7
> - `PARTIAL_DEPLOYED`：部分步骤完成但未达到完全部署状态（需补充说明）

---

## 10. 后续待处理事项

| 事项 | 优先级 | 负责人 | 状态 |
|------|-------|-------|------|
| deployment_report.md 回填并更新 status=APPROVED | 高 | 操作人员 | 待执行 |
| 确认 MQTT Broker（192.168.31.98:32788）连通性 | 中 | 操作人员 | 待确认 |
| 部署后 1 小时监控（5xx 错误率） | 中 | 操作人员 | 待执行 |
| 建立 Staging 环境（降低后续版本的 RISK_ACCEPTED_001） | 低 | 项目负责人 | 待规划 |
| 将 SSH 认证升级为密钥认证（降低 RISK_ACCEPTED_002） | 低 | 项目负责人 | 待规划 |

---

*文档状态：DRAFT — 等待操作人员执行 Runbook 并回填留空字段后，更新为 APPROVED*
