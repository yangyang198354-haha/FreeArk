# 生产 Dashboard 接口超时根因分析报告（RCA）

- **日期**：2026-05-20
- **现象**：系统看板「总电量查询 / 今日用电量 / 本月用电量」长时间转圈，随后前端报
  `404 (Not Found)`（`/api/dashboard/total-energy/`、`/api/dashboard/summary/`）与
  `net::ERR_NETWORK_CHANGED`（`/api/dashboard/activities/`），多刷新几次又能成功。
- **调查方式**：plink 经动态域名 `et116374mm892.vicp.fun:57279` 连入生产树莓派，
  实测后端、nginx 日志、生产 MySQL（192.168.31.98）。
- **结论**：**确认是数据库性能问题。** 用户判断正确。

---

## 一、证据链

### 1. nginx 错误日志 —— 不是网络抖动，是后端超时
`/var/log/nginx/error.log` 中持续出现（11:05、11:09、11:13、11:18、11:23、11:29、11:32、11:35……几乎每 3–5 分钟一次）：

```
upstream timed out (110: Connection timed out) while reading response header from upstream,
request: "GET /api/dashboard/total-energy/?start_date=2026-01-01&end_date=2026-05-20"
upstream: "http://192.168.31.51:8000/..."
```

紧接同一请求：
```
open() "/usr/share/nginx/html/50x.html" failed (2: No such file or directory)
```

### 2. 服务器本身空闲 —— 排除树莓派资源 / waitress 线程
- 负载 `0.20 0.24 0.18`，内存可用 3.0 GiB，CPU 占用最高进程 < 2%。
- 直连后端 `curl http://127.0.0.1:8000/...` 返回 401 仅 0.002 s。
- → 树莓派和 waitress 都不是瓶颈。

### 3. 数据库实测 —— 每个操作都慢 10–100 倍
| 操作 | 表 | 耗时 |
|---|---|---|
| `COUNT(*)` | usage_quantity_daily（19.7 万行）| **38.45 s** |
| `SHOW INDEX`（纯元数据）| usage_quantity_daily | **18.52 s** |
| `SELECT SUM ... WHERE time_period = CURDATE()` | usage_quantity_daily | **15.76 s** |
| `SELECT SUM ... WHERE time_period BETWEEN 月初 AND 今天` | usage_quantity_daily | **180 s 客户端超时未完成** |
| `SELECT ... GROUP BY energy_mode`（total-energy）| usage_quantity_daily | **180 s 客户端超时未完成** |
| `COUNT(*) WHERE created_at >= 近1分钟` | device_param_history | **120 s 客户端超时未完成** |

`Slow_queries = 37952`，`Innodb_row_lock_time_avg = 15753 ms`。

### 4. EXPLAIN —— 全表扫描（正常优化器行为，非主因）
```
type: ALL   key: NULL   rows: 196976   Extra: Using where
```
日期范围覆盖全表约 91% 数据，优化器选择全表扫描属正常；扫 19.7 万行小表本不该慢。

### 5. 真凶 —— 表膨胀 + 缓冲池过小
freeark 库各表体积：

| 表 | 行数 | 数据 | 索引 | 合计 |
|---|---|---|---|---|
| **device_param_history** | **36,168,481** | 4623 MB | **6977 MB** | **11600 MB** |
| plc_data | 212,039 | 24.6 MB | 261.5 MB | 286 MB |
| usage_quantity_daily | 196,974 | 35.6 MB | 43.4 MB | 79 MB |
| plc_latest_data | 48,077 | 7.5 MB | 22.6 MB | 30 MB |

InnoDB 配置：
```
innodb_buffer_pool_size = 134217728  (128 MB —— MySQL 默认最小值)
Free buffers = 0 / 994（缓冲池基本占满）
InnoDB 实测磁盘读取 ≈ 24 reads/s × 16KB ≈ 384 KB/s
```

---

## 二、根因链（完整因果）

