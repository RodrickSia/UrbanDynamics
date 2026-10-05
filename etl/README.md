# ETL

This service owns extraction, transformation, and loading into the warehouse. Each data domain has an independent pipeline under `src/pipelines/`; keep its source handling, transformations, models, and loading logic together. Put only genuinely shared infrastructure under `src/shared/`.

The CLI uses `run` with an optional pipeline name and stage. Run all stages with `python -m src.main run population_hcmc`, or run extraction only with `python -m src.main run population_hcmc --stage extract`. In Compose, each service sets `ETL_PIPELINE`, so use `docker compose --profile etl-population-hcmc run --rm etl-population-hcmc run --stage extract`.

The downloaded rasters are stored in `etl/data/population_hcmc/worldpop` on the host. Transform and load are placeholders, so currently run the population pipeline with `--stage extract`. The rainwater pipeline also has its own `etl-rainwater` service and profile.

Scheduling remains separate from pipeline logic so each pipeline can later receive its own cadence or scheduler configuration.
