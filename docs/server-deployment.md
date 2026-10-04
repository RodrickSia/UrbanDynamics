# GitHub Actions deployment

Run `Deploy` on `feature/frontend-map-workspace`. The Linux self-hosted runner needs
Docker Compose with `up --wait`, Python 3 and curl. Runner `gpu156` already has the
`self-hosted` and `Linux` labels; its name is not a scheduling label.

The workflow creates a mode-0600 `.env` before Compose reads it, using repository
Actions secrets (never printed by the generator):

| Actions secret | Application variable | Use |
| --- | --- | --- |
| `MLAI_FRONTEND_GOONG` | `VITE_GOONG_MAPTILES_KEY` | Browser map tiles key, embedded in the frontend build |
| `MLAI_BACKEND_GOONG` | `GOONG_API_KEY` | Backend-only REST credential, available to future backend integrations |

The backend currently implements only `/health`; providing its key does not add
geocoding/data endpoints. Restrict the frontend browser key at the provider. The
backend key is never passed as a frontend build argument. The generated `.env` is
removed at job completion; manual Compose commands need it recreated securely.

Default host ports are **51873** (frontend) and **51874** (backend), both bound to
`127.0.0.1` for SSH access. Container ports remain 80 and 8000. Override with
repository Actions **variables** `FRONTEND_PORT` / `BACKEND_PORT` (numeric values,
1024–65535, distinct). High ports reduce common collisions but cannot guarantee a
free port on a shared server; Docker will fail if another service owns the port.

The workflow validates configuration, starts only frontend/backend, waits for
backend health and checks both HTTP responses. ETL stays behind its opt-in profile.
Deploys are serialized so two runs cannot overwrite the runner's `.env` concurrently.
Do not run this workflow simultaneously from another checkout outside Actions.

```powershell
gh workflow run deploy.yaml --repo RodrickSia/UrbanDynamics --ref feature/frontend-map-workspace
gh run watch --repo RodrickSia/UrbanDynamics
```

On your own computer, replace `SSH_USER`, `SERVER_HOST` and SSH port `22`:

```powershell
ssh -N -T -p 22 -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 127.0.0.1:51873:127.0.0.1:51873 -L 127.0.0.1:51874:127.0.0.1:51874 SSH_USER@SERVER_HOST
```

Open http://127.0.0.1:51873 for the map and http://127.0.0.1:51874/health for backend
health. Keep SSH running. When overriding ports, change both sides of the relevant
forward so the frontend's build-time API URL remains consistent.

Nginx explicitly permits `https://tiles.mapterhorn.com` in CSP `connect-src` so
MapLibre can load terrain metadata and DEM tiles. With the SSH tunnel open, verify
the actual deployed headers and terrain requests in Chromium from `frontend/`:

```sh
npx playwright test --config playwright.deploy.config.ts
```

Set `DEPLOY_BASE_URL` to test a different deployment URL. HTTP health checks alone
do not verify map rendering. Geolocation is still disabled by Permissions-Policy,
and browser API integration will need routing/CORS.

Verify the environment generator locally without real keys:

```sh
python -m unittest discover -s scripts -p 'test_*.py'
```
