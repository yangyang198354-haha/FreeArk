import snap7
import struct
import time
from typing import Optional

# --------------------------
# 配置参数
# --------------------------
PLC_IP = "192.168.3.27"  # PLC IP地址
PLC_PORT = 102  # S7协议默认端口
DB_START = 1  # 起始DB块号
DB_END = 1000  # 结束DB块号
READ_OFFSET = 0  # 固定读取偏移量
DATA_LENGTH = 4  # 浮点数占4字节（32位）
READ_INTERVAL = 5  # 轮询间隔（秒）


class M10S7Client:
    def __init__(self, plc_ip: str, plc_port: int = 102):
        self.plc_ip = plc_ip
        self.plc_port = plc_port
        self.client = snap7.client.Client()  # 初始化S7客户端
        self.connected = False

    def connect(self) -> bool:
        """连接M1.0 PLC"""
        try:
            self.client.connect(self.plc_ip, 0, 1, self.plc_port)  # 机架0、槽位1
            if self.client.get_connected():
                self.connected = True
                print(f"✅ 成功连接PLC（IP: {self.plc_ip}:{self.plc_port}）")
                return True
            return False
        except:
            return False

    def disconnect(self) -> None:
        """断开PLC连接"""
        if self.connected:
            self.client.disconnect()
            self.connected = False
            print(f"✅ 已断开与PLC的连接")

    def read_db_data(self, db_num: int, db_offset: int, data_len: int) -> Optional[bytes]:
        """读取指定DB块、偏移量的数据（不输出异常信息）"""
        if not self.connected:
            return None

        try:
            data = self.client.db_read(db_num, db_offset, data_len)
            return data if len(data) == data_len else None
        except:
            return None

    @staticmethod
    def parse_data(raw_data: bytes) -> Optional[float]:
        """解析32位浮点数数据（不输出异常信息）"""
        if len(raw_data) != 4:
            return None

        try:
            # 西门子PLC默认大端字节序，解析32位浮点数
            return round(struct.unpack('>f', raw_data)[0], 2)
        except:
            return None

    def read_db_range(self, start_db: int, end_db: int, offset: int) -> None:
        """按序号读取DB块范围数据，仅打印成功结果"""
        for db_num in range(start_db, end_db + 1):
            # 读取数据
            raw_data = self.read_db_data(db_num, offset, DATA_LENGTH)
            if not raw_data:
                continue  # 读取失败，跳过

            # 解析数据
            value = self.parse_data(raw_data)
            if value is not None:
                print(f"📊 DB{db_num} 偏移量{offset}：{value}")


if __name__ == "__main__":
    plc_client = M10S7Client(plc_ip=PLC_IP, plc_port=PLC_PORT)

    try:
        if not plc_client.connect():
            print("❌ PLC连接失败，终止程序")
            exit()

        # 循环读取指定范围的DB块数据
        while True:
            print("\n" + "=" * 60)
            print(f"📅 本轮读取开始时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"📌 读取范围：DB{DB_START}至DB{DB_END}（偏移量{READ_OFFSET}，4字节浮点数）")

            # 读取并打印成功的结果
            plc_client.read_db_range(DB_START, DB_END, READ_OFFSET)

            print(f"\n📅 本轮读取结束时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 60)
            print(f"⌛ 等待{READ_INTERVAL}秒后开始下一轮读取...")
            time.sleep(READ_INTERVAL)

    except KeyboardInterrupt:
        print("\n✅ 用户终止程序")
    finally:
        plc_client.disconnect()