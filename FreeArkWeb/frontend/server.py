import http.server
import socketserver
import webbrowser
import os
import threading
import time

PORT = 8080

# 确保在前端目录下
os.chdir(os.path.dirname(os.path.abspath(__file__)))

Handler = http.server.SimpleHTTPRequestHandler

# 自定义Handler以支持跨域
class CORSRequestHandler(Handler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()

with socketserver.TCPServer(("0.0.0.0", PORT), CORSRequestHandler) as httpd:
    print(f"前端静态服务器启动在 http://localhost:{PORT}/")
    print("请在浏览器中访问 http://localhost:8080/")
    print("按 Ctrl+C 停止服务器")
    
    # 尝试自动打开浏览器
    try:
        threading.Thread(target=lambda: time.sleep(1) or webbrowser.open(f'http://localhost:{PORT}/')).start()
    except Exception:
        print("无法自动打开浏览器，请手动访问")
    
    httpd.serve_forever()