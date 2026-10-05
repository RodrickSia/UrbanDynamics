FROM postgis/postgis:17-3.5-alpine

COPY init/ /docker-entrypoint-initdb.d/
COPY migrations/ /opt/warehouse/migrations/
COPY scripts/migrate.sh /usr/local/bin/migrate-warehouse
RUN chmod +x /docker-entrypoint-initdb.d/02-apply-migrations.sh \
    /usr/local/bin/migrate-warehouse
