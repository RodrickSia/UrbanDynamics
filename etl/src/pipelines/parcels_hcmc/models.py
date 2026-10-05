"""One land-plot polygon decoded from a vector tile."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LandPlot:
    uniq_id: str | None
    tinh: str | None
    quan: str | None
    phuong: str | None
    to_ban_do: str | None
    thua: str | None
    mdsdd: str | None
    loai_dat_qh: str | None
    quyet_dinh: str | None
    do_an: str | None
    tile_z: int
    tile_x: int
    tile_y: int
    geojson: str
