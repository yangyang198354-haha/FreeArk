import requests

# 测试健康检查接口
def test_health_check():
    # 测试后端健康检查接口
    url = "http://192.168.31.51:8000/api/health"
    
    print(f"测试健康检查接口: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        
        if response.status_code == 200:
            print("✅ 健康检查接口测试成功！")
        else:
            print("❌ 健康检查接口测试失败！")
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")

if __name__ == "__main__":
    print("测试健康检查接口...")
    test_health_check()