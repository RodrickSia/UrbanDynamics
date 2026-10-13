"""Bounded ESA WorldCover COG window acquisition (preparation only)."""
import math
import hashlib
from shapely.geometry import box, shape, mapping


def fetch(bbox):
    import rasterio
    from rasterio.features import shapes
    from rasterio.windows import from_bounds
    west, south, east, north = bbox
    lon, lat = math.floor(west/3)*3, math.floor(south/3)*3
    if east > lon+3 or north > lat+3:
        raise ValueError("Pilot crosses WorldCover tile boundary; prepare separate windows")
    tile = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}"
    url = f"https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="20", GDAL_HTTP_CONNECTTIMEOUT="10",
                      CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", GDAL_HTTP_MAX_RETRY="0"):
        with rasterio.open(url) as source:
            if source.crs.to_epsg() != 4326:
                raise ValueError("Unexpected WorldCover CRS")
            window = from_bounds(*bbox, transform=source.transform).round_offsets().round_lengths()
            if window.width*window.height > 200000:
                raise ValueError("WorldCover window exceeds pilot limit")
            values = source.read(1, window=window)
            affine = source.window_transform(window)
            features = []
            for geometry, code in shapes(values, mask=values != 0, transform=affine):
                clipped = shape(geometry).intersection(box(*bbox))
                if not clipped.is_empty:
                    features.append({"type": "Feature", "geometry": mapping(clipped),
                                     "properties": {"class_code": int(code), "kind": "satellite_classification", "year": 2021}})
    return {"type": "FeatureCollection", "features": features,
            "metadata": {"source_url": url, "dataset": "ESA WorldCover 2021 v200", "year": 2021,
                         "resolution_m": 10, "license": "CC-BY-4.0", "attribution": "ESA WorldCover project 2021",
                         "reference": "https://esa-worldcover.org/en/data-access", "pixel_sha256": hashlib.sha256(values.tobytes()).hexdigest(),
                         "limitations": "Historical 2021 classification, not current survey. Built-up does not distinguish roofs from paving or quantify permeability."}}
