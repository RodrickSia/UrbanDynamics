FROM postgis/postgis:17-3.5-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN apk add --no-cache python3 py3-pip \
    && python3 -m pip install --break-system-packages --no-cache-dir \
        "pydantic>=2.13.5" "psycopg[binary]>=3.2.6,<4"
COPY src/ ./src/
ENTRYPOINT ["python3", "-m", "src.main"]
CMD ["run"]
