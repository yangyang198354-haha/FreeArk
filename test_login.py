import requests
import json

# 测试登录API
url = 'http://localhost:8000/api/auth/login/'
data = {
    'username': 'admin',
    'password': 'admin123'
}

print('正在发送登录请求...')
try:
    response = requests.post(url, json=data)
    print(f'状态码: {response.status_code}')
    print('响应内容:')
    
    # 尝试解析JSON
    try:
        json_data = response.json()
        print(json.dumps(json_data, indent=2, ensure_ascii=False))
        
        # 检查数据结构
        print('\n数据结构检查:')
        print(f'- 是否包含token: "token" in json_data = {"token" in json_data}')
        print(f'- 是否包含user: "user" in json_data = {"user" in json_data}')
        print(f'- 是否包含success: "success" in json_data = {"success" in json_data}')
        
        if "user" in json_data:
            print(f'- user字段类型: {type(json_data["user"])}')
            if isinstance(json_data["user"], dict):
                print(f'  - user包含的键: {list(json_data["user"].keys())}')
                
    except json.JSONDecodeError:
        print('响应不是有效的JSON格式')
        print(response.text)
        
except requests.exceptions.RequestException as e:
    print(f'请求失败: {e}')