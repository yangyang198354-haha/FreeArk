# 模块设计文档 — v0.5.5 ConnectionStatusHandler 行锁路径优化

```
file_header:
  document_id: MOD-v0.5.5
  title: MQTT 采集链路性能优化 P2 — ConnectionStatusHandler 行锁路径优化 — 模块设计文档
  author_agent: sub_agent_system_architect (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.5.5
  created_at: 2026-05-21
  status: CONFIRMED
  references:
    - docs/architecture/architecture_design_v0.5.5_connection_status_lock_opt.md
    - docs/requirements/v0.5.5_connection_status_lock_opt/requirements_spec.md
    - FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py (ConnectionStatusHandler, 452-594)
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-21 | 初始草稿，基于 ADR-001 方案 A（推荐方案），含方案 B 备用设计 |
| 1.0.0-CONFIRMED | 2026-05-21 | 用户确认方案 A。§1.3 方案 A 为最终实现，§1.4 方案 B 保留为备用记录（不实施）。模块设计锁定，进入开发。 |

---

## 1. 变更目标模块：`mqtt_handlers.py` — `ConnectionStatusHandler`

### 1.1 变更范围

**文件**：`FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py`

**受影响区域**：
1. 模块级常量区（约第 596-620 行）：新增 `_conn_status_cache` 缓存（方案 A）
2. `ConnectionStatusHandler._update_connection_status()` 方法（约第 528-593 行）：全面重写，实现快/慢路径分离

**不受影响区域**（明确保持不变）：
- `ConnectionStatusHandler.handle()` 方法（约第 455-497 行）：调用接口不变
- `ConnectionStatusHandler._parse_building_info()` 方法（约第 499-526 行）：不变
- `PLCDataHandler` 类（完整）：不变
- `PLCLatestDataHandler` 类（完整）：不变
- `_ENERGY_PARAM_NAMES`、`_general_hist_last_hour`、`_energy_hist_last_hour`、`_TIMESTAMP_FORMATS` 等既有模块常量：不变
- `PLCConnectionStatus`、`PLCStatusChangeHistory` 模型定义：不变，无 migration
- `mqtt_consumer.py`、`models.py` 等其他文件：不变

---

### 1.2 新增模块级常量：`_conn_status_cache`（方案 A）

**位置**：在 `_energy_hist_last_hour` 定义之后，`_TIMESTAMP_FORMATS` 之前（约第 613 行之后）。

**设计意图**：维护进程内已知的设备连接状态，用于在正常运行期间（状态无变化）跳过 `select_for_update()` 行锁，走轻量的快路径。

```python
# [P2 新增] ConnectionStatus 进程内状态缓存。
# key: specific_part (str) → last_known_status: str ('online' | 'offline')
#
# 用途：避免在设备状态无变化时重复执行 select_for_update() 行锁。
#   - 缓存命中且值与当前 status 一致 → 走快路径（QuerySet.update 或零写入）
#   - 缓存 miss 或值与 status 不一致 → 走慢路径（保留原有行锁事务语义）
#
# 线程安全：依赖 CPython GIL 保证单次 dict get/set 的原子性。
#   极端情况（两个 worker 同时 cache miss）：两者均进入慢路径，
#   后进入者在 select_for_update 处等待行锁，行为与优化前完全一致。
#
# 内存：约 568 设备 × ~60 bytes ≈ 34KB，可忽略。
# 持久化：仅进程内有效，服务重启后清空，首批消息走慢路径后自动重建。
_conn_status_cache: dict = {}
```

---

### 1.3 修改方法：`ConnectionStatusHandler._update_connection_status()`

#### 修改前（当前实现）

```python
def _update_connection_status(self, specific_part, status, building, unit, room_number):
    """更新设备连接状态"""
    logger.debug(f"ConnectionStatusHandler: 更新连接状态 - specific_part={specific_part}, status={status}")

    try:
        with transaction.atomic():
            plc_status, created = PLCConnectionStatus.objects.select_for_update().get_or_create(
                specific_part=specific_part,
                defaults={
                    'connection_status': status,
                    'building': building,
                    'unit': unit,
                    'room_number': room_number
                }
            )

            status_changed = False
            old_status = None

            if created:
                status_changed = True
                logger.debug(f"ConnectionStatusHandler: ✅ 新建连接状态记录 - {specific_part}: {status}")
            else:
                old_status = plc_status.connection_status
                if old_status != status:
                    status_changed = True
                    logger.debug(f"ConnectionStatusHandler: ✅ 状态发生变化 - {specific_part}: {old_status} -> {status}")

            if status_changed:
                try:
                    PLCStatusChangeHistory.objects.create(
                        specific_part=specific_part,
                        status=status,
                        building=building,
                        unit=unit,
                        room_number=room_number,
                        source='mqtt'
                    )
                    logger.debug(f"ConnectionStatusHandler: ✅ 记录状态变化历史成功 - {specific_part}: {status}")
                except Exception as e:
                    logger.error(f"ConnectionStatusHandler: ❌ 记录状态变化历史失败 - {specific_part}: {e}")

            if not created:
                plc_status.connection_status = status
                plc_status.building = building
                plc_status.unit = unit
                plc_status.room_number = room_number

            if status == 'online':
                plc_status.last_online_time = timezone.now()

            plc_status.save()
            logger.debug(f"ConnectionStatusHandler: ✅ 更新连接状态成功 - {specific_part}: {status}")

    except Exception as e:
        logger.error(f"ConnectionStatusHandler: 更新连接状态失败 - {specific_part}: {e}", exc_info=True)
