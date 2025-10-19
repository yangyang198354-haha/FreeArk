# 使用Python官方镜像作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBUG=False

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements.txt文件并安装Python依赖
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# 复制项目文件
COPY ./freearkweb /app/freearkweb

# 收集静态文件
WORKDIR /app/freearkweb
RUN python manage.py collectstatic --noinput

# 创建启动脚本
COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 暴露端口
EXPOSE 8000

# 设置启动命令
ENTRYPOINT ["/entrypoint.sh"]