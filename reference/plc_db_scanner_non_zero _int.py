import snap7
import struct
import time
import os
from typing import Optional

# 配置参数
PLC_IP = "192.168.3.27"  # PLC IP地址
PLC_RACK = 0             # 机架号
PLC_SLOT = 1             # 槽位号
DATA_LENGTH = 4          # 读取4字节（32位整数）
DB_LIST = [14, 15, 20, 500, 510, 550, 600, 602, 603]  # 需要扫描的DB块列表
START_OFFSET = 1         # 起始偏移量
PROGRESS_INTERVAL = 10   # 进度报告间隔（每扫描10个偏移量）
ZERO_THRESHOLD = 0       # 零值判断阈值（整数零）

# 生成文件名（以程序运行时间命名）
RUN_TIME = time.strftime("%Y%m%d_%H%M%S")
FILE_NAME = f"db_scan_non_zero_results_{RUN_TIME}.txt"

class PLCDBScanner:
    def __init__(self, plc_ip: str, rack: int, slot: int):
        self.plc_ip = plc_ip
        self.rack = rack
        self.slot = slot
        self.client = snap7.client.Client()
        self.connected = False
        self.results_file = None

    def connect(self) -> bool:
        """连接到PLC"""
        try:
            self.client.connect(self.plc_ip, self.rack, self.slot)
            if self.client.get_connected():
                self.connected = True
                print(f"✅ 成功连接到PLC: {self.plc_ip}")
                return True
            else:
                print(f"❌ 无法连接到PLC: {self.plc_ip}")
                return False
        except Exception as e:
            print(f"❌ 连接PLC时发生错误: {str(e)}")
            return False

    def disconnect(self) -> None:
        """断开与PLC的连接"""
        if self.connected:
            self.client.disconnect()
            self.connected = False
            print(f"✅ 已断开与PLC的连接")
        
        # 关闭结果文件
        if self.results_file and not self.results_file.closed:
            self.results_file.close()
            print(f"✅ 结果文件已保存: {os.path.abspath(FILE_NAME)}")

    def initialize_results_file(self) -> bool:
        """初始化结果文件"""
        try:
            self.results_file = open(FILE_NAME, "w", encoding="utf-8")
            # 写入文件头
            self.results_file.write(f"PLC DB块扫描结果（只记录非零值） - 开始时间: {RUN_TIME}\n")
            self.results_file.write(f"扫描DB块: {DB_LIST}\n")
            self.results_file.write("格式: DB号, 偏移量, 非零数据值(32位整数)\n")
            self.results_file.write("-" * 50 + "\n")
            return True
        except Exception as e:
            print(f"❌ 无法创建结果文件: {str(e)}")
            return False

    def read_int32_data(self, db_num: int, offset: int) -> Optional[int]:
        """读取指定DB块和偏移量的4字节32位整数"""
        if not self.connected:
            return None

        try:
            # 读取4字节数据
            data = self.client.db_read(db_num, offset, DATA_LENGTH)
            if len(data) != DATA_LENGTH:
                return None
            
            # 解析为32位整数（西门子PLC默认大端字节序）
            int_value = struct.unpack('>i', data)[0]
            return int_value
            
        except Exception as e:
            # 检查是否是地址超出范围异常
            if "address out of range" in str(e).lower():
                print(f"ℹ️ DB{db_num}: 检测到地址超出范围，停止扫描该DB块")
                return "OUT_OF_RANGE"
            return None

    def scan_db_block(self, db_num: int) -> None:
        """扫描指定的DB块，从起始偏移量开始，直到地址超出范围"""
        print(f"\n🔍 开始扫描DB{db_num} (从偏移量{START_OFFSET}开始)")
        
        offset = START_OFFSET
        total_scanned = 0
        non_zero_count = 0
        
        while True:
            # 每扫描指定数量的偏移量打印一次进度
            if total_scanned % PROGRESS_INTERVAL == 0 and total_scanned > 0:
                print(f"⏳ DB{db_num} 已扫描 {total_scanned} 个偏移量，发现 {non_zero_count} 个非零值")
                
            # 读取当前偏移量的数据
            value = self.read_int32_data(db_num, offset)
            
            # 检查是否地址超出范围
            if value == "OUT_OF_RANGE":
                break
                
            # 如果读取成功且为非零值，记录结果
            if value is not None:
                # 检查是否为非零值（整数判断）
                if value != ZERO_THRESHOLD:
                    non_zero_count += 1
                    result_line = f"DB{db_num}, {offset}, {value}\n"
                    
                    # 写入文件
                    if self.results_file and not self.results_file.closed:
                        self.results_file.write(result_line)
                        self.results_file.flush()  # 立即写入磁盘
            
            # 更新计数并递增偏移量
            total_scanned += 1
            offset += 1
        
        print(f"✅ DB{db_num} 扫描完成: 共扫描 {total_scanned} 个偏移量，发现 {non_zero_count} 个非零值")

    def run_scan(self) -> None:
        """执行所有DB块的扫描"""
        if not self.initialize_results_file():
            return
            
        if not self.connect():
            return
            
        try:
            for db_num in DB_LIST:
                self.scan_db_block(db_num)
                
            print("\n" + "=" * 50)
            print(f"🎉 所有DB块扫描完成")
            print(f"📄 非零值结果已保存到: {os.path.abspath(FILE_NAME)}")
            print("=" * 50)
            
        except KeyboardInterrupt:
            print("\n⚠️ 用户中断了扫描过程")
        except Exception as e:
            print(f"\n❌ 扫描过程中发生错误: {str(e)}")
        finally:
            self.disconnect()

if __name__ == "__main__":
    print("=" * 50)
    print(f"PLC DB块扫描程序（只记录非零值） - 启动时间: {RUN_TIME}")
    print(f"将扫描的DB块: {DB_LIST}")
    print(f"每扫描{PROGRESS_INTERVAL}个偏移量报告一次进度")
    print("=" * 50)
    
    scanner = PLCDBScanner(PLC_IP, PLC_RACK, PLC_SLOT)
    scanner.run_scan()
