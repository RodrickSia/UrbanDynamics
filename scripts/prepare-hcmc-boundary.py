"""Prepare the sourced analytical HCMC boundary, including Con Dao."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'etl'))
from src.shared.hcmc_boundary import run

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cached',action='store_true')
    run(parser.parse_args().cached)
