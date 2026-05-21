# 部署报告 — v0.5.5 ConnectionStatusHandler 行锁路径优化 (P2)

```
file_header:
  document_id: DEPLOY-v0.5.5
  title: MQTT 采集链路性能优化 P2 — ConnectionStatusHandler 行锁路径优化 — 部署报告
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.5
  deployed_at: 2026-05-21 16:33 CST
  status: SUCCESS
  references:
    - docs/requirements/v0.5.5_connection_status_lock_opt/module_design.md
    - docs/architecture/architecture_design_v0.5.5_connection_status_lock_opt.md
```

---

## 1. 部署概要

| 项 | 内容 |
|----|------|
| 部署目标 | 生产树莓派 192.168.31.51（外网经动态域名 `et116374mm892.vicp.fun:57279` 接入） |
| 项目路径 | `/home/yangyang/Freeark/FreeArk` |
| 部署方式 | plink SSH + `git pull`（无 pscp、无 migration、无前端发版） |
| 提交范围 | `cafa7b6..14229b5`（docs `752ff07` + code `14229b5`） |
| 受影响服务 | `freeark-mqtt-consumer`（systemd） |
| 重启时间 | 2026-05-21 16:33:45 CST |
| 部署结果 | **成功** |

---

## 2. 部署步骤与执行结果

| # | 步骤 | 结果 |
|---|------|------|
| 1 | `git pull` 拉取 `cafa7b6..14229b5` | OK，Fast-forward，6 文件 +1748 行 |
| 2 | `sudo systemctl restart freeark-mqtt-consumer` | OK |
| 3 | `systemctl status` 验证 | `active (running)`，Main PID 6282，Tasks 12 |
| 4 | journal 错误扫描（since restart） | 无 error / critical / exception / traceback |
| 5 | DB 数据流验证 | `last_online_time` 持续推进至当前时刻 |
| 6 | `PLCStatusChangeHistory` 验证 | 重启后无 spurious 行（`hist_since_restart = 0`） |

---

## 3. 投产后验证

### 3.1 服务健康

- `systemctl is-active` → `active`
- 重启后 02:45 持续稳定运行，无异常重启
- journal 自重启起无 ERROR / CRITICAL

### 3.2 数据流与优化效果验证（重启后 ~2.5 分钟采样）

| 指标 | 观测值 | 判读 |
|------|--------|------|
| `MAX(last_online_time)` | 16:36:28（≈采样时刻） | 设备消息持续处理，新代码路径在写入 `last_online_time` ✅ |
| `MAX(updated_at)` | 16:31:57（**重启前**，冻结） | 全字段 `.save()` 已被跳过——优化生效的直接信号 ✅ |
| `last_online_time >= 16:34` 的设备数 | 136 | 重启后 ~2.5 分钟已有 136 台设备经新路径处理，均正常 ✅ |
| 重启后 `PLCStatusChangeHistory` 新增行 | 0 | 无误判状态变化、无重复历史；真实上下线事件仍正常记录 ✅ |

**结论**：优化按设计生效。`updated_at` 冻结于重启前、而 `last_online_time` 持续推进，
证明优化前"每条 energy 消息均执行全字段 `save()`"的行为已消除——快路径仅以
`QuerySet.update()` 刷新 `last_online_time`，慢路径"无变化"分支仅
`save(update_fields=['last_online_time'])`，均不再触发全字段 UPDATE。

### 3.3 一致性确认

- 重启后进程内 `_conn_status_cache` 为空，首批消息按设计走慢路径（`select_for_update()`），
  与优化前行为一致；状态未变化的设备不写 `PLCStatusChangeHistory`（实测 0 行新增），符合预期。
- 真实状态变化事件（id ≤ 28522）保留完整，历史可审计。

---

## 4. 回滚预案（未触发）

```bash
git revert 14229b5 --no-edit && git push
plink ... "cd /home/yangyang/Freeark/FreeArk && git pull && sudo systemctl restart freeark-mqtt-consumer"
```

回滚后 `_update_connection_status()` 恢复原始 `select_for_update()` 实现，
`_conn_status_cache` 随进程消亡，`PLCConnectionStatus` / `PLCStatusChangeHistory` 数据无损。

---

## 5. 后续观察建议

- 建议运行 1-2 天后复查 `PLCStatusChangeHistory`，确认真实上下线事件记录无遗漏。
- 可在低峰期临时将 `mqtt_handlers` logger 调至 DEBUG，确认日志中"快路径（无状态变化）"
  出现，直接佐证缓存命中；常态下保持 production root = ERROR。
```