1. **`device_param_history` 表失控膨胀**到 3617 万行 / 11.6 GB，其中索引 7 GB（索引比数据还大）。
   被 PLC 参数采集高频 INSERT，且**没有清理 / 归档机制**。
2. **`innodb_buffer_pool_size` 仅 128 MB**（MySQL 默认值，从未调优），只能缓存全库约 1%。
3. 二者叠加：每次 INSERT `device_param_history` 都要维护 7 GB 索引 B-tree，
   而索引无法缓存 → 每次写入触发随机磁盘读 + 随机磁盘写 → **磁盘 I/O 被写入风暴打满**。
4. Dashboard 聚合查询要扫 `usage_quantity_daily`（79 MB），但：
   - 它的页不断被 `device_param_history` 写入风暴挤出 128 MB 缓冲池；
   - 磁盘已被随机 I/O 占满，扫描只能以 ~384 KB/s 龟速进行。
   → 单次查询耗时 **100 ~ 180+ 秒**。
5. 查询耗时超过 nginx 默认 `proxy_read_timeout`（60 s）→ nginx 返回 **504**。
6. nginx 配置 `error_page 500 502 503 504 /50x.html;`，但
   `/usr/share/nginx/html/50x.html` **文件不存在** → nginx 回退，最终给浏览器返回 **404**。
   —— 这就是前端控制台看到 `404 (Not Found)` 而非 `504` 的真正原因。
7. **「多刷新几次又能成功」**：偶尔某次查询所需的页恰好仍在缓冲池中，
   或恰好赶上写入风暴的短暂间隙，查询在 60 s 内完成 → 成功。

> `net::ERR_NETWORK_CHANGED`（activities 接口）是独立的次要现象，
> 属客户端网络 / vicp 内网穿透隧道抖动，与本次数据库根因无关。

---

## 三、修复建议（按优先级）

### P0 — 治本：清理 / 归档 device_param_history（核心）
- 删除或归档历史数据，仅保留近 N 天（如 30/90 天）。
- 新增定时清理任务（参考已有 `freeark-plc-cleanup` 服务模式）。
- 评估按时间分区（PARTITION BY RANGE）。
- 复核索引：7 GB 索引 > 4.6 GB 数据，疑有冗余索引可删。
- ⚠️ 直接 `DELETE` 3000 万行会产生巨大 undo / binlog，须分批小步删除，避开业务高峰。

### P0 — 治本：调大 InnoDB 缓冲池
- 先确认 DB 服务器 192.168.31.98 物理内存（本次 SSH 22 端口被拒，未取到 OS 指标）。
- 若内存 ≥ 4 GB，将 `innodb_buffer_pool_size` 调至 1–2 GB（占内存 50%~70%）。
- 修改 my.cnf 后需重启 MySQL。

### P1 — 治标：nginx 配置
- `/api` location 增加 `proxy_read_timeout 120s;`、`proxy_connect_timeout 10s;`。
- 补上 `/usr/share/nginx/html/50x.html`，让超时返回真实 504 + 友好页，
  而非误导性的 404。

### P1 — 优化：Dashboard 接口
- `total-energy`、`summary` 数据每天仅变化一次（凌晨 daily-usage 服务写入），
  适合加 Django 缓存（TTL 5–15 分钟）。
- 「本月 / 总量」可改查已有的预聚合表 `usage_quantity_monthly`（仅 7093 行），
  避免每次扫 `usage_quantity_daily`。

### P2 — 观测
- 开启 MySQL 慢查询日志（`slow_query_log=ON`）持续监控。
- Dashboard 关键指标卡与 `activities` 解耦加载，互不阻塞。

---

## 四、待确认事项
1. DB 服务器 192.168.31.98 的物理内存与磁盘类型（SSH 22 被拒，需另行登录确认）。
2. `device_param_history` 的业务保留期要求（决定清理保留窗口）。
3. 是否已有针对 `device_param_history` 的清理任务（现有 `freeark-plc-cleanup` 覆盖范围待查）。
