<file_header>
  <author_agent>sub_agent_devops_engineer</author_agent>
  <timestamp>2026-05-20T00:00:00+08:00</timestamp>
  <project_name>FreeArk-DeviceSettings-v0.5.0</project_name>
  <version>1.0.0</version>
  <input_files>
    <file>docs/requirements/requirements_spec_v0.5.0_device_settings.md</file>
    <file>docs/requirements/user_stories_v0.5.0_device_settings.md</file>
    <file>docs/architecture/architecture_design_v0.5.0_device_settings.md</file>
    <file>docs/architecture/module_design_v0.5.0_device_settings.md</file>
    <file>docs/development/v0.5.0_device_settings/implementation_plan.md</file>
    <file>docs/development/v0.5.0_device_settings/code_review_report.md</file>
    <file>docs/testing/v0.5.0_device_settings/test_plan.md</file>
    <file>docs/testing/v0.5.0_device_settings/unit_test_report.md</file>
    <file>docs/testing/v0.5.0_device_settings/integration_test_report.md</file>
    <file>docs/testing/v0.5.0_device_settings/fr001_hotfix_test_report.md</file>
    <file>FreeArkWeb/backend/freearkweb/api/views_device_settings.py</file>
    <file>FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py</file>
    <file>FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue</file>
    <file>FreeArkWeb/frontend/nginx.conf</file>
  </input_files>
  <phase>PHASE_10</phase>
  <status>DRAFT</status>
</file_header>

---

# 部署计划文档

**文档编号**：DEPLOY-PLAN-v0.5.0-device-settings  
**项目名称**：FreeArk 设备设置页面增量变更  
**目标版本**：v0.5.0  
**基线版本**：v0.4.7  
**日期**：2026-05-20  
**状态**：DRAFT  
**作者**：sub_agent_devops_engineer

---

## 1. 变更范围概述

本次 v0.5.0 版本针对「设备设置」功能进行增量变更，涉及 4 个源码文件：

| 文件 | 变更类型 | 对应需求 |
|------|---------|---------|
| `FreeArkWeb/backend/freearkweb/api/views_device_settings.py` | 可写性规则扩展（`WRITABLE_SUFFIXES` 追加 `_mode`；新增 `WRITABLE_PARAM_NAMES` 白名单） | REQ-FUNC-002、REQ-FUNC-003、ADR-09 |
| `FreeArkWeb/backend/freearkweb/api/param_value_label.py` | 新增 `operation_mode`、`away_energy_saving` 的值映射 label | REQ-FUNC-002、REQ-FUNC-003 |
| `FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py` | `system_switch`（主温控）设为 `is_active=False`（软删除）；水力模块新增三条可写记录 | REQ-FUNC-001、CHG-01 |
| `FreeArkWeb/frontend/src/views/DeviceSettingsPanelView.vue` | 新增 `dirtyFields` Set 追踪脏值，提交时仅发送变更项 | REQ-FUNC-004、ADR-10 |

**所有改动当前为未提交状态**（git working tree dirty），部署前需先执行 `git commit` 打 tag `v0.5.0`。

---

## 2. 变更影响分析

### 2.1 数据库 Schema 变更

**结论：本次无数据库 schema 变更，无需执行 `python manage.py migrate`。**

依据：
- v0.5.0 的 4 个改动文件均不涉及 Django Model 字段定义变更。
- `seed_device_config.py` 的变更是**数据层 seed 操作**（`update_or_create` / `get_or_create`），作用于 `device_config` 表的**行数据**，不改变表结构。
- 最新 migration 文件为 `0024_plcwriterecord_batch_request_id.py`，已在 v0.4.x 阶段应用完毕。
- **部署时必须执行 `python manage.py seed_device_config` 重跑**（非 migrate），原因见第 2.2 节。

### 2.2 数据 Seed 变更（必须重跑）

**必须在部署时重跑 `seed_device_config` 的原因**：

1. `system_switch`（`sub_type=main_thermostat`）新增了 `is_active=False` 标记（CHG-01）。
   - 该条目在 v0.4.7 数据库中若已存在（`is_active=True`），**仅执行代码部署无法改变其值**——必须重跑 seed 命令，利用 `update_or_create` 强制写入 `is_active=False`。
   - 若不执行，前端设备设置页面仍会显示「主温控 - 系统开关」字段，REQ-FUNC-001 验收不通过。

2. 水力模块新增 `operation_mode`、`away_energy_saving`（及相关映射）已在 seed 中声明，需确保这些记录存在于数据库中。