```

#### 修改后（方案 A — 进程内缓存 + 快/慢路径分离）

```python
def _update_connection_status(self, specific_part, status, building, unit, room_number):
    """更新设备连接状态。

    [P2] 快/慢路径分离，消除正常运行期间的 select_for_update() 行锁：

    快路径（缓存命中且状态一致）：
      - status='online' → QuerySet.update(last_online_time=now())，无行锁，约 5-15ms
      - status='offline' → 完全跳过，零 DB 写入，约 0ms

    慢路径（缓存 miss 或状态变化）：
      - 保留原有 transaction.atomic() + select_for_update() 语义
      - 保证 PLCStatusChangeHistory 写入的原子性
      - 事务提交后更新 _conn_status_cache

    一致性保证：
      - PLCStatusChangeHistory 不漏记：慢路径的行锁保证只有一个 worker 写入变更历史
      - _conn_status_cache 仅在事务提交后更新，不存在"缓存更新成功但事务回滚"的不一致
    """
    cached = _conn_status_cache.get(specific_part)

    # ── 快路径：状态无变化，跳过行锁事务 ────────────────────────────────────
    if cached == status:
        if status == 'online':
            # 仅更新 last_online_time，无事务，无行锁
            PLCConnectionStatus.objects.filter(
                specific_part=specific_part
            ).update(last_online_time=timezone.now())
        # status == 'offline' 且无变化：零 DB 写入，直接返回
        logger.debug(
            f"ConnectionStatusHandler: 快路径（无状态变化）- {specific_part}: {status}"
        )
        return

    # ── 慢路径：缓存 miss 或状态变化，走完整行锁事务 ────────────────────────
    logger.debug(
        f"ConnectionStatusHandler: 慢路径（缓存={cached!r} → status={status!r}）- {specific_part}"
    )
    try:
        with transaction.atomic():
            plc_status, created = PLCConnectionStatus.objects.select_for_update().get_or_create(
                specific_part=specific_part,
                defaults={
                    'connection_status': status,
                    'building': building,
                    'unit': unit,
                    'room_number': room_number,
                }
            )

            if created:
                # 新设备首次出现
                logger.debug(
                    f"ConnectionStatusHandler: ✅ 新建连接状态记录 - {specific_part}: {status}"
                )
                status_changed = True
            else:
                old_status = plc_status.connection_status
                status_changed = (old_status != status)
                if status_changed:
                    logger.debug(
                        f"ConnectionStatusHandler: ✅ 状态变化 - {specific_part}: {old_status} -> {status}"
                    )

            # 状态变化（含新建）：写入变更历史
            if status_changed:
                try:
                    PLCStatusChangeHistory.objects.create(
                        specific_part=specific_part,
                        status=status,
                        building=building,
                        unit=unit,
                        room_number=room_number,
                        source='mqtt',
                    )
                    logger.debug(
                        f"ConnectionStatusHandler: ✅ 状态变化历史记录成功 - {specific_part}: {status}"
                    )
                except Exception as e:
                    logger.error(
                        f"ConnectionStatusHandler: ❌ 状态变化历史记录失败 - {specific_part}: {e}"
                    )

            # 更新 PLCConnectionStatus 行（仅在 get_or_create 命中已有行时）
            if not created:
                if status_changed:
                    # 全字段更新
                    plc_status.connection_status = status
                    plc_status.building = building
                    plc_status.unit = unit
                    plc_status.room_number = room_number
                    if status == 'online':
                        plc_status.last_online_time = timezone.now()
                    plc_status.save()
                else:
                    # 并发竞争：两 worker 同时 cache miss，本 worker 后进入，
                    # 发现状态已同步（与 select_for_update 前的判断吻合）
                    # 仅在需要时更新 last_online_time
                    if status == 'online':
                        plc_status.last_online_time = timezone.now()
                        plc_status.save(update_fields=['last_online_time'])
                    logger.debug(
                        f"ConnectionStatusHandler: 慢路径-并发无变化 - {specific_part}: {status}"
                    )
            else:
                # created=True：get_or_create 的 INSERT 已写入初始字段
                # 若 status='online'，补写 last_online_time
                if status == 'online':
                    plc_status.last_online_time = timezone.now()
                    plc_status.save(update_fields=['last_online_time'])

        # 事务提交成功后更新缓存（放在 with 块外，确保事务已提交）
        _conn_status_cache[specific_part] = status
        logger.debug(
            f"ConnectionStatusHandler: ✅ 慢路径完成，缓存更新 - {specific_part}: {status}"
        )

    except Exception as e:
        logger.error(
            f"ConnectionStatusHandler: 更新连接状态失败 - {specific_part}: {e}", exc_info=True
        )
        # 注意：异常时不更新缓存，保留缓存 miss 状态，
        # 下次调用仍走慢路径，保证下次有机会重试数据库操作
