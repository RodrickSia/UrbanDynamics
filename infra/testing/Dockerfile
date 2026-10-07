FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.6 /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/etl:/app/backend
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 libgomp1 libatomic1 libx11-6 libxext6 libxrender1 libgl1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-dev.txt pytest.ini ./
COPY etl/requirements.txt ./etl/requirements.txt
COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN uv export --project backend --frozen --no-dev --format requirements.txt \
        > /tmp/backend-requirements.txt \
    && pip install --no-cache-dir -r /tmp/backend-requirements.txt \
    && pip install --no-cache-dir -r etl/requirements.txt \
    && pip install --no-cache-dir -r requirements-dev.txt
COPY etl/ ./etl/
COPY backend/ ./backend/
COPY scripts/building_demo.py ./scripts/building_demo.py
COPY docs/samples/ ./docs/samples/
CMD ["python", "-m", "pytest", "-q", "--junitxml=test-results/khoi-linux.xml"]