3. `seed_device_config` 的 `get_or_create` / `update_or_create` 语义确保**幂等性**（REQ-NFUNC-004）：重跑不会产生重复记录，安全可重试。

### 2.3 PLC 偏移量映射变更

**结论：本次无 PLC 偏移量变更。**

依据：
- v0.5.0 未新增任何 PLC 偏移量定义（`plc_config.json` 或等效配置未变更）。
- 本次变更的本质是：**扩展哪些已有 PLC 参数允许被前端写入**（`WRITABLE_SUFFIXES` + `WRITABLE_PARAM_NAMES`），以及**软删除哪些参数在 UI 的可见性**（`is_active=False`）。
- `operation_mode`（对应 PLC 地址）和 `away_energy_saving`（对应 PLC 地址）在 v0.4.x 中已有对应 PLC 偏移量记录（由 `plc_config.json` 管理），本次仅解锁其可写性。
- `datacollection/` 子系统的 PLC 采集配置**无需修改**。

### 2.4 前端构建产物变更

**变更内容**：
- `DeviceSettingsPanelView.vue` 的 `dirtyFields` Set 逻辑变更，导致前端 JS 产物更新。
- 构建产物目录：`FreeArkWeb/frontend/dist/`（Vite 构建输出）。
- 变更影响范围：仅设备设置页面（`/device-settings` 路由），其他页面 chunk 无变化（Vite manualChunks=undefined，单 bundle）。

**部署时必须替换整个 `dist/` 目录**（不可只替换单文件，Vite hash 文件名已变化）。

### 2.5 MQTT Topic 变更

**结论：本次无 MQTT Topic 变更。**

依据：
- 写入命令 topic 格式 `/datacollection/plc/write/command/{specific_part}` 不变（`views_device_settings.py` 第 264 行）。
- 新增可写参数（`operation_mode`、`away_energy_saving`）使用与现有参数相同的 topic，仅 payload 的 `param_name` 字段不同。
- 订阅方（PLCWriteSubscriber）的 topic 订阅模式不变，可自动处理新参数。
- MQTT Broker 地址（`192.168.31.98:32788`）不变。

---

## 3. 部署前置检查清单

在执行任何部署步骤前，操作人员须确认以下所有检查项已完成（逐项打勾）：

### 3.1 代码准备

- [ ] **1. 提交所有未提交改动**：执行 `git add` + `git commit`，提交信息格式：`feat(device-settings): v0.5.0 — [改动摘要]`
- [ ] **2. 打版本标签**：执行 `git tag v0.5.0`（与回滚基线 `v0.4.7` tag 并存）
- [ ] **3. 推送代码及标签**：（按用户决策，此步骤在 PHASE_10 后由用户确认是否执行）

### 3.2 数据备份（必须在部署前完成）

- [ ] **4. 备份 `device_config` 数据表**：

  ```bash
  # SQLite 环境
  cp /opt/freeark/backend/freearkweb/db.sqlite3 \
     /opt/freeark/backup/db.sqlite3.bak.$(date +%Y%m%d_%H%M%S)

  # 或导出 device_config 表（CSV 格式，便于对比）
  cd /opt/freeark/backend/freearkweb
  python manage.py shell -c "
  import csv, sys
  from api.models import DeviceConfig
  w = csv.writer(sys.stdout)
  w.writerow(['id','param_name','sub_type','is_active'])
  for r in DeviceConfig.objects.all():
      w.writerow([r.id, r.param_name, r.sub_type, r.is_active])
  " > /opt/freeark/backup/device_config_backup_$(date +%Y%m%d_%H%M%S).csv
  ```

