"""Durable planning worker; run alongside the API with the same store settings."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root/"backend"), str(root/"etl")]
from app.services.simulation.planning.worker import main

if __name__ == "__main__":
    main()
