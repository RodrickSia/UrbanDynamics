FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir "duckdb>=1.4.0" "pydantic>=2.13.5"
RUN python -c "import duckdb; c=duckdb.connect(); c.execute('INSTALL httpfs'); c.execute('INSTALL spatial')"
COPY src/ ./src/
ENTRYPOINT ["python", "-m", "src.main"]
CMD ["run"]
