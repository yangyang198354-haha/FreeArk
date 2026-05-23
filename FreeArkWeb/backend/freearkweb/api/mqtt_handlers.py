import logging
from datetime import datetime
from abc import ABC, abstractmethod
from django.db import transaction, connection
from django.utils import timezone
from .models import PLCData, PLCConnectionStatus, PLCStatusChangeHistory, PLCLatestData, DeviceParamHistory, ScreenConnectivityStatus
from .utils_room_filter import get_panel_param_blocklist  # v0.5.7 M4: 落库侧房型过滤

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
                            # 只处理能耗参数，其余参数由 PLCLatestDataHandler 负责
                            if param_key not in param_to_energy_mode:
                                logger.debug(f"PLCDataHandler: 跳过非能耗参数: {param_key}")
                                continue

                            success = param_data.get('success', False)

                            # 对于success为false的数据，只记录日志不保存
                            if not success:
                                message = param_data.get('message', '未知错误')
                                logger.warning(f"PLCDataHandler: 跳过失败的数据: specific_part={specific_part}, param_key={param_key}, message={message}")
                                continue

                            # 处理success为true的数据
                            logger.debug(f"PLCDataHandler: 处理数据项: param_key={param_key}, 数据={param_data}")

                            # 映射参数名到energy_mode
                            energy_mode = param_to_energy_mode[param_key]
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
            raise  # 向上传播，使 process_message 的重试/重连逻辑能感知到数据库错误


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
        
        logger.debug(f"ConnectionStatusHandler: ✅ 处理连接状态消息完成")
    
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
        """更新设备连接状态。

        [v0.5.5 P2] 快/慢路径分离，消除正常运行期间的 select_for_update() 行锁：

        快路径（缓存命中且状态一致）：
          - status='online'  -> QuerySet.update(last_online_time=now())，无事务无行锁
          - status='offline' -> 完全跳过，零 DB 写入

        慢路径（缓存 miss 或状态变化）：
          - 保留原有 transaction.atomic() + select_for_update() 行锁语义
          - 保证 PLCStatusChangeHistory 写入的原子性，不漏记
          - 事务提交成功后才更新 _conn_status_cache（异常时不更新，下次重试）
        """
        cached = _conn_status_cache.get(specific_part)

        # ── 快路径：状态无变化，跳过行锁事务 ──────────────────────────────
        if cached == status:
            if status == 'online':
                # [v0.5.8 F2] 加 connection_status='online' 守卫，利用 rows_affected
                # 检测 Path B（plc_connection_monitor）是否已悄悄把 DB 翻成 offline。
                # 常态（rows==1）：仅刷 last_online_time，无事务，无行锁，零额外开销。
                # 异常（rows==0）：DB 已被置 offline，cache 脏；清除 cache 并 fall-through
                # 到慢路径自动补正，写 source='mqtt'/status='online' history，前端实时感知。
                rows = PLCConnectionStatus.objects.filter(
                    specific_part=specific_part,
                    connection_status='online',
                ).update(last_online_time=timezone.now())
                if rows > 0:
                    logger.debug(
                        f"ConnectionStatusHandler: 快路径（无状态变化）- {specific_part}: online"
                    )
                    return
                # rows == 0：cache/DB 不一致，回退慢路径
                logger.warning(
                    f"ConnectionStatusHandler: {specific_part} cache/DB 不一致，"
                    f"cache=online 但 DB 已被 monitor 置 offline，回退慢路径补正"
                )
                _conn_status_cache.pop(specific_part, None)
                # fall-through：不 return，执行流进入下方慢路径块
            else:
                # status == 'offline' 且无变化：零 DB 写入
                logger.debug(
                    f"ConnectionStatusHandler: 快路径（无状态变化）- {specific_part}: offline"
                )
                return

        # ── 慢路径：缓存 miss 或状态变化，走完整行锁事务 ──────────────────
        logger.debug(
            f"ConnectionStatusHandler: 慢路径（缓存={cached!r} -> status={status!r}）- {specific_part}"
        )
        try:
            with transaction.atomic():
                # 查询或创建PLCConnectionStatus记录
                plc_status, created = PLCConnectionStatus.objects.select_for_update().get_or_create(
                    specific_part=specific_part,
                    defaults={
                        'connection_status': status,
                        'building': building,
                        'unit': unit,
                        'room_number': room_number
                    }
                )

                # 检查状态是否发生变化
                if created:
                    # 新创建的记录，状态变化为当前状态
                    status_changed = True
                    logger.debug(f"ConnectionStatusHandler: ✅ 新建连接状态记录 - {specific_part}: {status}")
                else:
                    # 记录已存在，检查状态是否变化
                    old_status = plc_status.connection_status
                    status_changed = (old_status != status)
                    if status_changed:
                        logger.debug(f"ConnectionStatusHandler: ✅ 状态发生变化 - {specific_part}: {old_status} -> {status}")

                # 如果状态发生变化（含新建），记录状态变化历史
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

                # 更新 PLCConnectionStatus 行
                if not created:
                    if status_changed:
                        # 状态变化：全字段更新
                        plc_status.connection_status = status
                        plc_status.building = building
                        plc_status.unit = unit
                        plc_status.room_number = room_number
                        if status == 'online':
                            plc_status.last_online_time = timezone.now()
                        plc_status.save()
                    else:
                        # 并发竞争：两 worker 同时 cache miss，本 worker 后进入，
                        # 发现 DB 中状态已与 status 一致，仅在需要时刷新 last_online_time
                        if status == 'online':
                            plc_status.last_online_time = timezone.now()
                            plc_status.save(update_fields=['last_online_time'])
                        logger.debug(f"ConnectionStatusHandler: 慢路径-并发无变化 - {specific_part}: {status}")
                else:
                    # created=True：get_or_create 的 INSERT 已写入初始字段，
                    # 若 status='online' 补写 last_online_time
                    if status == 'online':
                        plc_status.last_online_time = timezone.now()
                        plc_status.save(update_fields=['last_online_time'])

            # 事务提交成功后更新缓存（放在 with 块外，确保事务已提交）
            _conn_status_cache[specific_part] = status
            logger.debug(f"ConnectionStatusHandler: ✅ 慢路径完成，缓存更新 - {specific_part}: {status}")

        except Exception as e:
            # 异常时不更新缓存，保留 miss 状态，下次调用仍走慢路径重试
            logger.error(f"ConnectionStatusHandler: 更新连接状态失败 - {specific_part}: {e}", exc_info=True)


