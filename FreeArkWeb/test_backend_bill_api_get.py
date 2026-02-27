import requests
import json

# 直接测试后端API接口（使用GET方法）
def test_backend_bill_api_get():
    # 直接访问后端服务
    url = "http://192.168.31.51:8000/api/billing/list"
    headers = {
        "Content-Type": "application/json",
        "screenmac": "c5d29c52a237ade5"
    }
    params = {
        "startDate": "202511",
        "endDate": "202601"
    }
    
    print(f"请求URL: {url}")
    print(f"请求头: {headers}")
    print(f"请求参数: {params}")
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        print(f"响应状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        print(f"响应内容: {response.text}")
        
        try:
            json_response = response.json()
            print(f"JSON响应: {json.dumps(json_response, indent=2, ensure_ascii=False)}")
        except json.JSONDecodeError:
            print("响应不是有效的JSON格式")
        
        if response.status_code == 200:
            print("✅ 后端接口测试成功！")
        else:
            print("❌ 后端接口测试失败！")
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")

if __name__ == "__main__":
    print("测试后端历史用能API接口（GET方法）...")
    test_backend_bill_api_get()