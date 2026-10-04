# ETL

This service owns extraction, transformation, and loading into the warehouse. Each data domain has an independent pipeline under `src/pipelines/`; keep its source handling, transformations, models, and loading logic together. Put only genuinely shared infrastructure under `src/shared/`.

Run a selected pipeline with `python -m src.main population_hcmc` or `python -m src.main rainwater`. The current stage functions are placeholders and raise `NotImplementedError` until each source, data contract, and warehouse writer are selected. Tests are organized under `tests/pipelines/` to mirror the pipeline modules.

Run the WorldPop population extraction through Compose with `docker compose --profile etl-population-hcmc up --build etl-population-hcmc`. The downloaded rasters are stored in `etl/data/population_hcmc/worldpop` on the host. The rainwater pipeline has its own `etl-rainwater` service and profile; its stages are still placeholders.

Scheduling remains separate from pipeline logic so each pipeline can later receive its own cadence or scheduler configuration.
