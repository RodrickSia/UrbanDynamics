FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/etl \
    DATA_DIR=/data
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app/ ./app/
COPY etl/src/pipelines/flood_risk/ ./etl/src/pipelines/flood_risk/
COPY etl/src/__init__.py ./etl/src/__init__.py
COPY etl/src/pipelines/__init__.py ./etl/src/pipelines/__init__.py
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
