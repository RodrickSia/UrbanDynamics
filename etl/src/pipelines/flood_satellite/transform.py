from contextlib import ExitStack
from dataclasses import asdict

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import shapes
from rasterio.mask import mask
from rasterio.warp import transform_geom
from rasterio.vrt import WarpedVRT
from shapely.geometry import shape, mapping
from src.shared.data_io import collection,data_dir,read_json,write_json
import hashlib
import json
import logging
from pathlib import Path
import shutil
import tempfile
from .config import FLOOD_ASSET, MASK_ASSET, STAC_URL
from .models import RasterCounts


def observed_features(flood_path, exclusion_path, boundary, item):
    """Read bounded native raster windows, including disconnected island regions."""
    from rasterio.features import geometry_mask
    from rasterio.windows import Window, bounds as window_bounds
    from shapely.geometry import box
    from shapely.prepared import prep
    output = []
    valid_count = flood_count = excluded_count = 0
    with ExitStack() as stack:
        # GDAL makes many random block reads. Stage each compressed raster once
        # onto container-local disk instead of repeating Windows bind-mount I/O.
        scratch = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='gfm-raster-')))
        local_flood = scratch/'flood.tif'; shutil.copyfile(flood_path,local_flood)
        local_mask = scratch/'mask.tif'
        if exclusion_path: shutil.copyfile(exclusion_path,local_mask)
        flood = stack.enter_context(rasterio.open(local_flood))
        exclusion = stack.enter_context(rasterio.open(local_mask)) if exclusion_path else None
        if flood.crs is None or exclusion is not None and exclusion.crs is None:
            raise ValueError("Raster CRS missing")
        projected = shape(transform_geom("EPSG:4326",flood.crs,mapping(boundary)))
        prepared = prep(projected)
        aligned = stack.enter_context(WarpedVRT(exclusion,crs=flood.crs,transform=flood.transform,
                    width=flood.width,height=flood.height,resampling=Resampling.nearest)) if exclusion else None
        for row in range(0,flood.height,1024):
            for col in range(0,flood.width,1024):
                window = Window(col,row,min(1024,flood.width-col),min(1024,flood.height-row))
                tile = box(*window_bounds(window,flood.transform))
                if not prepared.intersects(tile):
                    continue
                values = flood.read(1,window=window,masked=True)
                affine = flood.window_transform(window)
                inside = (np.ones(values.shape,dtype=bool) if prepared.contains(tile) else
                          geometry_mask([mapping(projected.intersection(tile))],out_shape=values.shape,
                                        transform=affine,invert=True))
                source_valid = ~np.ma.getmaskarray(values) & inside
                if aligned is not None:
                    excluded = aligned.read(1,window=window,masked=True)
                    valid = source_valid & ~np.ma.getmaskarray(excluded) & (excluded.data==0)
                else:
                    valid = source_valid
                selected = valid & (values.data==1)
                valid_count += int(valid.sum())
                flood_count += int(selected.sum())
                excluded_count += int((source_valid & ~valid).sum())
                for geometry,value in shapes(selected.astype("uint8"),mask=selected,transform=affine):
                    geometry = shape(transform_geom(flood.crs,"EPSG:4326",geometry)).intersection(boundary)
                    if geometry.is_empty: continue
                    output.append({"type":"Feature","id":f'{item["id"]}:{len(output)}',
                        "geometry":mapping(geometry),"properties":{
                            "observed_at":item["properties"].get("datetime"),"item_id":item["id"],
                            "source_url":item["assets"][FLOOD_ASSET]["href"],
                            "exclusion_mask_applied_locally":exclusion is not None,
                            "mask_mode":"local_mask" if exclusion is not None else "provider_masked_ensemble",
                            "kind":"satellite_observed_flood"}})
    return output,asdict(RasterCounts(valid_count if exclusion else None,flood_count,
                                     excluded_count if exclusion else None))
def run(records, boundary, catalog_only=False):
    features, observations = [], []
    boundary_key = hashlib.sha256(json.dumps(mapping(boundary),sort_keys=True).encode()).hexdigest()[:20]
    for index,record in enumerate(records,1):
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
            logging.getLogger(__name__).info('GFM process %s/%s %s',index,len(records),item['id'])
            signatures = [(p['url'],p['sha256']) for p in record.get('provenance',[])]
            key = hashlib.sha256(json.dumps([item,boundary_key,signatures,'stream-clipped-v3'],sort_keys=True).encode()).hexdigest()
            cache = data_dir()/'derived/flood_satellite'/boundary_key/(key+'.json')
            if signatures and cache.exists():
                cached = read_json(cache); pixels,counts = cached['features'],cached['counts']
            else:
                pixels, counts = observed_features(record["paths"][FLOOD_ASSET], record["paths"].get(MASK_ASSET), boundary, item)
                if signatures: write_json(cache,{'features':pixels,'counts':counts})
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
