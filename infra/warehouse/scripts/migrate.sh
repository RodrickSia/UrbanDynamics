#!/bin/sh
set -eu

if [ "${WAREHOUSE_MIGRATION_TARGET:-local}" = "compose" ]; then
    migration_dir="${MIGRATIONS_DIR:-infra/warehouse/migrations}"
    psql_run() {
        docker compose exec -T postgis sh -c \
            'exec psql -X --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" "$@"' \
            sh "$@"
    }
else
    migration_dir="${MIGRATIONS_DIR:-/opt/warehouse/migrations}"
    : "${POSTGRES_USER:?POSTGRES_USER must be set}"
    : "${POSTGRES_DB:?POSTGRES_DB must be set}"
    psql_run() {
        psql -X --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" "$@"
    }
fi

psql_run --command '
    CREATE TABLE IF NOT EXISTS public.schema_migrations (
        version TEXT PRIMARY KEY,
        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )'

found_migration=false
for migration_file in "$migration_dir"/[0-9]*.sql; do
    [ -f "$migration_file" ] || continue
    found_migration=true
    version=${migration_file##*/}
    quoted_version=$(printf '%s' "$version" | sed "s/'/''/g")
    applied=$(psql_run --tuples-only --no-align \
        --command "SELECT EXISTS (SELECT 1 FROM public.schema_migrations WHERE version = '$quoted_version')")
    if [ "$applied" = "t" ]; then
        printf 'Already applied: %s\n' "$version"
        continue
    fi

    printf 'Applying migration: %s\n' "$version"
    {
        cat "$migration_file"
        printf "\nINSERT INTO public.schema_migrations (version) VALUES ('%s');\n" "$quoted_version"
    } | psql_run --single-transaction --file=-
done

if [ "$found_migration" = false ]; then
    printf 'No versioned SQL migrations found in %s\n' "$migration_dir"
fi
