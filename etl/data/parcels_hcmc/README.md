# HCMC land plots (`parcels_hcmc`)

Public cadastral plots ("chi tiết thửa") for Ho Chi Minh City. This folder is the pipeline download directory (`data/parcels_hcmc` inside the ETL container). It does not contain listing prices.

## Pipeline

Code: `etl/src/pipelines/parcels_hcmc/`. Warehouse table: `parcels.land_plot`, created by `infra/warehouse/migrations/03-parcels-hcmc.sql`.

`extract` downloads zoom-16 vector tiles from `https://map-tile.onehousing.vn/data/hcm_all_thua/{z}/{x}/{y}.pbf` for the city bounds used by that map. Requests are one at a time, 1.2 seconds apart, and wait 60 seconds after HTTP 429. Empty tiles (HTTP 204) are recorded in `done.txt` and not written. A failed tile is left out of `done.txt`, so the next run retries it.

`transform` checks that this directory exists. Polygons are decoded per tile during load, from tile-local coordinates to WGS84. The source layer is `alameda`.

`load` inserts polygons that are not yet listed in `parcels.loaded_tile`. Attributes kept are `UNIQ_ID`, province, district, ward, sheet number, plot number, `MDSDD`, `LoaiDatQH`, decision, and project. The same plot can appear in more than one tile because polygons are clipped at tile edges; those pieces are all kept.

Apply the warehouse migration first, then:

```sh
docker compose --profile etl-parcels-hcmc run --rm etl-parcels-hcmc
```

A rerun skips tiles already named in `done.txt` and rows already recorded in `parcels.loaded_tile`.

## Data in this directory

| Path | What it is |
| --- | --- |
| `16/{x}/{y}.pbf` | Mapbox vector tiles. 3,123 non-empty tiles are stored. |
| `done.txt` | Journal of tiles already requested, one `z/x/y` per line. 12,287 lines, including empty tiles. |
| `samples/thua-q1.geojson` | One GeoJSON of the District 1 plots (57,514 features). Not read by the loader. |
| `samples/quyhoach.geojson` | Smaller early sample of planning polygons (5,556 features). Not read by the loader. |
| `.gitkeep` | Keeps the directory in git. |

The city bounds at zoom 16 are 23,370 tiles. This copy is only the northwest of the city through District 1 (about 106.36–106.71 E, 10.63–11.16 N). The rest still has to be downloaded. Do not commit a second copy under `web/`.
