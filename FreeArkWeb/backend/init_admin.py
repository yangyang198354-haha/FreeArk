#!/usr/bin/env python
"""
初始化脚本：创建超级管理员用户
"""
import os
import sys
import django

# 获取当前脚本所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 将backend目录添加到Python路径，这样可以找到freearkweb模块
sys.path.append(current_dir)
# 也将父目录添加到路径以确保所有模块都能被找到
sys.path.append(os.path.dirname(current_dir))

# 设置Django环境变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')

# 确保环境变量已设置
try:
    django.setup()
except Exception as e:
    print(f"Django setup失败: {e}")
    print(f"当前Python路径: {sys.path}")
    print(f"当前工作目录: {os.getcwd()}")
    raise

from api.models import CustomUser
def create_superuser():
    """创建超级管理员用户"""
    # 检查是否已存在管理员用户
    if CustomUser.objects.filter(username='admin').exists():
        print("管理员用户 'admin' 已存在")
        return
    
    # 创建管理员用户
    admin_user = CustomUser.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='admin123',
        role='admin',
        first_name='系统',
        last_name='管理员',
        department='IT部门',
        position='系统管理员'
    )
    
    print(f"超级管理员用户创建成功：")
    print(f"用户名: {admin_user.username}")
    print(f"邮箱: {admin_user.email}")
    print(f"角色: {admin_user.role}")
    print(f"密码: admin123 (请及时修改)")

if __name__ == '__main__':
    create_superuser()