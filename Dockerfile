# Build stage: resolve the locked dependencies into /app/.venv with uv.
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY README.md LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

# Runtime stage: the venv, migrations, and git for `python -m football_api.sync`, which
# clones the sources into SOURCES_DIR (point it at a writable volume when running the sync).
FROM python:3.12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY seeds ./seeds
# HOME: `nobody` has none, and git needs one to run.
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 HOME=/tmp
USER nobody
EXPOSE 8000
# 0.0.0.0 is the container's own interface; docker-compose.yml publishes it on 127.0.0.1 only.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn football_api.api.app:app --host 0.0.0.0 --port 8000"]
