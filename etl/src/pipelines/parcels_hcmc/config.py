"""Source tile template and local extraction settings for HCMC land plots."""

from pathlib import Path

from pydantic import BaseModel


class ParcelsHCMCConfig(BaseModel):
    """Public cadastral tiles for the HCMC bounds used by the source map.

    Prices and listing tiles are not part of this pipeline. Requests stay slow
    because the tile host answers HTTP 429 when they are not.
    """

    download_dir: Path = Path("data/parcels_hcmc")
    tile_url: str = "https://map-tile.onehousing.vn/data/hcm_all_thua/{z}/{x}/{y}.pbf"
    west: float = 106.3567007
    south: float = 10.1399458
    east: float = 107.0276712
    north: float = 11.1603083
    zoom: int = 16
    request_delay_seconds: float = 1.2
    rate_limit_cooldown_seconds: float = 60.0
    database_schema: str = "parcels"
    plot_table: str = "land_plot"
    loaded_tile_table: str = "loaded_tile"
    user_agent: str = "urbandynamics-parcels/0.1"
    referer: str = "https://maps.onehousing.vn/quy-hoach"


config = ParcelsHCMCConfig()
