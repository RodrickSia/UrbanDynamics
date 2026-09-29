# ETL

This service owns extraction, transformation, and loading into the warehouse. Keep source connectors under `src/extract/`, transformations under `src/transform/`, and warehouse writers under `src/load/`. The runner and schedule are deliberately left open for the ETL framework decision.
