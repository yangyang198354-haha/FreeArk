import requests
import json

# 测试Nginx配置的历史用能接口
def test_nginx_bill_api():
    url = "http://localhost:8080/ark/billing-managerment/list"
    headers = {
        "Content-Type": "application/json",
        "screenMac": "00:11:22:33:44:55"
    }
    data = {
        "startDate": "202301",
        "endDate": "202312",
        "energyType": "electric",
        "deviceId": "device_001",
        "regionId": "region_001"
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"响应状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        print(f"响应内容: {response.text}")
        
        try:
            json_response = response.json()
            print(f"JSON响应: {json.dumps(json_response, indent=2, ensure_ascii=False)}")
        except json.JSONDecodeError:
            print("响应不是有效的JSON格式")
        
        if response.status_code == 200:
            print("✅ Nginx接口测试成功！")
        else:
            print("❌ Nginx接口测试失败！")
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")

if __name__ == "__main__":
    print("测试Nginx配置的历史用能API接口...")
    test_nginx_bill_api()
