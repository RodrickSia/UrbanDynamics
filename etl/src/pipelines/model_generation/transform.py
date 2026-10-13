"""Inset residential parcel silhouettes and assign reproducible observed heights."""

import hashlib
import json
import logging
import math
import os
from pathlib import Path

from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform as transform_geometry

from src.pipelines.model_generation.config import ModelGenerationConfig, config
from src.shared.data_io import data_dir

logger = logging.getLogger(__name__)
_TO_METERS = Transformer.from_crs("EPSG:4326", "EPSG:32648", always_xy=True)
_TO_WGS84 = Transformer.from_crs("EPSG:32648", "EPSG:4326", always_xy=True)


def _sample_height(parcel_id: int, distribution: dict, settings: ModelGenerationConfig) -> float:
    samples = distribution["height_samples"]
    total = sum(item["count"] for item in samples)
    selector = int(
        hashlib.sha256(f"{settings.seed}:{parcel_id}".encode()).hexdigest(), 16
    ) % total
    for item in samples:
        selector -= item["count"]
        if selector < 0:
            return float(item["height_m"])
    raise RuntimeError("Could not sample a residential height")


def _polygon_parts(geometry) -> list[Polygon]:
    geometry = make_valid(geometry)
    if geometry.geom_type == "Polygon":
        return [geometry] if not geometry.is_empty and geometry.area > 0 else []
    if geometry.geom_type == "MultiPolygon":
        return [part for part in geometry.geoms if not part.is_empty and part.area > 0]
    if hasattr(geometry, "geoms"):
        return [part for item in geometry.geoms for part in _polygon_parts(item)]
    return []


def _setback(area_m2: float, settings: ModelGenerationConfig) -> float:
    return min(
        settings.maximum_inset_m,
        max(settings.minimum_inset_m, math.sqrt(area_m2) * settings.inset_ratio),
    )


def run(settings: ModelGenerationConfig = config) -> Path:
    """Write inset synthetic building polygons as a streaming JSONL snapshot."""
    root = data_dir() / settings.data_dir.name
    candidates_path = root / "candidates.jsonl"
    distribution_path = root / "residential_height_distribution.json"
    output_path = root / "synthetic_buildings.jsonl"
    output_part = output_path.with_suffix(output_path.suffix + ".part")
    manifest_path = root / "manifest.json"
    manifest_part = manifest_path.with_suffix(manifest_path.suffix + ".part")
    if not candidates_path.is_file() or not distribution_path.is_file():
        raise FileNotFoundError("Run model_generation extract before transform")

    distribution = json.loads(distribution_path.read_text(encoding="utf-8"))
    candidate_count = generated = rejected = 0
    with candidates_path.open(encoding="utf-8") as source, output_part.open(
        "w", encoding="utf-8"
    ) as target:
        for line in source:
            candidate_count += 1
            parcel = json.loads(line)
            parcel_id = parcel["parcel_id"]
            area_m2 = parcel["area_m2"]
            source_geometry = shape(parcel["geometry"])
            metric_geometry = transform_geometry(_TO_METERS.transform, source_geometry)
            inset_m = _setback(area_m2, settings)
            inset = metric_geometry.buffer(-inset_m)
            parts = _polygon_parts(inset)
            if not parts:
                rejected += 1
                continue
            footprint = MultiPolygon(parts)
            wgs84_footprint = transform_geometry(_TO_WGS84.transform, footprint)
            height_m = _sample_height(parcel_id, distribution, settings)
            floors = max(1, round(height_m / settings.storey_height_m))
            target.write(
                json.dumps(
                    {
                        "parcel_id": parcel_id,
                        "mdsdd": parcel["mdsdd"],
                        "height_m": height_m,
                        "floors": floors,
                        "inset_m": inset_m,
                        "height_source": distribution["source"],
                        "geometry": mapping(wgs84_footprint),
                    },
                    allow_nan=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
            generated += 1
            if generated and generated % 100_000 == 0:
                logger.info("Generated %s parcel-based building models", generated)

    manifest = {
        "pipeline": "model_generation",
        "generator_version": "1",
        "seed": settings.seed,
        "residential_codes": list(settings.residential_codes),
        "height_source": distribution["source"],
        "candidate_count": candidate_count,
        "generated_count": generated,
        "rejected_geometry_count": rejected,
    }
    with manifest_part.open("w", encoding="utf-8") as stream:
        json.dump(manifest, stream, allow_nan=False)
    os.replace(output_part, output_path)
    os.replace(manifest_part, manifest_path)
    logger.info(
        "Generated %s models from %s candidate parcels (%s could not fit the setback)",
        generated,
        candidate_count,
        rejected,
    )
    return output_path
