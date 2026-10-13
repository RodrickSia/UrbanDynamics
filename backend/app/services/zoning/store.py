"""Atomic revision-checked documents; PostgreSQL or durable local SQLite."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb
from src.shared.database import connect_to_warehouse, warehouse_configured


class Conflict(Exception):
    pass


class StorageUnavailable(Exception):
    pass


@contextmanager
def database():
    remote = warehouse_configured()
    try:
        if remote:
            connection = connect_to_warehouse()
        else:
            directory = Path(os.getenv("ZONING_DATA_DIR", str(Path(os.getenv("DATA_DIR", "data")) / "zoning")))
            directory.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(directory / "plans.sqlite3", timeout=10)
        try:
            with connection:
                if remote:
                    connection.execute("SELECT pg_advisory_xact_lock(hashtext('zoning_plans_schema'))")
                else:
                    connection.execute("BEGIN IMMEDIATE")
                connection.execute("CREATE TABLE IF NOT EXISTS zoning_plans "
                                   "(id TEXT PRIMARY KEY, document " + ("JSONB" if remote else "TEXT") + " NOT NULL)")
                yield connection, remote
        finally:
            connection.close()
    except (OSError, sqlite3.Error, psycopg.Error) as error:
        raise StorageUnavailable("Plan storage is temporarily unavailable") from error


def decode(row):
    return (json.loads(row[0]) if isinstance(row[0], str) else row[0]) if row else None


def encode(document, remote):
    serialized = json.dumps(document, allow_nan=False)
    if len(serialized) > 20_000_000:
        raise ValueError("Plan history exceeds the 20 MB workspace limit")
    return Jsonb(document) if remote else serialized


def save_new(document):
    with database() as (connection, remote):
        placeholder = "%s" if remote else "?"
        connection.execute(f"INSERT INTO zoning_plans(id,document) VALUES ({placeholder},{placeholder})",
                           (document["id"], encode(document, remote)))
    return document


def load(identifier):
    with database() as (connection, remote):
        placeholder = "%s" if remote else "?"
        return decode(connection.execute(f"SELECT document FROM zoning_plans WHERE id={placeholder}",
                                         (str(identifier),)).fetchone())


def listing():
    with database() as (connection, remote):
        field = "document->>'updated_at'" if remote else "json_extract(document, '$.updated_at')"
        rows = connection.execute(f"SELECT document FROM zoning_plans ORDER BY {field} DESC LIMIT 100").fetchall()
        fields = ("id", "name", "description", "updated_at", "revision", "area_m2", "status")
        return [{k: document[k] for k in fields} for row in rows if (document := decode(row))]


def update(identifier, revision, mutate):
    with database() as (connection, remote):
        placeholder = "%s" if remote else "?"
        suffix = " FOR UPDATE" if remote else ""
        document = decode(connection.execute(
            f"SELECT document FROM zoning_plans WHERE id={placeholder}{suffix}", (str(identifier),)).fetchone())
        if document is None:
            return None
        if document["revision"] != revision:
            raise Conflict("This plan changed in another tab. Reload it before editing.")
        result = mutate(document)
        connection.execute(f"UPDATE zoning_plans SET document={placeholder} WHERE id={placeholder}",
                           (encode(result, remote), str(identifier)))
        return result


def delete(identifier, revision):
    with database() as (connection, remote):
        placeholder = "%s" if remote else "?"
        suffix = " FOR UPDATE" if remote else ""
        document = decode(connection.execute(
            f"SELECT document FROM zoning_plans WHERE id={placeholder}{suffix}", (str(identifier),)).fetchone())
        if document is None:
            return False
        if document["revision"] != revision:
            raise Conflict("This plan changed in another tab. Reload it before deleting.")
        connection.execute(f"DELETE FROM zoning_plans WHERE id={placeholder}", (str(identifier),))
        return True
