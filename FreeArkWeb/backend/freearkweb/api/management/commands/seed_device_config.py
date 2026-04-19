"""
Management command: seed_device_config
用途：初始化暖通系统的 DeviceConfig 元数据（param_name -> group/sub_type 映射）

用法：
  python manage.py seed_device_config           # 创建缺失条目，跳过已存在
  python manage.py seed_device_config --reset   # 先删除全部再重建

设计说明：
  每条 DeviceConfig 记录定义"某个 PLC 参数名（param_name）属于哪个 group/sub_type"。
  param_name 与 PLCLatestData.param_name 对应（来自 plc_config.json）。
  前端通过 specific_part（住宅专有部分标识）查询 PLCLatestData，
  再用 DeviceConfig 将每个参数归入对应的 group/sub_type 进行分组展示。
"""

from django.core.management.base import BaseCommand
from api.models import DeviceConfig

# 每条记录：param_name（唯一，来自 plc_config.json） -> group/sub_type/display_name
HVAC_PARAM_CONFIGS = [
    # ── 主温控器：系统级控制参数 ──────────────────────────────────────────
    {
        'param_name': 'operation_mode',
        'display_name': '运行模式',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控器',
    },
    {
        'param_name': 'system_switch',
        'display_name': '系统开关',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控器',
    },
    {
        'param_name': 'central_energy_supply',
        'display_name': '集中能源供给',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控器',
    },
    {
        'param_name': 'away_energy_saving',
        'display_name': '离家节能标识',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控器',
    },
    {
        'param_name': 'humidification_switch',
        'display_name': '加湿功能开关',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控器',
    },
    {
        'param_name': 'system_air_volume_setting',
        'display_name': '系统风量设置',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控器',
    },
    {
        'param_name': 'humidification_humidity_upper_limit',
        'display_name': '加湿湿度上限',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控器',
    },
    {
        'param_name': 'humidification_humidity_lower_limit',
        'display_name': '加湿湿度下限',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控器',
    },

    # ── 客厅温控面板 ──────────────────────────────────────────────────────
    {
        'param_name': 'living_room_switch',
        'display_name': '客厅开关',
        'group': 'hvac',
        'sub_type': 'panel_living_room',
        'group_display': '暖通',
        'sub_type_display': '客厅温控面板',
    },
    {
        'param_name': 'living_room_temperature',
        'display_name': '客厅实际温度',
        'group': 'hvac',
        'sub_type': 'panel_living_room',
        'group_display': '暖通',
        'sub_type_display': '客厅温控面板',
    },
    {
        'param_name': 'living_room_humidity',
        'display_name': '客厅相对湿度',
        'group': 'hvac',
        'sub_type': 'panel_living_room',
        'group_display': '暖通',
        'sub_type_display': '客厅温控面板',
    },
    {
        'param_name': 'living_room_temp_setting',
        'display_name': '客厅温度设置',
        'group': 'hvac',
        'sub_type': 'panel_living_room',
        'group_display': '暖通',
        'sub_type_display': '客厅温控面板',
    },
    {
        'param_name': 'living_room_ntc_temp',
        'display_name': '客厅NTC传感器温度',
        'group': 'hvac',
        'sub_type': 'panel_living_room',
        'group_display': '暖通',
        'sub_type_display': '客厅温控面板',
    },
    {
        'param_name': 'living_room_dew_point_setting',
        'display_name': '客厅露点温度设置',
        'group': 'hvac',
        'sub_type': 'panel_living_room',
        'group_display': '暖通',
        'sub_type_display': '客厅温控面板',
    },
    {
        'param_name': 'living_room_temp_sensor_error',
        'display_name': '客厅内置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_living_room',
        'group_display': '暖通',
        'sub_type_display': '客厅温控面板',
    },
    {
        'param_name': 'living_room_humidity_sensor_error',
        'display_name': '客厅湿度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_living_room',
        'group_display': '暖通',
        'sub_type_display': '客厅温控面板',
    },
    {
        'param_name': 'living_room_external_temp_sensor_error',
        'display_name': '客厅外置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_living_room',
        'group_display': '暖通',
        'sub_type_display': '客厅温控面板',
    },
    {
        'param_name': 'living_room_condensation_alert',
        'display_name': '客厅凝露提醒',
        'group': 'hvac',
        'sub_type': 'panel_living_room',
        'group_display': '暖通',
        'sub_type_display': '客厅温控面板',
    },
    {
        'param_name': 'living_room_communication_error',
        'display_name': '客厅面板通讯故障',
        'group': 'hvac',
        'sub_type': 'panel_living_room',
        'group_display': '暖通',
        'sub_type_display': '客厅温控面板',
    },

    # ── 主卧/次卧温控面板（bedroom 系列对应三房主卧/四房次卧）─────────────
    {
        'param_name': 'bedroom_switch',
        'display_name': '主卧/次卧开关',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '主卧温控面板',
    },
    {
        'param_name': 'bedroom_temperature',
        'display_name': '主卧/次卧实际温度',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '主卧温控面板',
    },
    {
        'param_name': 'bedroom_humidity',
        'display_name': '主卧/次卧相对湿度',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '主卧温控面板',
    },
    {
        'param_name': 'bedroom_temp_setting',
        'display_name': '主卧/次卧温度设置',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '主卧温控面板',
    },
    {
        'param_name': 'bedroom_ntc_temperature',
        'display_name': '主卧/次卧NTC传感器温度',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '主卧温控面板',
    },
    {
        'param_name': 'bedroom_dew_point_setting',
        'display_name': '主卧/次卧露点温度设置',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '主卧温控面板',
    },
    {
        'param_name': 'bedroom_temp_sensor_error',
        'display_name': '主卧/次卧内置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '主卧温控面板',
    },
    {
        'param_name': 'bedroom_humidity_sensor_error',
        'display_name': '主卧/次卧湿度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '主卧温控面板',
    },
    {
        'param_name': 'bedroom_external_temp_sensor_error',
        'display_name': '主卧/次卧外置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '主卧温控面板',
    },
    {
        'param_name': 'bedroom_condensation_alert',
        'display_name': '主卧/次卧凝露提醒',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '主卧温控面板',
    },
    {
        'param_name': 'bedroom_communication_error',
        'display_name': '主卧/次卧面板通讯故障',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '主卧温控面板',
    },

    # ── 书房温控面板（study_room 系列对应三房次卧/四房书房）─────────────────
    {
        'param_name': 'study_room_switch',
        'display_name': '书房开关',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房温控面板',
    },
    {
        'param_name': 'study_room_temperature',
        'display_name': '书房实际温度',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房温控面板',
    },
    {
        'param_name': 'study_room_humidity',
        'display_name': '书房相对湿度',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房温控面板',
    },
    {
        'param_name': 'study_room_temp_setting',
        'display_name': '书房温度设置',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房温控面板',
    },
    {
        'param_name': 'study_room_ntc_temperature',
        'display_name': '书房NTC传感器温度',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房温控面板',
    },
    {
        'param_name': 'study_room_dew_point_setting',
        'display_name': '书房露点温度设置',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房温控面板',
    },
    {
        'param_name': 'study_room_temp_sensor_error',
        'display_name': '书房内置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房温控面板',
    },
    {
        'param_name': 'study_room_humidity_sensor_error',
        'display_name': '书房湿度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房温控面板',
    },
    {
        'param_name': 'study_room_external_temp_sensor_error',
        'display_name': '书房外置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房温控面板',
    },
    {
        'param_name': 'study_room_condensation_alert',
        'display_name': '书房凝露提醒',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房温控面板',
    },
    {
        'param_name': 'study_room_communication_error',
        'display_name': '书房面板通讯故障',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房温控面板',
    },

    # ── 儿童房温控面板（children_room 系列对应三房儿童房/四房主卧）──────────
    {
        'param_name': 'children_room_switch',
        'display_name': '儿童房开关',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '儿童房温控面板',
    },
    {
        'param_name': 'children_room_temperature',
        'display_name': '儿童房实际温度',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '儿童房温控面板',
    },
    {
        'param_name': 'children_room_humidity',
        'display_name': '儿童房相对湿度',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '儿童房温控面板',
    },
    {
        'param_name': 'children_room_temp_setting',
        'display_name': '儿童房温度设置',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '儿童房温控面板',
    },
    {
        'param_name': 'children_room_ntc_temperature',
        'display_name': '儿童房NTC传感器温度',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '儿童房温控面板',
    },
    {
        'param_name': 'children_room_dew_point_setting',
        'display_name': '儿童房露点温度设置',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '儿童房温控面板',
    },
    {
        'param_name': 'children_room_temp_sensor_error',
        'display_name': '儿童房内置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '儿童房温控面板',
    },
    {
        'param_name': 'children_room_humidity_sensor_error',
        'display_name': '儿童房湿度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '儿童房温控面板',
    },
    {
        'param_name': 'children_room_external_temp_sensor_error',
        'display_name': '儿童房外置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '儿童房温控面板',
    },
    {
        'param_name': 'children_room_condensation_alert',
        'display_name': '儿童房凝露提醒',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '儿童房温控面板',
    },
    {
        'param_name': 'children_room_communication_error',
        'display_name': '儿童房面板通讯故障',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '儿童房温控面板',
    },

    # ── 四房儿童房温控面板 ────────────────────────────────────────────────
    {
        'param_name': 'fourth_children_room_switch',
        'display_name': '四房儿童房开关',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '四房儿童房温控面板',
    },
    {
        'param_name': 'fourth_children_room_temperature',
        'display_name': '四房儿童房实际温度',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '四房儿童房温控面板',
    },
    {
        'param_name': 'fourth_children_room_humidity',
        'display_name': '四房儿童房相对湿度',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '四房儿童房温控面板',
    },
    {
        'param_name': 'fourth_children_room_temp_setting',
        'display_name': '四房儿童房温度设置',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '四房儿童房温控面板',
    },
    {
        'param_name': 'fourth_children_room_ntc_temperature',
        'display_name': '四房儿童房NTC传感器温度',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '四房儿童房温控面板',
    },
    {
        'param_name': 'fourth_children_room_dew_point_setting',
        'display_name': '四房儿童房露点温度设置',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '四房儿童房温控面板',
    },
    {
        'param_name': 'fourth_children_room_temp_sensor_error',
        'display_name': '四房儿童房内置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '四房儿童房温控面板',
    },
    {
        'param_name': 'fourth_children_room_humidity_sensor_error',
        'display_name': '四房儿童房湿度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '四房儿童房温控面板',
    },
    {
        'param_name': 'fourth_children_room_external_temp_sensor_error',
        'display_name': '四房儿童房外置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '四房儿童房温控面板',
    },
    {
        'param_name': 'fourth_children_room_condensation_alert',
        'display_name': '四房儿童房凝露提醒',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '四房儿童房温控面板',
    },
    {
        'param_name': 'fourth_children_room_communication_error',
        'display_name': '四房儿童房面板通讯故障',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '四房儿童房温控面板',
    },

    # ── 新风 ──────────────────────────────────────────────────────────────
    {
        'param_name': 'fresh_air_valve_opening',
        'display_name': '新风机一次阀门开度',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'fan_speed',
        'display_name': '风机转速',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'fan_gear_feedback',
        'display_name': '风机档位反馈',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'filter_alarm_hours_setting',
        'display_name': '滤网报警小时数设置',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'filter_used_hours',
        'display_name': '滤网使用小时数',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'supply_air_temp_setting',
        'display_name': '出风温度设定',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'coil_supply_air_temp',
        'display_name': '过盘管出风温度',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'fresh_air_inlet_temp',
        'display_name': '新风入口温度',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'coil_inlet_temp',
        'display_name': '盘管进水温度',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'coil_outlet_temp',
        'display_name': '盘管出水温度',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'pm25',
        'display_name': 'PM2.5',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'co2',
        'display_name': 'CO2',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'fresh_air_fault_status',
        'display_name': '新风机故障状态',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'fresh_air_unit_stop_error',
        'display_name': '新风机停机故障',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'fresh_air_unit_communication_error',
        'display_name': '新风机通信故障',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'air_quality_sensor_communication_error',
        'display_name': '空气品质传感器通讯故障',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },

    # ── 水力模块 ──────────────────────────────────────────────────────────
    {
        'param_name': 'hydraulic_module_outlet_temp',
        'display_name': '二次水出水温度',
        'group': 'hvac',
        'sub_type': 'hydraulic_module',
        'group_display': '暖通',
        'sub_type_display': '水力模块',
    },
    {
        'param_name': 'hydraulic_module_inlet_temp',
        'display_name': '二次水进水温度',
        'group': 'hvac',
        'sub_type': 'hydraulic_module',
        'group_display': '暖通',
        'sub_type_display': '水力模块',
    },
    {
        'param_name': 'hydraulic_module_valve_opening',
        'display_name': '一次阀门开度',
        'group': 'hvac',
        'sub_type': 'hydraulic_module',
        'group_display': '暖通',
        'sub_type_display': '水力模块',
    },
    {
        'param_name': 'hydraulic_module_low_temp_error',
        'display_name': '水力模块低温故障',
        'group': 'hvac',
        'sub_type': 'hydraulic_module',
        'group_display': '暖通',
        'sub_type_display': '水力模块',
    },

    # ── 能耗表 ────────────────────────────────────────────────────────────
    {
        'param_name': 'total_hot_quantity',
        'display_name': '累计制热量',
        'group': 'hvac',
        'sub_type': 'energy_meter',
        'group_display': '暖通',
        'sub_type_display': '能耗表',
    },
    {
        'param_name': 'total_cold_quantity',
        'display_name': '累计制冷量',
        'group': 'hvac',
        'sub_type': 'energy_meter',
        'group_display': '暖通',
        'sub_type_display': '能耗表',
    },
    {
        'param_name': 'work_time',
        'display_name': '工作时间',
        'group': 'hvac',
        'sub_type': 'energy_meter',
        'group_display': '暖通',
        'sub_type_display': '能耗表',
    },
    {
        'param_name': 'energy_meter_status_communication_error',
        'display_name': '能耗表状态及通讯故障',
        'group': 'hvac',
        'sub_type': 'energy_meter',
        'group_display': '暖通',
        'sub_type_display': '能耗表',
    },
]


