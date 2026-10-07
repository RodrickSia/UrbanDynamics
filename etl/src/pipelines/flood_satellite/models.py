from dataclasses import dataclass


@dataclass(frozen=True)
class RasterCounts:
    valid_pixels: int | None
    flood_pixels: int
    excluded_pixels: int | None
