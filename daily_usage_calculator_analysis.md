# daily_usage_calculator 分析报告

## 1. 概述

本文档分析了 FreeArkWeb 项目中 `daily_usage_calculator` 的工作原理、systemctl 配置，以及 `usage_quantity_daily` 表中 `final_energy` 字段为空的原因和影响。

## 2. daily_usage_calculator 工作原理

### 2.1 核心功能

`daily_usage_calculator` 是一个每日用量计算工具类，主要功能包括：

1. 从 `PLCData` 表中获取指定日期的数据
2. 按照 `specific_part` 和 `energy_mode` 分组，计算每日能源使用量
3. 在 `usage_quantity_daily` 表中创建或更新当日记录
4. 创建次日记录，将当日最晚上报值设置为次日初始值

### 2.2 关键代码分析

#### 2.2.1 数据处理流程

```python
# 从 PLCData 表获取指定日期的数据
latest_records_qs = PLCData.objects.filter(
    usage_date=target_date_value
).select_related()

# 批量处理每条记录
for latest_record in batch:
    specific_part = latest_record.specific_part
    energy_mode = latest_record.energy_mode
    final_energy = latest_record.value
    
    # 处理当日记录
    if key in current_day_records_map:
        # 更新现有记录
        daily_record = current_day_records_map[key]
        daily_record.final_energy = final_energy
        daily_record.usage_quantity = final_energy - daily_record.initial_energy
        daily_records_to_update.append(daily_record)
    else:
        # 创建新记录
        daily_records_to_create.append(UsageQuantityDaily(
            time_period=target_date_value,
            specific_part=specific_part,
            energy_mode=mode_display,
            building=building,
            unit=unit,
            room_number=room_number,
            initial_energy=final_energy,
            final_energy=final_energy,
            usage_quantity=0
        ))
    
    # 处理次日记录
    if key in next_day_records_map:
        # 更新现有记录
        next_record = next_day_records_map[key]
        if not next_record.initial_energy:
            next_record.initial_energy = final_energy
            next_record.final_energy = None
            next_record.usage_quantity = None
            next_day_records_to_update.append(next_record)
    else:
        # 创建次日新记录
        next_day_records_to_create.append(UsageQuantityDaily(
            time_period=next_day,
            specific_part=specific_part,
            energy_mode=mode_display,
            building=building,
            unit=unit,
            room_number=room_number,
            initial_energy=final_energy,
            final_energy=None,
            usage_quantity=None
        ))
```

#### 2.2.2 final_energy 为空的原因

从代码中可以看出，`final_energy` 为空的情况是在处理次日记录时设置的。具体来说：

1. 当创建或更新次日记录时，会将 `final_energy` 字段设置为 `None`
2. 这是设计上的预期行为，因为次日的 `final_energy` 要等到次日结束后才能从 `PLCData` 表中获取
3. 同时，`usage_quantity` 也会被设置为 `None`，因为它是通过 `final_energy - initial_energy` 计算得出的

## 3. systemctl 配置

### 3.1 每日用量计算服务

| 服务名称 | 执行脚本 | 功能描述 | 默认运行时间 |
|---------|---------|---------|------------|
| daily_usage_service | daily_usage_service.py | 计算每日能源用量 | 每天凌晨00:00 |

### 3.2 每月用量计算服务

| 服务名称 | 执行脚本 | 功能描述 | 默认运行时间 |
|---------|---------|---------|------------|
| monthly_usage_service | monthly_usage_service.py | 计算每月能源用量 | 每月1号凌晨00:00 |

## 4. 月度用量计算分析

### 4.1 核心逻辑

月度用量计算服务 (`monthly_usage_calculator`) 从 `usage_quantity_daily` 表聚合数据，计算每月能源用量。关键代码如下：

```python
# 从 daily 表聚合数据
aggregated_data = UsageQuantityDaily.objects.filter(
    time_period__gte=month_start,
    time_period__lt=next_month_start
).values('specific_part', 'building', 'unit', 'room_number', 'energy_mode').annotate(
    min_initial_energy=Min('initial_energy'),
    max_final_energy=Max('final_energy')
)

# 计算月度用量
total_quantity = final_energy - initial_energy
```

### 4.2 对空 final_energy 的处理

当 `final_energy` 为 `None` 时，代码中做了处理：

```python
initial_energy = record['min_initial_energy'] or 0
final_energy = record['max_final_energy'] or 0
total_quantity = final_energy - initial_energy
```

这里使用 `or 0` 来处理 `None` 值，确保计算不会直接报错。

### 4.3 潜在问题

虽然月度计算不会直接报错，但存在以下潜在问题：

1. **数据不准确**：如果某个月的记录中存在大量 `final_energy` 为 `None` 的情况，`Max('final_energy')` 可能会返回 `None`，导致最终计算出的月度用量为 `0 - initial_energy`，产生负数，不符合实际情况。

2. **逻辑不合理**：月度计算使用 `Min('initial_energy')` 和 `Max('final_energy')` 来计算用量，这假设了能源使用是持续累积的。但如果 `final_energy` 为空，说明数据不完整，此时计算出的月度用量可能不准确。

3. **业务影响**：不准确的月度用量数据可能会影响用户账单计算、能耗分析等业务功能。

## 5. 解决方案建议

### 5.1 短期解决方案

1. **优化月度计算逻辑**：在月度计算时，增加对数据完整性的检查。如果某个月份的记录中存在大量 `final_energy` 为空的情况，应该跳过该月份的计算，或者给出警告。

2. **增加数据质量监控**：添加监控机制，定期检查 `usage_quantity_daily` 表中 `final_energy` 为空的记录数量，当比例超过阈值时发出告警。

### 5.2 长期解决方案

1. **完善数据采集机制**：确保 `PLCData` 表能够及时、完整地采集到所有设备的能源数据。

2. **优化每日计算逻辑**：考虑增加重试机制，对于计算失败或数据不完整的记录，在后续时间再次尝试计算。

3. **改进数据模型设计**：考虑在 `usage_quantity_daily` 表中添加数据状态字段，标识记录是否为完整数据，方便后续计算和查询。

## 6. 结论

1. `usage_quantity_daily` 表中 `final_energy` 为空是设计上的预期行为，是每日计算服务在创建次日记录时设置的。

2. 月度用量计算服务对空 `final_energy` 做了处理，不会直接报错，但可能导致计算结果不准确。

3. 建议优化月度计算逻辑，增加数据完整性检查，同时完善数据采集机制，确保能源数据的完整性和准确性。

4. 系统ctl 配置合理，每日和每月计算服务分别在合适的时间运行，能够满足业务需求。