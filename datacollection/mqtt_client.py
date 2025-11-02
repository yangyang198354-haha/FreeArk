import paho.mqtt.client as mqtt
import json
import time
import os
import sys
from typing import Dict, Any, Callable, Optional

# 添加FreeArk目录到Python路径，确保模块可以正确导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入统一的日志配置管理器
from datacollection.log_config_manager import get_logger

# 导入paho.mqtt.client模块
import paho.mqtt.client as mqtt

# 获取logger，日志级别从配置文件读取
logger = get_logger('mqtt_client')

class MQTTClient:
    """MQTT客户端类，提供订阅和推送消息的基本方法"""
    def __init__(self, host: str, port: int = 1883, client_id: str = None, 
                 username: str = None, password: str = None, 
                 keepalive: int = 60, tls_enabled: bool = False):
        """
        初始化MQTT客户端
        
        参数:
        - host: MQTT服务器地址
        - port: MQTT服务器端口，默认为1883
        - client_id: 客户端ID，如果为None则自动生成
        - username: 用户名，如果需要认证
        - password: 密码，如果需要认证
        - keepalive: 保活时间，单位为秒
        - tls_enabled: 是否启用TLS加密
        """
        self.host = host
        self.port = port
        self.client_id = client_id or f"mqtt_client_{int(time.time())}"
        self.username = username
        self.password = password
        self.keepalive = keepalive
        self.tls_enabled = tls_enabled
        
        # 创建MQTT客户端实例
        self.client = mqtt.Client(client_id=self.client_id)
        
        # 设置回调函数
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish
        
        # 设置认证信息
        if username and password:
            self.client.username_pw_set(username, password)
        
        # 如果启用了TLS加密
        if tls_enabled:
            # 这里可以添加TLS相关的配置，如证书等
            pass
        
        # 连接状态
        self.connected = False
        
        # 用户定义的回调函数
        self.message_callback: Optional[Callable[[str, Dict], None]] = None
    
    def _on_connect(self, client, userdata, flags, rc):
        """连接回调函数"""
        if rc == 0:
            self.connected = True
            logger.info(f"✅ 成功连接到MQTT服务器: {self.host}:{self.port}")
        else:
            self.connected = False
            logger.info(f"❌ 连接MQTT服务器失败，返回代码: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """断开连接回调函数"""
        self.connected = False
        logger.info(f"🔌 已从MQTT服务器断开连接，返回代码: {rc}")
    
    def _on_message(self, client, userdata, msg):
        """接收消息回调函数"""
        try:
            # 尝试将消息负载解析为JSON
            payload = json.loads(msg.payload.decode('utf-8'))
            logger.info(f"📥 收到消息 - 主题: {msg.topic}, 负载: {payload}")
            
            # 调用用户定义的回调函数
            if self.message_callback:
                self.message_callback(msg.topic, payload)
        except json.JSONDecodeError:
            # 如果不是JSON格式，直接返回原始字符串
            payload = msg.payload.decode('utf-8')
            logger.info(f"📥 收到消息 - 主题: {msg.topic}, 负载(非JSON): {payload}")
            
            # 调用用户定义的回调函数
            if self.message_callback:
                self.message_callback(msg.topic, payload)
    
    def _on_publish(self, client, userdata, mid):
        """发布消息回调函数"""
        logger.info(f"📤 消息发布成功，消息ID: {mid}")
    
    def connect(self) -> bool:
        """连接到MQTT服务器"""
        try:
            self.client.connect(self.host, self.port, self.keepalive)
            # 启动一个线程来处理网络流量和回调
            self.client.loop_start()
            
            # 等待连接建立
            max_wait_time = 5  # 最大等待时间（秒）
            start_time = time.time()
            while not self.connected and time.time() - start_time < max_wait_time:
                time.sleep(0.1)
            
            return self.connected
        except Exception as e:
            logger.info(f"❌ 连接MQTT服务器异常: {str(e)}")
            return False
    
    def disconnect(self):
        """断开与MQTT服务器的连接"""
        try:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
            logger.info("✅ MQTT客户端已停止")
        except Exception as e:
            logger.info(f"❌ 断开MQTT连接异常: {str(e)}")
    
    def publish(self, topic: str, payload: Any, qos: int = 0, retain: bool = False) -> bool:
        """
        发布消息到指定主题
        
        参数:
        - topic: 主题名称
        - payload: 消息负载，可以是字符串、字典或列表
        - qos: 服务质量，可选值为0、1、2
        - retain: 是否保留消息
        
        返回:
        - 是否发布成功
        """
        if not self.connected:
            logger.info(f"❌ 发布消息失败: 未连接到MQTT服务器")
            return False
        
        try:
            # 如果payload是字典或列表，转换为JSON字符串
            if isinstance(payload, (dict, list)):
                payload_str = json.dumps(payload, ensure_ascii=False)
            else:
                payload_str = str(payload)
            
            # 发布消息
            result = self.client.publish(topic, payload_str, qos=qos, retain=retain)
            
            # 检查是否发布成功
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"📤 正在发布消息 - 主题: {topic}, QoS: {qos}")
                return True
            else:
                logger.info(f"❌ 发布消息失败，返回代码: {result.rc}")
                return False
        except Exception as e:
            logger.info(f"❌ 发布消息异常: {str(e)}")
            return False
    
    def subscribe(self, topic: str, qos: int = 0, callback: Optional[Callable[[str, Dict], None]] = None) -> bool:
        """
        订阅指定主题
        
        参数:
        - topic: 主题名称
        - qos: 服务质量，可选值为0、1、2
        - callback: 消息接收回调函数
        
        返回:
        - 是否订阅成功
        """
        if not self.connected:
            logger.info(f"❌ 订阅主题失败: 未连接到MQTT服务器")
            return False
        
        try:
            # 设置用户定义的回调函数（如果提供）
            if callback:
                self.message_callback = callback
            
            # 订阅主题
            result, mid = self.client.subscribe(topic, qos=qos)
            
            # 检查是否订阅成功
            if result == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"✅ 已订阅主题: {topic}, QoS: {qos}")
                return True
            else:
                logger.info(f"❌ 订阅主题失败，返回代码: {result}")
                return False
        except Exception as e:
            logger.info(f"❌ 订阅主题异常: {str(e)}")
            return False
    
    def unsubscribe(self, topic: str) -> bool:
        """
        取消订阅指定主题
        
        参数:
        - topic: 主题名称
        
        返回:
        - 是否取消订阅成功
        """
        if not self.connected:
            logger.info(f"❌ 取消订阅主题失败: 未连接到MQTT服务器")
            return False
        
        try:
            # 取消订阅
            result, mid = self.client.unsubscribe(topic)
            
            # 检查是否取消订阅成功
            if result == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"✅ 已取消订阅主题: {topic}")
                return True
            else:
                logger.info(f"❌ 取消订阅主题失败，返回代码: {result}")
                return False
        except Exception as e:
            logger.info(f"❌ 取消订阅主题异常: {str(e)}")
            return False

# 示例用法
if __name__ == "__main__":
    # 创建MQTT客户端实例
    mqtt_client = MQTTClient(
        host="localhost",
        port=1883,
        # username="admin",
        # password="password",
        tls_enabled=False
    )
    
    try:
        # 连接到MQTT服务器
        if mqtt_client.connect():
            # 订阅测试主题
            mqtt_client.subscribe("test/topic", qos=1)
            
            # 发布测试消息
            test_message = {"message": "Hello, MQTT!", "timestamp": int(time.time())}
            mqtt_client.publish("test/topic", test_message, qos=1)
            
            # 保持运行一段时间以接收消息
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("✅ 用户手动终止程序")
    finally:
        # 断开连接
        mqtt_client.disconnect()