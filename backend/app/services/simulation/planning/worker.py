"""Planning worker entry point for local CLI and the backend Docker image."""
import argparse
import logging
import time

from .jobs import process_one
from .recovery import recover


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=1)
    args = parser.parse_args()
    if not .1 <= args.poll_seconds <= 10:
        parser.error("Poll interval must be between .1 and 10 seconds")
    logging.basicConfig(level=logging.INFO)
    while True:
        for recovered in recover():
            if recovered["action"] == "recovered":
                logging.info("Planning recovery: %s", recovered)
        result = process_one()
        if result:
            print(result, flush=True)
        if args.once:
            break
        if result is None:
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
