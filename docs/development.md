# Development conventions

- Keep each service's runtime dependencies and container build context inside that service directory.
- Use the root `compose.yaml` to run the local stack; run the ETL profile explicitly until its scheduler is chosen.
- Keep credentials in local `.env` files or GitHub Actions secrets. Commit only `.env.example` with variable names and safe defaults.
- Put CI/CD workflow definitions in `.github/workflows/` and keep deployment runner labels and secrets environment-specific.
