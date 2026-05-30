# PLC 在线数量持续走低故障 — 根因分析（生产取证确认版）

**日期**：2026-05-30
**故障现象**：看板"在线 PLC"长期偏低（用户观察约 170，取证时实测 DB online=65），而现场约 80% PLC 已开机。
**历史规律**：重启 freeark-task-scheduler + freeark-mqtt-consumer 后立即恢复。
**本报告状态**：✅ **已通过生产实时取证确认根因**。本结论**推翻**了上一版纯静态分析报告（`plc_online_frozen_root_cause.md`）关于"mqtt-consumer 断连未重连"的猜测——经取证 mqtt-consumer 完全正常。

---

## 一、结论先行（根本原因）

**task-scheduler 的 snap7 PLC 连接缓存（`PLCManager.clients_cache`）会随运行时间累积"半死连接"，且代码无法自愈，只能靠重启进程清空缓存恢复。**

精确机制：

1. `PLCManager` 按 IP 缓存 `PLCReadWriter`（snap7 client），**跨采集轮次复用、从不主动断开**。
2. 运行数小时后，相当一部分缓存连接被 PLC 侧 / 中间网络设备静默断开。本地 TCP socket 仍显示 `ESTABLISHED`，`reader.connected` 仍为 `True`——**操作系统在尝试发送前不知道连接已死**。
3. 下一轮读取时 `PLCReadWriter.connect()` 命中短路分支（`multi_thread_plc_handler.py:51` `if self.connected: return True`），**不做任何存活校验直接返回成功**。
4. 紧接着的 `db_read` 在死 socket 上发送，报错 **`ISO : An error occurred during send TCP : Other Socket error (32)`**（Socket error 32 = EPIPE / Broken pipe）。
5. `read_db_data` 在**同一条死连接**上重试 2 次（`multi_thread_plc_handler.py:111-116`），必然全失败，返回失败结果。
6. **关键缺陷**：读取失败后，热路径 `_read_single_plc_multiple_params` **从不调用 `disconnect()`、从不把 `connected` 置回 False、从不从缓存剔除**。于是这条死连接**永久驻留缓存**，该 PLC 每一轮都重复"短路返回 True → 读取 EPIPE → 失败"，**永远不会恢复**，直到整个进程重启清空 `clients_cache`。

这一条机制完整解释了全部现象（见第四节）。

---

## 二、生产取证证据链

| # | 取证项 | 结果 | 含义 |
|---|--------|------|------|
| 1 | 三服务状态 | 均 active，已运行 19h | 进程都没崩；problem 是运行态退化 |
| 2 | mqtt-consumer→broker:32788 连接 | **ESTABLISHED（pid=2109 fd=5）** | ❌**推翻"mqtt-consumer 断连"假设**：消费端正常 |
| 3 | DB 在线分布 | online=**65**, offline=569；online 的 last_online_time MAX=当前时刻 | 消费/判定/展示链路正常工作；上游供数不足 |
| 4 | 全量 ping 扫描（Pi 本机，eth0 直连 PLC 子网） | 1267 台中 **567 可达** | 网络是通的 |
| 5 | 对 567 可达 PLC 扫 S7 端口 102 | **567 全部 OPEN** | 567 台完全可采集 |
| 6 | **可采(567) vs 在线(65) 的巨大缺口** | **约 502 台可采但没被标在线** | ❌排除网络问题，锁定采集环节 |
| 7 | task-scheduler 持有的 ESTABLISHED:102 连接数 | **567**（与可达数完全一致） | 连接确实都建好了、被缓存复用 |
| 8 | multi_thread_plc_handler.log 实时尾部 | 持续刷 `Socket error (32)` 读取重试 | **死连接上读取失败的实时铁证** |
| 9 | 代码审计 `set_param/RecvTimeout` | 全仓库 0 处 | snap7 无超时，半开连接可长期占用 worker |
| 10 | 代码审计 热路径失败后是否 disconnect | **否**（仅 stop/写订阅器有 disconnect） | 死连接无法被剔除，无法自愈 |

> 时区旁注：`last_online_time` 以本地 CST 朴素时间写入，而 MySQL `NOW()` 返回 UTC（差 8h）。这是一个潜在 bug，但只会"高估在线"，**不是本次掉线的成因**，本次分析已排除其干扰。

---

## 三、真实数据链路（取证修正版）

