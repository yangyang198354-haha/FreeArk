import logging
from datetime import datetime
from abc import ABC, abstractmethod
from django.db import transaction
from django.utils import timezone
from .models import PLCData, PLCConnectionStatus, PLCStatusChangeHistory

# 获取logger
logger = logging.getLogger(__name__)


class MessageHandler(ABC):
    """消息处理器基类，定义统一的消息处理接口"""
    
    @abstractmethod
    def handle(self, topic, payload, building_file=None):
        """处理消息的抽象方法"""
        pass


class PLCDataHandler(MessageHandler):
    """PLC数据处理器，处理PLC用量数据更新"""
    
    def handle(self, topic, payload, building_file=None):
        """处理PLC数据消息"""
        logger.debug(f"PLCDataHandler: 处理消息 - 主题={topic}")
        
        # 收集所有数据点
        batch_data = []
        
        # 处理不同格式的消息
        if isinstance(payload, dict):
            logger.debug(f"PLCDataHandler: 处理字典类型消息，包含键: {list(payload.keys())}")
            
            # 检查是否是improved_data_collection_manager.py发送的数据格式：{device_id: device_info}
            if len(payload) == 1 and not any(key in ['data', 'device_id', 'param_key', 'results'] for key in payload.keys()):
                device_id = list(payload.keys())[0]
                device_info = payload[device_id]
                logger.debug(f"PLCDataHandler: 处理improved_data_collection_manager发送的数据格式: device_id={device_id}")
                
                # device_id就是PLCData的specific_part
                specific_part = device_id
                plc_ip = device_info.get('PLC IP地址', '') or device_info.get('IP地址', '')
                logger.debug(f"PLCDataHandler: 提取信息: specific_part={specific_part}, plc_ip={plc_ip}")
                
                # 检查是否包含data字段
                if 'data' in device_info and isinstance(device_info['data'], dict):
                    logger.debug(f"PLCDataHandler: 处理data字段，包含{len(device_info['data'])}个数据项")
                    
                    # 参数名到energy_mode的映射
                    param_to_energy_mode = {
                        'total_hot_quantity': '制热',
                        'total_cold_quantity': '制冷'
                    }
                    
                    for param_key, param_data in device_info['data'].items():
                        if isinstance(param_data, dict):
                            success = param_data.get('success', False)
                            
                            # 对于success为false的数据，只记录日志不保存
                            if not success:
                                message = param_data.get('message', '未知错误')
                                logger.warning(f"PLCDataHandler: 跳过失败的数据: specific_part={specific_part}, param_key={param_key}, message={message}")
                                continue
                            
                            # 处理success为true的数据
                            logger.debug(f"PLCDataHandler: 处理数据项: param_key={param_key}, 数据={param_data}")
                            
                            # 映射参数名到energy_mode
                            energy_mode = param_to_energy_mode.get(param_key, param_key)
                            logger.debug(f"PLCDataHandler: 参数映射: {param_key} -> {energy_mode}")
                            
                            # 构建数据点
                            data_point = {
                                'specific_part': specific_part,
                                'energy_mode': energy_mode,
                                'plc_ip': plc_ip,
                                'param_value': param_data.get('value'),
                                'success': success,
                                'message': param_data.get('message', ''),
                                'timestamp': param_data.get('timestamp')
                            }
                            
                            # 添加到批量数据列表
                            batch_data.append(data_point)
                    logger.debug(f"PLCDataHandler: improved_data_collection_manager数据处理完成，收集了{len(batch_data)}个数据点")
            # 检查是否是新格式的消息，包含data字段
            elif 'data' in payload and isinstance(payload['data'], dict):
                logger.debug(f"PLCDataHandler: 处理新格式消息: 包含data字段，data包含{len(payload['data'])}个数据项")
                # 提取房间信息
                specific_part = None
                building = ''
                unit = ''
                room_number = ''
                plc_ip = ''
                
                # 尝试从不同字段获取specific_part
                if '专有部分坐落' in payload:
                    logger.debug(f"PLCDataHandler: 从'专有部分坐落'字段提取信息: {payload['专有部分坐落']}")
                    # 从专有部分坐落提取（格式：成都乐府（二仙桥）-9-1-3104）
                    location_parts = payload['专有部分坐落'].split('-')
                    logger.debug(f"PLCDataHandler: 专有部分坐落解析: 部分数量={len(location_parts)}, 内容={location_parts}")
                    if len(location_parts) >= 4:
                        specific_part = f"{location_parts[1]}-{location_parts[2]}-{location_parts[3]}"
                        logger.debug(f"PLCDataHandler: 成功解析specific_part: {specific_part}")
                
                # 如果没有专有部分坐落，尝试从键名获取（例如："9-1-31-3104"）
                if not specific_part and topic.split('/') and len(topic.split('/')) > 4:
                    possible_key = topic.split('/')[4]
                    if '-' in possible_key:
                        specific_part = possible_key
                        logger.debug(f"PLCDataHandler: 从主题获取specific_part: {specific_part}")
                
                # 获取楼栋、单元、房号信息
                if '楼栋' in payload:
                    building = payload['楼栋'].replace('栋', '')
                    logger.debug(f"PLCDataHandler: 从'楼栋'字段提取: {building}")
                if '单元' in payload:
                    unit = payload['单元'].replace('单元', '')
                    logger.debug(f"PLCDataHandler: 从'单元'字段提取: {unit}")
                if '户号' in payload:
                    room_number = str(payload['户号'])
                    logger.debug(f"PLCDataHandler: 从'户号'字段提取: {room_number}")
                
                # 获取PLC IP地址
                if 'PLC IP地址' in payload:
                    plc_ip = payload['PLC IP地址']
                    logger.debug(f"PLCDataHandler: 从'PLC IP地址'字段提取: {plc_ip}")
                elif 'IP地址' in payload:
                    plc_ip = payload['IP地址']
                    logger.debug(f"PLCDataHandler: 从'IP地址'字段提取: {plc_ip}")
                
                logger.debug(f"PLCDataHandler: 解析完成: specific_part={specific_part}, building={building}, unit={unit}, room_number={room_number}, plc_ip={plc_ip}")
                
                # 处理data字段中的各项数据
                for energy_mode, mode_data in payload['data'].items():
                    if isinstance(mode_data, dict):
                        logger.debug(f"PLCDataHandler: 处理data项: energy_mode={energy_mode}, 数据={mode_data}")
                        # 构建数据点
                        data_point = {
                            'specific_part': specific_part,
                            'building': building,
                            'unit': unit,
                            'room_number': room_number,
                            'energy_mode': energy_mode,
                            'plc_ip': plc_ip,
                            'param_value': mode_data.get('value'),
                            'success': mode_data.get('success', False),
                            'message': mode_data.get('message', ''),
                            'timestamp': mode_data.get('timestamp')
                        }
                        # 添加到批量数据列表
                        batch_data.append(data_point)
                logger.debug(f"PLCDataHandler: 新格式消息处理完成，收集了{len(batch_data)}个数据点")
            # 检查是否是单个PLC数据点
            elif 'device_id' in payload and 'param_key' in payload:
                logger.debug(f"PLCDataHandler: 处理单个PLC数据点: device_id={payload['device_id']}, param_key={payload['param_key']}")
                # 添加到批量数据列表
                batch_data.append(payload)
            # 检查是否包含多个结果的列表
            elif 'results' in payload and isinstance(payload['results'], list):
                result_count = len(payload['results'])
                logger.debug(f"PLCDataHandler: 处理结果列表，共{result_count}个项目")
                for i, result in enumerate(payload['results']):
                    logger.debug(f"PLCDataHandler: 处理结果项[{i}]: {result}")
                    # 添加到批量数据列表
                    batch_data.append(result)
            # 检查是否直接是数据点列表（旧格式）
            elif all(isinstance(item, dict) for item in payload.values()):
                device_count = len(payload)
                logger.debug(f"PLCDataHandler: 处理旧格式数据点列表，共{device_count}个设备")
                for device_id, device_data in payload.items():
                    if isinstance(device_data, dict):
                        param_count = len(device_data)
                        logger.debug(f"PLCDataHandler: 处理设备数据: device_id={device_id}, 包含{param_count}个参数")
                        # 检查是否是新格式的数据结构
                        if 'data' in device_data and isinstance(device_data['data'], dict):
                            # 处理嵌套的data结构
                            specific_part = device_id
                            plc_ip = (device_data.get('PLC IP地址', '') or 
                                      device_data.get('IP地址', ''))
                            logger.debug(f"PLCDataHandler: 嵌套data结构: specific_part={specific_part}, "
                                        f"plc_ip={plc_ip}")
                            
                            for energy_mode, mode_data in device_data['data'].items():
                                if isinstance(mode_data, dict):
                                    logger.debug(f"PLCDataHandler: 处理嵌套data项: energy_mode={energy_mode}")
                                    data_point = {
                                        'specific_part': specific_part,
                                        'energy_mode': energy_mode,
                                        'plc_ip': plc_ip,
                                        'param_value': mode_data.get('value'),
                                        'success': mode_data.get('success', False),
                                        'message': mode_data.get('message', ''),
                                        'timestamp': mode_data.get('timestamp')
                                    }
                                    # 添加到批量数据列表
                                    batch_data.append(data_point)
                        else:
                            # 处理旧格式的数据结构
                            for param_key, param_value in device_data.items():
                                logger.debug(f"PLCDataHandler: 处理旧格式参数: param_key={param_key}")
                                # 构建数据点
                                data_point = {
                                    'device_id': device_id,
                                    'param_key': param_key,
                                    'param_value': param_value,
                                    'success': True,
                                    'message': '数据接收成功'
                                }
                                # 添加到批量数据列表
                                batch_data.append(data_point)
        elif isinstance(payload, list):
            # 如果payload直接是列表，收集所有数据点
            logger.debug(f"PLCDataHandler: 处理列表类型消息，共{len(payload)}个项目")
            for i, item in enumerate(payload):
                if isinstance(item, dict):
                    logger.debug(f"PLCDataHandler: 处理列表项[{i}]: {item}")
                    # 添加到批量数据列表
                    batch_data.append(item)
                else:
                    logger.warning(f"PLCDataHandler: 列表项[{i}]不是字典类型: {type(item)}")
        else:
            logger.warning(f"PLCDataHandler: 未知的消息格式: {type(payload).__name__}")
        
        # 批量保存所有数据点
        if batch_data:
            logger.debug(f"PLCDataHandler: 准备批量保存 {len(batch_data)} 个数据点")
            self.batch_save_plc_data(batch_data, building_file)
        else:
            logger.warning(f"PLCDataHandler: 没有数据点需要保存: 主题={topic}")
    
    def batch_save_plc_data(self, batch_data, building_file=None):
        """批量保存PLC数据点到数据库"""
        if not batch_data:
            logger.warning("PLCDataHandler: 没有数据点需要保存")
            return
        
        logger.debug(f"PLCDataHandler: 开始批量保存PLC数据点，共{len(batch_data)}个数据点，building_file={building_file}")
        
        # 数据解析部分，解析所有数据点
        parsed_data = []
        valid_data_count = 0
        
        try:
            for data_point in batch_data:
                logger.debug(f"PLCDataHandler: 解析数据点原始内容: {data_point}")
                
                # 获取必要字段，支持新旧字段名称
                specific_part = (data_point.get('specific_part') or 
                               data_point.get('device_id'))
                energy_mode = (data_point.get('energy_mode') or 
                             data_point.get('param_key'))

                logger.debug(f"PLCDataHandler: 提取关键字段: specific_part={specific_part}, "
                            f"energy_mode={energy_mode}")

                if not specific_part or not energy_mode:
                    logger.warning(f"PLCDataHandler: 缺少必要字段: specific_part={specific_part}, "
                                 f"energy_mode={energy_mode}")
                    continue

                # 获取数据点状态
                success = data_point.get('success', True)
                message = data_point.get('message', '')

                # 如果数据点不成功（连接失败等），记录日志但不保存
                if not success:
                    logger.warning(f"PLCDataHandler: 跳过失败的数据: {specific_part} - {energy_mode}, "
                                 f"消息: {message}")
                    continue

                # 获取楼栋、单元、房号信息 - 优先使用data_point中直接提供的
                building = data_point.get('building', '')
                unit = data_point.get('unit', '')
                room_number = data_point.get('room_number', '')

                logger.debug(f"PLCDataHandler: 直接提供的建筑信息: building={building}, unit={unit}, "
                            f"room_number={room_number}")

                # 如果没有直接提供，则尝试从specific_part解析
                if (not (building and unit and room_number) 
                        and '-' in specific_part):
                    logger.debug(f"PLCDataHandler: 尝试从specific_part解析建筑信息: {specific_part}")
                    parts = specific_part.split('-')
                    logger.debug(f"PLCDataHandler: 解析结果: 部分数量={len(parts)}, 内容={parts}")

                    # 处理不同格式：楼栋-单元-房号 或 楼栋-单元-楼层-房号
                    if len(parts) >= 3:
                        building = parts[0]
                        unit = parts[1]
                        if len(parts) >= 4:
                            # 格式：楼栋-单元-楼层-房号
                            room_number = parts[3]  # 使用房号部分
                            logger.debug(
                                f"PLCDataHandler: 解析为楼栋-单元-楼层-房号格式: building={building}, " 
                                f"unit={unit}, room_number={room_number}")
                        else:
                            # 格式：楼栋-单元-房号
                            room_number = parts[2]  # 使用第三部分作为房号
                            logger.debug(
                                f"PLCDataHandler: 解析为楼栋-单元-房号格式: building={building}, " 
                                f"unit={unit}, room_number={room_number}")

                # 准备数据
                plc_data = {
                    'specific_part': specific_part,
                    'building': building,
                    'unit': unit,
                    'room_number': room_number,
                    'energy_mode': energy_mode,
                    'value': (data_point.get('value') or 
                             data_point.get('param_value')),
                    'plc_ip': data_point.get('plc_ip')
                }

                # 提取timestamp并设置usage_date
                timestamp = data_point.get('timestamp')
                usage_date_set = False

                if timestamp:
                    try:
                        # 解析timestamp字符串为datetime对象
                        # 支持多种时间戳格式
                        if isinstance(timestamp, str):
                            # 尝试不同的时间格式
                            date_formats = [
                                '%Y-%m-%d %H:%M:%S',
                                '%Y-%m-%dT%H:%M:%S',
                                '%Y-%m-%d %H:%M:%S.%f',
                                '%Y-%m-%dT%H:%M:%S.%f',
                            ]
                            parsed_date = None
                            for fmt in date_formats:
                                try:
                                    parsed_date = datetime.strptime(timestamp, fmt)
                                    break
                                except ValueError:
                                    continue

                            if parsed_date:
                                # 设置usage_date为日期部分
                                plc_data['usage_date'] = parsed_date.date()
                                usage_date_set = True
                                logger.debug(f"PLCDataHandler: 从timestamp提取日期: {timestamp} -> {parsed_date.date()}")
                            else:
                                logger.warning(f"PLCDataHandler: 无法解析timestamp格式: {timestamp}")
                    except Exception as e:
                        logger.error(f"PLCDataHandler: 处理timestamp时发生错误: {e}")

                # 如果没有设置usage_date，使用当前日期作为默认值
                if not usage_date_set:
                    default_date = datetime.now().date()
                    plc_data['usage_date'] = default_date
                    logger.debug(f"PLCDataHandler: 未提供有效的timestamp，使用默认日期: {default_date}")

                logger.debug(f"PLCDataHandler: 准备保存的数据: {plc_data}")
                
                # 添加到解析后的数据集
                parsed_data.append(plc_data)
                valid_data_count += 1
            
            if not parsed_data:
                logger.warning("PLCDataHandler: 没有有效数据点需要保存")
                return
            
            logger.debug(f"PLCDataHandler: 数据解析完成，有效数据点数量: {valid_data_count}")
            
        except Exception as e:
            logger.error(f"PLCDataHandler: 解析PLC数据时发生错误: {e}", exc_info=True)
            return
        
        # 数据库批量操作
        try:
            # 使用事务确保数据库操作的原子性
            logger.debug("PLCDataHandler: 开始数据库事务")
            
            with transaction.atomic():
                logger.debug("PLCDataHandler: 事务已开始，设置保存点")
                
                # 1. 按唯一键（specific_part, energy_mode, usage_date）分组数据
                unique_key_map = {}
                for data in parsed_data:
                    key = (data['specific_part'], data['energy_mode'], data['usage_date'])
                    unique_key_map[key] = data
                
                logger.debug(f"PLCDataHandler: 按唯一键分组后的数据数量: {len(unique_key_map)}")
                
                # 2. 批量查询现有记录
                existing_records = PLCData.objects.filter(
                    specific_part__in=[k[0] for k in unique_key_map.keys()],
                    energy_mode__in=[k[1] for k in unique_key_map.keys()],
                    usage_date__in=[k[2] for k in unique_key_map.keys()]
                )
                
                logger.debug(f"PLCDataHandler: 查询到的现有记录数量: {len(existing_records)}")
                
                # 3. 构建现有记录映射
                existing_map = {(r.specific_part, r.energy_mode, r.usage_date): r for r in existing_records}
                
                # 4. 区分插入和更新
                to_create = []
                to_update = []
                update_values = []
                
                current_time = timezone.now()
                
                for key, data in unique_key_map.items():
                    if key in existing_map:
                        # 更新现有记录
                        record = existing_map[key]
                        old_value = record.value
                        record.value = data['value']
                        record.building = data['building']
                        record.unit = data['unit']
                        record.room_number = data['room_number']
                        record.plc_ip = data['plc_ip']
                        # 手动设置updated_at字段，因为bulk_update不会触发auto_now
                        record.updated_at = current_time
                        
                        to_update.append(record)
                        update_values.append((old_value, data['value']))
                    else:
                        # 创建新记录
                        to_create.append(PLCData(**data))
                
                logger.debug(f"PLCDataHandler: 需要插入的记录数量: {len(to_create)}, 需要更新的记录数量: {len(to_update)}")
                
                # 5. 执行批量操作
                if to_create:
                    PLCData.objects.bulk_create(to_create)
                    logger.info(f"PLCDataHandler: ✅ 批量插入完成，共{len(to_create)}条记录")
                
                if to_update:
                    # 只更新需要修改的字段
                    update_fields = ['value', 'building', 'unit', 'room_number', 'plc_ip', 'updated_at']
                    PLCData.objects.bulk_update(to_update, update_fields)
                    logger.info(f"PLCDataHandler: ✅ 批量更新完成，共{len(to_update)}条记录")
            
            logger.info(f"PLCDataHandler: ✅ 批量保存PLC数据点完成，共处理{valid_data_count}个有效数据点")
            
        except Exception as e:
            logger.error(f"PLCDataHandler: 批量保存PLC数据点时发生错误: {e}", exc_info=True)


