"""Queue and monitor the complete weekday/half-hour SUMO scenario matrix."""

from __future__ import annotations

import argparse
import logging
import time
from datetime import time as clock_time
from uuid import uuid4

from src.shared.database import connect_to_warehouse

from app.services.traffic_sumo_prediction import catalog

WEEKDAYS = range(1, 8)
PERIODS = tuple(clock_time(hour, minute) for hour in range(24) for minute in (0, 30))
SCENARIO_COUNT = len(WEEKDAYS) * len(PERIODS)
logger = logging.getLogger(__name__)


def queue_missing_scenarios() -> tuple[int, int]:
    """Queue every uncached scenario, leaving completed entries untouched."""
    if not catalog()["available"]:
        raise RuntimeError(
            "SUMO scenario batch requires the HCMC network and matched traffic observations"
        )
    queued = 0
    with connect_to_warehouse() as connection, connection.transaction():
        migration = connection.execute("""
            SELECT to_regclass('transport.sumo_congestion_scenario_cache')
        """).fetchone()
        if migration[0] is None:
            raise RuntimeError(
                "SUMO scenario cache migration is missing; run Deploy database first"
            )
        cached = {
            (int(weekday), period)
            for weekday, period in connection.execute(
                "SELECT weekday, period FROM transport.sumo_congestion_scenario_cache"
            ).fetchall()
        }
        for weekday in WEEKDAYS:
            for period in PERIODS:
                if (weekday, period) in cached:
                    continue
                result = connection.execute(
                    """
                    INSERT INTO transport.sumo_congestion_run (run_id, weekday, period, status)
                    VALUES (%s, %s, %s, 'queued')
                    ON CONFLICT (weekday, period)
                        WHERE status IN ('queued', 'running') DO NOTHING
                    """,
                    (uuid4(), weekday, period),
                )
                queued += result.rowcount
    return queued, len(cached)


def run_batch(poll_seconds: float = 15, timeout_minutes: float = 350) -> None:
    queued, cached = queue_missing_scenarios()
    logger.info(
        "SUMO scenario batch: %d cached, %d newly queued, %d total",
        cached,
        queued,
        SCENARIO_COUNT,
    )
    deadline = time.monotonic() + timeout_minutes * 60
    while True:
        with connect_to_warehouse() as connection:
            cached_count = connection.execute(
                "SELECT count(*) FROM transport.sumo_congestion_scenario_cache"
            ).fetchone()[0]
            active_count = connection.execute("""
                SELECT count(*) FROM transport.sumo_congestion_run
                WHERE status IN ('queued', 'running')
            """).fetchone()[0]
            failures = connection.execute("""
                SELECT weekday, period, error
                FROM (
                    SELECT DISTINCT ON (weekday, period)
                           weekday, period, status, error
                    FROM transport.sumo_congestion_run
                    ORDER BY weekday, period, created_at DESC, run_id DESC
                ) AS latest
                WHERE status = 'failed'
                  AND NOT EXISTS (
                      SELECT 1 FROM transport.sumo_congestion_scenario_cache AS cached
                      WHERE cached.weekday = latest.weekday AND cached.period = latest.period
                  )
                ORDER BY weekday, period
            """).fetchall()

        logger.info("SUMO scenario batch progress: %d/%d cached; %d queued/running",
                    cached_count, SCENARIO_COUNT, active_count)
        if cached_count >= SCENARIO_COUNT:
            logger.info("All %d SUMO weekday/time scenarios are cached", SCENARIO_COUNT)
            return
        if active_count == 0 and failures:
            details = "; ".join(
                f"weekday={weekday} period={period} error={error}"
                for weekday, period, error in failures[:12]
            )
            raise RuntimeError(f"SUMO batch has failed scenarios: {details}")
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"SUMO batch timed out with {cached_count}/{SCENARIO_COUNT} scenarios cached; "
                "rerun this workflow to resume"
            )
        time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poll-seconds", type=float, default=15)
    parser.add_argument("--timeout-minutes", type=float, default=350)
    args = parser.parse_args()
    if not 1 <= args.poll_seconds <= 120:
        parser.error("Poll interval must be between 1 and 120 seconds")
    if not 1 <= args.timeout_minutes <= 350:
        parser.error("Timeout must be between 1 and 350 minutes")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_batch(args.poll_seconds, args.timeout_minutes)


if __name__ == "__main__":
    main()
