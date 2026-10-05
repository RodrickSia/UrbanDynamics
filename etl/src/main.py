"""Command-line entry point for the UrbanDynamics ETL pipelines."""

import argparse
import importlib
import logging
import os


PIPELINES = ("population_hcmc", "rainwater")
STAGES = ("all", "extract", "transform", "load")


def _run(pipeline_name: str, stage: str) -> None:
    if stage == "all":
        importlib.import_module(f"src.pipelines.{pipeline_name}.pipeline").run()
        return

    if stage == "extract":
        importlib.import_module(f"src.pipelines.{pipeline_name}.extract").run()
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
        _run(args.pipeline, args.stage)


if __name__ == "__main__":
    main()