# 不写入 PLCLatestData 的参数（当前无排除项）
# 注：total_hot_quantity / total_cold_quantity 同时由 PLCDataHandler 写能耗表、
#     由 PLCLatestDataHandler 写 PLCLatestData，两个路径并行互不干扰。
_EXCLUDED_PARAMS = frozenset()

# Energy 参数由独立采集任务每约 6 分钟推送；自 v0.5.4(P1-1) 起，其历史
# （device_param_history）也只保留每小时第一条，与 general 一致。
# General 参数每 10 分钟一轮，历史只保留每小时第一条。
_ENERGY_PARAM_NAMES = frozenset(['total_hot_quantity', 'total_cold_quantity'])

# General 历史去重缓存：(specific_part, param_name) -> 'YYYY-MM-DD-HH'
# Python GIL 保证单次 dict get/set 的原子性；极端情况同一小时最多多写一条，可接受。
_general_hist_last_hour: dict = {}

# Energy 历史去重缓存（v0.5.4 P1-1）：与 _general_hist_last_hour 同策略、同结构，
# energy 参数每小时也只保留第一条 device_param_history 样本。
# (specific_part, param_name) -> 'YYYY-MM-DD-HH'；线程安全模型同上（依赖 GIL）。
_energy_hist_last_hour: dict = {}

# [v0.5.5 P2] ConnectionStatus 进程内状态缓存。
# key: specific_part (str) -> last_known_status: str ('online' | 'offline')
# 用途：设备状态无变化时跳过 select_for_update() 行锁，走轻量快路径。
#   - 命中且与当前 status 一致 -> 快路径（online 仅刷新 last_online_time；offline 零写入）
#   - 缓存 miss 或与 status 不一致 -> 慢路径（保留原有 select_for_update 行锁事务）
# 线程安全：依赖 CPython GIL；极端并发（两 worker 同时 miss）下两者均走慢路径，
#   后者在 select_for_update 处排队，行为与优化前一致。
# 仅进程内有效，服务重启后清空，首批消息走慢路径自动重建。
_conn_status_cache: dict = {}

