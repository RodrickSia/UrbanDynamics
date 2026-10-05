"""Validate and normalize the downloaded population raster paths."""

from collections.abc import Mapping
from pathlib import Path


def run(raw_data: Mapping[int, Path]) -> dict[int, Path]:
    """Pass through the extracted year-to-raster mapping in stable year order."""
    if not raw_data:
        raise ValueError("No population rasters were extracted")

    normalized: dict[int, Path] = {}
    for year, raster_path in sorted(raw_data.items()):
        if not isinstance(year, int) or not 1900 <= year <= 2200:
            raise ValueError(f"Invalid population raster year: {year!r}")
        normalized[year] = Path(raster_path)
    return normalized