```
[PLC ×1267]  ── eth0 直连 192.168.1-12.0/24 ──┐
                                              │ S7comm:102（snap7）
[task-scheduler (PID1011)]                    │
  两个调度线程共享同一个 10-worker 线程池 + 同一 clients_cache：
    · energy  组：300s，2 参数(total_hot/cold_quantity)
    · general 组：600s，全部参数（通配）
  每组每轮：为 ~1267 个 IP 各 submit 一个 future
            → as_completed 等【全部】future（future.result(timeout=60) 实为空操作*）
            → 批量结束后才 send_results_to_mqtt 逐设备发布
                                              │ MQTT publish → broker:32788
[mqtt-consumer (PID2109)]  ← 正常，ESTABLISHED，实时消费、写 last_online_time
[plc-connection-monitor]   ← 正常，每 300s 把超 600s 未更新者翻 offline
[Django API COUNT]→[看板]  ← 正常，实时查库无缓存
```

\* `as_completed` 只产出"已完成"的 future，`future.result(timeout=60)` 对已完成 future 立即返回，**该 60s 超时永不生效**，即整个 building 批次**没有总体截止时间**；任一 worker 在死/半开连接上长时间阻塞都会拖慢甚至卡死本轮的"读完→发布"，进一步压低当轮在线增量。

---

## 四、为什么各现象都对得上

- **"重启即恢复"**：重启 task-scheduler → `clients_cache` 清空 → 所有连接重建为新鲜连接 → 读取成功 → 在线数立刻回升。（实际上**只需重启 task-scheduler**；mqtt-consumer 经取证正常，历史上一起重启只是"宁可多重启一个"。）
- **"在线数从 ~170 一路走低到 65"**：连接是**渐进式**变死的——刚重启时大多新鲜（在线高），运行越久死连接越多（在线越低）。这是缓存腐烂的典型时间曲线。
- **"现场 80% 开机却不在线"**：开机/可达（567）≠ 被成功采集（65）。差额就是缓存里那批死连接对应的 PLC。
- **日志只见 ERROR 不见成功**：生产 log_config 全局 ERROR，INFO 成功日志被压制；`multi_thread_plc_handler.log` 只剩失败的 `Socket error(32)`，正好暴露问题。

---

## 五、确定性代码缺陷清单（修复目标）

| 编号 | 位置 | 缺陷 | 后果 |
|------|------|------|------|
| **D1（主因）** | `multi_thread_plc_handler.py:51-53` `connect()` | 缓存连接命中 `self.connected==True` 即短路返回，不校验 socket 存活 | 死连接被当成活连接复用 |
| **D2（主因）** | `_read_single_plc_multiple_params`（约 445-528） | 读取失败后从不 `disconnect()` / 不重置 `connected` / 不剔除缓存 | 死连接永久驻留，PLC 永不恢复 |
| **D3** | `read_db_data:88-116` | 重试在**同一死连接**上进行，未先重连 | 重试对 EPIPE 必然无效，纯浪费 |
| **D4** | 全仓库无 `client.set_param` 超时 | snap7 connect/recv 无超时上限 | 真半开 socket 可长期占用 worker，加剧线程池饥饿 |
| **D5** | `improved_data_collection_manager.py:436-439` | `as_completed`+`future.result(timeout=60)` 不构成总体截止时间 | 单个卡死 future 可阻塞整轮"读完→发布" |
| **D6（结构）** | `task_scheduler.start()` | energy/general 两组共享同一 10-worker 池与同一连接缓存，各自 submit ~1267 任务 | 互相抢占 worker + 共享缓存竞争，放大上述问题 |

---

## 六、处置方案（待用户确认后执行）

### 阶段 0 · 立即缓解（恢复在线数，分钟级）
- **重启 `freeark-task-scheduler`**（清空死连接缓存）。预期在线数在 1~2 个采集周期内回升。
  - mqtt-consumer 经取证正常，**可不重启**；若想与历史操作一致也可一并重启，无害。
  - 风险：低；仅短暂中断一轮采集。回滚：无需（仅重启）。
  - ⚠️ 这是**治标**，不修代码则数小时后会再次走低。

### 阶段 1 · 根因修复（代码，治本）
按优先级：

1. **D1+D2+D3 — 失败即弃连重连（核心修复）**
   - `connect()` 短路前用 `client.get_connected()` 校验真实存活；不活则先 `disconnect()` 再重连。
   - 读取出现 socket/ISO 类错误（含 error 32）时，立即 `reader.disconnect()`（置 `connected=False`），下一轮自然重建；或直接从 `clients_cache` 剔除该 IP。
   - `read_db_data` 重试前先重连，避免在死 socket 上空转。
2. **D4 — 设置 snap7 超时**
   - 在 `PLCReadWriter.__init__`/`connect` 调 `client.set_param`（RecvTimeout/SendTimeout，建议 3~5s），给底层 C 调用兜底，杜绝 worker 永久卡死。
3. **D5 — 真正的轮次截止 + 增量发布**
   - 用 `wait(timeout=...)` 或 future 级 `concurrent.futures.wait` 强制本轮总超时；超时的 IP 标失败并**仍发布已完成结果**，保证 last_online_time 持续推进。