class ConnectionStatusHandler(MessageHandler):
    """连接状态处理器，处理设备连接状态更新"""
    
    def handle(self, topic, payload, building_file=None):
        """处理连接状态消息"""
        logger.debug(f"ConnectionStatusHandler: 处理消息 - 主题={topic}")
        
        # 处理不同格式的消息
        if isinstance(payload, dict):
            logger.debug(f"ConnectionStatusHandler: 处理字典类型消息，包含键: {list(payload.keys())}")
            
            # 检查是否是improved_data_collection_manager.py发送的数据格式：{device_id: device_info}
            if len(payload) == 1 and not any(key in ['data', 'device_id', 'param_key', 'results'] for key in payload.keys()):
                device_id = list(payload.keys())[0]
                device_info = payload[device_id]
                logger.debug(f"ConnectionStatusHandler: 处理improved_data_collection_manager发送的数据格式: device_id={device_id}")
                
                # device_id就是specific_part
                specific_part = device_id
                
                # 解析建筑信息
                building, unit, room_number = self._parse_building_info(specific_part)
                
                # 检查是否包含data字段
                if 'data' in device_info and isinstance(device_info['data'], dict):
                    # 检查是否有任何成功的数据项
                    has_success = any(data.get('success', False) for data in device_info['data'].values())
                    
                    if has_success:
                        # 有成功的数据，标记为在线
                        self._update_connection_status(specific_part, 'online', building, unit, room_number)
                    else:
                        # 所有数据都失败，标记为离线
                        self._update_connection_status(specific_part, 'offline', building, unit, room_number)
                else:
                    # 没有data字段，无法确定状态，默认标记为离线
                    logger.warning(f"ConnectionStatusHandler: 没有找到有效的data字段，标记为离线: {specific_part}")
                    self._update_connection_status(specific_part, 'offline', building, unit, room_number)
            # 处理其他格式的消息
            else:
                logger.debug(f"ConnectionStatusHandler: 处理其他格式的字典消息")
                # 对于其他格式的消息，我们需要根据具体情况进行处理
                # 这里可以添加更多的处理逻辑
                pass
        
        logger.info(f"ConnectionStatusHandler: ✅ 处理连接状态消息完成")
    
    def _parse_building_info(self, specific_part):
        """从specific_part解析楼栋、单元和房号信息"""
        building = ''
        unit = ''
        room_number = ''
        
        if '-' in specific_part:
            parts = specific_part.split('-')
            logger.debug(f"ConnectionStatusHandler: 解析specific_part: {specific_part}, 部分数量={len(parts)}, 内容={parts}")
            
            # 处理不同格式：楼栋-单元-房号 或 楼栋-单元-楼层-房号
            if len(parts) >= 3:
                building = parts[0]
                unit = parts[1]
                if len(parts) >= 4:
                    # 格式：楼栋-单元-楼层-房号
                    room_number = parts[3]  # 使用房号部分
                    logger.debug(
                        f"ConnectionStatusHandler: 解析为楼栋-单元-楼层-房号格式: building={building}, " 
                        f"unit={unit}, room_number={room_number}")
                else:
                    # 格式：楼栋-单元-房号
                    room_number = parts[2]  # 使用第三部分作为房号
                    logger.debug(
                        f"ConnectionStatusHandler: 解析为楼栋-单元-房号格式: building={building}, " 
                        f"unit={unit}, room_number={room_number}")
        
        return building, unit, room_number
    
    def _update_connection_status(self, specific_part, status, building, unit, room_number):
        """更新设备连接状态"""
        logger.debug(f"ConnectionStatusHandler: 更新连接状态 - specific_part={specific_part}, status={status}")
        
        try:
            # 使用事务确保数据库操作的原子性
            with transaction.atomic():
                # 查询或创建PLCConnectionStatus记录
                plc_status, created = PLCConnectionStatus.objects.get_or_create(
                    specific_part=specific_part,
                    defaults={
                        'connection_status': status,
                        'building': building,
                        'unit': unit,
                        'room_number': room_number
                    }
                )
                
                # 检查状态是否发生变化
                status_changed = False
                old_status = None
                
                if created:
                    # 新创建的记录，状态变化为当前状态
                    status_changed = True
                    logger.debug(f"ConnectionStatusHandler: ✅ 新建连接状态记录 - {specific_part}: {status}")
                else:
                    # 记录已存在，检查状态是否变化
                    old_status = plc_status.connection_status
                    if old_status != status:
                        status_changed = True
                        logger.debug(f"ConnectionStatusHandler: ✅ 状态发生变化 - {specific_part}: {old_status} -> {status}")
                
                # 如果状态发生变化，记录状态变化历史
                if status_changed:
                    try:
                        PLCStatusChangeHistory.objects.create(
                            specific_part=specific_part,
                            status=status,
                            building=building,
                            unit=unit,
                            room_number=room_number
                        )
                        logger.info(f"ConnectionStatusHandler: ✅ 记录状态变化历史成功 - {specific_part}: {status}")
                    except Exception as e:
                        logger.error(f"ConnectionStatusHandler: ❌ 记录状态变化历史失败 - {specific_part}: {e}")
                
                # 更新状态和最后在线时间
                if not created:
                    plc_status.connection_status = status
                    plc_status.building = building
                    plc_status.unit = unit
                    plc_status.room_number = room_number
                
                # 如果状态是在线，更新最后在线时间
                if status == 'online':
                    plc_status.last_online_time = timezone.now()
                
                # 保存记录
                plc_status.save()
                
                logger.info(f"ConnectionStatusHandler: ✅ 更新连接状态成功 - {specific_part}: {status}")
                
        except Exception as e:
            logger.error(f"ConnectionStatusHandler: 更新连接状态失败 - {specific_part}: {e}", exc_info=True)
