FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-dev.txt pytest.ini ./
COPY etl/requirements.txt ./etl/requirements.txt
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r requirements-dev.txt
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 libx11-6 libxext6 libxrender1 libgl1 \
    && rm -rf /var/lib/apt/lists/*
COPY etl/ ./etl/
COPY backend/ ./backend/
COPY scripts/building_demo.py ./scripts/building_demo.py
COPY docs/samples/ ./docs/samples/
CMD ["python", "-m", "pytest", "-q", "--junitxml=test-results/khoi-linux.xml"]
