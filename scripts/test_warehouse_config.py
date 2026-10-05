"""Guard against accidentally restoring shared database password defaults."""

import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("docker"), "Docker CLI required for Compose parser check")
class WarehouseConfigurationTests(unittest.TestCase):
    def warehouse_passwords(self, password):
        environ = {**os.environ, "WAREHOUSE_PASSWORD": password}
        # Isolate from local .env files and avoid version-specific Compose flags.
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            shutil.copyfile(ROOT / "compose.yaml", fixture / "compose.yaml")
            shutil.copyfile(ROOT / ".env.example", fixture / ".env")
            result = subprocess.run(
                ["docker", "compose", "--project-name", "warehouse-config-test",
                 "--env-file", str(fixture / ".env"),
                 "--profile", "etl-population-hcmc", "--profile", "etl-rainwater",
                 "config", "--format", "json"],
                cwd=fixture, env=environ, capture_output=True, text=True, timeout=30,
            )
        diagnostics = result.stderr.replace(password, "[REDACTED]") if password else result.stderr
        self.assertEqual(result.returncode, 0, diagnostics)
        services = json.loads(result.stdout)["services"]
        return [
            services["postgis"]["environment"]["POSTGRES_PASSWORD"],
            services["etl-population-hcmc"]["environment"]["WAREHOUSE_PASSWORD"],
            services["etl-rainwater"]["environment"]["WAREHOUSE_PASSWORD"],
        ]

    def test_missing_password_does_not_select_a_shared_default(self):
        self.assertTrue(all(value == "" for value in self.warehouse_passwords("")),
                        "Database and ETL must not fall back to a shared password")

    def test_explicit_password_reaches_database_and_etl(self):
        password = secrets.token_hex(24)
        self.assertTrue(all(value == password for value in self.warehouse_passwords(password)),
                        "Database and ETL must use the supplied password")


if __name__ == "__main__":
    unittest.main()
