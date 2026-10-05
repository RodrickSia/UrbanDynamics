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

    ports = {}
    for name, default in (("FRONTEND_PORT", "51873"), ("BACKEND_PORT", "51874")):
        value = environ.get(name, default)
        if not value.isascii() or not value.isdecimal() or not 1024 <= int(value) <= 65535:
            raise ValueError(f"{name} must be a port between 1024 and 65535")
        ports[name] = int(value)
        values[name] = f"127.0.0.1:{int(value)}"
    if ports["FRONTEND_PORT"] == ports["BACKEND_PORT"]:
        raise ValueError("Frontend and backend must use different ports")
    values["VITE_API_BASE_URL"] = f"http://127.0.0.1:{ports['BACKEND_PORT']}"
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
