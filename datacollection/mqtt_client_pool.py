import threading
import time
import sys
import os
import threading
from queue import Queue
from typing import Optional, Dict, Any

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入统一的日志配置管理器
from datacollection.log_config_manager import get_logger

# 获取logger，日志级别从配置文件读取
logger = get_logger('mqtt_client')

from datacollection.mqtt_client import MQTTClient


class MQTTClientPool:
    def __init__(self, host: str, port: int, username: Optional[str] = None, 
                 password: Optional[str] = None, tls_enabled: bool = False, 
                 pool_size: int = 5, keep_alive: int = 60):
        """初始化MQTT客户端连接池"""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.tls_enabled = tls_enabled
        self.pool_size = pool_size
        self.keep_alive = keep_alive
        self.pool = Queue(maxsize=pool_size)
        self.lock = threading.Lock()
        self.created_clients = 0
        
    def get_client(self) -> MQTTClient:
        """从连接池获取或创建MQTT客户端"""
        # 尝试从池中获取可用客户端
        try:
            client = self.pool.get_nowait()
            # 检查连接是否有效
            if client.connected:
                return client
            else:
                # 重新连接
                if client.connect():
                    return client
                else:
                    # 连接失败，创建新客户端
                    return self._create_new_client()
        except:
            # 如果池为空且未达到最大连接数，创建新客户端
            with self.lock:
                if self.created_clients < self.pool_size:
                    return self._create_new_client()
            # 否则等待可用客户端
            return self.pool.get()
    
    def _create_new_client(self) -> MQTTClient:
        """创建新的MQTT客户端"""
        logger.info(f"创建新的MQTT客户端连接到 {self.host}:{self.port}")
        client = MQTTClient(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            tls_enabled=self.tls_enabled
        )
        if client.connect():
            self.created_clients += 1
            logger.info(f"成功创建MQTT客户端，当前活跃客户端数: {self.created_clients}/{self.pool_size}")
            return client
        else:
            # 如果连接失败，等待一小段时间后重试一次
            logger.warning(f"第一次尝试连接MQTT服务器失败，等待0.5秒后重试: {self.host}:{self.port}")
            time.sleep(0.5)
            if client.connect():
                self.created_clients += 1
                logger.info(f"重试后成功创建MQTT客户端: {self.host}:{self.port}")
                return client
            error_msg = f"Failed to connect to MQTT server: {self.host}:{self.port}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def return_client(self, client: MQTTClient):
        """将客户端归还池中"""
        try:
            # 确保客户端仍然连接
            if client.connected:
                self.pool.put_nowait(client)
            else:
                # 如果已断开连接，重新创建一个连接并放入池中
                try:
                    new_client = self._create_new_client()
                    self.pool.put_nowait(new_client)
                except:
                    # 如果创建失败，忽略错误
                    pass
                # 关闭旧客户端
                try:
                    client.disconnect()
                except:
                    pass
                with self.lock:
                    self.created_clients -= 1
        except:
            # 如果池已满，关闭客户端
            try:
                client.disconnect()
            except:
                pass
            with self.lock:
                self.created_clients -= 1
    
    def shutdown(self):
        """关闭连接池中的所有客户端"""
        logger.info(f"关闭MQTT客户端连接池，正在断开 {self.created_clients} 个客户端连接")
        with self.lock:
            closed_count = 0
            while not self.pool.empty():
                try:
                    client = self.pool.get_nowait()
                    client.disconnect()
                    closed_count += 1
                except Exception as e:
                    logger.error(f"关闭MQTT客户端时出错: {str(e)}")
            self.created_clients = 0
            logger.info(f"MQTT客户端连接池已关闭，共断开 {closed_count} 个客户端连接")


class MQTTClientManager:
    _instance = None
    _lock = threading.Lock()
    _config = None
    
    @classmethod
    def get_instance(cls, config: Optional[Dict[str, Any]] = None) -> MQTTClientPool:
        """获取连接池单例实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    if config:
                        cls._config = config
                        cls._instance = MQTTClientPool(
                            host=config.get('host', 'localhost'),
                            port=config.get('port', 1883),
                            username=config.get('username'),
                            password=config.get('password'),
                            tls_enabled=config.get('tls_enabled', False),
                            pool_size=config.get('pool_size', 5),
                            keep_alive=config.get('keep_alive', 60)
                        )
                    else:
                        raise ValueError("Initial configuration required for MQTTClientManager")
        elif config and config != cls._config:
            # 如果提供了不同的配置，关闭旧实例并创建新实例
            with cls._lock:
                if config != cls._config:
                    try:
                        cls._instance.shutdown()
                    except:
                        pass
                    cls._config = config
                    cls._instance = MQTTClientPool(
                        host=config.get('host', 'localhost'),
                        port=config.get('port', 1883),
                        username=config.get('username'),
                        password=config.get('password'),
                        tls_enabled=config.get('tls_enabled', False),
                        pool_size=config.get('pool_size', 5),
                        keep_alive=config.get('keep_alive', 60)
                    )
        return cls._instance
    
    @classmethod
    def shutdown(cls):
        """关闭管理器并释放资源"""
        with cls._lock:
            if cls._instance:
                try:
                    cls._instance.shutdown()
                except:
                    pass
                cls._instance = None
                cls._config = None