- [ ] **5. 备份前端 dist/**：

  ```bash
  cp -r /usr/share/nginx/html/ \
        /opt/freeark/backup/nginx_html_backup_$(date +%Y%m%d_%H%M%S)/
  ```

- [ ] **6. 记录当前 `system_switch`（main_thermostat）的 `is_active` 值**（用于验证 seed 执行效果）：

  ```bash
  cd /opt/freeark/backend/freearkweb
  python manage.py shell -c "
  from api.models import DeviceConfig
  obj = DeviceConfig.objects.filter(param_name='system_switch', sub_type='main_thermostat').first()
  print(f'system_switch is_active: {obj.is_active if obj else \"NOT FOUND\"}')
  "
  # 预期当前值：True（v0.4.7 基线）
  # 部署后预期值：False
  ```

### 3.3 服务与环境确认

- [ ] **7. 确认 MQTT Broker 可达**：

  ```bash
  ping -c 3 192.168.31.98
  # 或：python -c "import socket; s=socket.create_connection(('192.168.31.98',32788),3); print('OK')"
  ```

- [ ] **8. 确认 Django 后端当前运行版本**：

  ```bash
  # 查看运行中的后端进程
  systemctl status freeark-backend
  # 或：ps aux | grep waitress | grep -v grep
  ```

- [ ] **9. 通知设备终端用户停机窗口**（如适用）：
  - 本次变更属于**低影响变更**（仅扩展可写字段集合 + 软删除 1 个 UI 字段），无需长时间停机。
  - 建议告知用户：部署期间（约 5-10 分钟）设备设置页面不可操作，但**设备监控页面不受影响**（PLC 采集子系统独立运行）。
  - 停机窗口建议选择业务低峰时段（如凌晨 2:00-4:00）。

- [ ] **10. 确认回滚制品已准备**：
  - `v0.4.7` 版本的后端代码制品可获取（git tag `v0.4.7` 或对应备份包）。
  - `v0.4.7` 版本的前端 dist 备份（即步骤 5 的备份）已完成。

---

## 4. 部署步骤（编号清单）

> 以下步骤假设服务器路径为 `/opt/freeark/`，根据实际环境调整。  
> 每步完成后在对应行打勾。

---

**步骤 1：拉取最新代码（或解压制品包）**

```bash
# 方式 A：直接在服务器拉取（有 git 访问权限）
cd /opt/freeark/backend
git fetch origin
git checkout v0.5.0

# 方式 B：解压 CI 产出的制品包
tar -xzf /opt/freeark/deploy/backend-v0.5.0.tar.gz -C /opt/freeark/deploy/extracted/
rsync -av --delete /opt/freeark/deploy/extracted/FreeArkWeb/backend/ /opt/freeark/backend/
```

- [ ] 步骤 1 完成

---

**步骤 2：安装/更新 Python 依赖**

```bash
cd /opt/freeark/backend
pip install -r requirements.txt
```

> 说明：v0.5.0 未新增 Python 依赖，若 `requirements.txt` 未变化则此步骤快速跳过。

- [ ] 步骤 2 完成

---

**步骤 3：执行 Migration 检查（只检查不执行）**

```bash
cd /opt/freeark/backend/freearkweb
python manage.py migrate --check
```

预期输出：退出码 0（无待执行 migration）。若有未应用 migration，**停止部署，检查原因**。

- [ ] 步骤 3 完成，`migrate --check` 退出码 = 0

---

**步骤 4：执行 `seed_device_config` 重跑（核心步骤）**

```bash
cd /opt/freeark/backend/freearkweb
python manage.py seed_device_config
```

预期输出：
```
  [deactivated(updated)] system_switch -> main_thermostat (is_active=False)
  [skipped] living_room_ntc_temp already exists
  ...
  Done: created N, skipped M
```

关键验证：确认 `system_switch -> main_thermostat (is_active=False)` 出现在输出中。

若 `system_switch`（main_thermostat）记录不存在（首次部署场景），输出将为 `[deactivated(created)]`，同样正确。

- [ ] 步骤 4 完成，日志确认 `system_switch is_active=False`

---

**步骤 5：重启 Django 后端服务**

```bash
systemctl restart freeark-backend
# 等待 10s 后确认服务正常运行
sleep 10
systemctl status freeark-backend
```

**此步骤是关键步骤**，原因：
- `WRITABLE_SUFFIXES = ('_temp_setting', '_switch', '_mode')` 和 `WRITABLE_PARAM_NAMES = frozenset({'away_energy_saving'})` 是模块级常量，**在 Django 进程启动时加载**。
- 若不重启服务，生产环境仍运行 v0.4.7 的旧常量（`_mode` 未在白名单中），导致 `operation_mode` 写入请求被拒绝（HTTP 400）。

- [ ] 步骤 5 完成，`systemctl status` 显示 `active (running)`

---

**步骤 6：构建并部署前端静态文件**

```bash
# 方式 A：在服务器本地构建（需安装 Node.js 20+）
cd /opt/freeark/frontend
npm ci
npm run build
# 构建输出：/opt/freeark/frontend/dist/

# 方式 B：解压 CI 产出的前端制品包
tar -xzf /opt/freeark/deploy/frontend-dist-v0.5.0.tar.gz -C /tmp/frontend_new/

# 替换 Nginx 静态目录（先清理旧文件）
rsync -av --delete /opt/freeark/frontend/dist/ /usr/share/nginx/html/
# 或使用制品包：
rsync -av --delete /tmp/frontend_new/dist/ /usr/share/nginx/html/
```

- [ ] 步骤 6 完成，`dist/` 已替换

---

**步骤 7：重载 Nginx**

```bash
nginx -t
# 预期输出：nginx: configuration file ... syntax is ok
# 预期输出：nginx: configuration file ... test is successful
nginx -s reload
# 或：systemctl reload nginx
```

- [ ] 步骤 7 完成，Nginx 配置测试通过并已重载

---

**步骤 8：Django 系统检查**

```bash
cd /opt/freeark/backend/freearkweb
python manage.py check
```

预期：输出 `System check identified no issues (0 silenced).`

- [ ] 步骤 8 完成，无 CRITICAL 错误

---

**步骤 9：部署验证（功能验收）**

按以下顺序逐项验证：

**9.1 API 健康检查**

```bash
curl -s http://localhost:8000/api/health/ | python -m json.tool
```

预期：返回 `{"status": "ok"}` 或类似健康响应（HTTP 200）。

- [ ] 9.1 通过

**9.2 设备设置参数接口可达（未认证应返回 401）**

```bash
curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8000/api/device-settings/params/test_part/
```

预期：`401`（未提供认证 token，接口已注册但需认证）。

- [ ] 9.2 通过（HTTP 401）

**9.3 前端页面可访问**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost/
```

预期：`200`（Nginx 返回 index.html）。

- [ ] 9.3 通过（HTTP 200）

**9.4 手动功能验收（需登录）**

操作人员使用有效账号登录前端，导航至设备设置页面，逐项确认：

| 验收项 | 预期结果 | 实际结果 | 通过？ |
|--------|---------|---------|-------|
| 主温控（Main Thermostat）分组 | **系统开关字段消失**（is_active=False 过滤） | | |
| 水力模块（Hydraulic Module）分组 | 出现**工作模式**（`operation_mode`）字段，可编辑 | | |
| 水力模块（Hydraulic Module）分组 | 出现**离家节能标识**（`away_energy_saving`）字段，可编辑 | | |
| 修改任意字段值（不提交） | 提交按钮旁显示脏值数量（`dirtyFields` 功能） | | |
| 仅提交已修改字段 | 请求 payload 中只包含已修改的参数，不包含未修改参数 | | |
| 对 `operation_mode` 发起写入请求 | 后端返回 HTTP 202（pending），无 HTTP 400 "不在可写白名单" | | |

- [ ] 9.4 所有手动验收项通过

---

**步骤 10：记录部署完成信息**

```
部署完成时间：____________________
执行人员：____________________
实际耗时：____________________
异常记录（如有）：____________________
```

- [ ] 步骤 10 完成，部署信息已记录

---

## 5. 生产部署 CONFIRM 信号机制

### 5.1 PHASE_11 执行条件

**PHASE_11（生产部署执行阶段）必须满足以下全部条件才可启动**：

1. PHASE_10（本文档）门控评审 decision = **PASS**
2. Staging 环境部署及验证通过（`deployment_report` = `DEPLOYED_SUCCESSFULLY`）
3. 用户发出明确的生产部署授权信号：`PRODUCTION_DEPLOY_CONFIRM=true`

### 5.2 授权信号说明

- `PRODUCTION_DEPLOY_CONFIRM=true` 信号必须由**项目负责人在当次会话/当次 CI 运行中明确提供**。
- 信号**不可从历史会话推断**，不可跨 CI 运行复用。
- 在 CI 流水线中，此信号对应「人工审批节点」（见 `cicd_pipeline.md` 第 3.7 节）中审批人回复 `approved`。
- 在手动部署场景中，此信号对应操作人员向 PM Orchestrator 发送明确的授权消息。

### 5.3 授权确认记录

> 本区域在用户发出授权后由 PM Orchestrator 填写。

```
PRODUCTION_DEPLOY_CONFIRM 授权记录
用户确认时间：____________________
授权范围：FreeArk v0.5.0 生产环境部署（本次 SDLC 运行唯一有效）
授权人：____________________
PM Orchestrator 记录时间：____________________
```

---

## 6. 回滚方案

### 6.1 回滚决策原则

在以下任一情况下，应立即启动回滚：

- 步骤 9（部署验证）中有任何一项**9.1/9.2/9.3 失败**（服务不可达）
- 步骤 9.4 手动验收中发现**主温控系统开关仍然显示**（seed 未生效）
- 步骤 9.4 手动验收中发现**`operation_mode` 写入返回 400**（服务重启未生效）
- 部署后 1 小时内出现生产告警（`5xx` 错误率异常上升）

### 6.2 代码回滚

```bash
# 方式 A：git checkout 回 v0.4.7 tag
cd /opt/freeark/backend
git checkout v0.4.7

# 方式 B：从备份包恢复（若无 git 访问权限）
rsync -av --delete /opt/freeark/backup/backend-v0.4.7/ /opt/freeark/backend/
```

### 6.3 数据库回滚（seed 回滚）

**目标**：恢复 `system_switch`（main_thermostat）的 `is_active=True`。

```bash
# 方式 A：重跑 v0.4.7 版本的 seed_device_config（--reset 模式，全量重建）
cd /opt/freeark/backend/freearkweb
git checkout v0.4.7 -- api/management/commands/seed_device_config.py
python manage.py seed_device_config --reset

# 方式 B：直接 Django shell 精确修复（无需 --reset，避免影响其他数据）
python manage.py shell -c "
from api.models import DeviceConfig
obj = DeviceConfig.objects.filter(param_name='system_switch', sub_type='main_thermostat').first()
if obj:
    obj.is_active = True
    obj.save()
    print(f'已恢复 system_switch is_active=True (id={obj.id})')
else:
    print('WARNING: system_switch main_thermostat 记录不存在')
"
```

**验证**：

```bash
python manage.py shell -c "
from api.models import DeviceConfig
obj = DeviceConfig.objects.filter(param_name='system_switch', sub_type='main_thermostat').first()
print(f'system_switch is_active: {obj.is_active if obj else \"NOT FOUND\"}')
"
# 预期：system_switch is_active: True
```

### 6.4 前端回滚

```bash
# 恢复备份的 v0.4.7 dist/ 快照
rsync -av --delete /opt/freeark/backup/nginx_html_backup_<时间戳>/ /usr/share/nginx/html/
nginx -t && systemctl reload nginx
```

### 6.5 服务重启

```bash
systemctl restart freeark-backend
sleep 10
systemctl status freeark-backend
```

### 6.6 dirtyFields 状态说明

`dirtyFields` 是 `DeviceSettingsPanelView.vue` 中的**纯前端内存状态**（`const dirtyFields = new Set()`），以下说明其回滚特性：

- `dirtyFields` **无持久化**：不写入 localStorage、sessionStorage，也不写入任何后端数据库表。
- **无需回滚**：页面刷新或前端回滚后，`dirtyFields` 自动清空（初始为空 Set），无遗留状态。
- **用户操作影响**：若用户在 v0.5.0 部署期间有未提交的修改，回滚到 v0.4.7 前端后，这些未提交修改将消失（因从未写入后端）。

### 6.7 回滚完成验证

回滚后按以下清单验证：

- [ ] `system_switch`（main_thermostat）`is_active=True`（已恢复，设备设置页面重新显示系统开关）
- [ ] 前端页面可访问（HTTP 200）
- [ ] API 健康检查通过（HTTP 200）
- [ ] `operation_mode` 写入请求返回 HTTP 400（可写白名单已回退，仅有 `_temp_setting`、`_switch` 后缀）

---

## 7. 部署时间估算

| 阶段 | 预计耗时 | 说明 |
|-----|---------|------|
| 前置检查（步骤 0） | 10-15 分钟 | 备份数据库、备份 dist/、确认服务状态 |
| 后端代码更新（步骤 1-3） | 5-10 分钟 | 拉取代码 + pip install（依赖无变化则快速） |
| Seed 执行（步骤 4） | 1-2 分钟 | Django 管理命令，幂等快速 |
| 后端重启（步骤 5） | 2-3 分钟 | waitress 进程重启 + 就绪等待 |
| 前端构建 + 部署（步骤 6-7） | 3-8 分钟（构建）+ 1 分钟（nginx reload） | 若使用 CI 制品包则跳过构建，仅需 1-2 分钟 |
| 验证（步骤 8-9） | 10-15 分钟 | 自动验证 + 手动功能验收 |
| **总计** | **约 35-55 分钟** | 建议预留 90 分钟（含回滚时间裕量） |

---

## 8. 联系人与升级路径

| 角色 | 负责范围 | 升级条件 |
|-----|---------|---------|
| 部署操作人员 | 执行本文档所有步骤 | 任何步骤失败或不确定时 |
| 项目负责人 | 授权生产部署（`PRODUCTION_DEPLOY_CONFIRM=true`）；回滚决策 | 9.4 验收失败；服务不可恢复 |
| 后端开发 | 分析 `views_device_settings.py`、`seed_device_config.py` 相关问题 | 步骤 4/5 异常 |
| 前端开发 | 分析 `DeviceSettingsPanelView.vue` 相关问题 | 步骤 6/9.4 异常 |

---

*文档状态：DRAFT — 待 PHASE_10 门控评审通过后更新为 APPROVED*
