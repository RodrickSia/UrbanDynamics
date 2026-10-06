"""Color PostGIS raster samples into cached PNG map tiles."""

from io import BytesIO

import numpy as np
from PIL import Image

TILE_SIZE = 256
PALETTES = {
    "pseudocolor": (
        (0, (0, 0, 0, 0)),
        (1, (255, 255, 178, 180)),
        (10, (254, 204, 92, 190)),
        (50, (253, 141, 60, 210)),
        (100, (240, 59, 32, 220)),
        (500, (189, 0, 38, 235)),
        (1000, (128, 0, 38, 245)),
    ),
    "greyscale": (
        (0, (0, 0, 0, 0)),
        (1, (245, 245, 245, 180)),
        (10, (210, 210, 210, 190)),
        (100, (120, 120, 120, 220)),
        (1000, (20, 20, 20, 245)),
    ),
    "fire": (
        (0, (0, 0, 0, 0)),
        (1, (255, 245, 180, 180)),
        (10, (255, 180, 70, 195)),
        (50, (235, 70, 35, 215)),
        (100, (145, 0, 24, 230)),
        (1000, (45, 0, 10, 245)),
    ),
}


def render_population_tile(samples: list[list[float | None]], palette: str) -> bytes:
    """Colorize 256x256 population samples with transparent nodata pixels."""
    if palette not in PALETTES:
        raise ValueError("Unknown population color palette")
    values = np.asarray(samples, dtype=np.float64)
    if values.shape != (TILE_SIZE, TILE_SIZE):
        raise ValueError("Population renderer requires a 256x256 raster tile")

    valid = np.isfinite(values)
    rgba = np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)
    if valid.any():
        stops = PALETTES[palette]
        positions = np.asarray([stop[0] for stop in stops], dtype=np.float64)
        pixels = values[valid]
        for band in range(4):
            colors = np.asarray([stop[1][band] for stop in stops], dtype=np.float64)
            rgba[..., band][valid] = np.rint(np.interp(pixels, positions, colors)).astype(np.uint8)

    image = Image.fromarray(rgba, mode="RGBA")
    output = BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()