```

---

### 1.4 方案 B（备用 — 保留行锁，仅优化 save 路径）

> 若架构评审后用户选择方案 B，以下为最终实现代码。方案 B 无需新增模块级常量。

```python
def _update_connection_status(self, specific_part, status, building, unit, room_number):
    """更新设备连接状态。

    [P2-方案B] 保留 select_for_update() 行锁，但优化无变化时的 save() 路径：
      - 状态无变化 + online：save(update_fields=['last_online_time']) 最小化 UPDATE
      - 状态无变化 + offline：完全跳过 save()，零额外写入
      - 状态变化或新建：原有全字段逻辑不变
    """
    logger.debug(
        f"ConnectionStatusHandler: 更新连接状态 - specific_part={specific_part}, status={status}"
    )
    try:
        with transaction.atomic():
            plc_status, created = PLCConnectionStatus.objects.select_for_update().get_or_create(
                specific_part=specific_part,
                defaults={
                    'connection_status': status,
                    'building': building,
                    'unit': unit,
                    'room_number': room_number,
                }
            )

            if created:
                logger.debug(
                    f"ConnectionStatusHandler: ✅ 新建连接状态记录 - {specific_part}: {status}"
                )
                PLCStatusChangeHistory.objects.create(
                    specific_part=specific_part, status=status,
                    building=building, unit=unit, room_number=room_number, source='mqtt',
                )
                if status == 'online':
                    plc_status.last_online_time = timezone.now()
                    plc_status.save(update_fields=['last_online_time'])
            else:
                old_status = plc_status.connection_status
                if old_status != status:
                    logger.debug(
                        f"ConnectionStatusHandler: ✅ 状态变化 - {specific_part}: {old_status} -> {status}"
                    )
                    PLCStatusChangeHistory.objects.create(
                        specific_part=specific_part, status=status,
                        building=building, unit=unit, room_number=room_number, source='mqtt',
                    )
                    plc_status.connection_status = status
                    plc_status.building = building
                    plc_status.unit = unit
                    plc_status.room_number = room_number
                    if status == 'online':
                        plc_status.last_online_time = timezone.now()
                    plc_status.save()
                else:
                    # 状态无变化：最小化写入
                    if status == 'online':
                        plc_status.last_online_time = timezone.now()
                        plc_status.save(update_fields=['last_online_time'])
                    # status == 'offline' 且无变化：跳过 save()
                    logger.debug(
                        f"ConnectionStatusHandler: 无状态变化，最小化写入 - {specific_part}: {status}"
                    )

            logger.debug(
                f"ConnectionStatusHandler: ✅ 更新连接状态成功 - {specific_part}: {status}"
            )
    except Exception as e:
        logger.error(
            f"ConnectionStatusHandler: 更新连接状态失败 - {specific_part}: {e}", exc_info=True
        )
