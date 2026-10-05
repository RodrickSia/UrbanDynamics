# ETL

This service owns extraction, transformation, and loading into the warehouse. Each data domain has an independent pipeline under `src/pipelines/`; keep its source handling, transformations, models, and loading logic together. Put only genuinely shared infrastructure under `src/shared/`.

The CLI uses `run` with an optional pipeline name and stage. Run all stages with `python -m src.main run population_hcmc`, or run extraction only with `python -m src.main run population_hcmc --stage extract`. In Compose, each service sets `ETL_PIPELINE`, so use `docker compose --profile etl-population-hcmc run --rm etl-population-hcmc run --stage extract`.

The downloaded rasters are stored in `etl/data/population_hcmc/worldpop` on the host. The `Run ETL pipelines` GitHub Actions workflow currently has a manual `HCMC population` job that runs all population stages against the configured warehouse. It uses a self-hosted Linux runner and preserves ignored workspace files between checkouts so later runs can reuse the downloaded rasters. Apply database migrations with the separate database workflow before running ETL. Configure the same `WAREHOUSE_PASSWORD` secret in the GitHub `production` environment.

The rainwater pipeline has its own `etl-rainwater` Compose service and profile; add a separate ETL workflow job when that pipeline is ready to run.

Scheduling remains separate from pipeline logic so each pipeline can later receive its own cadence or scheduler configuration.
