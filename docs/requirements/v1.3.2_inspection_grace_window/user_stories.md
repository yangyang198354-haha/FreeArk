# 用户故事清单 — v1.3.2 巡检持续存在防抖窗口

**文档编号**: US-AIA-v132-IGW-001
**项目名称**: FreeArk Inspection Agent Grace Window（自治巡检防抖窗口）
**版本**: 1.0.0
**状态**: 🟡 草稿，待用户确认
**创建日期**: 2026-06-22
**关联需求**: REQ-SPEC-AIA-v132-IGW-001

---

## 验收场景总览

| 用户故事   | 覆盖场景            | 优先级     | AC 数 |
|------------|---------------------|------------|-------|
| US-GW-001  | A（未满窗口不认领）、C（满窗口正常认领）、E（计时起点 first_seen_at） | Must Have  | 3 |
| US-GW-002  | B（窗口内恢复永不认领、不建单 — 核心价值）                          | Must Have  | 2 |
| US-GW-003  | D（可配置、默认值、非法回退、范式一致）                            | Must Have  | 4 |
| US-GW-004  | F（行为变更声明、按需巡检不受影响）                                | Must Have  | 2 |
| US-GW-005  | G（最坏延迟量化可知）                                              | Should Have| 1 |
| US-GW-006  | 性能（SQL 层过滤）+ 可观测性（过滤日志）                          | Should Have| 2 |
| US-GW-007  | 孤儿 PENDING 行周期清理标 SKIPPED（OQ-2=B）                       | Must Have  | 2 |

---

## US-GW-001：真实持续故障须熬过防抖窗口才被巡检处置

**As** 运维人员
**I want** 巡检智能体只处置"持续存在满设定时长"的故障/预警
**So that** 真实问题被处置，而短暂事件被自动忽略

**优先级**: Must Have

### 验收标准

**AC-1（场景 A：未满窗口不认领）**
```
Given 一条故障事件于 T0 经 MQTT 上报（first_seen_at=T0，is_active=True，inspection_status=PENDING）
  And 防抖窗口为 10 分钟
When 巡检轮询在 T0+5 分钟运行 _fetch_pending()
Then 该事件不出现在认领结果中（inspection_status 保持 PENDING）
  And 不触发任何巡检决策、不建工单
```

**AC-2（场景 C：满窗口正常认领）**
```
Given 同上一条事件，至 T0+10 分钟仍 is_active=True、inspection_status=PENDING
When 巡检轮询在 T0+10 分钟（或之后）运行 _fetch_pending()
Then 该事件被原子认领为 IN_PROGRESS
  And 进入既有的 process_event 决策九步流程（行为与本期之前完全一致）
```

**AC-3（场景 E：计时起点为 first_seen_at）**
```
Given 防抖窗口为 10 分钟
When 判断一条事件是否达到窗口
Then 用于计时的起点是事件的 first_seen_at（consumer T1 INSERT 时写入的 MQTT 首次上报时间）
  And 不使用 last_seen_at、created_at 或认领时间作为计时起点
```

---

## US-GW-002：窗口内自愈的瞬态抖动绝不被处置（核心价值）

**As** 运维人员
**I want** 像"485 通信故障报错后马上恢复"这类一闪而过的抖动被完全忽略
**So that** 工单列表和 LLM 调用不被瞬态噪声污染

**优先级**: Must Have

### 验收标准

**AC-1（场景 B：窗口内恢复 → 永不认领、不建单）**
```
Given 一条故障事件于 T0 上报（first_seen_at=T0，is_active=True，PENDING）
  And 防抖窗口为 10 分钟
When 该故障于 T0+30 秒恢复（consumer T3 置 is_active=False）
Then 该事件自始至终不被巡检认领
  And 不产生任何工单
  And 不产生任何巡检决策日志（PROCESS_STARTED / DELEGATION_* / WORKORDER_CREATED 均不发生）
```

**AC-2（恢复后即使年龄超窗口也不认领）**
```
Given 上述已恢复事件（is_active=False，PENDING），其 first_seen_at 距今已超过 10 分钟
When 巡检轮询运行 _fetch_pending()
Then 该事件仍不被认领（因 is_active=False 被过滤排除）
```

---

## US-GW-003：管理员可配置防抖窗口时长，默认 10 分钟

**As** 系统管理员
**I want** 通过 .env 调整防抖窗口时长且有合理默认
**So that** 不同抖动特性的现场可独立调参，无需改代码

**优先级**: Must Have

### 验收标准

**AC-1（默认值）**
```
Given 未设置防抖窗口相关环境变量
When 巡检智能体启动并读取窗口配置
Then 窗口时长 = 10 分钟（600 秒）
```

**AC-2（合法配置生效）**
```
Given 环境变量 INSPECTION_GRACE_WINDOW_SECONDS 设为合法正整数（如 300）
When 读取窗口配置
Then 窗口时长 = 该值（300 秒 = 5 分钟）
```

