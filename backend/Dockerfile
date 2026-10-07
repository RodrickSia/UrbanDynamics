FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/etl \
    DATA_DIR=/data
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 libx11-6 libxext6 libxrender1 libgl1 \
    && rm -rf /var/lib/apt/lists/*
COPY backend/app/ ./app/
COPY etl/src/shared/ ./etl/src/shared/
COPY etl/src/pipelines/flood_risk/ ./etl/src/pipelines/flood_risk/
COPY etl/src/pipelines/rainwater/ ./etl/src/pipelines/rainwater/
COPY etl/src/__init__.py ./etl/src/__init__.py
COPY etl/src/pipelines/__init__.py ./etl/src/pipelines/__init__.py
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
