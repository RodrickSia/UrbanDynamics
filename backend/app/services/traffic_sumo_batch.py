"""Queue and monitor exactly one six-hour SUMO scenario."""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import time as clock_time
from uuid import uuid4

from src.shared.database import connect_to_warehouse

from app.services.traffic_sumo_prediction import SIMULATION_MODEL, catalog

DEFAULT_WEEKDAY = int(os.getenv("TRAFFIC_SIMULATION_WEEKDAY", "1"))
DEFAULT_PERIOD = os.getenv("TRAFFIC_SIMULATION_PERIOD", "08:00")
logger = logging.getLogger(__name__)


def _validate_scenario(weekday: int, period: str) -> clock_time:
    if not 1 <= weekday <= 7:
        raise ValueError("weekday must be between 1 (Monday) and 7 (Sunday)")
    try:
        parsed = clock_time.fromisoformat(period)
    except ValueError as error:
        raise ValueError("period must be a time such as 08:00 or 08:30") from error
    if parsed.minute not in (0, 30) or parsed.second or parsed.microsecond:
        raise ValueError("period must be on a 30-minute boundary, such as 08:00 or 08:30")
    return parsed


def queue_missing_scenario(weekday: int, period: str) -> tuple[int, bool]:
    """Queue one uncached weekday/start-time scenario; leave a valid cache untouched."""
    parsed_period = _validate_scenario(weekday, period)
    if not catalog()["available"]:
        raise RuntimeError(
            "SUMO scenario run requires the HCMC network input, road-edge catalog, and queue table"
        )
    with connect_to_warehouse() as connection, connection.transaction():
        migration = connection.execute(
            "SELECT to_regclass('transport.sumo_congestion_scenario_cache')"
        ).fetchone()
        if migration[0] is None:
            raise RuntimeError(
                "SUMO scenario cache migration is missing; run Deploy database first"
            )
        cached = connection.execute(
            """
            SELECT 1 FROM transport.sumo_congestion_scenario_cache
            WHERE weekday = %s AND period = %s
              AND metadata->>'simulation_model' = %s
            """,
            (weekday, parsed_period, SIMULATION_MODEL),
        ).fetchone()
        if cached:
            return 0, True
        result = connection.execute(
            """
            INSERT INTO transport.sumo_congestion_run (run_id, weekday, period, status)
            VALUES (%s, %s, %s, 'queued')
            ON CONFLICT (weekday, period)
                WHERE status IN ('queued', 'running') DO NOTHING
            """,
            (uuid4(), weekday, parsed_period),
        )
        return result.rowcount, False


def enqueue_scenario(weekday: int, period: str) -> str:
    """Queue a scenario, or report that it is already active or cached."""
    queued, cached = queue_missing_scenario(weekday, period)
    outcome = "cached" if cached else "queued" if queued else "already_active"
    logger.info(
        "SUMO six-hour scenario enqueue result: weekday=%d start=%s outcome=%s",
        weekday,
        _validate_scenario(weekday, period).strftime("%H:%M"),
        outcome,
    )
    return outcome


def run_batch(
    weekday: int = DEFAULT_WEEKDAY,
    period: str = DEFAULT_PERIOD,
    poll_seconds: float = 15,
    timeout_minutes: float = 320,
) -> None:
    parsed_period = _validate_scenario(weekday, period)
    queued, cached = queue_missing_scenario(weekday, period)
    logger.info(
        "SUMO six-hour scenario: weekday=%d start=%s queued=%d already_cached=%s",
        weekday,
        parsed_period.strftime("%H:%M"),
        queued,
        cached,
    )
    if cached:
        logger.info("The selected six-hour SUMO scenario is already cached")
        return

    deadline = time.monotonic() + timeout_minutes * 60
    while True:
        with connect_to_warehouse() as connection:
            cached_row = connection.execute(
                """
                SELECT 1 FROM transport.sumo_congestion_scenario_cache
                WHERE weekday = %s AND period = %s
                  AND metadata->>'simulation_model' = %s
                """,
                (weekday, parsed_period, SIMULATION_MODEL),
            ).fetchone()
            active = connection.execute(
                """
                SELECT count(*) FROM transport.sumo_congestion_run
                WHERE weekday = %s AND period = %s AND status IN ('queued', 'running')
                """,
                (weekday, parsed_period),
            ).fetchone()[0]
            latest = connection.execute(
                """
                SELECT status, error FROM transport.sumo_congestion_run
                WHERE weekday = %s AND period = %s
                ORDER BY created_at DESC, run_id DESC LIMIT 1
                """,
                (weekday, parsed_period),
            ).fetchone()

        if cached_row:
            logger.info("Six-hour SUMO scenario completed and was cached")
            return
        status, error = latest if latest else (None, None)
        logger.info(
            "SUMO six-hour scenario progress: weekday=%d start=%s status=%s",
            weekday,
            parsed_period.strftime("%H:%M"),
            status or "missing",
        )
        if active == 0 and status == "failed":
            raise RuntimeError(f"SUMO six-hour scenario failed: {error}")
        if active == 0 and status == "completed":
            raise RuntimeError("SUMO scenario completed without a matching six-hour cache entry")
        if active == 0:
            raise RuntimeError("SUMO scenario is no longer queued or running")
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"SUMO six-hour scenario timed out (weekday={weekday}, "
                f"start={parsed_period.strftime('%H:%M')}); rerun to resume"
            )
        time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weekday", type=int, default=DEFAULT_WEEKDAY, help="ISO weekday, 1-7")
    parser.add_argument(
        "--period", default=DEFAULT_PERIOD, help="HCMC start time on a half-hour boundary"
    )
    parser.add_argument("--poll-seconds", type=float, default=15)
    parser.add_argument("--timeout-minutes", type=float, default=320)
    parser.add_argument(
        "--enqueue-only",
        action="store_true",
        help="queue the scenario and exit without waiting for simulation completion",
    )
    args = parser.parse_args()
    try:
        _validate_scenario(args.weekday, args.period)
    except ValueError as error:
        parser.error(str(error))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.enqueue_only:
        enqueue_scenario(args.weekday, args.period)
        return
    if not 1 <= args.poll_seconds <= 120:
        parser.error("Poll interval must be between 1 and 120 seconds")
    if not 1 <= args.timeout_minutes <= 320:
        parser.error("Timeout must be between 1 and 320 minutes")
    run_batch(args.weekday, args.period, args.poll_seconds, args.timeout_minutes)


if __name__ == "__main__":
    main()