```

---

### 1.5 变更影响矩阵

| 调用路径 | 变更影响 | 说明 |
|---------|---------|------|
| `ConnectionStatusHandler.handle()` | 无变更 | 调用接口 `_update_connection_status(...)` 签名不变 |
| `PLCDataHandler.handle()` | 无变更 | 完全独立，不受影响 |
| `PLCLatestDataHandler.handle()` | 无变更 | 完全独立，不受影响 |
| `PLCConnectionStatus.objects.select_for_update()` | 快路径下不调用，慢路径保留 | 正常运行期间行锁消除 |
| `PLCStatusChangeHistory.objects.create()` | 行为语义不变，仅在状态变化时调用 | 状态变化检测逻辑完整保留 |
| `PLCConnectionStatus.objects.filter(...).update(...)` | 新增（快路径，方案 A） | 仅 `status='online'` 时更新 `last_online_time` |
| `_conn_status_cache` | 新增模块级缓存（方案 A） | 进程内有效，重启后清空 |

---

## 2. 测试要点（供测试工程师参考）

### 2.1 单元测试关键用例（方案 A）

| 用例编号 | 场景 | 测试方法 | 预期结果 |
|---------|------|---------|---------|
| T-P2-01 | 新设备首次调用（缓存 miss，created=True） | 清空 `_conn_status_cache`，清空两张表，调用 `_update_connection_status('新设备', 'online', ...)` | `PLCConnectionStatus` 新增一行；`PLCStatusChangeHistory` 新增一行（`status='online'`）；`_conn_status_cache['新设备'] == 'online'` |
| T-P2-02 | 同设备第二次调用，状态无变化（online→online，快路径） | 先建立缓存，再调用同 `status='online'` | `PLCStatusChangeHistory` 不新增；`PLCConnectionStatus.last_online_time` 更新；DB 无 SELECT FOR UPDATE |
| T-P2-03 | 同设备调用，状态无变化（offline→offline，快路径） | 先建立缓存（offline），再调用 `status='offline'` | `PLCStatusChangeHistory` 不新增；`PLCConnectionStatus` 无任何 UPDATE；零 DB 写入 |
| T-P2-04 | 状态变化（online→offline，慢路径） | 先建立缓存（online），再调用 `status='offline'` | `PLCStatusChangeHistory` 新增一行（`status='offline'`）；`PLCConnectionStatus.connection_status` 更新为 `offline`；`_conn_status_cache['设备'] == 'offline'` |
| T-P2-05 | 状态变化（offline→online，慢路径） | 先建立缓存（offline），再调用 `status='online'` | `PLCStatusChangeHistory` 新增一行（`status='online'`）；`PLCConnectionStatus` 更新；`last_online_time` 推进 |
| T-P2-06 | 服务重启模拟（缓存清空后全量慢路径） | 清空 `_conn_status_cache`，对已有设备调用 | 走慢路径；若状态未变化（DB 中已有相同 status），不写 `PLCStatusChangeHistory`；缓存重建 |
| T-P2-07 | SQLite 环境下全部用例 | 上述 T-P2-01~06 在 SQLite 测试库运行 | 所有 assert 通过，无 `DatabaseError` 或 SQLite 兼容异常 |
| T-P2-08 | 异常处理：DB 写入失败时缓存不更新 | mock `PLCConnectionStatus.objects.select_for_update().get_or_create` 抛异常 | `logger.error` 被调用；`_conn_status_cache` 无该 key（不更新），下次调用仍走慢路径 |

### 2.2 与 P1-1 测试用例的兼容性

P2 不修改 `PLCLatestDataHandler` 及其 `_write_history()`，P1-1 的既有测试用例（`_energy_hist_last_hour` 相关）不受影响，应继续全部通过。

---

## 3. 部署步骤（概要，供 devops 参考）

```bash
# 1. 在开发机器 commit 并 push（包含 mqtt_handlers.py 的变更）
git add FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py
git commit -m "perf(mqtt): P2 — 优化 ConnectionStatusHandler 行锁路径，引入进程内状态缓存 (v0.5.5)"
git push

