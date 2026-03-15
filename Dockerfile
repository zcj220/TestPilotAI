# TestPilot AI — API 服务镜像
#
# 多阶段构建：
#   Stage 1: 安装 Python 依赖
#   Stage 2: 精简运行镜像
#
# 构建：docker build -t testpilot/api .
# 运行：docker run --env-file .env -p 8900:8900 testpilot/api

# ── Stage 1: 依赖安装 ────────────────────────────
FROM python:3.11-slim AS builder

RUN pip install --no-cache-dir poetry

WORKDIR /build
COPY pyproject.toml poetry.lock* ./

RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-root --only main

# ── Stage 2: 运行镜像 ────────────────────────────
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini cli.py main.py pyproject.toml ./

RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV TP_SERVER_HOST=0.0.0.0
ENV TP_SERVER_PORT=8900

EXPOSE 8900

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8900/api/v1/health || exit 1

CMD ["python", "-m", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8900"]
