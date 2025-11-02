import snap7
import struct
import time
from typing import Optional

# --------------------------
# 配置参数（偏移量逐1递增）
# --------------------------
PLC_IP = "192.168.3.27"  # PLC IP地址
DB_NUMBER = 20  # 固定读取DB1
START_OFFSET = 0  # 起始偏移量
END_OFFSET = 999  # 结束偏移量（前1000个偏移量：0~999）
DATA_LENGTH = 8  # 64位双精度浮点数占8字节
READ_INTERVAL = 5  # 轮询间隔（秒）


class S7PLCReader:
    def __init__(self, plc_ip: str):
        self.plc_ip = plc_ip
        self.client = snap7.client.Client()
        self.connected = False

    def connect(self) -> bool:
        """连接PLC（机架0，槽位1）"""
        try:
            self.client.connect(self.plc_ip, 0, 1)
            if self.client.get_connected():
                self.connected = True
                print(f"✅ 成功连接PLC：{self.plc_ip}")
                return True
            else:
                print(f"❌ PLC连接失败：{self.plc_ip}（未建立连接）")
                return False
        except Exception as e:
            print(f"❌ PLC连接异常：{str(e)}（检查IP/网络）")
            return False

    def disconnect(self) -> None:
        """断开PLC连接"""
        if self.connected:
            self.client.disconnect()
            self.connected = False
            print(f"✅ 已断开PLC连接")

    def read_offset_data(self, db_num: int, offset: int, length: int) -> Optional[bytes]:
        """读取指定DB块和偏移量的原始数据（带异常提示）"""
        if not self.connected:
            print(f"❌ 偏移量{offset}：读取失败（未连接PLC）")
            return None

        # 检查偏移量+长度是否超出DB块最大范围（防止越界）
        max_possible_offset = offset + length - 1
        if max_possible_offset > (65535 - 1):  # DB块最大偏移量为65535字节（64KB）
            print(f"❌ 偏移量{offset}：读取范围越界（最大允许偏移量+长度≤65535）")
            return None

        try:
            # 使用db_read读取指定偏移量的8字节数据（64位）
            raw_data = self.client.db_read(db_num, offset, length)
            if len(raw_data) == length:
                return raw_data
            else:
                print(f"❌ 偏移量{offset}：数据长度不匹配（预期{length}字节，实际{len(raw_data)}字节）")
                return None
        except Exception as e:
            print(f"❌ 偏移量{offset}：读取异常 - {str(e)}（检查DB块配置/偏移量合法性）")
            return None

    @staticmethod
    def parse_lreal(raw_data: bytes, offset: int) -> Optional[float]:
        """解析64位双精度浮点数（大端模式），带异常提示"""
        if len(raw_data) != DATA_LENGTH:
            print(f"❌ 偏移量{offset}：解析失败（数据长度不足，需{DATA_LENGTH}字节）")
            return None

        try:
            # 西门子PLC默认大端字节序（>），d表示64位双精度浮点数
            value = struct.unpack('>d', raw_data)[0]
            return round(value, 4)  # 双精度保留4位小数
        except Exception as e:
            print(f"❌ 偏移量{offset}：解析异常 - {str(e)}（数据格式非64位双精度）")
            return None

    def read_lreal_range(self, db_num: int, start: int, end: int) -> None:
        """读取从start到end的偏移量（逐1递增），解析64位双精度浮点数"""
        for offset in range(start, end + 1):
            # 序号 = 偏移量 - 起始偏移量 + 1（从1开始计数）
            sequence = offset - start + 1

            # 读取当前偏移量的8字节数据（64位）
            raw_data = self.read_offset_data(db_num, offset, DATA_LENGTH)
            if not raw_data:
                continue  # 读取失败则跳过解析

            # 解析并打印结果
            value = self.parse_lreal(raw_data, offset)
            if value is not None:
                print(f"📊 序号{sequence} | DB{db_num}.{offset}：{value}")


if __name__ == "__main__":
    plc_reader = S7PLCReader(plc_ip=PLC_IP)

    try:
        if not plc_reader.connect():
            raise Exception("PLC连接失败，无法继续执行")

        # 循环读取偏移量0~999的64位双精度浮点数
        while True:
            print("\n" + "=" * 70)
            print(f"📅 本轮读取开始时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"📌 读取目标：DB{DB_NUMBER}（偏移量{START_OFFSET}至{END_OFFSET}，64位双精度浮点数）")
            print("-" * 70)

            # 按偏移量逐1递增读取并打印
            plc_reader.read_lreal_range(DB_NUMBER, START_OFFSET, END_OFFSET)

            print("-" * 70)
            print(f"📅 本轮读取结束时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"⌛ 等待{READ_INTERVAL}秒后开始下一轮...")
            print("=" * 70)
            time.sleep(READ_INTERVAL)

    except KeyboardInterrupt:
        print("\n✅ 用户手动终止程序")
    except Exception as e:
        print(f"\n❌ 程序异常终止：{str(e)}")
    finally:
        plc_reader.disconnect()
