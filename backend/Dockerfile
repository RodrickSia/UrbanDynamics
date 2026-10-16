FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.6 /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/etl \
    DATA_DIR=/data \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/app/.venv/bin:$PATH
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 libgomp1 libatomic1 libx11-6 libxext6 libxrender1 libgl1 osmium-tool \
    && rm -rf /var/lib/apt/lists/*
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app
RUN mkdir -p /runtime && chown app:app /runtime
COPY --chown=app:app backend/app/ ./app/
COPY --chown=app:app frontend/src/features/zoning/zoningCatalog.json ./app/services/zoning/zoningCatalog.json
COPY --chown=app:app etl/src/ ./etl/src/
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
