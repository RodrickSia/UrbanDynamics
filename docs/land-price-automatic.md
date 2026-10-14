# Automatic land-price references

The requested policy prioritizes road coverage. Prices are preserved from the
published table; automatic placement can approximate the published road extent.
The map has one common presentation. Internal provenance remains available.

The verified 2026-10-13 snapshot contains 9,502 PDF rows, including all 7,080
original pending IDs, and 63,621 sourced OSM road pieces with reference prices.
The original 2,367 verified segment geometries are preserved separately.
Coverage is limited to roads present in the cached OSM source, not every possible street.

## Generate, verify and publish

Run from the repository root:

```sh
python scripts/auto-match-land-prices.py --output-dir .runtime/land-price-automatic
python scripts/verify-land-price-automatic.py --snapshot-dir .runtime/land-price-automatic
python scripts/publish-land-price-automatic.py --snapshot-dir .runtime/land-price-automatic --mirror-dir data --warehouse
python scripts/verify-land-price-automatic.py --api
```

The publisher checks input/output SHA256 hashes and saves the previous snapshot.
Runtime data is transferred separately and is not committed to Git.

`layers/land_price.geojson` supplies the road map and PostGIS. The catalogue API
`GET /api/v1/land-prices/catalog` reads `review/land_price_row_matches.geojson`,
so PDF row identities remain distinct from OSM road identities. Geometry is
optional; pagination, text search and region filters are supported.

From `etl/`, run `python -m src.main run land_price --full-city --automatic-reference`.
For scheduled refreshes set `LAND_PRICE_AUTOMATIC_REFERENCE=true` on the Khôi
ETL service. This reuses cached sources; source refresh is an explicit CLI task.
Keep the verified segment snapshot when refreshing to preserve earlier matches.

## Persistent deployment data

Set `URBANDYNAMICS_DATA_DIR` to an absolute directory outside the Git checkout
on deployed hosts. Backend and ETL share this directory.
The local default remains `./etl/data`. Copy existing data and the verified
land-price snapshot before switching the mount; retain a backup.
This protects raw sources, row matches and PDF files from checkout cleanup.
Keep deployment credentials and the Goong build key in an environment file
outside the checkout and pass it using `docker compose --env-file PATH`.
