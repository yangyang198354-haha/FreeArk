import json
import logging
import os
import re
import time
import threading
from datetime import datetime
import paho.mqtt.client as mqtt
import MySQLdb
from django.conf import settings
from django.db import connection as django_connection
from django.db import transaction
from django.db.utils import OperationalError as DjangoOperationalError
from django.utils import timezone
from .models import PLCData

# 获取logger
logger = logging.getLogger(__name__)

# 获取配置文件路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MQTT_CONFIG_PATH = os.path.join(BASE_DIR, 'mqtt_config.json')


def load_mqtt_config(config_path=MQTT_CONFIG_PATH):
    """加载MQTT配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info(f"成功加载MQTT配置文件: {config_path}")
        return config
    except FileNotFoundError:
        logger.warning(f"MQTT配置文件不存在: {config_path}，使用默认配置")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"MQTT配置文件解析错误: {e}")
        return {}
    except Exception as e:
        logger.error(f"加载MQTT配置文件时发生错误: {e}")
        return {}

class MQTTConsumer:
    def __init__(self):
        # 加载MQTT配置
        mqtt_config = load_mqtt_config()
        
        # MQTT配置 - 从配置文件读取，环境变量作为备份
        self.mqtt_broker = os.environ.get('MQTT_BROKER', mqtt_config.get('host', '192.168.31.97'))
        self.mqtt_port = int(os.environ.get('MQTT_PORT', mqtt_config.get('port', 32795)))
        self.mqtt_username = os.environ.get('MQTT_USERNAME', mqtt_config.get('username', ''))
        self.mqtt_password = os.environ.get('MQTT_PASSWORD', mqtt_config.get('password', ''))
        self.mqtt_topic = os.environ.get('MQTT_TOPIC', mqtt_config.get('topic', '/datacollection/plc/to/collector/#'))
        self.mqtt_client_id = os.environ.get('MQTT_CLIENT_ID', f'django-mqtt-client-{os.getpid()}')
        self.keepalive = int(os.environ.get('MQTT_KEEPALIVE', mqtt_config.get('keepalive', 60)))
        self.qos = mqtt_config.get('qos', 1)
        self.retain = mqtt_config.get('retain', False)
        self.tls_enabled = mqtt_config.get('tls_enabled', False)
        
        # 创建MQTT客户端
        self.client = mqtt.Client(client_id=self.mqtt_client_id, clean_session=True)
        
        # 设置回调函数
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.client.on_log = self.on_log
        
        # 设置用户名和密码
        if self.mqtt_username and self.mqtt_password:
            self.client.username_pw_set(self.mqtt_username, self.mqtt_password)
        
        # 数据库连接维护配置
        self.db_maintenance_interval = 300  # 定期检查数据库连接的间隔（秒）
        self.db_maintenance_thread = None
        self.db_maintenance_running = False
    
    def on_connect(self, client, userdata, flags, rc):
        """连接到MQTT代理后的回调函数"""
        if rc == 0:
            logger.info(f"成功连接到MQTT代理: {self.mqtt_broker}:{self.mqtt_port}")
            # 订阅主题，使用配置的QoS
            client.subscribe(self.mqtt_topic, qos=self.qos)
            logger.info(f"已订阅主题: {self.mqtt_topic} (QoS: {self.qos})")
        else:
            logger.error(f"连接到MQTT代理失败，返回代码: {rc}")
    
    def _safe_json_parse(self, json_str):
        """增强的JSON解析功能，专门处理格式错误的JSON字符串"""
        try:
            # 尝试直接解析
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {str(e)}，消息内容前200字节: {json_str[:200]}")
            logger.error(f"错误位置上下文: '{json_str[max(0, e.pos-20):e.pos+20]}' (位置: {e.pos})")
            
            # 1. 尝试使用简单的修复方法 - 专注于已知的问题点
            try:
                # 直接使用手动解析方法，因为这是最可靠的方式
                # 从日志中我们知道消息格式是相对固定的
                
                # 提取device_id（格式如"9-1-31-3104"）
                device_id_match = re.search(r'\"([0-9\-]+)\"\s*:\s*\{', json_str)
                if not device_id_match:
                    raise ValueError("无法提取device_id")
                device_id = device_id_match.group(1)
                logger.info(f"提取到device_id: {device_id}")
                
                # 提取PLC IP地址
                plc_ip_match = re.search(r'\"PLC IP地址\"\s*:\s*\"([^\"]*)\"', json_str)
                plc_ip = plc_ip_match.group(1) if plc_ip_match else "未知"
                logger.debug(f"提取到PLC IP地址: {plc_ip}")
                
                # 提取total_hot_quantity相关信息
                hot_value_match = re.search(r'\"total_hot_quantity\"\s*:\s*\{[^}]*\"value\"\s*:\s*([^,}]*)', json_str)
                hot_success_match = re.search(r'\"total_hot_quantity\"\s*:\s*\{[^}]*\"success\"\s*:\s*([^,}]*)', json_str)
                hot_message_match = re.search(r'\"total_hot_quantity\"\s*:\s*\{[^}]*\"message\"\s*:\s*\"([^\"]*)\"', json_str)
                
                # 提取total_cold_quantity相关信息
                cold_value_match = re.search(r'\"total_cold_quantity\"\s*:\s*\{[^}]*\"value\"\s*:\s*([^,}]*)', json_str)
                cold_success_match = re.search(r'\"total_cold_quantity\"\s*:\s*\{[^}]*\"success\"\s*:\s*([^,}]*)', json_str)
                cold_message_match = re.search(r'\"total_cold_quantity\"\s*:\s*\{[^}]*\"message\"\s*:\s*\"([^\"]*)\"', json_str)
                
                # 提取时间戳
                timestamp_match = re.search(r'\"timestamp\"\s*:\s*\"([^\"]*)\"', json_str)
                timestamp = timestamp_match.group(1) if timestamp_match else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # 构建完整的结果字典
                manual_result = {
                    device_id: {
                        "PLC IP地址": plc_ip,
                        "data": {}
                    }
                }
                
                # 添加制热数据
                if hot_value_match:
                    hot_value = hot_value_match.group(1).strip()
                    manual_result[device_id]["data"]["total_hot_quantity"] = {
                        "value": None if hot_value == "null" else int(hot_value) if hot_value.isdigit() else hot_value,
                        "success": hot_success_match and hot_success_match.group(1).strip() == "true",
                        "message": hot_message_match.group(1) if hot_message_match else "",
                        "timestamp": timestamp
                    }
                    logger.debug(f"提取到制热数据: value={manual_result[device_id]['data']['total_hot_quantity']['value']}, success={manual_result[device_id]['data']['total_hot_quantity']['success']}")
                
                # 添加制冷数据
                if cold_value_match:
                    cold_value = cold_value_match.group(1).strip()
                    manual_result[device_id]["data"]["total_cold_quantity"] = {
                        "value": None if cold_value == "null" else int(cold_value) if cold_value.isdigit() else cold_value,
                        "success": cold_success_match and cold_success_match.group(1).strip() == "true",
                        "message": cold_message_match.group(1) if cold_message_match else "",
                        "timestamp": timestamp
                    }
                    logger.debug(f"提取到制冷数据: value={manual_result[device_id]['data']['total_cold_quantity']['value']}, success={manual_result[device_id]['data']['total_cold_quantity']['success']}")
                
                logger.debug("成功通过手动解析构建JSON数据")
                return manual_result
                
            except Exception as e:
                logger.error(f"手动解析过程中发生错误: {str(e)}")
                
                # 作为最后的备选方案，尝试直接从字符串中提取关键信息
                try:
                    # 最简单的方法：只提取我们真正需要的数据
                    device_id = re.search(r'\"([0-9\-]+)\"\s*:\s*\{', json_str)
                    if device_id:
                        device_id = device_id.group(1)
                        # 返回一个最小化但可用的结构
                        minimal_result = {
                            device_id: {
                                "PLC IP地址": "手动解析",
                                "data": {
                                    "total_hot_quantity": {"value": 0, "success": False},
                                    "total_cold_quantity": {"value": 0, "success": False}
                                }
                            }
                        }
                        logger.warning(f"返回最小化结构: device_id={device_id}")
                        return minimal_result
                except Exception:
                    logger.error("最小化解析也失败")
            
            # 所有修复尝试都失败
            logger.error("所有JSON解析修复尝试都失败")
            raise
    
    def on_message(self, client, userdata, msg):
        """收到MQTT消息后的回调函数"""
        try:
            logger.info(f"收到消息: 主题={msg.topic}, 长度={len(msg.payload)}字节, QoS={msg.qos}, 保留={msg.retain}")
            
            # 先解码消息负载
            payload_str = None
            try:
                # 尝试UTF-8解码，如果失败尝试其他编码
                try:
                    payload_str = msg.payload.decode('utf-8')
                except UnicodeDecodeError:
                    # 尝试Latin-1作为备选编码
                    payload_str = msg.payload.decode('latin-1')
                
                logger.debug(f"消息内容: {payload_str[:500]}{'...' if len(payload_str) > 500 else ''}")
            except UnicodeDecodeError as e:
                logger.error(f"消息解码错误: {e}，原始字节: {str(msg.payload[:100])}")
                return
            
            # 使用安全的JSON解析方法
            try:
                payload = self._safe_json_parse(payload_str)
                logger.debug(f"成功解析JSON，数据类型: {type(payload).__name__}")
                
                # 处理消息
                self.process_message(msg.topic, payload)
                
            except json.JSONDecodeError as e:
                # 确保payload_str已定义
                content_preview = payload_str[:200] if payload_str else "无法解码"
                logger.error(f"JSON解析错误: {e}，消息内容前200字节: {content_preview}")
                # 尝试找出错误位置附近的字符
                error_pos = min(e.pos, len(payload_str)-1) if payload_str and hasattr(e, 'pos') else 0
                context_start = max(0, error_pos - 20)
                context_end = min(len(payload_str), error_pos + 20) if payload_str else 0
                if payload_str:
                    logger.error(f"错误位置上下文: '{payload_str[context_start:context_end]}' (位置: {error_pos})")
                    # 记录完整的消息内容用于调试
                    logger.debug(f"完整消息内容: {payload_str}")
            
        except Exception as e:
            logger.error(f"处理消息时发生意外错误: {e}", exc_info=True)
    
    def on_disconnect(self, client, userdata, rc):
        """与MQTT代理断开连接后的回调函数"""
        if rc != 0:
            logger.warning(f"意外断开与MQTT代理的连接，返回代码: {rc}")
        else:
            logger.info("已断开与MQTT代理的连接")
    
    def on_log(self, client, userdata, level, buf):
        """MQTT日志回调函数"""
        # 可以根据需要调整日志级别
        if level == mqtt.MQTT_LOG_ERR:
            logger.error(f"MQTT错误: {buf}")
        elif level == mqtt.MQTT_LOG_WARNING:
            logger.warning(f"MQTT警告: {buf}")
        elif level == mqtt.MQTT_LOG_INFO:
            logger.info(f"MQTT信息: {buf}")
        elif level == mqtt.MQTT_LOG_DEBUG and settings.DEBUG:
            logger.debug(f"MQTT调试: {buf}")
    
    def process_message(self, topic, payload):
        """处理接收到的消息并保存到数据库"""
        logger.debug(f"开始处理消息: 主题={topic}, 消息大小={len(str(payload))}字节")
        
        max_retries = 3  # 最大重试次数
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                logger.debug(f" 开始处理消息内容: 主题={topic}, 重试次数={retry_count}")
                
                # 从topic中提取楼栋文件名（如果存在）
                building_file = None
                topic_parts = topic.split('/')
                logger.debug(f"主题解析: 部分数量={len(topic_parts)}, 内容={topic_parts}")
                
                if len(topic_parts) > 4:
                    building_file = topic_parts[4]  # 假设格式为 /datacollection/plc/to/collector/[building_file]
                    logger.debug(f"从主题提取楼栋文件名: {building_file}")
                
                # 收集所有数据点
                batch_data = []
                
                # 处理不同格式的消息
                if isinstance(payload, dict):
                    logger.debug(f"处理字典类型消息，包含键: {list(payload.keys())}")
                    
                    # 检查是否是improved_data_collection_manager.py发送的数据格式：{device_id: device_info}
                    # 这种格式的特点是：只有一个键，且键名可能是房间标识（如9-1-31-3104）
                    if len(payload) == 1 and not any(key in ['data', 'device_id', 'param_key', 'results'] for key in payload.keys()):
                        device_id = list(payload.keys())[0]
                        device_info = payload[device_id]
                        logger.debug(f"处理improved_data_collection_manager发送的数据格式: device_id={device_id}")
                        
                        # device_id就是PLCData的specific_part
                        specific_part = device_id
                        plc_ip = device_info.get('PLC IP地址', '') or device_info.get('IP地址', '')
                        logger.debug(f"提取信息: specific_part={specific_part}, plc_ip={plc_ip}")
                        
                        # 检查是否包含data字段
                        if 'data' in device_info and isinstance(device_info['data'], dict):
                            logger.debug(f"处理data字段，包含{len(device_info['data'])}个数据项")
                            
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
                                        logger.warning(f"跳过失败的数据: specific_part={specific_part}, param_key={param_key}, message={message}")
                                        continue
                                    
                                    # 处理success为true的数据
                                    logger.debug(f"处理数据项: param_key={param_key}, 数据={param_data}")
                                    
                                    # 映射参数名到energy_mode
                                    energy_mode = param_to_energy_mode.get(param_key, param_key)
                                    logger.debug(f"参数映射: {param_key} -> {energy_mode}")
                                    
                                    # 构建数据点
                                    data_point = {
                                        'specific_part': specific_part,
                                        'energy_mode': energy_mode,
                                        'plc_ip': plc_ip,
                                        'param_value': param_data.get('value'),
                                        'success': success,
                                        'message': param_data.get('message', ''),
                                        'timestamp': param_data.get('timestamp')  # 传递timestamp
                                    }
                                    
                                    # 添加到批量数据列表
                                    batch_data.append(data_point)
                            
                            logger.debug(f"improved_data_collection_manager数据处理完成，收集了{len(batch_data)}个数据点")
                        else:
                            logger.warning(f"device_info中未找到data字段或data不是字典类型: {device_info}")
                    # 检查是否是新格式的消息，包含data字段
                    elif 'data' in payload and isinstance(payload['data'], dict):
                        logger.debug(f"处理新格式消息: 包含data字段，data包含{len(payload['data'])}个数据项")
                        # 提取房间信息
                        specific_part = None
                        building = ''
                        unit = ''
                        room_number = ''
                        plc_ip = ''
                        
                        # 尝试从不同字段获取specific_part
                        if '专有部分坐落' in payload:
                            logger.debug(f"从'专有部分坐落'字段提取信息: {payload['专有部分坐落']}")
                            # 从专有部分坐落提取（格式：成都乐府（二仙桥）-9-1-3104）
                            location_parts = payload['专有部分坐落'].split('-')
                            logger.debug(f"专有部分坐落解析: 部分数量={len(location_parts)}, 内容={location_parts}")
                            if len(location_parts) >= 4:
                                specific_part = f"{location_parts[1]}-{location_parts[2]}-{location_parts[3]}"
                                logger.debug(f"成功解析specific_part: {specific_part}")
                        
                        # 如果没有专有部分坐落，尝试从键名获取（例如："9-1-31-3104"）
                        if not specific_part and topic_parts and len(topic_parts) > 4:
                            possible_key = topic_parts[4]
                            if '-' in possible_key:
                                specific_part = possible_key
                                logger.debug(f"从主题获取specific_part: {specific_part}")
                        
                        # 获取楼栋、单元、房号信息
                        if '楼栋' in payload:
                            building = payload['楼栋'].replace('栋', '')
                            logger.debug(f"从'楼栋'字段提取: {building}")
                        if '单元' in payload:
                            unit = payload['单元'].replace('单元', '')
                            logger.debug(f"从'单元'字段提取: {unit}")
                        if '户号' in payload:
                            room_number = str(payload['户号'])
                            logger.debug(f"从'户号'字段提取: {room_number}")
                        
                        # 获取PLC IP地址
                        if 'PLC IP地址' in payload:
                            plc_ip = payload['PLC IP地址']
                            logger.debug(f"从'PLC IP地址'字段提取: {plc_ip}")
                        elif 'IP地址' in payload:
                            plc_ip = payload['IP地址']
                            logger.debug(f"从'IP地址'字段提取: {plc_ip}")
                        
                        logger.debug(f"解析完成: specific_part={specific_part}, building={building}, unit={unit}, room_number={room_number}, plc_ip={plc_ip}")
                        
                        # 处理data字段中的各项数据
                        for energy_mode, mode_data in payload['data'].items():
                            if isinstance(mode_data, dict):
                                logger.debug(f"处理data项: energy_mode={energy_mode}, 数据={mode_data}")
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
                                    'timestamp': mode_data.get('timestamp')  # 传递timestamp
                                }
                                # 添加到批量数据列表
                                batch_data.append(data_point)
                        logger.debug(f"新格式消息处理完成，收集了{len(batch_data)}个数据点")
                    # 检查是否是单个PLC数据点
                    elif 'device_id' in payload and 'param_key' in payload:
                        logger.debug(f"处理单个PLC数据点: device_id={payload['device_id']}, param_key={payload['param_key']}")
                        # 添加到批量数据列表
                        batch_data.append(payload)
                    # 检查是否包含多个结果的列表
                    elif 'results' in payload and isinstance(payload['results'], list):
                        result_count = len(payload['results'])
                        logger.debug(f"处理结果列表，共{result_count}个项目")
                        for i, result in enumerate(payload['results']):
                            logger.debug(f"处理结果项[{i}]: {result}")
                            # 添加到批量数据列表
                            batch_data.append(result)
                    # 检查是否直接是数据点列表（旧格式）
                    elif all(isinstance(item, dict) for item in payload.values()):
                        device_count = len(payload)
                        logger.debug(f"处理旧格式数据点列表，共{device_count}个设备")
                        for device_id, device_data in payload.items():
                            if isinstance(device_data, dict):
                                param_count = len(device_data)
                                logger.debug(f"处理设备数据: device_id={device_id}, 包含{param_count}个参数")
                                # 检查是否是新格式的数据结构
                                if 'data' in device_data and isinstance(device_data['data'], dict):
                                    # 处理嵌套的data结构
                                    specific_part = device_id
                                    plc_ip = (device_data.get('PLC IP地址', '') or 
                                              device_data.get('IP地址', ''))
                                    logger.debug(f"嵌套data结构: specific_part={specific_part}, "
                                                f"plc_ip={plc_ip}")
                                    
                                    for energy_mode, mode_data in device_data['data'].items():
                                        if isinstance(mode_data, dict):
                                            logger.debug(f"处理嵌套data项: energy_mode={energy_mode}")
                                            data_point = {
                                                'specific_part': specific_part,
                                                'energy_mode': energy_mode,
                                                'plc_ip': plc_ip,
                                                'param_value': mode_data.get('value'),
                                                'success': mode_data.get('success', False),
                                                'message': mode_data.get('message', ''),
                                                'timestamp': mode_data.get('timestamp')  # 传递timestamp
                                            }
                                            # 添加到批量数据列表
                                            batch_data.append(data_point)
                                else:
                                    # 处理旧格式的数据结构
                                    for param_key, param_value in device_data.items():
                                        logger.debug(f"处理旧格式参数: param_key={param_key}")
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
                    logger.debug(f"处理列表类型消息，共{len(payload)}个项目")
                    for i, item in enumerate(payload):
                        if isinstance(item, dict):
                            logger.debug(f"处理列表项[{i}]: {item}")
                            # 添加到批量数据列表
                            batch_data.append(item)
                        else:
                            logger.warning(f"列表项[{i}]不是字典类型: {type(item)}")
                else:
                    logger.warning(f"未知的消息格式: {type(payload).__name__}")
                
                # 批量保存所有数据点
                if batch_data:
                    logger.debug(f"准备批量保存 {len(batch_data)} 个数据点")
                    self.batch_save_plc_data(batch_data, building_file)
                else:
                    logger.warning(f"没有数据点需要保存: 主题={topic}")
                
                # 处理成功
                logger.info(f"✅ 消息处理完成: 主题={topic}")
                break  # 成功处理，跳出循环
                
            except (MySQLdb.OperationalError, MySQLdb.InterfaceError, 
                    DjangoOperationalError, ConnectionResetError, 
                    ConnectionAbortedError, BrokenPipeError) as e:
                error_msg = str(e)
                logger.error(f"❌ 数据库操作错误: {error_msg}")
                logger.debug(f"当前连接状态: connection_id={id(django_connection)}")
                # 如果是连接已断开的错误，尝试重新连接
                if ('2006' in error_msg \
                        or 'server has gone away' in error_msg.lower() \
                        or 'connection reset by peer' in error_msg.lower()
                        or 'broken pipe' in error_msg.lower()
                        or 'connection aborted' in error_msg.lower()
                        or isinstance(e, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError))):
                    retry_count += 1
                    if retry_count <= max_retries:
                        logger.warning(f"🔄 数据库连接已断开，尝试重新连接并重试消息处理... (重试 {retry_count}/{max_retries})")
                        logger.debug(f"重试前连接状态: connection_id={id(django_connection)}")
                        # 尝试重新连接
                        if self._check_and_reconnect_db(with_diagnostic=False):
                            logger.info("✅ 数据库连接已重新建立，准备重试消息处理")
                            logger.debug(f"重连后连接状态: connection_id={id(django_connection)}")
                            # 等待一小段时间确保连接稳定
                            time.sleep(0.5)
                            continue  # 重试当前消息
                        else:
                            logger.error("❌ 数据库重新连接失败")
                    else:
                        logger.error("❌ 达到最大重试次数，放弃处理此消息")
                else:
                    logger.error("❌ 非连接类数据库错误，不重试")
                break  # 跳出循环
            
            except Exception as e:
                # 处理其他错误
                logger.error(f"处理消息时发生错误: {e}", exc_info=True)
                break  # 跳出循环
    
    def _check_and_reconnect_db(self, with_diagnostic=True):
        """检查数据库连接并在需要时重新连接，增强版包含重试机制和完整连接重置"""
        max_reconnect_attempts = 3  # 保持足够的重试次数
        reconnect_delay = 1  # 保持合适的初始重连延迟
        
        logger.debug(f"开始检查数据库连接状态，当前线程ID: {threading.get_ident()}")
        logger.debug(f"初始连接状态: connection_id={id(django_connection)}")
        
        def is_connection_valid():
            """更彻底地检查连接有效性，包括实际执行SQL查询"""
            try:
                django_connection.ensure_connection()
                # 执行一个简单的SQL查询来验证连接是否真正可用
                with django_connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    logger.debug(f"连接验证查询结果: {result}")
                    
                    # 获取连接ID信息
                    cursor.execute("SELECT CONNECTION_ID()")
                    connection_id = cursor.fetchone()[0]
                    logger.debug(f"数据库连接ID: {connection_id}")
                logger.info(f"✓ 数据库连接正常 [ID: {id(django_connection)}, DB ID: {connection_id}]")
                return True
            except Exception as e:
                logger.debug(f"连接验证失败: {e}")
                return False
        
        for attempt in range(max_reconnect_attempts):
            try:
                if is_connection_valid():
                    return True
                
                logger.error(f"✗ 数据库连接检查失败 (尝试 {attempt+1}/{max_reconnect_attempts})")
                
                if attempt == max_reconnect_attempts - 1:
                    # 最后一次尝试失败
                    logger.warning("✗ 所有数据库连接检查尝试都失败，准备强制重建连接")
                    break
                
                # 等待后重试
                wait_time = reconnect_delay * (2 ** attempt)
                logger.debug(f"⏱ 等待 {wait_time} 秒后尝试重新检查数据库连接...")
                time.sleep(wait_time)
            except Exception as e:
                logger.error(f"连接检查尝试中发生错误: {e}")
                if attempt == max_reconnect_attempts - 1:
                    logger.warning("✗ 所有数据库连接检查尝试都失败，准备强制重建连接")
                    break
                wait_time = reconnect_delay * (2 ** attempt)
                logger.debug(f"⏱ 等待 {wait_time} 秒后尝试重新检查数据库连接...")
                time.sleep(wait_time)
        
        try:
            # 1. 关闭旧连接
            logger.info("🔄 正在关闭旧的数据库连接...")
            old_connection_id = id(django_connection)
            logger.debug(f"旧连接ID: {old_connection_id}")
            django_connection.close()
            logger.info(f"✅ 已关闭旧的数据库连接 [ID: {old_connection_id}]")
            
            # 2. 清除连接状态，确保完全重置
            if hasattr(django_connection, '_cursor') and django_connection._cursor:
                logger.debug("关闭并重置连接游标...")
                django_connection._cursor.close()
                django_connection._cursor = None
                logger.debug("✅ 游标已重置")
            
            # 3. 清除连接池中的其他可能失效连接
            if hasattr(django_connection, '_connections'):
                conn_count = len(django_connection._connections)
                django_connection._connections.clear()
                logger.debug(f"✅ 已清除连接池中的 {conn_count} 个连接")
            
            # 4. 延迟一下，给数据库服务器时间处理连接关闭
            logger.debug("等待数据库服务器处理连接关闭...")
            time.sleep(0.5)
            
            # 5. 尝试重新建立连接
            logger.info("🔄 正在尝试重新建立数据库连接...")
            django_connection.connect()
            new_connection_id = id(django_connection)
            logger.info(f"✅ 数据库连接已成功重新建立 [新ID: {new_connection_id}]")
            
            # 6. 验证新连接是否真正可用
            logger.debug("验证新连接有效性...")
            if is_connection_valid():
                logger.info("✅ 新连接验证成功")
            else:
                logger.error("❌ 新连接验证失败")
                return False
            
            # 7. 可选的诊断功能（仅在调试模式下或显式请求时启用）
            if with_diagnostic and settings.DEBUG:
                try:
                    logger.debug("🔍 正在使用原始MySQLdb连接进行诊断...")
                    db_config = settings.DATABASES['default']
                    
                    direct_conn = MySQLdb.connect(
                        host=db_config['HOST'],
                        port=int(db_config['PORT']) if db_config['PORT'] else 3306,
                        user=db_config['USER'],
                        password=db_config['PASSWORD'],
                        database=db_config['NAME'],
                        charset=db_config.get('OPTIONS', {}).get('charset', 'utf8')
                    )
                    direct_conn.ping()
                    direct_conn.close()
                    logger.debug("✅ 原始MySQLdb连接诊断成功")
                except Exception as diag_error:
                    logger.debug(f"⚠️ 原始MySQLdb连接诊断失败: {diag_error}")
            
            return True
            
        except Exception as re_conn_error:
            logger.error(f"✗ 数据库重新连接失败: {re_conn_error}", exc_info=True)
            
            # 仅在调试模式下进行详细诊断
            if with_diagnostic and settings.DEBUG:
                try:
                    logger.debug("🔍 正在进行详细的数据库连接诊断...")
                    from django.conf import settings
                    db_config = settings.DATABASES['default']
                    
                    direct_conn = MySQLdb.connect(
                        host=db_config['HOST'],
                        port=int(db_config['PORT']) if db_config['PORT'] else 3306,
                        user=db_config['USER'],
                        password=db_config['PASSWORD'],
                        database=db_config['NAME'],
                        charset=db_config.get('OPTIONS', {}).get('charset', 'utf8')
                    )
                    direct_conn.ping()
                    direct_conn.close()
                    logger.debug("✅ 原始MySQLdb连接成功，问题可能出在Django连接管理上")
                except Exception as diag_error:
                    logger.error(f"✗ 原始MySQLdb连接诊断失败: {diag_error}", exc_info=True)
                    logger.error("✗ 数据库连接问题可能与网络、认证或数据库服务器配置有关")
                
            return False
    
    def _db_maintenance_thread(self):
        """数据库连接维护线程，定期检查连接可用性"""
        logger.info(f"启动数据库连接维护线程，间隔 {self.db_maintenance_interval} 秒")
        
        while self.db_maintenance_running:
            try:
                logger.debug("执行定期数据库连接检查...")
                # 执行简单的连接检查
                with django_connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                logger.debug(f"定期连接检查结果: {result}")
                
            except (MySQLdb.OperationalError, MySQLdb.InterfaceError, 
                    DjangoOperationalError, ConnectionResetError, 
                    ConnectionAbortedError, BrokenPipeError) as e:
                error_msg = str(e)
                logger.error(f"定期数据库连接检查失败: {error_msg}")
                # 尝试重新连接
                logger.warning("🔄 定期检查发现连接断开，尝试重新连接...")
                self._check_and_reconnect_db(with_diagnostic=False)
            
            except Exception as e:
                logger.error(f"定期数据库连接检查发生未知错误: {e}")
            
            # 等待下一次检查
            for _ in range(self.db_maintenance_interval):
                if not self.db_maintenance_running:
                    break
                time.sleep(1)
        
        logger.info("数据库连接维护线程已停止")


    
    def batch_save_plc_data(self, batch_data, building_file=None):
        """批量保存PLC数据点到数据库"""
        if not batch_data:
            logger.warning("没有数据点需要保存")
            return
        
        logger.debug(f"开始批量保存PLC数据点，共{len(batch_data)}个数据点，building_file={building_file}")
        
        # 数据解析部分，解析所有数据点
        parsed_data = []
        valid_data_count = 0
        
        try:
            for data_point in batch_data:
                logger.debug(f"解析数据点原始内容: {data_point}")
                
                # 获取必要字段，支持新旧字段名称
                specific_part = (data_point.get('specific_part') or 
                               data_point.get('device_id'))
                energy_mode = (data_point.get('energy_mode') or 
                             data_point.get('param_key'))

                logger.debug(f"提取关键字段: specific_part={specific_part}, "
                            f"energy_mode={energy_mode}")

                if not specific_part or not energy_mode:
                    logger.warning(f"缺少必要字段: specific_part={specific_part}, "
                                 f"energy_mode={energy_mode}")
                    continue

                # 获取数据点状态
                success = data_point.get('success', True)
                message = data_point.get('message', '')

                # 如果数据点不成功（连接失败等），记录日志但不保存
                if not success:
                    logger.warning(f"跳过失败的数据: {specific_part} - {energy_mode}, "
                                 f"消息: {message}")
                    continue

                # 获取楼栋、单元、房号信息 - 优先使用data_point中直接提供的
                building = data_point.get('building', '')
                unit = data_point.get('unit', '')
                room_number = data_point.get('room_number', '')

                logger.debug(f"直接提供的建筑信息: building={building}, unit={unit}, "
                            f"room_number={room_number}")

                # 如果没有直接提供，则尝试从specific_part解析
                if (not (building and unit and room_number) 
                        and '-' in specific_part):
                    logger.debug(f"尝试从specific_part解析建筑信息: {specific_part}")
                    parts = specific_part.split('-')
                    logger.debug(f"解析结果: 部分数量={len(parts)}, 内容={parts}")

                    # 处理不同格式：楼栋-单元-房号 或 楼栋-单元-楼层-房号
                    if len(parts) >= 3:
                        building = parts[0]
                        unit = parts[1]
                        if len(parts) >= 4:
                            # 格式：楼栋-单元-楼层-房号
                            room_number = parts[3]  # 使用房号部分
                            logger.debug(
                                f"解析为楼栋-单元-楼层-房号格式: building={building}, " 
                                f"unit={unit}, room_number={room_number}"
                            )
                        else:
                            # 格式：楼栋-单元-房号
                            room_number = parts[2]  # 使用第三部分作为房号
                            logger.debug(
                                f"解析为楼栋-单元-房号格式: building={building}, " 
                                f"unit={unit}, room_number={room_number}"
                            )

                # 准备数据
                plc_data = {
                    'specific_part': specific_part,
                    'building': building,
                    'unit': unit,
                    'room_number': room_number,
                    'energy_mode': energy_mode,
                    'value': (data_point.get('value') or 
                             data_point.get('param_value')),
                    'plc_ip': data_point.get('plc_ip')  # 从data_point获取plc_ip值
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
                                logger.debug(f"从timestamp提取日期: {timestamp} -> {parsed_date.date()}")
                            else:
                                logger.warning(f"无法解析timestamp格式: {timestamp}")
                    except Exception as e:
                        logger.error(f"处理timestamp时发生错误: {e}")

                # 如果没有设置usage_date，使用当前日期作为默认值
                if not usage_date_set:
                    default_date = datetime.now().date()
                    plc_data['usage_date'] = default_date
                    logger.debug(f"未提供有效的timestamp，使用默认日期: {default_date}")

                logger.debug(f"准备保存的数据: {plc_data}")
                
                # 添加到解析后的数据集
                parsed_data.append(plc_data)
                valid_data_count += 1
            
            if not parsed_data:
                logger.warning("没有有效数据点需要保存")
                return
            
            logger.debug(f"数据解析完成，有效数据点数量: {valid_data_count}")
            
        except Exception as e:
            logger.error(f"解析PLC数据时发生错误: {e}", exc_info=True)
            return
        
        # 数据库批量操作
        try:
            # 操作前检查并确保数据库连接可用
            logger.debug("操作前检查数据库连接...")
            logger.debug(f"线程ID: {threading.get_ident()}, 连接状态: connection_id={id(django_connection)}")
            
            # 更严格的连接检查：先确保连接存在，然后执行一个简单查询验证
            logger.debug("执行ensure_connection()检查...")
            django_connection.ensure_connection()
            logger.debug(f"ensure_connection()完成，新连接状态: connection_id={id(django_connection)}")
            
            # 执行SELECT 1验证连接是否真正可用
            logger.debug("执行SELECT 1验证连接...")
            with django_connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                logger.debug(f"连接验证查询结果: {result}")
                
                # 获取数据库连接ID
                cursor.execute("SELECT CONNECTION_ID()")
                db_connection_id = cursor.fetchone()[0]
                logger.debug(f"数据库服务器连接ID: {db_connection_id}")
            
            logger.info(f"数据库连接正常 [线程ID: {threading.get_ident()}, 连接ID: {id(django_connection)}, 数据库ID: {db_connection_id}]")
            
            # 使用事务确保数据库操作的原子性
            logger.debug("开始数据库事务")
            logger.debug(f"事务状态检查: in_atomic_block={transaction.get_connection().in_atomic_block}")
            
            try:
                with transaction.atomic():
                    logger.debug("事务已开始，设置保存点")
                    
                    # 1. 按唯一键（specific_part, energy_mode, usage_date）分组数据
                    unique_key_map = {}
                    for data in parsed_data:
                        key = (data['specific_part'], data['energy_mode'], data['usage_date'])
                        unique_key_map[key] = data
                    
                    logger.debug(f"按唯一键分组后的数据数量: {len(unique_key_map)}")
                    
                    # 2. 批量查询现有记录
                    existing_records = PLCData.objects.filter(
                        specific_part__in=[k[0] for k in unique_key_map.keys()],
                        energy_mode__in=[k[1] for k in unique_key_map.keys()],
                        usage_date__in=[k[2] for k in unique_key_map.keys()]
                    )
                    
                    logger.debug(f"查询到的现有记录数量: {len(existing_records)}")
                    
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
                    
                    logger.debug(f"需要插入的记录数量: {len(to_create)}, 需要更新的记录数量: {len(to_update)}")
                    
                    # 5. 执行批量操作
                    if to_create:
                        PLCData.objects.bulk_create(to_create)
                        logger.info(f"✅ 批量插入完成，共{len(to_create)}条记录")
                    
                    if to_update:
                        # 只更新需要修改的字段
                        update_fields = ['value', 'building', 'unit', 'room_number', 'plc_ip', 'updated_at']
                        PLCData.objects.bulk_update(to_update, update_fields)
                        
                        # 记录更新详情
                        for i, (old_value, new_value) in enumerate(update_values):
                            record = to_update[i]
                            logger.info(f"✅ 更新现有PLC数据记录: {record.specific_part} - {record.energy_mode}, " 
                                      f"旧值={old_value}, 新值={new_value}")
                    
                logger.debug("事务已成功提交")
                logger.info(f"✅ 批量保存完成，处理了{valid_data_count}个有效数据点")
                
            except Exception as e:
                logger.debug(f"事务执行失败，检查事务状态: in_atomic_block={transaction.get_connection().in_atomic_block}")
                # 确保事务状态被正确重置
                if transaction.get_connection().in_atomic_block:
                    logger.debug("手动回滚事务")
                    transaction.rollback()
                    logger.debug("手动回滚完成")
                raise

        except (MySQLdb.OperationalError, MySQLdb.InterfaceError, 
                DjangoOperationalError, ConnectionResetError, 
                ConnectionAbortedError, BrokenPipeError) as e:
            # 捕获数据库操作错误，尝试重连
            error_msg = str(e)
            logger.error(f"❌ 数据库批量操作错误: {error_msg}")
            
            # 检查最终事务状态
            final_transaction_state = transaction.get_connection().in_atomic_block
            logger.debug(f"最终事务状态: in_atomic_block={final_transaction_state}")
            
            # 如果是连接相关的错误，尝试重新连接
            if ('2006' in error_msg or 'server has gone away' in error_msg.lower() 
                    or 'connection reset by peer' in error_msg.lower()
                    or 'broken pipe' in error_msg.lower()
                    or 'connection aborted' in error_msg.lower()
                    or isinstance(e, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError))):
                logger.warning("🔄 数据库连接已断开，尝试重新连接...")
                self._check_and_reconnect_db()
            raise
        except Exception as e:
            # 检查最终事务状态
            final_transaction_state = transaction.get_connection().in_atomic_block
            logger.debug(f"未知错误最终事务状态: in_atomic_block={final_transaction_state}")
            logger.error(f"批量保存PLC数据时发生未知错误: {e}", exc_info=True)
            raise
    
    def save_single_plc_data(self, data_point, building_file=None):
        """保存单个PLC数据点到数据库（保留接口兼容）"""
        self.batch_save_plc_data([data_point], building_file)
    
    def connect(self):
        """连接到MQTT代理"""
        try:
            logger.info(f"正在连接到MQTT代理: {self.mqtt_broker}:{self.mqtt_port}")
            
            # 如果启用了TLS，则配置TLS
            if self.tls_enabled:
                logger.info("启用TLS连接")
                # 可以根据需要添加ca_certs、certfile、keyfile等参数
                self.client.tls_set()
            
            # 连接到MQTT代理
            self.client.connect(self.mqtt_broker, self.mqtt_port, self.keepalive)
            return True
        except Exception as e:
            logger.error(f"连接到MQTT代理失败: {e}")
            return False
    
    def start(self):
        """启动MQTT客户端循环"""
        try:
            if not self.connect():
                return False
            
            logger.info("启动MQTT客户端循环")
            # 使用loop_start()在后台线程中运行MQTT客户端
            self.client.loop_start()
            
            # 启动数据库连接维护线程
            self.db_maintenance_running = True
            self.db_maintenance_thread = threading.Thread(target=self._db_maintenance_thread, daemon=True)
            self.db_maintenance_thread.start()
            
            return True
        except Exception as e:
            logger.error(f"启动MQTT客户端时发生错误: {e}")
            return False
    
    def stop(self):
        """停止MQTT客户端"""
        try:
            logger.info("停止MQTT客户端")
            # 使用loop_stop()停止后台线程
            self.client.loop_stop()
            # 断开连接
            self.client.disconnect()
            
            # 停止数据库连接维护线程
            logger.info("停止数据库连接维护线程")
            self.db_maintenance_running = False
            if self.db_maintenance_thread:
                self.db_maintenance_thread.join(timeout=5)  # 添加超时防止阻塞
                if self.db_maintenance_thread.is_alive():
                    logger.warning("数据库连接维护线程未能在超时内停止")
            
            return True
        except Exception as e:
            logger.error(f"停止MQTT客户端时发生错误: {e}")
            return False


# 创建全局MQTT客户端实例
mqtt_consumer = MQTTConsumer()


def start_mqtt_consumer():
    """启动MQTT消费者"""
    return mqtt_consumer.start()


def stop_mqtt_consumer():
    """停止MQTT消费者"""
    return mqtt_consumer.stop()