# 支持的时间戳格式
_TIMESTAMP_FORMATS = (
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%d %H:%M:%S.%f',
    '%Y-%m-%dT%H:%M:%S.%f',
)


def _parse_timestamp(ts_str):
    """将时间戳字符串解析为 naive datetime，解析失败返回 None。"""
    if not isinstance(ts_str, str):
        return None
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    return None


def _parse_building_parts(specific_part):
    """从 specific_part（格式 楼-单-层-户 或 楼-单-户）解析 building/unit/room_number。"""
    if '-' not in specific_part:
        return '', '', ''
    parts = specific_part.split('-')
    if len(parts) >= 4:
        return parts[0], parts[1], parts[3]
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    return '', '', ''


class PLCLatestDataHandler(MessageHandler):
    """处理 MQTT PLC 消息，将各参数最新值 upsert 到 PLCLatestData 表。

    - total_hot_quantity / total_cold_quantity 同时也由 PLCDataHandler 写能耗表，此处照常写入
    - success=false 的参数丢弃，不写入
    - 以 (specific_part, param_name) 为唯一键执行 update-or-create
    """

    def handle(self, topic, payload, building_file=None):
        logger.debug(f"PLCLatestDataHandler: 处理消息 - 主题={topic}")

        if not isinstance(payload, dict):
            logger.warning(f"PLCLatestDataHandler: 不支持的 payload 类型: {type(payload).__name__}")
            return

        # 仅处理 improved_data_collection_manager 格式：{device_id: device_info}
        if not (len(payload) == 1 and not any(
            k in payload for k in ('data', 'device_id', 'param_key', 'results')
        )):
            logger.debug("PLCLatestDataHandler: payload 不符合目标格式，跳过")
            return

        device_id = next(iter(payload))
        device_info = payload[device_id]

        if not isinstance(device_info, dict) or 'data' not in device_info:
            logger.debug(f"PLCLatestDataHandler: device_info 缺少 data 字段，跳过: {device_id}")
            return

        specific_part = device_id
        plc_ip = device_info.get('PLC IP地址', '') or device_info.get('IP地址', '')
        building, unit, room_number = _parse_building_parts(specific_part)

        data_dict = device_info['data']
        if not isinstance(data_dict, dict):
            return

        # v0.5.7 M4: 获取该专有部分不应落库的参数黑名单（带 300s 缓存）
        # 兜底防御层：覆盖所有 MQTT 消息来源（定时采集、按需采集、其他）
        param_blocklist = get_panel_param_blocklist(specific_part)

        total_params = len(data_dict)
        records = []
        skipped_excluded = 0
        skipped_not_dict = 0
        skipped_failed = 0
        skipped_room_filter = 0  # v0.5.7 M4: 房型过滤跳过计数

        for param_name, param_data in data_dict.items():
            # 排除由 PLCDataHandler 处理的参数
            if param_name in _EXCLUDED_PARAMS:
                skipped_excluded += 1
                logger.debug(
                    f"PLCLatestDataHandler: 跳过 excluded 参数: "
                    f"topic={topic}, device_id={specific_part}, param={param_name}, 原因=in _EXCLUDED_PARAMS"
                )
                continue

            # v0.5.7 M4: 跳过不存在房间的温控面板参数（落库侧防御层，不落库）
            if param_blocklist and param_name in param_blocklist:
                skipped_room_filter += 1
                logger.debug(
                    'PLCLatestDataHandler: 跳过不存在房间参数 %s/%s (room_filter)',
                    specific_part, param_name,
                )
                continue
            # ── end v0.5.7 M4 ───────────────────────────────────────────────

            if not isinstance(param_data, dict):
                skipped_not_dict += 1
                logger.debug(
                    f"PLCLatestDataHandler: 跳过非 dict 参数: "
                    f"topic={topic}, device_id={specific_part}, param={param_name}, type={type(param_data).__name__}"
                )
                continue
            if not param_data.get('success', False):
                skipped_failed += 1
                logger.debug(
                    f"PLCLatestDataHandler: 跳过失败参数 {specific_part}/{param_name}: "
                    f"{param_data.get('message', '')}"
                )
                continue

            raw_value = param_data.get('value')
            try:
                int_value = int(raw_value) if raw_value is not None else None
            except (TypeError, ValueError):
                logger.warning(
                    f"PLCLatestDataHandler: 参数 {param_name} 的值无法转换为整数: {raw_value!r}，置为 None"
                )
                int_value = None

            collected_at = _parse_timestamp(param_data.get('timestamp'))

            records.append({
                'specific_part': specific_part,
                'param_name': param_name,
                'value': int_value,
                'collected_at': collected_at,
                'plc_ip': plc_ip,
                'building': building,
                'unit': unit,
                'room_number': room_number,
            })

        valid_count = len(records)
        logger.debug(
            f"PLCLatestDataHandler: 消息处理摘要 - topic={topic}, device_id={specific_part}, "
            f"总参数数={total_params}, 有效参数数={valid_count}, "
            f"跳过(excluded={skipped_excluded}, not_dict={skipped_not_dict}, "
            f"failed={skipped_failed}, room_filter={skipped_room_filter})"  # v0.5.7 M4
        )

        if not records:
            if skipped_failed > 0 and valid_count == 0:
                logger.warning(
                    f"PLCLatestDataHandler: {specific_part} 所有 {total_params} 个参数均无有效数据 "
                    f"(excluded={skipped_excluded}, failed={skipped_failed})，本次跳过写入"
                )
            else:
                logger.debug(f"PLCLatestDataHandler: {specific_part} 无有效参数需要写入")
            return

        self._bulk_upsert(records)
        self._write_history(records)

    def _write_history(self, records):
        """追加写入 DeviceParamHistory（时序历史，append-only）。

        Energy 与 General 参数均按「每小时保留第一条」去重（v0.5.4 P1-1 起一致）：
        - Energy 参数（total_hot/cold_quantity）：经 _energy_hist_last_hour 去重
          （约 6 分钟采集 → 每小时 1 条，写入量降约 10 倍）。
        - General 参数：经 _general_hist_last_hour 去重（10 分钟采集 → 每小时 1 条）。
        两者去重算法相同，仅使用各自的缓存。
        """
        hist_objs = []
        for r in records:
            param_name = r['param_name']
            collected_at = r['collected_at']  # datetime or None

            # 按参数类型选择对应的小时去重缓存（energy / general 算法一致）
            hist_cache = (_energy_hist_last_hour
                          if param_name in _ENERGY_PARAM_NAMES
                          else _general_hist_last_hour)
            # 无时间戳无法定位小时窗口，跳过
            if collected_at is None:
                continue
            hour_key = collected_at.strftime('%Y-%m-%d-%H')
            cache_key = (r['specific_part'], param_name)
            if hist_cache.get(cache_key) == hour_key:
                continue  # 本小时已有样本，跳过
            hist_cache[cache_key] = hour_key

            hist_objs.append(DeviceParamHistory(
                specific_part=r['specific_part'],
                param_name=param_name,
                value=str(r['value']) if r['value'] is not None else None,
                collected_at=collected_at,
            ))

        if not hist_objs:
            logger.debug("PLCLatestDataHandler: 历史写入跳过（均已在本小时记录）")
            return
        try:
            DeviceParamHistory.objects.bulk_create(hist_objs)
            logger.debug(f"PLCLatestDataHandler: 历史追加 {len(hist_objs)} 条")
        except Exception as e:
            logger.error(f"PLCLatestDataHandler: 历史写入失败: {e}", exc_info=True)

    def _bulk_upsert(self, records):
        """批量 upsert PLCLatestData 记录（单条 INSERT … ON DUPLICATE KEY UPDATE）。"""
        if not records:
            return

        logger.debug(f"PLCLatestDataHandler: 开始批量 upsert，共 {len(records)} 条记录")

        # 同一批消息内相同唯一键取最后一条
        keyed = {}
        for rec in records:
            keyed[(rec['specific_part'], rec['param_name'])] = rec

        objs = [PLCLatestData(**rec) for rec in keyed.values()]

        try:
            # MySQL 不支持 unique_fields（使用表约束自动冲突检测），SQLite/PostgreSQL 需要显式指定
            kwargs = dict(
                update_conflicts=True,
                update_fields=['value', 'collected_at', 'plc_ip', 'building', 'unit', 'room_number', 'updated_at'],
            )
            if connection.vendor != 'mysql':
                kwargs['unique_fields'] = ['specific_part', 'param_name']
            PLCLatestData.objects.bulk_create(objs, **kwargs)
            logger.debug(f"PLCLatestDataHandler: upsert 完成，共 {len(objs)} 条")
        except Exception as e:
            logger.error(f"PLCLatestDataHandler: 批量 upsert 失败: {e}", exc_info=True)
            raise


