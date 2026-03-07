# TestPilot AI CI Runner 镜像（v4.0）
#
# 用途：CI/CD 环境中运行 TestPilot AI 测试
#
# 构建：docker build -t testpilot/runner .
# 使用：docker run --rm -v ./testpilot.json:/app/blueprint.json testpilot/runner run -b /app/blueprint.json
#

FROM python:3.11-slim

# 安装系统依赖（Playwright 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Poetry
RUN pip install --no-cache-dir poetry

WORKDIR /app

# 复制依赖文件
COPY pyproject.toml poetry.lock* ./

# 安装 Python 依赖
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-root

# 安装 Playwright 浏览器
RUN playwright install chromium \
    && playwright install-deps chromium

# 复制项目文件
COPY . .

# 暴露引擎端口
EXPOSE 8900

# 默认命令：启动引擎
ENTRYPOINT ["python", "cli.py"]
CMD ["serve", "--host", "0.0.0.0"]
