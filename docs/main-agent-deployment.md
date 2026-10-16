# Main web deployment: AI agent and simulation

The main web uses server 156 loopback port **51873**. Preview **51875** (local tunnel 8192) stays separate.

GitHub Actions **Deploy** is a manual workflow targeting `main`. It calls the same deployment script against the persistent server checkout and private configuration; it does not delete the server env files or deploy from a temporary runner data directory. It must run on the existing server 156 Linux runner.

On the existing server checkout, run:

```sh
python3 scripts/deploy-main-agent.py
```

The script checks for active planning jobs, records the previous commit and image tags in `.runtime/main-release-<UTC timestamp>/`, preserves existing PostGIS/runtime volumes, fast-forwards the server checkout to `origin/main`, builds, and recreates only the application services. It does not run ETL or database migrations. The backend initializes its own application storage when used, as before.

If the server cannot authenticate to GitHub, transfer a Git bundle of the already pushed main commit and pass `--bundle /absolute/path/main.bundle`. The script verifies it before fetching; no GitHub credentials need to be copied to the server.

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

## Verification on 16 October 2026

- Merged the development simulation context and all 34 agent tools into current main, retaining main's newer SUMO fixes.
- 82 agent/PostGIS tests and 35 traffic/development-context/zoning tests passed (117 total); frontend TypeScript/Vite build passed.
- Deployed frontend, backend, planning worker and the existing traffic worker service; PostGIS was not recreated and no warehouse migration/ETL was run.
- Main web and agent configuration returned HTTP 200; all 11 dataset query adapters returned HTTP 200. Empty flood/SUMO results in the tested viewport indicate missing records/results, not absence of risk.
- Verified the robot button opens the panel, Goong map responses succeed, and no browser runtime errors occurred in Edge.
- A real English prompt submitted with Enter completed through the model and PostGIS query tools and returned counts, two candidates and the vacancy caveat.
- Local evidence: ignored `test-results/main-release/`, including `main-smoke.json`, `main-model.json`, and desktop/response screenshots.
- The updated manual GitHub Deploy workflow has not itself been dispatched as part of this deployment.
