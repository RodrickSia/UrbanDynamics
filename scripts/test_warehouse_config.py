"""Guard against accidentally restoring shared database password defaults."""

import json
import os
import secrets
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    shutil.which("docker"), "Docker CLI required for Compose parser check"
)
class WarehouseConfigurationTests(unittest.TestCase):
    def warehouse_passwords(self, password):
        environ = {**os.environ, "WAREHOUSE_PASSWORD": password}
        # Isolate from local .env files and avoid version-specific Compose flags.
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            shutil.copyfile(ROOT / "compose.yaml", fixture / "compose.yaml")
            shutil.copyfile(ROOT / ".env.example", fixture / ".env")
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "--project-name",
                    "warehouse-config-test",
                    "--env-file",
                    str(fixture / ".env"),
                    "--profile",
                    "etl-population-hcmc",
                    "--profile",
                    "etl-flood-history",
                    "--profile",
                    "etl-flood-satellite",
                    "--profile",
                    "etl-flood-risk",
                    "--profile",
                    "etl-land-price",
                    "config",
                    "--format",
                    "json",
                ],
                cwd=fixture,
                env=environ,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        diagnostics = (
            result.stderr.replace(password, "[REDACTED]") if password else result.stderr
        )
        self.assertEqual(result.returncode, 0, diagnostics)
        services = json.loads(result.stdout)["services"]
        return [
            services["postgis"]["environment"]["POSTGRES_PASSWORD"],
            services["etl-population-hcmc"]["environment"]["WAREHOUSE_PASSWORD"],
            services["etl-flood-history"]["environment"]["WAREHOUSE_PASSWORD"],
            services["etl-flood-satellite"]["environment"]["WAREHOUSE_PASSWORD"],
            services["etl-flood-risk"]["environment"]["WAREHOUSE_PASSWORD"],
            services["etl-land-price"]["environment"]["WAREHOUSE_PASSWORD"],
        ]

    def test_missing_password_does_not_select_a_shared_default(self):
        self.assertTrue(
            all(value == "" for value in self.warehouse_passwords("")),
            "Database and ETL must not fall back to a shared password",
        )

    def test_explicit_password_reaches_database_and_etl(self):
        password = secrets.token_hex(24)
        self.assertTrue(
            all(value == password for value in self.warehouse_passwords(password)),
            "Database and ETL must use the supplied password",
        )

    def test_frontend_is_the_only_service_publishing_a_host_port(self):
        services = self.compose_config()
        exposed = {name for name, service in services.items() if service.get("ports")}
        self.assertEqual(exposed, {"frontend"})

    def compose_config(self):
        password = secrets.token_hex(24)
        environ = {**os.environ, "WAREHOUSE_PASSWORD": password}
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            shutil.copyfile(ROOT / "compose.yaml", fixture / "compose.yaml")
            shutil.copyfile(ROOT / ".env.example", fixture / ".env")
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "--project-name",
                    "warehouse-config-test",
                    "--env-file",
                    str(fixture / ".env"),
                    "--profile",
                    "etl-population-hcmc",
                    "--profile",
                    "etl-flood-history",
                    "--profile",
                    "etl-flood-satellite",
                    "--profile",
                    "etl-flood-risk",
                    "--profile",
                    "etl-land-price",
                    "config",
                    "--format",
                    "json",
                ],
                cwd=fixture,
                env=environ,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        self.assertEqual(
            result.returncode, 0, result.stderr.replace(password, "[REDACTED]")
        )
        return json.loads(result.stdout)["services"]


if __name__ == "__main__":
    unittest.main()
