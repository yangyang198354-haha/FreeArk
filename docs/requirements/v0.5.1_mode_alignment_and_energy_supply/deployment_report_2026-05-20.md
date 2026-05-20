# FreeArk v0.5.1 生产部署实际执行报告

**日期**：2026-05-20
**目标**：`192.168.31.51`（树莓派，用户 `yangyang`）— 本次经外网动态域名隧道 `et116374mm892.vicp.fun:57279` 接入
**基线**：v0.5.0（`21d831f`）→ **目标**：v0.5.1（`72363d6`）
**部署方式**：plink SSH + `git pull --ff-only` + 生产服务器构建前端（沿用内存中既有部署 recipe）
**执行人**：Claude Code（受用户明确 CONFIRM 授权后通过 plink 代为执行）
**最终状态**：`DEPLOYED_SUCCESSFULLY`

---

## 1. 变更内容

| 类别 | 文件 | 改动 |
|---|---|---|
| 后端 | `param_value_label.py` | `_mode` 映射 0-3→1-4；`get_display_value` 历史值 0 兼容映射为制冷 |
| 后端 | `views_device_settings.py` | `central_energy_supply` 纳入可写白名单；新增枚举值域校验（1/2/3，越界 400） |
| 采集 | `plc_write_manager.py` | 新增 `MODE_DEHUMIDIFICATION=4`；有效值扩为 [1-4]；`write_mode_for_building` 与 `central_energy_supply` 写入解耦 |
| 采集 | `plc_data_viewer_gui.py` | 删除除湿(4)静默降级为制冷的逻辑 |
| 前端 | `DeviceCardsView.vue` | `operation_mode`/`central_energy_supply` 三值展示，旧值 0 兼容 |
| 配置 | `plc_config.json` | 首次纳入仓库；`operation_mode` 补 `enum_values` 注释 |
| 测试 | `test_device_settings_v050.py` | 新增/更新 25 用例，SQLite 全通过 |

---

## 2. 实际执行步骤与证据

| Step | 操作 | 关键证据 |
|---|---|---|
| 1 | 本地 `git add`（精确 16 文件）+ `git commit` | commit `72363d6`，16 files changed, +1620/-47 |
| 2 | 本地 `git push origin main` | `21d831f..72363d6  main -> main` |
| 3 | 服务器预检 | 服务器**无** `plc_config.json`（无冲突风险）；`.env`/`package-lock.json` 本地修改保留 |
| 4 | 服务器 `git pull --ff-only origin main` | `Updating 21d831f..72363d6`，Fast-forward，16 files；`plc_config.json` 新建成功 |
| 5 | `manage.py check` | `System check identified no issues (0 silenced)` |
| 6 | `systemctl restart freeark-backend` | 重启后 `is-active=active` |
| 7 | 前端 `npm run build` + `rsync --delete dist/ → /usr/share/nginx/html/` + `nginx -t && nginx -s reload` | 构建 23.48s；rsync sent 3,798,464 bytes；`nginx -t` syntax ok；reload 成功 |

---

## 3. 验证矩阵（agent 可独立执行部分）

| 检查项 | 预期 | 实际 | 通过 |
|---|---|---|---|
| 监听端口 | 80 + 8000 + 8080 | `ss -tlnp` 确认 :80 / :8000 / :8080 全部监听 | ✅ |
| 后端路由 | `/api/device-settings/records/` 返回 401 | HTTP 401 | ✅ |
| 前端首页 | HTTP 200 | HTTP 200 | ✅ |
| Django 校验 | check 无 issue | `0 issues` | ✅ |
| 服务状态 | backend/mqtt-consumer/task-scheduler 均 active | 三者 `active` | ✅ |
| DB migration | 无新 migration | v0.5.1 无 model 变更，未产生 migration | ✅ |

---

## 4. 偏差与说明

1. **datacollection 服务未重启**：改动文件 `plc_write_manager.py` 仅被 `plc_data_viewer_gui.py`（GUI 工具）与 `log_config_manager.py` 引用，无运行中的 systemd 服务直接引用它。该改动将在下次运行楼栋模式下发 GUI/批量工具时生效，无需重启常驻服务。
2. **未单独生成 cicd_pipeline.md / deployment_plan.md**：沿用 v0.5.0 既定做法，按内存知识库 `feedback_deploy_via_git_pull.md` 的 plink + git pull recipe 直接执行。
3. **nginx 既有告警**：reload 时出现 `conflicting server name` warning（`et116374mm892.vicp.fun` / `192.168.31.51` 在 :8080 重复），为既有配置问题，非本次引入，`nginx -t` 通过。
4. **未做 MySQL dump**：v0.5.1 无 model/migration 变更，DB schema 未动，回滚仅需代码层。

---

## 5. 待用户人工验收（agent 无法操作浏览器 UI）

登录前端 `http://192.168.31.51:8080/`（或外网入口）验证：

| 编号 | 验收项 | 预期 |
|---|---|---|
| AC-01 | 设备卡片运行模式标签 | 1=制冷 / 2=制热 / 3=通风 / 4=除湿 显示正确 |
| AC-02 | 水利模块设备设置面板 | 出现「集中能源供给」下拉，三值 1=制冷/2=制热/3=无，可编辑 |
| AC-03 | 集中能源供给写入 | 选择并提交后端返回 202（pending），非 400 |
| AC-04 | 集中能源供给越界校验 | 非 1/2/3 的值被拒（400） |
| AC-05 | 历史旧值兼容 | `operation_mode`/`central_energy_supply` 残留旧值 0 分别展示为「制冷」/「无」 |

---

## 6. 回滚方案

- 代码回滚：`cd /home/yangyang/Freeark/FreeArk && git reset --hard 21d831f`，重启 `freeark-backend`，前端 `npm run build` + rsync。
- `plc_config.json` 为本次新增文件，回滚到 21d831f 后该文件将变为未跟踪（git reset --hard 不删未跟踪文件，但因其本由该 commit 创建会被一并回退）；如需彻底移除可手动删除。
- 无 DB 变更，无需 DB 回滚。

---

## 7. 最终判定

```
final_status: DEPLOYED_SUCCESSFULLY
(待用户完成 AC-01~AC-05 UI 验收后确认无回滚)
```
