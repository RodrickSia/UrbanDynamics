# Main web deployment: AI agent and simulation

The main web uses server 156 loopback port **51873**. Preview **51875** (local tunnel 8192) stays separate.

On the existing server checkout, run:

```sh
python3 scripts/deploy-main-agent.py
```

The script checks for active planning jobs, records the previous commit and image tags in `.runtime/main-release-<UTC timestamp>/`, preserves existing PostGIS/runtime volumes, fast-forwards the server checkout to `origin/main`, builds, and recreates only the application services. It does not run ETL or database migrations. The backend initializes its own application storage when used, as before.

Backend credentials are copied server-to-server from the authorized preview into ignored `.env.agent.production.local` (mode 0600). They are not included in the frontend or added to Git. Only the public map tile key is a frontend build argument. Supplementary offline POIs and read-only snapshot/counting mounts are reused; preview conversations, plans and job history are not moved into main.

For later manual Compose commands, include **both** env files and the override:

```sh
docker compose -p urbandynamics --env-file .env --env-file .env.production.local -f compose.yaml -f compose.production-agent.yaml up -d
```

Before rollback, stop new submissions and check for running jobs. The release directory contains `previous-commit.txt`, `images.json`, and private copies of the previous env files. Use those saved images with a temporary Compose image override and the matching previous checkout; do not delete volumes or run `down -v`. An update failure is reported and needs an operator to inspect the log and restore the saved release if necessary.

Local tunnel to the main web:

```sh
ssh -N -L 127.0.0.1:8173:127.0.0.1:51873 nguyenmv@192.168.20.156
```

Open `http://127.0.0.1:8173/`. The server port is bound to loopback; use a tunnel or the team's existing reverse proxy.