4. **D6 — 资源隔离（可选，进阶）**
   - energy / general 两组各用独立线程池（或独立连接缓存），互不抢占；或加"连接最长寿命"周期性回收（例如 >10min 的连接强制重建）作为纵深防御。

### 阶段 2 · 防回归与可观测性
- 临时把 `multi_thread_plc_handler` / `improved_data_collection` 日志拉到 INFO 跑一轮，确认"成功 N/总数"恢复，再复原为 ERROR。
- 增加"本轮成功采集 PLC 数 / 可达 PLC 数"指标，低于阈值告警（避免再靠肉眼看板发现）。
- 修复 `last_online_time` 时区一致性（统一 UTC 或统一本地），消除潜在判定偏差。

### 验证标准（修复后）
- `Socket error (32)` 重试在日志中基本消失；
- DB online 稳定在"可达数"量级（~560+）且**持续数小时不衰减**；
- `last_online_time` 对 500+ 设备持续推进；
- 连续观察 ≥ 一个工作日不再需要人工重启。

---

## 六之二、阶段 0（重启 task-scheduler）执行结果 —— ⚠️ 重启并未恢复，结论修正

**执行时间**：2026-05-30 18:46（CST），已获用户授权，仅重启 `freeark-task-scheduler`（mqtt-consumer 经取证正常，未动）。

**观测（重启后 ~30min 全程跟踪）**：

| 时点 | online | 关键观测 |
|------|--------|----------|
| 重启前基线 | 65→105 波动 | 退化态 |
| T+1.5min | 108 | 已重建连接 |
| T+4min | 109；持有 **571 条全新 ESTABLISHED:102** | Socket err(32) 短暂消失，换成对死机 PLC 的 Unreachable |
| T+8min | 85；**最近5min 仅 15 台被刷新** | 批量发布未上量 |
| T+12min | 94 | — |
| T+21min | **稳定 94~95，不再上升**；`last_online_time` 每 ~300s 整批跳一次 | energy 周期在跑，但每轮只读成功 ~94 台 |
| T+30min | **Socket error(32) 回潮：最近500行日志 332 行 EPIPE / 168 行 Unreachable** | 新连接在数分钟内重新烂掉 |

**❌ 结论修正：重启 task-scheduler 不是可靠的缓解手段（至少当前规模下不是）。** 它清掉废连接、重建 569 条新连接，但 10 个 worker 来不及在 PLC 空闲超时窗口内轮完 1267 个 IP（叠加 general 组大读取 + ~700 台死机冷连接），新连接在被再次读取前就被 PLC/网络空闲关闭 → 下次读取 EPIPE → 因 D1/D2 短路不校验、失败不弃连而**永久变废**。系统稳定在 ~94（能保持热度的连接数），重启只换来几分钟的"假新鲜"。

### 决定性反证：可达 PLC 在干净连接下 100% 可读
从 Pi 用独立 snap7 进程直接对 30 台随机"可达但离线"的 PLC 读 DB14/offset442（energy 参数）：

```
sample=30  S7_READ_OK=30  FAIL=0
```

**30/30 全部读成功。** 证明这 ~470 台"可达却不在线"的 PLC **不是 PLC 端坏了**，而是 task-scheduler 读不到它们。**真实在线天花板应为 ~560，而非 170 或 94。**"170"本身可能已是长期退化值。

### 由此对处置方案的修正
- **阶段 0 重启降级为"无效/临时"**：不再推荐把重启当常规手段。
- **阶段 1 代码修复从"治本优化"升级为"唯一可行解"**，且优先级最高的是：
  - **D4：给 snap7 设 `set_param` 连接/收发超时**（让冷连接与死 socket 快速失败，释放 worker）；
  - **D1+D2+D3：读取失败即 `disconnect()`+下轮重连/剔除缓存，connect 前校验真实存活，重试前先重连**（杜绝废连接永久驻留）；
  - **D6：energy/general 拆独立线程池**或显著提高 worker 数 / 降低单轮 IP 量，保证每个连接在 PLC 空闲超时内被及时复用（避免被 PLC 空闲关闭）；
  - **D5：单轮总截止 + 增量发布**，避免死机 PLC 冷连接拖垮整轮。
- 仅靠 D1/D2/D3（弃废连重连）可能仍不够——若 worker 轮询太慢，连接会持续被空闲关闭。**D4+D6（超时 + 提速/隔离）才是让在线数稳定到 ~560 的关键。**

## 七、风险与执行纪律
- 阶段 0 重启属生产操作，需用户明确确认后执行。
- 阶段 1 代码改动需走正常流程：本地改 → 推 main → 生产 `git pull`（注意不要碰 `.env`/`package-lock.json`/`heartbeat_broker_config.json`）→ 重启 `freeark-task-scheduler` 验证。
- 全部取证为只读，未对生产做任何变更、未重启任何服务、未改配置。
