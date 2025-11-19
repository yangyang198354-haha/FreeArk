# 使用Python 3.9作为基础镜像
FROM python:3.9-slim-bullseye
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libc6-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件（使用上层目录作为构建上下文）
COPY . /app/

# 安装Python依赖
RUN pip install --no-cache-dir -r /app/datacollection/requirements.txt

# 创建output目录
RUN mkdir -p /app/output

# 设置环境变量
ENV PYTHONPATH=/app

# 运行命令
CMD ["python", "datacollection/run_task_scheduler.py"]