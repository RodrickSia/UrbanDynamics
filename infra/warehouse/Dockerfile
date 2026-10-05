FROM postgis/postgis:17-3.5-alpine

COPY init/ /docker-entrypoint-initdb.d/
COPY migrations/ /docker-entrypoint-initdb.d/
