# 后端镜像：python-slim + uv（阿里源）装依赖
# 镜像源可换官方：docker.1ms.run/library/python → python
FROM docker.1ms.run/library/python:3.12-slim AS deps
WORKDIR /app
ENV UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/ \
    UV_PYTHON_DOWNLOADS=never
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ uv
COPY pyproject.toml uv.lock ./
# 强制用容器系统 Python（避免 uv 从外网下载解释器）
RUN uv sync --frozen --no-dev --no-install-project --python /usr/local/bin/python3

FROM docker.1ms.run/library/python:3.12-slim
WORKDIR /app
COPY --from=deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8
COPY . .
# 启动即迁移 schema，随后起服务
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
