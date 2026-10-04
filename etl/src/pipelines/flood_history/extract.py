from pathlib import Path
from src.shared.data_io import data_dir, download, file_provenance
from .config import GPKG_URL, TSV_URL

def run(source=None):
    if source:
        return Path(source), [file_provenance(source,GPKG_URL)]
    directory = data_dir() / "raw" / "flood_history"
    gpkg = directory / "HCMC_Floods_BDD.gpkg"
    provenance = [download(GPKG_URL, gpkg), download(TSV_URL, directory / "Flood_event_locations.tsv")]
    return gpkg, provenance
