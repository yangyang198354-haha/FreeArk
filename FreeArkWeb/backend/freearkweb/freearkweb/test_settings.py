"""
测试专用 settings — 强制使用 SQLite，禁止连接生产 MySQL
用法：python manage.py test api --settings=freearkweb.test_settings
"""
from .settings import *  # noqa: F401, F403

# 强制测试使用 SQLite，不连接生产数据库
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# 测试环境关闭 DEBUG
DEBUG = False

# 加速密码哈希（测试不需要强哈希）
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]
