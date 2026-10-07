"""Run Khoi's integration checks against an isolated main-Compose warehouse."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    password = os.environ.get("WAREHOUSE_PASSWORD", "")
    if not password.strip():
        raise SystemExit("Set WAREHOUSE_PASSWORD before running local checks; no default password is used.")
    docker = shutil.which("docker")
    if not docker and os.name == "nt":
        docker = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    if not docker or not Path(docker).exists():
        raise SystemExit("Docker was not found; start Docker Desktop and try again.")

    environment = {
        **os.environ,
        "COMPOSE_PROJECT_NAME": f"khoi-local-{uuid.uuid4().hex[:8]}",
        "WAREHOUSE_HOST": "postgis",
        "WAREHOUSE_PORT": "5432",
        "WAREHOUSE_DATABASE": "khoi_local",
        "WAREHOUSE_USER": "khoi_local",
        "WAREHOUSE_PASSWORD": password,
        "POSTGIS_TESTS": "1",
    }
    compose = [docker, "compose"]
    env_path = ROOT / ".env"
    created_env = False
    if not env_path.exists():
        shutil.copyfile(ROOT / ".env.example", env_path)
        created_env = True

    def run(*arguments: str) -> None:
        subprocess.run([*compose, *arguments], cwd=ROOT, env=environment, check=True)

    try:
        run("up", "-d", "--build", "--wait", "--wait-timeout", "180", "postgis", "backend")
        run("exec", "-T", "postgis", "/usr/local/bin/migrate-warehouse")
        run("--profile", "checks", "run", "--rm", "khoi-checks")
        api_check = (
            "import urllib.request; "
            "[urllib.request.urlopen('http://backend:8000'+path, timeout=15).read() "
            "for path in ['/health','/api/v1/layers']]"
        )
        run("--profile", "checks", "run", "--rm", "--entrypoint", "python", "khoi-checks", "-c", api_check)
    finally:
        subprocess.run(
            [*compose, "down", "--volumes", "--remove-orphans"],
            cwd=ROOT,
            env=environment,
            check=False,
        )
        if created_env:
            env_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
