import snap7
import struct
import time
import os
from typing import Optional

# --------------------------
# 配置参数
# --------------------------
PLC_IP = "192.168.3.27"  # PLC IP地址
PLC_PORT = 102  # S7协议默认端口
DB_START = 1  # 起始DB块（1）
DB_END = 65535  # 结束DB块（65535）
READ_OFFSET = 0  # 固定读取第一个偏移量（0）
DATA_LENGTH = 4  # 读取长度（4字节，32位浮点数）
READ_INTERVAL = 30  # 轮询间隔（秒，建议设长，因DB数量多）
PROG_START_TIME = time.strftime("%Y%m%d_%H%M%S")  # 程序启动时间（用于文件名）
FILE_NAME = f"{PROG_START_TIME}_plc_db_data.txt"  # 文本文件名（同级目录）


class S7PLCDataReader:
    def __init__(self, plc_ip: str, plc_port: int = 102):
        self.plc_ip = plc_ip
        self.plc_port = plc_port
        self.client = snap7.client.Client()
        self.connected = False
        self.data_file = None  # 数据文件对象
        self._init_data_file()  # 初始化数据文件

    def _init_data_file(self) -> None:
        """初始化数据文件（同级目录，不存在则创建，存在则追加）"""
        try:
            # 打开文件（追加模式，UTF-8编码，确保中文/特殊字符正常）
            self.data_file = open(FILE_NAME, "a+", encoding="utf-8")
            # 写入文件头（仅首次创建时写）
            if os.path.getsize(FILE_NAME) == 0:
                file_header = f"PLC数据记录文件（启动时间：{PROG_START_TIME}）\n"
                file_header += f"格式：DB号 | 偏移量{READ_OFFSET}数值（32位浮点数）\n"
                file_header += "-" * 50 + "\n"
                self.data_file.write(file_header)
                self.data_file.flush()  # 强制写入磁盘，避免缓存丢失
            print(f"✅ 数据文件初始化完成：{os.path.abspath(FILE_NAME)}")
        except Exception as e:
            print(f"❌ 数据文件初始化失败：{str(e)}（检查目录权限）")
            raise  # 文件初始化失败，终止程序

    def connect(self) -> bool:
        """连接PLC（机架0，槽位1）"""
        try:
            self.client.connect(self.plc_ip, 0, 1, self.plc_port)
            if self.client.get_connected():
                self.connected = True
                print(f"✅ 成功连接PLC：{self.plc_ip}:{self.plc_port}")
                return True
            else:
                print(f"❌ PLC连接失败：{self.plc_ip}:{self.plc_port}（未建立连接）")
                return False
        except Exception as e:
            print(f"❌ PLC连接异常：{str(e)}（检查IP/网络/端口）")
            return False

    def disconnect(self) -> None:
        """断开PLC连接并关闭文件"""
        if self.connected:
            self.client.disconnect()
            self.connected = False
            print(f"✅ 已断开PLC连接")
        # 关闭数据文件（确保数据写入）
        if self.data_file and not self.data_file.closed:
            self.data_file.close()
            print(f"✅ 数据文件已关闭：{os.path.abspath(FILE_NAME)}")

    def read_single_db(self, db_num: int) -> Optional[float]:
        """读取单个DB块的偏移量0数据（4字节），返回解析后的浮点数"""
        if not self.connected:
            print(f"❌ DB{db_num}：读取失败（未连接PLC）")
            return None

        try:
            # 读取DB块偏移量0的4字节数据
            raw_data = self.client.db_read(db_num, READ_OFFSET, DATA_LENGTH)
            if len(raw_data) != DATA_LENGTH:
                print(f"❌ DB{db_num}：数据长度不匹配（预期{DATA_LENGTH}字节，实际{len(raw_data)}字节）")
                return None

            # 解析32位浮点数（西门子大端字节序）
            parsed_value = struct.unpack(">f", raw_data)[0]
            return round(parsed_value, 2)  # 保留2位小数，符合计量习惯
        except Exception as e:
            # 捕获读取/解析异常（如DB不存在、地址超范围等）
            print(f"❌ DB{db_num}：读取/解析异常 - {str(e)}")
            return None

    def write_to_file(self, db_num: int, value: float) -> None:
        """将成功读取的数据写入文本文件（一行一条）"""
        if self.data_file and not self.data_file.closed:
            try:
                # 格式：DB号 | 数值（如：DB1 | 123.45）
                line = f"DB{db_num} | {value}\n"
                self.data_file.write(line)
                self.data_file.flush()  # 实时写入，避免程序崩溃导致数据丢失
            except Exception as e:
                print(f"❌ DB{db_num}：数据写入文件失败 - {str(e)}")

    def read_all_dbs(self) -> None:
        """读取DB1~DB65535的所有目标数据，处理成功/失败逻辑"""
        print(f"\n📌 开始读取DB{DB_START}~DB{DB_END}（共{DB_END - DB_START + 1}个DB块）")
        success_count = 0  # 成功读取计数
        start_time = time.time()  # 读取开始时间

        for db_num in range(DB_START, DB_END + 1):
            # 每读取1000个DB块打印一次进度（避免控制台刷屏）
            if (db_num - DB_START + 1) % 1000 == 0:
                elapsed = round(time.time() - start_time, 2)
                print(f"🔄 进度：已读取{db_num - DB_START + 1}个DB块，成功{success_count}个，耗时{elapsed}秒")

            # 读取单个DB块数据
            value = self.read_single_db(db_num)
            if value is not None:
                # 读取成功：写入文件+计数
                self.write_to_file(db_num, value)
                success_count += 1

        # 本轮读取统计
        elapsed_total = round(time.time() - start_time, 2)
        print(f"📊 本轮读取完成：共{DB_END - DB_START + 1}个DB块，成功{success_count}个，耗时{elapsed_total}秒")
        print(f"✅ 成功数据已写入文件：{os.path.abspath(FILE_NAME)}")

    def run(self) -> None:
        """程序主运行逻辑（连接+循环读取）"""
        try:
            if not self.connect():
                raise Exception("PLC连接失败，无法启动读取")

            print("\n" + "=" * 60)
            print(f"📅 本轮读取开始时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
            self.read_all_dbs()  # 执行一次全量读取
            print(f"📅 本轮读取结束时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"⌛ 等待{READ_INTERVAL}秒后开始下一轮...")
            print("=" * 60)
        except Exception as e:
            print(f"\n❌ 程序异常终止：{str(e)}")
        finally:
            self.disconnect()  # 无论异常与否，确保断开连接+关闭文件


if __name__ == "__main__":
    # 初始化并启动程序
    plc_reader = S7PLCDataReader(plc_ip=PLC_IP, plc_port=PLC_PORT)
    plc_reader.run()