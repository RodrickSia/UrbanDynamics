import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    "deploy_env", Path(__file__).with_name("create-deploy-env.py")
)
deploy_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy_env)


class DeploymentEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.secrets = {
            "MLAI_FRONTEND_GOONG": "test-public-key",
            "MLAI_BACKEND_GOONG": "test-private-key",
        }

    def test_maps_secrets_and_uses_private_high_ports(self):
        values = deploy_env.deployment_values(self.secrets)
        self.assertEqual(values["VITE_GOONG_MAPTILES_KEY"], "test-public-key")
        self.assertEqual(values["GOONG_API_KEY"], "test-private-key")
        self.assertNotIn("test-private-key", str({k: v for k, v in values.items() if k.startswith("VITE_")}))
        self.assertEqual(values["FRONTEND_PORT"], "127.0.0.1:51873")
        self.assertEqual(values["BACKEND_PORT"], "127.0.0.1:51874")
        self.assertEqual(values["VITE_API_BASE_URL"], "http://127.0.0.1:51874")

    def test_accepts_port_overrides(self):
        values = deploy_env.deployment_values({**self.secrets, "BACKEND_PORT": "52102"})
        self.assertEqual(values["BACKEND_PORT"], "127.0.0.1:52102")
        self.assertEqual(values["VITE_API_BASE_URL"], "http://127.0.0.1:52102")

    def test_rejects_missing_or_multiline_secrets_without_disclosing_them(self):
        for value in ("", "  ", "sensitive\nINJECTED=1", "sensitive\r", "sensitive\x00"):
            with self.subTest(value=value), self.assertRaises(ValueError) as caught:
                deploy_env.deployment_values({**self.secrets, "MLAI_BACKEND_GOONG": value})
            self.assertNotIn("sensitive", str(caught.exception))

    def test_rejects_invalid_or_duplicate_ports(self):
        for port in ("0", "80", "65536", "51874", "127.0.0.1:51873", "$(command)"):
            with self.subTest(port=port), self.assertRaises(ValueError):
                deploy_env.deployment_values({**self.secrets, "FRONTEND_PORT": port})

    def test_creates_missing_env_and_escapes_compose_interpolation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            deploy_env.write_environment(path, {**self.secrets, "MLAI_BACKEND_GOONG": 'a$VALUE#"\\b'})
            content = path.read_text(encoding="utf-8")
            self.assertIn('GOONG_API_KEY="a$$VALUE#\\"\\\\b"', content)
            self.assertNotIn("\r", content)
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_invalid_config_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("existing", encoding="utf-8")
            with self.assertRaises(ValueError):
                deploy_env.write_environment(path, {})
            self.assertEqual(path.read_text(encoding="utf-8"), "existing")

    @unittest.skipUnless(shutil.which("docker"), "Docker CLI required for Compose parser check")
    def test_compose_reads_generated_values_without_changing_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_key = 'test$UNSET#"\\key'
            deploy_env.write_environment(root / ".env", {**self.secrets, "MLAI_BACKEND_GOONG": private_key})
            (root / "compose.yaml").write_text(
                'services:\n  check:\n    image: alpine\n    env_file: [.env]\n'
                '    ports: ["${FRONTEND_PORT}:80"]\n'
                '    build:\n      context: .\n      args:\n'
                '        KEY: ${VITE_GOONG_MAPTILES_KEY}\n', encoding="utf-8"
            )
            environ = {k: v for k, v in os.environ.items() if k not in deploy_env.deployment_values(self.secrets)}
            result = subprocess.run(
                ["docker", "compose", "--project-name", "env-test", "--env-file", str(root / ".env"),
                 "-f", str(root / "compose.yaml"), "config", "--format", "json"],
                capture_output=True, text=True, env=environ, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            service = json.loads(result.stdout)["services"]["check"]
            # Canonical Compose output escapes $ again for reuse as a Compose file.
            self.assertEqual(service["environment"]["GOONG_API_KEY"], private_key.replace("$", "$$"))
            self.assertEqual(service["build"]["args"]["KEY"], "test-public-key")
            self.assertEqual(service["ports"][0]["host_ip"], "127.0.0.1")
            self.assertEqual(service["ports"][0]["published"], "51873")
            resolved = subprocess.run(
                ["docker", "compose", "--project-name", "env-test", "--env-file", str(root / ".env"),
                 "-f", str(root / "compose.yaml"), "config", "--environment"],
                capture_output=True, text=True, env=environ, timeout=30,
            )
            self.assertEqual(resolved.returncode, 0, resolved.stderr)
            resolved_values = dict(line.split("=", 1) for line in resolved.stdout.splitlines() if "=" in line)
            self.assertEqual(resolved_values["GOONG_API_KEY"], private_key)


if __name__ == "__main__":
    unittest.main()
