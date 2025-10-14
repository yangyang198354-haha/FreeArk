import socket
import struct
import threading
from typing import Dict, Tuple


class S7Simulator:
    def __init__(self, ip: str = "0.0.0.0", port: int = 102):
        self.ip = ip
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.running = False

        # 模拟DB块数据（DB1.100=1234.56, DB1.104=7890.12，32位浮点数）
        self.db_data: Dict[Tuple[int, int], bytes] = {
            (1, 100): struct.pack('>f', 1234.56),  # 累计制冷量
            (1, 104): struct.pack('>f', 7890.12),  # 累计制热量
        }

        # 协议常量（修正COTP数据传输帧类型）
        self.TPKT_VERSION = 0x03
        self.COTP_CR = 0x0E  # 连接请求
        self.COTP_CC = 0x0F  # 连接确认
        self.COTP_DT = 0x02  # 数据传输（关键修正：原0x0F与CC冲突）
        self.S7_PDU_TYPE_DATA = 0x03
        self.FUNCTION_READ = 0x04  # 读取变量
        self.FUNCTION_WRITE = 0x05  # 写入变量
        self.ERROR_NONE = 0x00

    def start(self):
        self.socket.bind((self.ip, self.port))
        self.socket.listen(5)
        self.running = True
        print(f"✅ S7-1200模拟器启动，监听 {self.ip}:{self.port}")

        while self.running:
            client_socket, addr = self.socket.accept()
            print(f"📞 新连接：{addr}")
            client_thread = threading.Thread(target=self.handle_client, args=(client_socket,))
            client_thread.start()

    def stop(self):
        self.running = False
        self.socket.close()
        print("\n❌ 模拟器已停止")

    def handle_cotp_connect(self, data: bytes) -> bytes:
        """处理COTP连接请求（CR），返回连接确认（CC）"""
        if len(data) < 5:
            return b''  # 无效CR帧

        # 提取源参考和构建目标参考
        src_ref = data[3:5]
        dst_ref = b'\x00\x01'  # 服务器标识

        # 解析TSAP信息（客户端与服务器的TSAP匹配）
        options = data[7:]
        src_tsap = b'\x01\x00'  # 客户端TSAP默认值
        dst_tsap = b'\x03\x01'  # 服务器TSAP（机架0+槽位1）

        i = 0
        while i < len(options):
            opt_type = options[i]
            opt_len = options[i + 1]
            opt_data = options[i + 2:i + 2 + opt_len]
            if opt_type == 0xC0:  # TSAP选项
                if opt_len == 4:
                    src_tsap = opt_data[:2]
                    dst_tsap = opt_data[2:]
            i += 2 + opt_len

        # 构建COTP连接确认帧
        cotp_cc = (
            b'\x0F'  # 类型：CC
            b'\x0C'  # 长度
            + dst_ref
            + src_ref
            + b'\xC0'  # TSAP选项类型
            + b'\x04'  # 选项长度
            + src_tsap
            + dst_tsap
            + b'\x00'  # 结束标记
        )

        # 封装TPKT头部
        tpkt_length = 4 + len(cotp_cc)
        tpkt = struct.pack('>BBH', self.TPKT_VERSION, 0x00, tpkt_length)
        return tpkt + cotp_cc

    def parse_s7_request(self, data: bytes) -> Tuple[int, int, int, int, int]:
        """解析S7数据请求，返回（功能码, DB号, 偏移量, 长度, 错误码）"""
        try:
            # 最小帧长度检查（TPKT(4) + COTP(2) + S7 PDU(至少4)）
            if len(data) < 10:
                return (0, 0, 0, 0, 0xFE)

            # 解析COTP数据传输帧头部
            cotp_type = data[4]
            if cotp_type != self.COTP_DT:
                return (0, 0, 0, 0, 0xFD)  # 非数据传输帧

            # 计算COTP头部长度（处理可选长度字段）
            cotp_header_len = 2  # 基础长度（类型+保留位）
            if data[5] & 0x80:  # 存在长度字段
                cotp_header_len += 2

            # 提取S7 PDU（跳过TPKT和COTP头部）
            s7_pdu_start = 4 + cotp_header_len
            s7_pdu = data[s7_pdu_start:]
            if len(s7_pdu) < 10:
                return (0, 0, 0, 0, 0xFE)

            # 解析功能码（S7 PDU第3字节）
            function = s7_pdu[2]
            print(f"📌 解析到功能码：0x{function:02X}")

            if function not in [self.FUNCTION_READ, self.FUNCTION_WRITE]:
                return (function, 0, 0, 0, 0x01)

            # 解析DB块信息（适配snap7的db_get请求格式）
            db_number = struct.unpack('>H', s7_pdu[16:18])[0] & 0x7FFF  # 15位DB号
            start_offset = struct.unpack('>H', s7_pdu[18:20])[0]
            data_length = struct.unpack('>H', s7_pdu[20:22])[0]

            return (function, db_number, start_offset, data_length, self.ERROR_NONE)

        except Exception as e:
            print(f"❌ 请求解析失败：{str(e)}，原始数据：{data.hex()}")
            return (0, 0, 0, 0, 0xFF)

    def build_s7_response(self, function: int, db_number: int, start_offset: int, data_length: int) -> bytes:
        """构建S7响应帧"""
        if function == self.FUNCTION_READ:
            # 处理读取请求
            key = (db_number, start_offset)
            if key in self.db_data and len(self.db_data[key]) >= data_length:
                # 成功响应：包含数据
                data = self.db_data[key][:data_length]
                response_pdu = (
                    struct.pack('>BB', self.S7_PDU_TYPE_DATA, self.ERROR_NONE)
                    + b'\x00\x00\x00'  # 预留字段
                    + struct.pack('>H', data_length)  # 数据长度
                    + data  # 实际数据
                )
            else:
                # 地址错误响应
                response_pdu = struct.pack('>BB', self.S7_PDU_TYPE_DATA, 0x05)

        elif function == self.FUNCTION_WRITE:
            # 处理写入请求（简化实现）
            response_pdu = struct.pack('>BB', self.S7_PDU_TYPE_DATA, self.ERROR_NONE)

        else:
            # 不支持的功能码
            response_pdu = struct.pack('>BB', self.S7_PDU_TYPE_DATA, 0x01)

        # 构建COTP DT头部（类型0x02 + 保留位0x00）
        cotp_dt = b'\x02\x00'
        # 封装TPKT头部（总长度=4+2+PDU长度）
        total_length = 4 + len(cotp_dt) + len(response_pdu)
        tpkt = struct.pack('>BBH', self.TPKT_VERSION, 0x00, total_length)

        return tpkt + cotp_dt + response_pdu

    def handle_client(self, client_socket: socket.socket):
        """处理客户端连接生命周期"""
        try:
            # 阶段1：处理COTP连接
            data = client_socket.recv(1024)
            if not data:
                return

            # 验证TPKT版本
            tpkt_version = data[0]
            if tpkt_version != self.TPKT_VERSION:
                print("❌ TPKT版本错误")
                return

            # 处理连接请求
            cotp_type = data[4]
            if cotp_type == self.COTP_CR:
                cc_response = self.handle_cotp_connect(data[4:])
                client_socket.sendall(cc_response)
                print(f"📤 发送连接确认（CC），数据：{cc_response.hex()}")

            # 阶段2：处理数据传输
            while True:
                data = client_socket.recv(1024)
                if not data:
                    break
                print(f"📥 接收到数据帧：{data.hex()}")

                # 解析请求并生成响应
                function, db_num, offset, length, error = self.parse_s7_request(data)
                if error != self.ERROR_NONE:
                    print(f"❌ 请求错误（错误码：{error}）")
                    continue

                response = self.build_s7_response(function, db_num, offset, length)
                client_socket.sendall(response)
                print(f"📤 发送响应帧：{response.hex()}（功能码：0x{function:02X}）")

        except Exception as e:
            print(f"❌ 客户端处理异常：{str(e)}")
        finally:
            client_socket.close()
            print("🔌 连接已关闭")


if __name__ == "__main__":
    simulator = S7Simulator(ip="0.0.0.0", port=102)
    try:
        simulator.start()
    except KeyboardInterrupt:
        simulator.stop()