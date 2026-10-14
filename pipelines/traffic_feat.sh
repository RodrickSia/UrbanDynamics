#!/usr/bin/env bash
set -euo pipefail

# Run from the repository root regardless of the caller's working directory.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# Build the shared ETL image so all three services use the current pipeline code.
docker compose build \
  etl-osm-sumo-hcmc \
  etl-traffic-history \
  etl-road-data-tomtom

# Dependency order: publish the network, load historical observations, then
# attach the TomTom snapshot to SUMO edge IDs.
docker compose --profile traffic_feat run --rm \
  etl-osm-sumo-hcmc run --stage all

docker compose --profile traffic_feat run --rm \
  etl-traffic-history run --stage all

docker compose --profile traffic_feat run --rm \
  etl-road-data-tomtom run --stage all
