#!/usr/bin/env bash
set -euo pipefail
cd /GuestShare_NAS/WorkingSpace/Personal/nguyenmv/MLAI/traffic-counting-test
export YOLO_CONFIG_DIR="$PWD/.yolo"
export OMP_NUM_THREADS=4
export MKL_NUM_THREADS=4
.venv/bin/python -m pytest scripts/test_count_core.py -q --junitxml=outputs/core-tests.xml
.venv/bin/python scripts/prepare_samples.py > logs/sample-inventory.log
for config in configs/50m*.json; do
  name=$(basename "$config" .json)
  .venv/bin/python scripts/run_counting.py --config "$config" --output "outputs/$name" > "logs/$name.log" 2>&1
done