# ---------------------------------------------------------------------------
# v0.5.6 — OndemandPLCLatestDataHandler (MOD-BE-03)
#
# 按需采集专用 handler：仅写 plc_latest_data，不写 device_param_history（ADR-004）。
# 继承 PLCLatestDataHandler，覆盖 _write_history() 为 no-op，改动量最小，逻辑清晰。
# ---------------------------------------------------------------------------
class OndemandPLCLatestDataHandler(PLCLatestDataHandler):
    """按需采集专用 handler。

    仅调用 _bulk_upsert()，覆盖 _write_history() 为 no-op，
    防止 device_param_history 因按需采集（每 30 秒）大量膨胀（OQ-003 决议）。
    """

    def _write_history(self, records):
        """按需采集不写历史（ADR-004，OQ-003 用户已确认）。"""
        logger.debug('OndemandPLCLatestDataHandler: 跳过历史写入（按需采集不写 device_param_history）')


# ---------------------------------------------------------------------------
# MOD-MQTT-01 — ScreenConnectivityHandler（已适配心跳方案）
#
# 历史：旧版通过 datacollection ICMP 探测写入 status/last_checked_at。
# 新版（2026-05）：ScreenConnectivityStatus 已改为仅含 last_seen_at。
# ScreenConnectivityHandler 保留接口兼容性，但内部改为写入 last_seen_at，
# "online" payload → last_seen_at = now()（视为刚刚心跳）。
# "offline" payload → 不写入（离线状态由阈值判断，不需要主动写入）。
# ---------------------------------------------------------------------------
class ScreenConnectivityHandler(MessageHandler):
    """[兼容层] 大屏连通性 MQTT 消息处理器。

    旧接口保留，适配新模型（仅 last_seen_at）：
    - "online" payload → upsert last_seen_at = now()
    - "offline" / 其他 → no-op（离线由 15 分钟阈值自动判断）
    - payload 非 dict / specific_part 为空 → 丢弃

    生产环境中此 handler 不再被主动调用（心跳由 screen_heartbeat_consumer 写入）。
    保留以兼容 test_device_management.py 等旧测试文件。
    """

    ALLOWED_STATUSES = {'online', 'offline'}

    def handle(self, topic, payload, building_file=None):
        """处理单条大屏连通性消息（兼容旧接口）。"""
        if not isinstance(payload, dict):
            logger.debug(
                'ScreenConnectivityHandler: payload 类型不正确 (%s)，跳过',
                type(payload).__name__,
            )
            return

        specific_part = payload.get('specific_part', '').strip()
        status_val = payload.get('status', '').strip().lower()

        if not specific_part:
            logger.debug(
                'ScreenConnectivityHandler: specific_part 为空，丢弃: topic=%s', topic
            )
            return

        if status_val not in self.ALLOWED_STATUSES:
            logger.debug(
                'ScreenConnectivityHandler: status 非法 %r，丢弃: specific_part=%s',
                status_val, specific_part,
            )
            return

        # 只有 online 才写入 last_seen_at（离线状态由阈值判断）
        if status_val == 'online':
            try:
                from django.utils import timezone as _tz
                ScreenConnectivityStatus.objects.update_or_create(
                    specific_part=specific_part,
                    defaults={'last_seen_at': _tz.now()},
                )
                logger.debug(
                    'ScreenConnectivityHandler: upsert last_seen_at — specific_part=%s',
                    specific_part,
                )
            except Exception as exc:
                logger.error(
                    'ScreenConnectivityHandler: DB 写入失败 — specific_part=%s, error=%s',
                    specific_part, exc, exc_info=True,
                )
        else:
            logger.debug(
                'ScreenConnectivityHandler: status=%r，不写入（离线由阈值判断）: specific_part=%s',
                status_val, specific_part,
            )
