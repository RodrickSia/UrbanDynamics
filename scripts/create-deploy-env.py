"""Create Compose's .env before deployment; never print secret values."""

import json
import os
from pathlib import Path
import sys
import tempfile


def deployment_values(environ):
    values = {}
    for secret, target in (
        ("MLAI_FRONTEND_GOONG", "VITE_GOONG_MAPTILES_KEY"),
        ("MLAI_BACKEND_GOONG", "GOONG_API_KEY"),
    ):
        value = environ.get(secret, "")
        if not value.strip() or any(char in value for char in "\r\n\x00"):
            raise ValueError(f"{secret} must contain a non-empty, single-line API key")
        values[target] = value

    warehouse_password = environ.get("WAREHOUSE_PASSWORD", "")
    if not warehouse_password.strip() or any(char in warehouse_password for char in "\r\n\x00"):
        raise ValueError("WAREHOUSE_PASSWORD must contain a non-empty, single-line password")
    values["WAREHOUSE_DATABASE"] = environ.get("WAREHOUSE_DATABASE", "urbandynamics")
    values["WAREHOUSE_USER"] = environ.get("WAREHOUSE_USER", "urbandynamics")
    values["WAREHOUSE_PASSWORD"] = warehouse_password

    value = environ.get("FRONTEND_PORT", "51873")
    if not value.isascii() or not value.isdecimal() or not 1024 <= int(value) <= 65535:
        raise ValueError("FRONTEND_PORT must be a port between 1024 and 65535")
    values["FRONTEND_PORT"] = f"127.0.0.1:{int(value)}"
    values["VITE_API_BASE_URL"] = ""
    return values


def write_environment(destination, environ):
    values = deployment_values(environ)
    # Double-quoted dotenv values escape quotes/backslashes. $$ prevents Compose
    # from expanding dollar signs present in a secret as variable references.
    content = "".join(
        f"{name}={json.dumps(value, ensure_ascii=False).replace('$', '$$')}\n"
        for name, value in values.items()
    )
    destination = Path(destination)
    descriptor, temporary = tempfile.mkstemp(prefix=".env.deploy-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        write_environment(Path(".env"), os.environ)
    except ValueError as error:
        print(f"Deployment configuration error: {error}", file=sys.stderr)
        sys.exit(1)
