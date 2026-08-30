"""
测试专用 settings — 强制使用 SQLite，禁止连接生产 MySQL
用法：python manage.py test api --settings=freearkweb.test_settings
"""
import os

from .settings import *  # noqa: F401, F403

# P2-9：mock 模式从测试模块级 os.environ.setdefault 迁移到 settings 统一管理，
# 避免跨模块 import 副作用。setdefault 不覆盖已有值，生产/显式设置不受影响。
os.environ.setdefault("FREEARK_POC_MOCK", "1")

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

# ---------------------------------------------------------------------------
# 测试环境日志配置：禁用所有文件 handler，避免在测试运行时生成日志文件。
# 使用 NullHandler 吸收所有日志输出，不影响测试结果。
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'null': {
            'class': 'logging.NullHandler',
        },
    },
    'root': {
        'handlers': ['null'],
        'level': 'CRITICAL',
    },
    'loggers': {
        'django': {
            'handlers': ['null'],
            'propagate': False,
        },
        'django.request': {
            'handlers': ['null'],
            'propagate': False,
        },
        'api': {
            'handlers': ['null'],
            'propagate': False,
        },
    },
}