**AC-3（非法值回退默认）**
```
Given 环境变量设为非法值（空字符串 / 非数字 / 0 / 负数）
When 读取窗口配置
Then 窗口时长回退为默认 600 秒
  And 记录一条 WARNING 日志说明已回退默认
```

**AC-4（配置范式一致）**
```
Given 现有 get_poll_interval() / get_decision_timeout() 的实现范式
When 实现窗口配置读取函数
Then 沿用同一范式（读环境变量、try/except 解析、≤0 与非法均回退默认）
  And 调参经 .env，无需改代码、无需重新构建前端
```

---

## US-GW-004：行为变更被显式声明，按需巡检不受影响

**As** 部署评审人 / 系统管理员
**I want** 清楚知道本次默认时序行为的变化范围
**So that** 上线后不会误以为"巡检不工作了"

**优先级**: Must Have

### 验收标准

**AC-1（行为变更声明）**
```
Given 本期引入防抖窗口
When 阅读部署文档 / 发布说明
Then 明确记载：自治巡检对事件的处置由"落库后下一轮即可能认领"变为"持续存在满 10 分钟后才认领"
  And 说明真实持续故障的处置会比此前延迟约一个窗口时长
```

**AC-2（按需巡检 v1.3.0 不受影响）**
```
Given 管理员在故障管理/结露预警页面点击「智能体巡检」按钮手动触发某条事件
When 该事件 first_seen_at 距今不足防抖窗口
Then 该手动触发仍立即处置该事件（防抖窗口不作用于按需触发路径）
  And 自治轮询路径与按需触发路径互不干扰
```

---

## US-GW-005：处理延迟可量化、可预期

**As** 运维人员
**I want** 知道引入窗口后真实故障最坏多久会被处置
**So that** 对"为什么这条故障 10 分钟后才建单"有合理预期

**优先级**: Should Have

### 验收标准

**AC-1（最坏延迟量化）**
```
Given 防抖窗口 = W 秒，轮询周期 INSPECTION_POLL_INTERVAL = P 秒
When 一条故障持续存在
Then 其被认领处置的最坏延迟 ≈ W + P（默认 600 + 30 = 630 秒 ≈ 10.5 分钟）
  And 该延迟在需求文档中被明示为预期、可接受
```

---

## US-GW-006：过滤在 DB 层完成且可观测

**As** 开发/运维人员
**I want** 窗口过滤高效且能从日志看出它在工作
**So that** 不因积压事件量增长而性能退化，且现场可核实配置生效

**优先级**: Should Have

### 验收标准

**AC-1（SQL 层过滤）**
```
Given 大量 PENDING 事件积压
When _fetch_pending() 应用窗口门槛
Then 年龄门槛以 SQL WHERE first_seen_at <= ? 条件下推到数据库
  And 不在 Python 层拉取全部 PENDING 后逐条循环判断
```

**AC-2（可观测性）**
```
Given 某轮轮询存在因未达窗口而被跳过的事件
When 查看 journald 巡检日志
Then 能从日志推断窗口正在生效（建议：认领日志附带"未达窗口跳过 N 条"计数或等价信息）
```

## US-GW-007：窗口内恢复的孤儿 PENDING 行被周期清理为 SKIPPED

**As** 系统管理员
**I want** "恢复了却从未被处置"的事件行状态收尾为 SKIPPED 而非长期停在 PENDING
**So that** 按 inspection_status 统计/展示时语义准确，不被"假 PENDING"干扰

**优先级**: Must Have（OQ-2 拍板=B）

### 验收标准

**AC-1（孤儿行被标 SKIPPED）**
```
Given 一条事件 is_active=False 且 inspection_status=PENDING（窗口内恢复、从未被认领）
When 巡检循环执行一轮孤儿行清理
Then 该行 inspection_status 变为 SKIPPED
  And 清理以批量 SQL UPDATE 完成，不在 Python 层逐条循环
```

**AC-2（不误伤活跃事件）**
```
Given 一批事件，部分 is_active=True 且 PENDING（仍在等待/可被认领），部分 is_active=False 且 PENDING
When 执行孤儿行清理
Then 仅 is_active=False 的 PENDING 行被标 SKIPPED
  And 所有 is_active=True 的 PENDING 行状态不变，仍可正常等待或被认领
  And 清理失败不阻断主巡检流程（catch + WARNING，下一轮重试）
```

---

## 开放问题（✅ 已全部拍板 2026-06-22，与需求规格 §4 一致）

- **OQ-1 = A**: 不加高频复发升级规则，每次复发以新 first_seen_at 独立计窗口。
- **OQ-2 = B**: 周期扫描把 is_active=False 且 PENDING 的孤儿行标 SKIPPED（已落为 REQ-FUNC-GW-005 / US-GW-007）。