class Command(BaseCommand):
    help = '初始化暖通参数 DeviceConfig 元数据（param_name -> group/sub_type 映射）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='先删除全部 DeviceConfig 记录再重建（谨慎使用）',
        )

    def handle(self, *args, **options):
        if options['reset']:
            deleted, _ = DeviceConfig.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'已删除 {deleted} 条 DeviceConfig 记录'))

        created_count = 0
        skipped_count = 0

        for cfg in HVAC_PARAM_CONFIGS:
            obj, created = DeviceConfig.objects.get_or_create(
                param_name=cfg['param_name'],
                defaults={
                    'display_name': cfg['display_name'],
                    'group': cfg['group'],
                    'sub_type': cfg['sub_type'],
                    'group_display': cfg['group_display'],
                    'sub_type_display': cfg['sub_type_display'],
                    'is_active': True,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(
                    f'  [created] {cfg["param_name"]} -> {cfg["sub_type"]} ({cfg["display_name"]})'
                )
            else:
                skipped_count += 1
                self.stdout.write(f'  [skipped] {cfg["param_name"]} already exists')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone: created {created_count}, skipped {skipped_count}'
        ))
        self.stdout.write(self.style.WARNING(
            '\n注意：DeviceConfig 定义的是 param_name -> sub_type 的分组映射，'
            '与 PLCLatestData.param_name 对应。'
            '前端需通过 specific_part 参数指定住宅单元，API 才能返回对应数据。'
        ))
