import json
import os
import sys
import time
from typing import Dict, Any

# 系统模式常量定义
MODE_HOT = "hot"           # 制热模式
MODE_COLD = "cold"         # 制冷模式
MODE_WIND = "wind"         # 通风模式
MODE_DEHUMIDIFICATION = "dehumidification"  # 除湿模式

# 添加FreeArk目录到Python路径，确保模块可以正确导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入MQTT客户端
from datacollection.mqtt_client import MQTTClient
# 导入统一的日志配置管理器
from datacollection.log_config_manager import get_logger

# 获取logger
logger = get_logger('publish_system_mode')

class SystemModePublisher:
    """系统模式发布器，用于向MQTT服务器发送系统模式信息"""
    # 类变量，用于跟踪消息ID的自增
    _message_id_counter = 1
    
    def __init__(self, config_file: str = None):
        """
        初始化系统模式发布器
        
        参数:
        - config_file: MQTT配置文件路径，如果为None则使用默认路径
        """
        # 设置默认配置文件路径
        self.config_file = config_file or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'resource', 'mqtt_config.json'
        )
        # 加载配置
        self.config = self._load_config()
        # 打印加载的配置，用于调试
        logger.info(f"🔧 加载的配置内容: {self.config}")
        # MQTT客户端实例
        self.mqtt_client = None
    
    def _load_config(self) -> Dict[str, Any]:
        """从配置文件加载MQTT配置信息"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"✅ 成功加载配置文件: {self.config_file}")
            return config
        except Exception as e:
            logger.error(f"❌ 加载配置文件失败: {str(e)}")
            # 返回默认配置
            return {
                "host": "localhost",
                "port": 1883,
                "username": "",
                "password": "",
                "tls_enabled": False,
                "topic": "/system/mode",
                "qos": 1,
                "retain": False
            }
    
    def connect(self) -> bool:
        """连接到MQTT服务器"""
        try:
            # 创建MQTT客户端实例
            self.mqtt_client = MQTTClient(
                host=self.config.get('host', 'localhost'),
                port=self.config.get('port', 1883),
                username=self.config.get('username'),
                password=self.config.get('password'),
                tls_enabled=self.config.get('tls_enabled', False)
            )
            
            # 连接到MQTT服务器
            if self.mqtt_client.connect():
                logger.info(f"✅ 成功连接到MQTT服务器: {self.config.get('host')}:{self.config.get('port')}")
                return True
            else:
                logger.error(f"❌ 连接MQTT服务器失败: {self.config.get('host')}:{self.config.get('port')}")
                return False
        except Exception as e:
            logger.error(f"❌ 连接MQTT服务器异常: {str(e)}")
            return False
    
    def disconnect(self):
        """断开与MQTT服务器的连接"""
        if self.mqtt_client:
            try:
                self.mqtt_client.disconnect()
                logger.info("✅ 已断开与MQTT服务器的连接")
            except Exception as e:
                logger.error(f"❌ 断开MQTT连接异常: {str(e)}")
    
    def publish_system_mode(self, mode: str, identifier: str, device_sn: int = 21996, attrTag: str = "mode", product_code: str = "10016") -> bool:
        """
        发布系统模式信息到MQTT服务器
        
        参数:
        - mode: 系统模式，例如 "wind"
        - identifier: 作为订阅topic的后缀
        - device_sn: 设备序列号
        - product_code: 产品代码
        
        返回:
        - 是否发布成功
        """
        # 检查MQTT客户端是否已连接
        if not self.mqtt_client or not self.mqtt_client.connected:
            logger.error("❌ MQTT客户端未连接，无法发布消息")
            # 尝试重新连接
            if not self.connect():
                return False
        
        try:
            # 获取screenMac值
            screen_mac = self.config.get('screenMac', '9e1f3fca84e43404')
            
            # 获取当前消息ID并递增计数器
            message_id = str(SystemModePublisher._message_id_counter)
            SystemModePublisher._message_id_counter += 1
            
            # 构建消息体
            message = {
                "header": {
                    "ackCode": "0",
                    "messageId": message_id,  # 使用自增的消息ID
                    "name": "DeviceWrite",
                    "screenMac": screen_mac
                },
                "payload": {
                    "data": {
                        "deviceSn": device_sn,
                        "items": [{
                            "attrConstraint": 1,
                            "attrTag": attrTag,
                            "attrValue": mode
                        }],
                        "productCode": product_code,
                        # "systemFlag": 
                        "systemFlag": 2
                    }
                }
            }
            
            # 构建主题，将identifier作为后缀拼接
            base_topic = self.config.get('topic', '/system/mode')
            topic = f"{base_topic.rstrip('/')}/{identifier}"
            qos = self.config.get('qos', 1)
            retain = self.config.get('retain', False)
            
            # 发布消息
            success = self.mqtt_client.publish(topic, message, qos=qos, retain=retain)
            
            if success:
                logger.info(f"✅ 系统模式消息发布成功，模式: {mode}，主题: {topic}")
            else:
                logger.error(f"❌ 系统模式消息发布失败，模式: {mode}，主题: {topic}")
            
            return success
        except Exception as e:
            logger.error(f"❌ 发布系统模式消息异常: {str(e)}")
            return False

# 示例用法
if __name__ == "__main__":
    # 创建系统模式发布器实例
    publisher = SystemModePublisher()
    
    try:
        if publisher.connect():
            # 发布系统模式消息，添加identifier参数
            # 从配置中获取screenMac值并添加QoS后缀
            screen_mac = publisher.config.get('screenMac', '2860fae9a34ab8a9')
            identifier = f"{screen_mac}"  # 使用screenMac值，不添加QoS后缀
            publisher.publish_system_mode(MODE_WIND, identifier, 21996, "mode", "10016")
            publisher.publish_system_mode("no", identifier, 21997, "energy_supply_mode", "270001")
            
            # 等待消息发送完成
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("✅ 用户手动终止程序")
    finally:
        # 断开连接
        publisher.disconnect()