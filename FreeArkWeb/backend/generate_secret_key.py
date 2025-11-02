#!/usr/bin/env python
"""
生成 Django SECRET_KEY 的脚本
"""
import sys

def generate_django_secret_key():
    """使用 Django 的 get_random_secret_key() 函数生成安全密钥"""
    try:
        # 尝试直接导入 Django 的 get_random_secret_key 函数
        from django.core.management.utils import get_random_secret_key
        
        # 生成随机密钥
        secret_key = get_random_secret_key()
        print("生成的 Django SECRET_KEY:")
        print(secret_key)
        print("\n请将此密钥复制到您的 .env 文件中的 SECRET_KEY 字段")
        
    except ImportError:
        print("错误: 未安装 Django")
        print("\n请先安装 Django:")
        print("pip install django")
        
        # 如果没有 Django，提供一个备选方案
        import string
        import random
        
        print("\n备选方案 - 生成随机字符串:")
        chars = string.ascii_letters + string.digits + string.punctuation
        secret_key = ''.join(random.choice(chars) for _ in range(50))
        print(secret_key)
        print("\n注意: 这是一个简单的随机字符串，建议优先使用 Django 的专用函数")

if __name__ == "__main__":
    generate_django_secret_key()