"""Shared connection settings for the PostGIS warehouse."""

from dataclasses import dataclass, field
import os

import psycopg
from psycopg import Connection


@dataclass(frozen=True)
class WarehouseConfig:
    """PostgreSQL connection settings loaded from WAREHOUSE_* environment vars."""

    host: str = "localhost"
    port: int = 5432
    database: str = "urbandynamics"
    user: str = "urbandynamics"
    password: str = field(default="localdev", repr=False)

    @classmethod
    def from_env(cls) -> "WarehouseConfig":
        """Create settings from the environment, using local-development defaults."""
        return cls(
            host=os.getenv("WAREHOUSE_HOST") or "localhost",
            port=int(os.getenv("WAREHOUSE_PORT") or "5432"),
            database=os.getenv("WAREHOUSE_DATABASE") or "urbandynamics",
            user=os.getenv("WAREHOUSE_USER") or "urbandynamics",
            password=os.getenv("WAREHOUSE_PASSWORD") or "localdev",
        )

    def connect(self) -> Connection:
        """Open a synchronous psycopg connection to the warehouse."""
        return psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
        )


def connect_to_warehouse() -> Connection:
    """Open a warehouse connection using the current environment settings."""
    return WarehouseConfig.from_env().connect()