# 2. 生产服务器拉取代码
plink yangyang@192.168.31.51 -pw <password> \
  "cd /home/yangyang/Freeark/FreeArk && git pull"

# 3. 重启 MQTT 消费服务
plink yangyang@192.168.31.51 -pw <password> \
  "sudo systemctl restart freeark-mqtt-consumer"

# 4. 验证服务状态
plink yangyang@192.168.31.51 -pw <password> \
  "sudo systemctl status freeark-mqtt-consumer"

# 5. 验证效果（约 10 分钟后）
# 在生产 MySQL 执行，验证 PLCStatusChangeHistory 仍在正常记录变化事件：
#   SELECT * FROM plc_status_change_history ORDER BY id DESC LIMIT 10;
# 在 Django 日志中确认"快路径（无状态变化）"日志出现（表明缓存生效）：
#   journalctl -u freeark-mqtt-consumer -n 100 | grep "快路径"
```

### 3.1 回滚

```bash
# 方法一：revert commit（推荐）
# 在开发机本地 revert 后 push，生产 git pull
git revert <P2-commit-hash> --no-edit
git push
plink yangyang@192.168.31.51 -pw <password> \
  "cd /home/yangyang/Freeark/FreeArk && git pull && sudo systemctl restart freeark-mqtt-consumer"
```

**回滚后数据影响**：回滚后 `_update_connection_status()` 恢复原始 `select_for_update()` 实现；`_conn_status_cache` 随进程消亡（无持久化）；`PLCConnectionStatus` 和 `PLCStatusChangeHistory` 表数据完整保留，无数据损失。

---

## 4. 版本间文档继承关系

| 版本 | 特性 | 修改文件 | 服务重启 |
|------|------|---------|---------|
| v0.5.2 | P0-1: dph 清理服务 | 新增 systemd unit | 新增服务 |
| v0.5.4 | P1-1: energy 历史去重 | `mqtt_handlers.py` | `freeark-mqtt-consumer` |
| **v0.5.5** | **P2: ConnectionStatusHandler 行锁优化** | **`mqtt_handlers.py`** | **`freeark-mqtt-consumer`** |
| （未来）P1-2 | worker 分配调整（暂缓） | `mqtt_consumer.py` | `freeark-mqtt-consumer` |
