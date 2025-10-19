#!/bin/bash

# 等待数据库服务就绪
echo "等待数据库服务就绪..."
sleep 5

# 运行数据库迁移
echo "运行数据库迁移..."
python manage.py migrate

# 检查是否需要创建超级用户（仅在开发环境）
if [ "$DEBUG" = "True" ] && [ "$CREATE_SUPERUSER" = "True" ]; then
    echo "创建超级用户..."
    python manage.py createsuperuser --noinput || true
fi

# 启动Django服务器
echo "启动Django服务器..."
gunicorn freearkweb.wsgi:application --bind 0.0.0.0:8000 --workers 3