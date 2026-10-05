from contextlib import ExitStack
from dataclasses import asdict

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import shapes
from rasterio.mask import mask
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_geom
from shapely.geometry import mapping, shape

from src.shared.data_io import collection

from .config import FLOOD_ASSET, MASK_ASSET, STAC_URL
from .models import RasterCounts


def observed_features(flood_path, exclusion_path, boundary, item):
    with ExitStack() as stack:
        flood = stack.enter_context(rasterio.open(flood_path))
        exclusion = (
            stack.enter_context(rasterio.open(exclusion_path))
            if exclusion_path
            else None
        )
        if flood.crs is None or exclusion is not None and exclusion.crs is None:
            raise ValueError("Raster CRS missing")
        boundary_projected = transform_geom("EPSG:4326", flood.crs, mapping(boundary))
        pixels, affine = mask(flood, [boundary_projected], crop=True, filled=False)
        height, width = pixels.shape[1:]
        if height * width > 20_000_000:
            raise ValueError("Raster window too large for MVP; use a smaller boundary")
        flood_values = pixels[0]
        source_valid = ~np.ma.getmaskarray(flood_values)
        if exclusion is not None:
            with WarpedVRT(
                exclusion,
                crs=flood.crs,
                transform=affine,
                height=height,
                width=width,
                resampling=Resampling.nearest,
            ) as aligned:
                excluded = aligned.read(1, masked=True)
            valid = source_valid & ~np.ma.getmaskarray(excluded) & (excluded.data == 0)
        else:
            # The provider's final ensemble already applies exclusion/reference-water masks.
            # We can display its positive flood pixels; zeros cannot establish verified dry coverage.
            valid = source_valid
        selected = valid & (flood_values.data == 1)
        output = []
        for index, (geometry, value) in enumerate(
            shapes(selected.astype("uint8"), mask=selected, transform=affine)
        ):
            geometry = shape(
                transform_geom(flood.crs, "EPSG:4326", geometry)
            ).intersection(boundary)
            if geometry.is_empty:
                continue
            output.append(
                {
                    "type": "Feature",
                    "id": f"{item['id']}:{index}",
                    "geometry": mapping(geometry),
                    "properties": {
                        "observed_at": item["properties"].get("datetime"),
                        "item_id": item["id"],
                        "source_url": item["assets"][FLOOD_ASSET]["href"],
                        "exclusion_mask_applied_locally": exclusion is not None,
                        "mask_mode": "local_mask"
                        if exclusion is not None
                        else "provider_masked_ensemble",
                        "kind": "satellite_observed_flood",
                    },
                }
            )
        counts = RasterCounts(
            int(valid.sum()) if exclusion is not None else None,
            int(selected.sum()),
            int((source_valid & ~valid).sum()) if exclusion is not None else None,
        )
        return output, asdict(counts)


def run(records, boundary, catalog_only=False):
    features, observations = [], []
    for record in records:
        item = record["item"]
        if catalog_only:
            footprint = shape(item["geometry"]).intersection(boundary)
            if not footprint.is_empty:
                features.append(
                    {
                        "type": "Feature",
                        "id": item["id"],
                        "geometry": mapping(footprint),
                        "properties": {
                            "observed_at": item["properties"].get("datetime"),
                            "item_id": item["id"],
                            "kind": "coverage_only",
                            "assets": item.get("assets", {}),
                            "flood_pixels_verified": False,
                        },
                    }
                )
        else:
            pixels, counts = observed_features(
                record["paths"][FLOOD_ASSET],
                record["paths"].get(MASK_ASSET),
                boundary,
                item,
            )
            features.extend(pixels)
            observations.append(
                {
                    "item_id": item["id"],
                    "counts": counts,
                    "provenance": record["provenance"],
                }
            )
    return collection(
        "flood_satellite_catalog" if catalog_only else "flood_satellite",
        features,
        scope="boundary-filtered",
        source_url=STAC_URL,
        observations=observations,
        raster_verified=not catalog_only,
        items=len(records),
        mask_reference="https://extwiki.eodc.eu/GFM/PUM/Products",
        dry_coverage_verified=False,
        limitations="Satellite sampling may miss short urban floods. Excluded areas are not verified dry.",
    )
