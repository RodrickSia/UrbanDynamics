FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SUMO_HOME=/usr/share/sumo
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && install -d /usr/share/keyrings \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-17 postgresql-17-postgis-3 postgis sumo sumo-tools osmium-tool \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && python -c "import duckdb; connection = duckdb.connect(); connection.execute('INSTALL httpfs'); connection.execute('INSTALL spatial'); connection.close()" \
    && raster2pgsql_path="$(command -v raster2pgsql || find /usr -type f -name raster2pgsql -print -quit)" \
    && test -n "$raster2pgsql_path" \
    && ln -s "$raster2pgsql_path" /usr/local/bin/raster2pgsql \
    && command -v netconvert \
    && command -v osmium \
    && test -s "$SUMO_HOME/data/typemap/osmNetconvert.typ.xml" \
    && command -v psql
COPY src/ ./src/
ENTRYPOINT ["python", "-m", "src.main"]
CMD ["run"]
