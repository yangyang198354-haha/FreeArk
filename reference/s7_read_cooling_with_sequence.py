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
            else:
                print(f"❌ PLC连接失败（IP: {self.plc_ip}:{self.plc_port}）")
                return False
        except Exception as e:
            print(f"❌ PLC连接异常：{str(e)}（检查网络/IP是否正确）")
            return False

    def disconnect(self) -> None:
        """断开PLC连接"""
        if self.connected:
            self.client.disconnect()
            self.connected = False
            print(f"✅ 已断开与PLC的连接")

    def read_db_data(self, db_num: int, db_offset: int, data_len: int) -> Optional[bytes]:
        """读取指定DB块、偏移量的数据（使用db_read方法）"""
        if not self.connected:
            print(f"❌ DB{db_num} 读取失败：未连接PLC")
            return None

        try:
            # 使用db_read方法：参数为(DB号, 偏移量, 读取长度)
            data = self.client.db_read(db_num, db_offset, data_len)
            if len(data) == data_len:
                return data
            else:
                print(f"❌ DB{db_num} 偏移量{db_offset}：数据长度不匹配（预期{data_len}字节，实际{len(data)}字节）")
                return None
        except Exception as e:
            print(f"❌ DB{db_num} 偏移量{db_offset}：读取异常 - {str(e)}（检查DB块是否存在/偏移量是否合法）")
            return None

    @staticmethod
    def parse_data(raw_data: bytes, db_num: int, offset: int) -> Optional[float]:
        """解析32位浮点数数据"""
        if len(raw_data) != 4:
            print(f"❌ DB{db_num} 偏移量{offset}：解析失败 - 需4字节数据（当前{len(raw_data)}字节）")
            return None

        try:
            # 西门子PLC默认大端字节序，解析32位浮点数
            parsed_value = struct.unpack('>f', raw_data)[0]
            return round(parsed_value, 2)
        except Exception as e:
            print(f"❌ DB{db_num} 偏移量{offset}：解析异常 - {str(e)}（数据可能不是浮点数格式）")
            return None

    def read_db_range(self, start_db: int, end_db: int, offset: int) -> None:
        """按序号读取从start_db到end_db的所有DB块中指定偏移量的数据"""
        for db_num in range(start_db, end_db + 1):
            # 读取当前DB块偏移量0的4字节数据
            raw_data = self.read_db_data(db_num, offset, DATA_LENGTH)
            if raw_data:
                # 解析并打印数据
                value = self.parse_data(raw_data, db_num, offset)
                if value is not None:
                    print(f"📊 DB{db_num} 偏移量{offset}：{value}")


if __name__ == "__main__":
    plc_client = M10S7Client(plc_ip=PLC_IP, plc_port=PLC_PORT)

    try:
        if not plc_client.connect():
            raise Exception("PLC连接失败，终止程序")

        # 循环读取指定范围的DB块数据
        while True:
            print("\n" + "=" * 60)
            print(f"📅 本轮读取开始时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"📌 读取范围：DB{DB_START}至DB{DB_END}（每个DB块偏移量{READ_OFFSET}，4字节浮点数）")

            # 读取并打印所有DB块数据
            plc_client.read_db_range(DB_START, DB_END, READ_OFFSET)

            print(f"\n📅 本轮读取结束时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 60)
            print(f"⌛ 等待{READ_INTERVAL}秒后开始下一轮读取...")
            time.sleep(READ_INTERVAL)

    except KeyboardInterrupt:
        print("\n✅ 用户终止程序")
    except Exception as e:
        print(f"\n❌ 程序异常：{str(e)}")
    finally:
        plc_client.disconnect()