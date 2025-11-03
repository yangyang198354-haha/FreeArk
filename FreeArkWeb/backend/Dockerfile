FROM python:3.11-slim

WORKDIR /app

# 设置Python环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBUG=False \
    PYTHONPATH=/app:/app/freearkweb

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 设置pip国内源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 复制requirements.txt文件并安装Python依赖
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# 复制项目文件
COPY ./freearkweb /app/freearkweb

# 检查并复制环境变量文件（如果存在）
RUN if [ -f ./.env ]; then cp ./.env /app/freearkweb/.env && echo "已复制.env文件"; else echo "没有找到.env文件，将使用默认配置"; fi

# 复制entrypoint.sh文件
COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 创建必要的目录
RUN mkdir -p /app/logs /app/freearkweb/staticfiles

# 验证安装的包
RUN pip list | grep -E 'django|waitress|python-dotenv'

# 暴露端口
EXPOSE 8000

# 设置启动命令
ENTRYPOINT ["/entrypoint.sh"]