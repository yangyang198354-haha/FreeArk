"""
Management command: seed_device_config
用途：初始化暖通系统的 DeviceConfig 元数据（param_name -> group/sub_type 映射）

用法：
  python manage.py seed_device_config           # 创建缺失条目，跳过已存在
  python manage.py seed_device_config --reset   # 先删除全部再重建

sub_type 对应关系（三恒系统定义）：
  main_thermostat       → 主温控（客厅面板 + 系统开关）
  panel_study_room      → 书房-温控面板
  panel_bedroom         → 次卧-温控面板
  panel_children_room   → 主卧-温控面板
  panel_fourth_children → 儿童房-温控面板
  fresh_air             → 新风（含加湿参数、风量设置）
  energy_meter          → 能耗表
  hydraulic_module      → 水力模块（含运行模式、节能、集中能源供给）
  air_quality           → 空气品质（CO₂、PM2.5）
"""

from django.core.management.base import BaseCommand
from api.models import DeviceConfig

HVAC_PARAM_CONFIGS = [
    # ── 主温控（客厅温控面板 + 系统级控制） ──────────────────────────────────
    {
        'param_name': 'living_room_ntc_temp',
        'display_name': 'NTC温度',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控',
    },
    {
        'param_name': 'living_room_condensation_alert',
        'display_name': '凝露提醒',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控',
    },
    {
        'param_name': 'living_room_dew_point_setting',
        'display_name': '面板露点温度',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控',
    },
    {
        'param_name': 'living_room_humidity',
        'display_name': '湿度',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控',
    },
    {
        'param_name': 'living_room_switch',
        'display_name': '开关',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控',
    },
    {
        'param_name': 'system_switch',
        'display_name': '系统开关',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控',
    },
    {
        'param_name': 'living_room_temperature',
        'display_name': '温度',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控',
    },
    {
        'param_name': 'living_room_temp_setting',
        'display_name': '设定温度',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控',
    },
    {
        'param_name': 'living_room_temp_sensor_error',
        'display_name': '内置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控',
    },
    {
        'param_name': 'living_room_humidity_sensor_error',
        'display_name': '湿度传感器故障',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控',
    },
    {
        'param_name': 'living_room_external_temp_sensor_error',
        'display_name': '外置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控',
    },
    {
        'param_name': 'living_room_communication_error',
        'display_name': '通讯故障',
        'group': 'hvac',
        'sub_type': 'main_thermostat',
        'group_display': '暖通',
        'sub_type_display': '主温控',
    },

    # ── 书房-温控面板 ──────────────────────────────────────────────────────
    {
        'param_name': 'study_room_ntc_temperature',
        'display_name': 'NTC温度',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房-温控面板',
    },
    {
        'param_name': 'study_room_condensation_alert',
        'display_name': '凝露提醒',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房-温控面板',
    },
    {
        'param_name': 'study_room_dew_point_setting',
        'display_name': '面板露点温度',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房-温控面板',
    },
    {
        'param_name': 'study_room_humidity',
        'display_name': '湿度',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房-温控面板',
    },
    {
        'param_name': 'study_room_switch',
        'display_name': '开关',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房-温控面板',
    },
    {
        'param_name': 'study_room_temperature',
        'display_name': '温度',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房-温控面板',
    },
    {
        'param_name': 'study_room_temp_setting',
        'display_name': '设定温度',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房-温控面板',
    },
    {
        'param_name': 'study_room_temp_sensor_error',
        'display_name': '内置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房-温控面板',
    },
    {
        'param_name': 'study_room_humidity_sensor_error',
        'display_name': '湿度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房-温控面板',
    },
    {
        'param_name': 'study_room_external_temp_sensor_error',
        'display_name': '外置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房-温控面板',
    },
    {
        'param_name': 'study_room_communication_error',
        'display_name': '通讯故障',
        'group': 'hvac',
        'sub_type': 'panel_study_room',
        'group_display': '暖通',
        'sub_type_display': '书房-温控面板',
    },

    # ── 次卧-温控面板 ──────────────────────────────────────────────────────
    {
        'param_name': 'bedroom_ntc_temperature',
        'display_name': 'NTC温度',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '次卧-温控面板',
    },
    {
        'param_name': 'bedroom_condensation_alert',
        'display_name': '凝露提醒',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '次卧-温控面板',
    },
    {
        'param_name': 'bedroom_dew_point_setting',
        'display_name': '面板露点温度',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '次卧-温控面板',
    },
    {
        'param_name': 'bedroom_humidity',
        'display_name': '湿度',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '次卧-温控面板',
    },
    {
        'param_name': 'bedroom_switch',
        'display_name': '开关',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '次卧-温控面板',
    },
    {
        'param_name': 'bedroom_temperature',
        'display_name': '温度',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '次卧-温控面板',
    },
    {
        'param_name': 'bedroom_temp_setting',
        'display_name': '设定温度',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '次卧-温控面板',
    },
    {
        'param_name': 'bedroom_temp_sensor_error',
        'display_name': '内置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '次卧-温控面板',
    },
    {
        'param_name': 'bedroom_humidity_sensor_error',
        'display_name': '湿度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '次卧-温控面板',
    },
    {
        'param_name': 'bedroom_external_temp_sensor_error',
        'display_name': '外置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '次卧-温控面板',
    },
    {
        'param_name': 'bedroom_communication_error',
        'display_name': '通讯故障',
        'group': 'hvac',
        'sub_type': 'panel_bedroom',
        'group_display': '暖通',
        'sub_type_display': '次卧-温控面板',
    },

    # ── 主卧-温控面板 ──────────────────────────────────────────────────────
    {
        'param_name': 'children_room_ntc_temperature',
        'display_name': 'NTC温度',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '主卧-温控面板',
    },
    {
        'param_name': 'children_room_condensation_alert',
        'display_name': '凝露提醒',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '主卧-温控面板',
    },
    {
        'param_name': 'children_room_dew_point_setting',
        'display_name': '面板露点温度',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '主卧-温控面板',
    },
    {
        'param_name': 'children_room_humidity',
        'display_name': '湿度',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '主卧-温控面板',
    },
    {
        'param_name': 'children_room_switch',
        'display_name': '开关',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '主卧-温控面板',
    },
    {
        'param_name': 'children_room_temperature',
        'display_name': '温度',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '主卧-温控面板',
    },
    {
        'param_name': 'children_room_temp_setting',
        'display_name': '设定温度',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '主卧-温控面板',
    },
    {
        'param_name': 'children_room_temp_sensor_error',
        'display_name': '内置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '主卧-温控面板',
    },
    {
        'param_name': 'children_room_humidity_sensor_error',
        'display_name': '湿度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '主卧-温控面板',
    },
    {
        'param_name': 'children_room_external_temp_sensor_error',
        'display_name': '外置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '主卧-温控面板',
    },
    {
        'param_name': 'children_room_communication_error',
        'display_name': '通讯故障',
        'group': 'hvac',
        'sub_type': 'panel_children_room',
        'group_display': '暖通',
        'sub_type_display': '主卧-温控面板',
    },

    # ── 儿童房-温控面板 ────────────────────────────────────────────────────
    {
        'param_name': 'fourth_children_room_ntc_temperature',
        'display_name': 'NTC温度',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '儿童房-温控面板',
    },
    {
        'param_name': 'fourth_children_room_condensation_alert',
        'display_name': '凝露提醒',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '儿童房-温控面板',
    },
    {
        'param_name': 'fourth_children_room_dew_point_setting',
        'display_name': '面板露点温度',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '儿童房-温控面板',
    },
    {
        'param_name': 'fourth_children_room_humidity',
        'display_name': '湿度',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '儿童房-温控面板',
    },
    {
        'param_name': 'fourth_children_room_switch',
        'display_name': '开关',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '儿童房-温控面板',
    },
    {
        'param_name': 'fourth_children_room_temperature',
        'display_name': '温度',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '儿童房-温控面板',
    },
    {
        'param_name': 'fourth_children_room_temp_setting',
        'display_name': '设定温度',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '儿童房-温控面板',
    },
    {
        'param_name': 'fourth_children_room_temp_sensor_error',
        'display_name': '内置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '儿童房-温控面板',
    },
    {
        'param_name': 'fourth_children_room_humidity_sensor_error',
        'display_name': '湿度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '儿童房-温控面板',
    },
    {
        'param_name': 'fourth_children_room_external_temp_sensor_error',
        'display_name': '外置温度传感器故障',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '儿童房-温控面板',
    },
    {
        'param_name': 'fourth_children_room_communication_error',
        'display_name': '通讯故障',
        'group': 'hvac',
        'sub_type': 'panel_fourth_children',
        'group_display': '暖通',
        'sub_type_display': '儿童房-温控面板',
    },

    # ── 新风（含加湿参数、风量设置） ─────────────────────────────────────────
    {
        'param_name': 'fan_speed',
        'display_name': '风机转速反馈',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'fan_gear_feedback',
        'display_name': '风量',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'filter_alarm_hours_setting',
        'display_name': '粗效滤网报警小时数设置',
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
        'param_name': 'humidification_humidity_lower_limit',
        'display_name': '加湿温度下限',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'humidification_humidity_upper_limit',
        'display_name': '加湿温度上限',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'humidification_switch',
        'display_name': '加湿使能',
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
        'param_name': 'fresh_air_valve_opening',
        'display_name': '一次水阀开度反馈',
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
        'param_name': 'coil_supply_air_temp',
        'display_name': '过盘管出风温度',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'system_air_volume_setting',
        'display_name': '系统风量设置',
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
        'display_name': '停机故障',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },
    {
        'param_name': 'fresh_air_unit_communication_error',
        'display_name': '通信故障',
        'group': 'hvac',
        'sub_type': 'fresh_air',
        'group_display': '暖通',
        'sub_type_display': '新风',
    },

    # ── 能耗表 ────────────────────────────────────────────────────────────
    {
        'param_name': 'total_cold_quantity',
        'display_name': '累计冷量',
        'group': 'hvac',
        'sub_type': 'energy_meter',
        'group_display': '暖通',
        'sub_type_display': '能耗表',
    },
    {
        'param_name': 'total_hot_quantity',
        'display_name': '累计热量',
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
        'display_name': '故障',
        'group': 'hvac',
        'sub_type': 'energy_meter',
        'group_display': '暖通',
        'sub_type_display': '能耗表',
    },

    # ── 水力模块（含运行模式、节能标识、集中能源供给） ─────────────────────────
    {
        'param_name': 'hydraulic_module_inlet_temp',
        'display_name': '二次水进水温度检测值',
        'group': 'hvac',
        'sub_type': 'hydraulic_module',
        'group_display': '暖通',
        'sub_type_display': '水力模块',
    },
    {
        'param_name': 'hydraulic_module_outlet_temp',
        'display_name': '二次水出水温度检测值',
        'group': 'hvac',
        'sub_type': 'hydraulic_module',
        'group_display': '暖通',
        'sub_type_display': '水力模块',
    },
    {
        'param_name': 'away_energy_saving',
        'display_name': '离家节能标识',
        'group': 'hvac',
        'sub_type': 'hydraulic_module',
        'group_display': '暖通',
        'sub_type_display': '水力模块',
    },
    {
        'param_name': 'central_energy_supply',
        'display_name': '集中能源供给',
        'group': 'hvac',
        'sub_type': 'hydraulic_module',
        'group_display': '暖通',
        'sub_type_display': '水力模块',
    },
    {
        'param_name': 'operation_mode',
        'display_name': '模式',
        'group': 'hvac',
        'sub_type': 'hydraulic_module',
        'group_display': '暖通',
        'sub_type_display': '水力模块',
    },
    {
        'param_name': 'hydraulic_module_valve_opening',
        'display_name': '一次阀门开度反馈',
        'group': 'hvac',
        'sub_type': 'hydraulic_module',
        'group_display': '暖通',
        'sub_type_display': '水力模块',
    },
    {
        'param_name': 'system_switch',
        'display_name': '系统开关',
        'group': 'hvac',
        'sub_type': 'hydraulic_module',
        'group_display': '暖通',
        'sub_type_display': '水力模块',
    },
    {
        'param_name': 'hydraulic_module_low_temp_error',
        'display_name': '低温故障',
        'group': 'hvac',
        'sub_type': 'hydraulic_module',
        'group_display': '暖通',
        'sub_type_display': '水力模块',
    },

    # ── 空气品质（CO₂、PM2.5，独立于新风卡片） ────────────────────────────────
    {
        'param_name': 'co2',
        'display_name': 'CO₂',
        'group': 'hvac',
        'sub_type': 'air_quality',
        'group_display': '暖通',
        'sub_type_display': '空气品质',
    },
    {
        'param_name': 'pm25',
        'display_name': 'PM2.5',
        'group': 'hvac',
        'sub_type': 'air_quality',
        'group_display': '暖通',
        'sub_type_display': '空气品质',
    },
    {
        'param_name': 'air_quality_sensor_communication_error',
        'display_name': '故障',
        'group': 'hvac',
        'sub_type': 'air_quality',
        'group_display': '暖通',
        'sub_type_display': '空气品质',
    },
]


class Command(BaseCommand):
    help = '初始化暖通参数 DeviceConfig 元数据（param_name -> group/sub_type 映射）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='先删除全部 DeviceConfig 记录再重建（切换 sub_type 归属时需使用）',
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
                sub_type=cfg['sub_type'],
                defaults={
                    'display_name': cfg['display_name'],
                    'group': cfg['group'],
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
        if skipped_count > 0:
            self.stdout.write(self.style.WARNING(
                '注意：有已存在记录被跳过。若需更新 sub_type 归属，请使用 --reset 标志重建。'
            ))
