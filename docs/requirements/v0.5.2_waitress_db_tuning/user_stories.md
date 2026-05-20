# 用户故事清单

```
file_header:
  document_id: US-V052-WAITRESS-DB-TUNING-001
  title: waitress 线程数与数据库连接调优 — 用户故事
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: 1.0
  created_at: 2026-05-20
  status: DRAFT
  references:
    - docs/requirements/v0.5.2_waitress_db_tuning/requirements_spec.md
    - sdlc/perf_analysis_report.md (APPROVED)
    - sdlc/perf_test_report.md (APPROVED)
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 1.0 | 2026-05-20 | 初始版本，覆盖 REQ-FUNC-001~005 + REQ-NFR-001~005 |

---

## US-001：多用户同时刷新看板时，面板不再转圈归零

**关联需求**：REQ-FUNC-001（waitress threads 可配置）、REQ-NFR-001（并发能力提升）
**优先级**：P0

作为**运维人员**，
我希望**多人同时打开或刷新看板首页时，总电量/今日用电量/本月用电量等面板能正常显示数据**，
以便**我不需要反复刷新、不因「归零」误判设备或系统出现故障**。

### 验收标准（Given / When / Then）

**AC-US001-01：单用户看板 7 个请求无排队**
- Given waitress 已配置 `threads=16`，freeark-backend 服务已重启
- When 一名运维人员打开看板首页（onMounted 同时触发 7 个 dashboard API 请求）
- Then Chrome DevTools Network 面板中，所有 7 个请求的 "Waiting (TTFB)" 时间均 < 100ms（无线程排队等待），面板正常显示数据

**AC-US001-02：两用户同时刷新，面板均正常**
- Given waitress 已配置 `threads=16`
- When 两名运维人员在同一秒内各自刷新看板首页（共 14 个并发请求）
- Then 两名用户的面板均在合理时间（< 5s）内显示数据，无一面板归零

**AC-US001-03：面板归零现象消除**
- Given waitress 已配置 `threads=16`，且生产环境数据正常（有当年/当月/今日用电记录）
- When 运维人员正常使用看板（非网络故障、非 MySQL 宕机场景）
- Then 总电量、今日用电量、本月用电量、PLC 在线率、大屏在线率等面板显示正确数值，不显示 0

---

## US-002：慢请求不永久占用线程，不拖垮其他面板

**关联需求**：REQ-FUNC-002（channel_timeout 可配置）、REQ-NFR-002（超时回收）
**优先级**：P1

作为**系统管理员**，
我希望**单个异常慢请求（如 dashboard_services 卡住某个 systemctl 调用）超时后，其占用的线程能被自动回收**，
以便**该异常不会拖垮其他用户的所有面板请求**。

### 验收标准（Given / When / Then）

**AC-US002-01：异常慢请求在 channel_timeout 内被回收**
- Given waitress 已配置 `channel_timeout=120`
- When 某个请求因 systemctl D-Bus 卡顿或网络异常导致 120 秒未响应
- Then waitress 强制关闭该连接，对应线程被释放回线程池，其他正常请求不受影响

**AC-US002-02：channel_timeout 不影响正常请求**
- Given waitress 已配置 `channel_timeout=120`
- When 正常的看板请求在 5s 内完成
- Then 该请求正常返回 HTTP 200，不被 channel_timeout 打断

---

## US-003：系统管理员可在不修改代码的情况下调整 waitress 参数

**关联需求**：REQ-FUNC-001（环境变量覆盖）、REQ-FUNC-002、REQ-FUNC-003
**优先级**：P1

作为**系统管理员**，
我希望**通过设置环境变量（WAITRESS_THREADS、WAITRESS_CHANNEL_TIMEOUT、WAITRESS_CONNECTION_LIMIT）来调整 waitress 运行参数，而无需修改 Python 源代码**，
以便**我能根据服务器实际负载灵活调整，且调整过程不需要前端或后端开发人员介入**。

### 验收标准（Given / When / Then）

**AC-US003-01：WAITRESS_THREADS 环境变量生效**
- Given 系统管理员在 systemd service 文件中设置 `Environment=WAITRESS_THREADS=8`（例如测试低配置）
- When 执行 `sudo systemctl restart freeark-backend`
- Then waitress 以 8 线程启动（可通过启动日志或 `/proc/<pid>/status` 验证线程数）

**AC-US003-02：未设置环境变量时代码默认值生效**
- Given 环境变量 `WAITRESS_THREADS` 未设置
- When 执行 `sudo systemctl restart freeark-backend`
- Then waitress 以代码默认值 16 线程启动

**AC-US003-03：connection_limit 在高并发攻击场景下保护服务**
- Given waitress 已配置 `connection_limit=100`
- When 外部产生 150 个同时连接（压测模拟）
- Then 前 100 个连接被正常处理，第 101~150 个连接被拒绝（返回 503 或 TCP 拒绝），已有连接不中断

---

## US-004：系统管理员确认 16 线程 MySQL 连接数在安全范围内

**关联需求**：REQ-FUNC-004（CONN_MAX_AGE 配置核实）、REQ-NFR-003（连接稳定性）
**优先级**：P1

作为**系统管理员**，
我希望**在将 waitress 线程数从 4 增加到 16 之前，能看到明确的容量计算文档，证明 16 个持久 MySQL 连接在 MySQL max_connections 安全范围内**，
以便**我能放心实施变更，不担心数据库连接耗尽导致其他服务（如定时任务、MQTT 消费者）无法连接 MySQL**。

### 验收标准（Given / When / Then）

**AC-US004-01：设计文档中有容量计算**
- Given architecture_design.md 已完成
- When 系统管理员查看"线程数与连接数容量计算"章节
- Then 文档中包含：`16（waitress threads）× 1（CONN_MAX_AGE 持久连接/线程）= 16 个 Django 连接`，并与其他服务（MQTT消费者、定时任务等）的连接数估算相加，给出总连接数 ≤ MySQL max_connections（151） 的结论

**AC-US004-02：线程数增加后生产数据库不出现连接耗尽**
- Given waitress 以 16 线程运行
- When 运维人员执行 `SHOW STATUS LIKE 'Threads_connected';`
- Then 显示连接数 ≤ 30（Django 16 + 其他服务估算 ≤ 14），不超过 MySQL max_connections

---

## US-005："Lost Connection" 场景下请求自动重连，不产生用户可见错误

**关联需求**：REQ-FUNC-005（连接健康检查）、REQ-NFR-003
**优先级**：P1

作为**运维人员**，
我希望**当某个 waitress 线程持有的 MySQL 持久连接在空闲期被 MySQL 服务端断开（如超过网络设备 NAT 超时）时，该线程的下一个请求能自动重连，不向用户返回 500 错误**，
以便**用户不会因为后台的 "Lost Connection" 看到面板报错或白屏**。

### 验收标准（Given / When / Then）

**AC-US005-01：连接空闲后首次请求自动重连成功**
- Given waitress 线程持有一个已空闲 > 8 小时的 MySQL 连接（模拟服务器 wait_timeout 或 NAT 断开）
- When 用户刷新看板，该线程收到新请求
- Then Django 检测到连接失效，自动重建连接并成功执行查询，返回 HTTP 200 而非 HTTP 500

**AC-US005-02："Lost Connection" 不产生连续失败**
- Given 某连接已断开
- When 第一次查询失败（Django 重连中）
- Then 第二次查询成功（重连后），用户最多感知到 1 次轻微延迟，不出现连续的面板归零

---

## 用户故事优先级总览

| US编号 | 标题 | 优先级 | 关联需求 |
|--------|------|--------|---------|
| US-001 | 多用户同时刷新看板不归零 | P0 | REQ-FUNC-001, REQ-NFR-001 |
| US-002 | 慢请求不永久占用线程 | P1 | REQ-FUNC-002, REQ-NFR-002 |
| US-003 | 管理员可通过环境变量调整参数 | P1 | REQ-FUNC-001~003 |
| US-004 | 16 线程连接数在安全范围内 | P1 | REQ-FUNC-004, REQ-NFR-003 |
| US-005 | Lost Connection 自动重连 | P1 | REQ-FUNC-005, REQ-NFR-003 |

---

*文档版本: 1.0 | 生成时间: 2026-05-20 | 状态: DRAFT（待门控评审）*
