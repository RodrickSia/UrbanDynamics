FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir "pydantic>=2.13.5"
COPY src/ ./src/
CMD ["python", "-m", "src.main"]
