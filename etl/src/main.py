"""Command-line entry point for the UrbanDynamics ETL pipelines."""

import argparse
import importlib
import logging
import os
import sys

PIPELINES = (
    "rainwater",
    "population_hcmc",
    "flood_history",
    "flood_satellite",
    "flood_risk",
    "land_price",
    "parcels_hcmc",
    "buildings_footprint",
    "buildings_footprint_gba",
)
STAGES = ("all", "extract", "transform", "load")


def _run(pipeline_name: str, stage: str, options) -> None:
    if stage == "all":
        option_names = {
            "rainwater": ("boundary", "refresh_history"),
            "flood_history": ("source", "boundary"),
            "flood_satellite": ("boundary", "catalog_only", "limit"),
            "flood_risk": ("weather_input", "history_input"),
            "land_price": ("source", "segments", "full_city", "automatic_reference"),
            "buildings_footprint": ("source", "refresh"),
            "buildings_footprint_gba": ("source", "refresh"),
        }.get(pipeline_name, ())
        kwargs = {name: getattr(options, name) for name in option_names}
        if pipeline_name == "flood_satellite" and kwargs["limit"] is None:
            kwargs.pop("limit")
        importlib.import_module(f"src.pipelines.{pipeline_name}.pipeline").run(
            **{key: value for key, value in kwargs.items() if value is not None}
        )
        return

    if pipeline_name == "parcels_hcmc" and stage in ("transform", "load"):
        from src.pipelines.parcels_hcmc import load, transform
        from src.pipelines.parcels_hcmc.config import config

        normalized = transform.run(config.download_dir)
        if stage == "load":
            load.run(normalized)
        return

    if pipeline_name == "buildings_footprint" and stage == "transform":
        from src.pipelines.buildings_footprint.transform import run

        run(options.source)
        return

    if pipeline_name == "buildings_footprint_gba" and stage == "transform":
        from src.pipelines.buildings_footprint_gba.transform import run

        run(options.source)
        return

    if pipeline_name == "buildings_footprint" and stage == "load":
        from src.pipelines.buildings_footprint.load import run

        run(options.source)
        return

    if pipeline_name == "buildings_footprint_gba" and stage == "load":
        from src.pipelines.buildings_footprint_gba.load import run

        run(options.source)
        return

    if stage == "extract":
        extractor = importlib.import_module(f"src.pipelines.{pipeline_name}.extract")
        if pipeline_name == "flood_history":
            extractor.run(options.source)
        elif pipeline_name == "flood_satellite":
            from src.shared.spatial import read_boundary

            if not options.boundary:
                raise ValueError("flood_satellite extract requires --boundary")
            extractor.run(
                read_boundary(options.boundary), options.catalog_only, options.limit
            )
        elif pipeline_name == "flood_risk":
            extractor.run(options.weather_input, options.history_input)
        elif pipeline_name == "land_price":
            from src.shared.data_io import data_dir, write_json

            rows, _provenance = extractor.run(
                options.source, full_city=options.full_city
            )
            output = data_dir() / "review" / "land_price_rows.json"
            write_json(output, rows)
            logging.getLogger(__name__).info("Extracted land-price rows to %s", output)
        elif (
            pipeline_name == "buildings_footprint"
            or pipeline_name == "buildings_footprint_gba"
        ):
            extractor.run(refresh=options.refresh)
        else:
            extractor.run()
        return

    raise NotImplementedError(
        f"The {stage!r} stage for {pipeline_name!r} is not ready to run on its own. "
        "Transform and load need persisted stage inputs and outputs."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an UrbanDynamics ETL pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser(
        "run", help="Run a pipeline or one of its stages"
    )
    run_parser.add_argument(
        "pipeline",
        nargs="?",
        choices=PIPELINES,
        default=os.getenv("ETL_PIPELINE"),
        help="Pipeline name (defaults to ETL_PIPELINE when set)",
    )
    run_parser.add_argument(
        "--source", help="Optional source file for supported pipelines"
    )
    run_parser.add_argument(
        "--boundary", help="WGS84 polygon file for spatial flood pipelines"
    )
    run_parser.add_argument(
        "--segments", help="Reviewed land-price road-segment GeoJSON"
    )
    run_parser.add_argument(
        "--weather-input", help="Rainfall forecast JSON for flood-risk"
    )
    run_parser.add_argument(
        "--history-input", help="Rainfall history JSON for flood-risk"
    )
    run_parser.add_argument(
        "--catalog-only",
        action="store_true",
        help="Load satellite catalog footprints only",
    )
    run_parser.add_argument(
        "--limit", type=int, default=None, help="Maximum satellite items to process"
    )
    run_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-fetch cached source data for building-footprint pipelines",
    )
    run_parser.add_argument(
        "--stage",
        choices=STAGES,
        default="all",
        help="Stage to run (default: all)",
    )
    run_parser.add_argument("--refresh-history", action="store_true")
    run_parser.add_argument("--full-city", action="store_true")
    run_parser.add_argument("--automatic-reference", action="store_true",
                            help="Automatically allocate table reference prices to all cached city roads")

    argv = sys.argv[1:]
    if argv and argv[0] in PIPELINES:
        argv = ["run", *argv]
    args = parser.parse_args(argv)
    if args.command == "run":
        if args.pipeline not in PIPELINES:
            parser.error(
                "provide a pipeline name or set ETL_PIPELINE "
                f"to one of: {', '.join(PIPELINES)}"
            )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        _run(args.pipeline, args.stage, args)


if __name__ == "__main__":
    main()
