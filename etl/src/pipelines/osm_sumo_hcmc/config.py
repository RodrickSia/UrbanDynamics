"""Paths and source settings for the HCMC OSM/SUMO network."""

from pathlib import Path

from pydantic import BaseModel


class OsmSumoConfig(BaseModel):
    data_dir: Path = Path("data/osm_sumo_hcmc")
    pbf_url: str = "https://download.geofabrik.de/asia/vietnam-latest.osm.pbf"
    # Expanded HCMC bounds, including a modest fringe for through-routes.
    west: float = 106.25
    south: float = 10.20
    east: float = 107.15
    north: float = 11.25
    database_schema: str = "transport"
    edge_table: str = "sumo_edge"
    junction_table: str = "sumo_junction"
    connection_table: str = "sumo_connection"


config = OsmSumoConfig()
