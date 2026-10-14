"""Build a routable SUMO network from the cropped OSM PBF."""

import logging
import os
import subprocess
from pathlib import Path

from src.pipelines.osm_sumo_hcmc.config import OsmSumoConfig, config

logger = logging.getLogger(__name__)


def run(settings: OsmSumoConfig = config):
    source = settings.data_dir / "hcmc.osm.pbf"
    osm_xml = settings.data_dir / "hcmc.osm"
    output = settings.data_dir / "hcmc.net.xml"
    if not source.exists():
        raise FileNotFoundError(f"Missing {source}; run the extract stage first")
    if not osm_xml.exists() or osm_xml.stat().st_mtime < source.stat().st_mtime:
        logger.info("Converting cropped OSM PBF to OSM XML for netconvert")
        subprocess.run(
            ["osmium", "cat", str(source), "--output", str(osm_xml), "--overwrite"],
            check=True,
        )
    type_map = Path(os.environ.get("SUMO_HOME", "/usr/share/sumo")) / "data/typemap/osmNetconvert.typ.xml"
    if not type_map.is_file():
        raise FileNotFoundError(
            f"SUMO OSM type map not found at {type_map}; check the SUMO_HOME setting"
        )
    subprocess.run(
        [
            "netconvert",
            "--osm-files", str(osm_xml),
            "--output-file", str(output),
            "--type-files", str(type_map),
            "--junctions.join",
            "--tls.guess-signals",
            "--roundabouts.guess",
            "--output.street-names",
            "--proj.utm",
            "--no-turnarounds",
        ],
        check=True,
    )
    logger.info("SUMO network written to %s", output)
    return output
