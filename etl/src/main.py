"""Command-line entry point for the UrbanDynamics ETL pipelines."""

import argparse
import importlib
import logging
import os


PIPELINES = (
    "population_hcmc",
    "rainwater",
    "flood_history",
    "flood_satellite",
    "flood_risk",
    "land_price",
)
STAGES = ("all", "extract", "transform", "load")


def _run(pipeline_name: str, stage: str, options) -> None:
    if stage == "all":
        option_names = {
            "flood_history": ("source", "boundary"),
            "flood_satellite": ("boundary", "catalog_only", "limit"),
            "flood_risk": ("weather_input", "history_input"),
            "land_price": ("source", "segments"),
        }.get(pipeline_name, ())
        kwargs = {name: getattr(options, name) for name in option_names}
        if pipeline_name == "flood_satellite" and kwargs["limit"] is None:
            kwargs.pop("limit")
        importlib.import_module(f"src.pipelines.{pipeline_name}.pipeline").run(
            **{key: value for key, value in kwargs.items() if value is not None}
        )
        return

    if stage == "extract":
        extractor = importlib.import_module(f"src.pipelines.{pipeline_name}.extract")
        if pipeline_name == "flood_history":
            extractor.run(options.source)
        elif pipeline_name == "flood_satellite":
            from src.shared.spatial import read_boundary
            if not options.boundary:
                raise ValueError("flood_satellite extract requires --boundary")
            extractor.run(read_boundary(options.boundary), options.catalog_only, options.limit)
        elif pipeline_name == "flood_risk":
            extractor.run(options.weather_input, options.history_input)
        elif pipeline_name == "land_price":
            extractor.run(options.source)
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
    run_parser = subparsers.add_parser("run", help="Run a pipeline or one of its stages")
    run_parser.add_argument(
        "pipeline",
        nargs="?",
        choices=PIPELINES,
        default=os.getenv("ETL_PIPELINE"),
        help="Pipeline name (defaults to ETL_PIPELINE when set)",
    )
    run_parser.add_argument("--source", help="Optional source file for supported pipelines")
    run_parser.add_argument("--boundary", help="WGS84 polygon file for spatial flood pipelines")
    run_parser.add_argument("--segments", help="Reviewed land-price road-segment GeoJSON")
    run_parser.add_argument("--weather-input", help="Rainfall forecast JSON for flood-risk")
    run_parser.add_argument("--history-input", help="Rainfall history JSON for flood-risk")
    run_parser.add_argument("--catalog-only", action="store_true", help="Load satellite catalog footprints only")
    run_parser.add_argument("--limit", type=int, default=None, help="Maximum satellite items to process")
    run_parser.add_argument(
        "--stage",
        choices=STAGES,
        default="all",
        help="Stage to run (default: all)",
    )

    args = parser.parse_args()
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
