"""Append-only scenario runs; PostGIS in production, atomic JSON for local testing."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb


class StorageUnavailable(Exception):
    pass


def _directory():
    return Path(os.getenv("SCENARIO_DATA_DIR", str(Path(os.getenv("DATA_DIR", "data")) / "scenarios")))


def save(result: dict) -> dict:
    identifier = uuid4()
    document = {**result, "id": str(identifier), "created_at": datetime.now(timezone.utc).isoformat()}
    url = os.getenv("DATABASE_URL")
    try:
        if url:
            with psycopg.connect(url, connect_timeout=5) as connection:
                connection.execute("SELECT pg_advisory_xact_lock(hashtext('building_scenario_schema'))")
                connection.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO building_scenario_runs(id,created_at,model_version,input_sha256,site,document) "
                    "VALUES (%s,%s,%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),%s)",
                    (identifier, document["created_at"], document["model_version"], document["input_sha256"],
                     json.dumps(document["inputs"]["site"]), Jsonb(document)))
        else:
            directory = _directory()
            directory.mkdir(parents=True, exist_ok=True)
            temporary = directory / f"{identifier}.tmp"
            try:
                with temporary.open("x", encoding="utf-8") as handle:
                    json.dump(document, handle, ensure_ascii=False, allow_nan=False)
                temporary.replace(directory / f"{identifier}.json")
            finally:
                temporary.unlink(missing_ok=True)
    except (psycopg.Error, OSError) as error:
        raise StorageUnavailable("Scenario storage unavailable") from error
    return document


def load(identifier: UUID) -> dict | None:
    url = os.getenv("DATABASE_URL")
    try:
        if url:
            with psycopg.connect(url, connect_timeout=5) as connection:
                # No runs exist before the first successful scenario creation.
                if connection.execute("SELECT to_regclass('building_scenario_runs')").fetchone()[0] is None:
                    return None
                row = connection.execute("SELECT document FROM building_scenario_runs WHERE id=%s",
                                         (identifier,)).fetchone()
                return row[0] if row else None
        path = _directory() / f"{identifier}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (psycopg.Error, OSError, ValueError) as error:
        raise StorageUnavailable("Scenario storage unavailable") from error
