"""Dedicated worker for standalone SUMO congestion-prediction runs."""

import argparse
import gzip
import json
import logging
import time

from psycopg.types.json import Jsonb
from src.shared.database import connect_to_warehouse

from app.services.traffic_sumo_prediction import cleanup_run, run_prediction

logger = logging.getLogger(__name__)


def process_one() -> bool:
    with connect_to_warehouse() as connection:
        with connection.transaction():
            row = connection.execute("""
                SELECT run_id, weekday, period
                FROM transport.sumo_congestion_run
                WHERE status = 'queued'
                ORDER BY created_at, run_id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            """).fetchone()
            if row is None:
                return False
            run_id, weekday, period = row
            connection.execute(
                """
                UPDATE transport.sumo_congestion_run
                SET status = 'running', error = NULL, updated_at = now()
                WHERE run_id = %s
            """,
                (run_id,),
            )

    try:
        started = time.monotonic()
        logger.info("Starting SUMO scenario %s (weekday=%s period=%s)", run_id, weekday, period)
        result = run_prediction(int(weekday), period.strftime("%H:%M"), str(run_id))
        with connect_to_warehouse() as connection:
            with connection.transaction():
                connection.execute(
                    """
                    INSERT INTO transport.sumo_congestion_scenario_cache
                        (weekday, period, run_id, metadata, result_gzip)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (weekday, period) DO UPDATE
                    SET run_id = EXCLUDED.run_id,
                        metadata = EXCLUDED.metadata,
                        result_gzip = EXCLUDED.result_gzip,
                        generated_at = now()
                    """,
                    (
                        weekday,
                        period,
                        run_id,
                        Jsonb(result["metadata"]),
                        gzip.compress(json.dumps(result, separators=(",", ":")).encode("utf-8")),
                    ),
                )
                connection.execute(
                    """
                    UPDATE transport.sumo_congestion_run
                    SET status = 'completed', metadata = %s, updated_at = now()
                    WHERE run_id = %s
                    """,
                    (Jsonb(result["metadata"]), run_id),
                )
        logger.info("Cached SUMO scenario %s in %.1fs", run_id, time.monotonic() - started)
    except Exception as error:
        logger.exception("Standalone SUMO run %s failed", run_id)
        with connect_to_warehouse() as connection:
            connection.execute(
                """
                UPDATE transport.sumo_congestion_run
                SET status = 'failed', error = %s, updated_at = now()
                WHERE run_id = %s
            """,
                (str(error)[:2000], run_id),
            )
    finally:
        cleanup_run(str(run_id))
    return True


def recover_stale_runs() -> int:
    """Requeue only worker leases older than the maximum possible run duration."""
    with connect_to_warehouse() as connection:
        row = connection.execute("""
            UPDATE transport.sumo_congestion_run
            SET status = 'queued', error = NULL, updated_at = now()
            WHERE status = 'running' AND updated_at < now() - interval '40 minutes'
            RETURNING run_id
        """).fetchall()
    return len(row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2)
    args = parser.parse_args()
    if not 0.1 <= args.poll_seconds <= 30:
        parser.error("Poll interval must be between .1 and 30 seconds")
    logging.basicConfig(level=logging.INFO)
    try:
        recovered = recover_stale_runs()
        if recovered:
            logger.warning("Requeued %d stale standalone SUMO runs", recovered)
    except Exception:
        logger.exception("Could not inspect stale SUMO prediction runs")
    while True:
        try:
            worked = process_one()
        except Exception:
            logger.exception("Traffic prediction worker could not reach its queue")
            if args.once:
                break
            time.sleep(min(30, args.poll_seconds * 5))
            continue
        if args.once:
            break
        if not worked:
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
