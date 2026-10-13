# Traffic counting test on server 152

Standalone experiment. No integration into the team frontend or automatic SUMO calibration.

Test root:
`/GuestShare_NAS/WorkingSpace/Personal/nguyenmv/MLAI/traffic-counting-test`

## Pipeline

Public UIT-ADrone video → downloaded YOLOv8m–VisDrone checkpoint → BoT-SORT
tracking → finite directed line crossings → per-class/direction CSV + annotated video.
The selected checkpoint requires **no local training**. `train_detector.py` and
`prepare_training.py` are optional experiments and are not needed to run the demo.

Install in an isolated Linux environment; ffmpeg/ffprobe must already be available:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu126
.venv/bin/python -m pip install -r scripts/requirements.txt
```

Copy these scripts into `scripts/`, `botsort-demo.yaml` into `configs/`, and create
`inputs/`, `outputs/`, `models/`, `logs/`. The server test environment additionally
shares preinstalled Python dependencies through `--system-site-packages`; see the
captured `outputs/environment.json` for the exact versions actually used.

```bash
export YOLO_CONFIG_DIR="$PWD/.yolo"
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
.venv/bin/python scripts/check_environment.py
.venv/bin/python -m pytest scripts/test_count_core.py -q
.venv/bin/python scripts/fetch_dataset.py --help
.venv/bin/python scripts/prepare_samples.py
.venv/bin/python scripts/fetch_pretrained.py
.venv/bin/python scripts/run_pretrained.py --run-name visdrone-pretrained
.venv/bin/python scripts/evaluate_labels.py --runs-dir outputs/visdrone-pretrained --annotation-image-id-offset=-1
.venv/bin/python scripts/build_report.py --runs-dir outputs/visdrone-pretrained
.venv/bin/python scripts/verify_outputs.py
```

Use a new `--run-name` for each run. Existing output folders are deliberately not
overwritten. `prepare_samples.py` resets the original camera configurations;
edit these before counting if using a different camera or road segment.

## Data and evidence

- Source: https://uit-together.github.io/datasets/UIT-ADrone/
- Model: https://huggingface.co/dronefreak/visdrone-yolov8m
- Download manifests record URLs, fetch times and SHA256; model manifest also pins revision.
- Selected videos: `inputs/uit-snippets/`; downloaded labels: `inputs/uit-annotations/`.
- `outputs/index.html`: three video results, CSV links and limitations.
- `outputs/visdrone-pretrained/detection-check.json`: tracked box precision/recall
  at IoU 0.3/0.5. This is neither official mAP nor counting accuracy.
- `outputs/dataset-index-audit.json`: original image IDs are zero-based and
  annotation image IDs one-based in these downloaded files. Apply offset -1 only
  after the documented range checks and visual alignment. Original files are unchanged.

Counts are only crossings of a configured line during the actual observation
window, not all vehicles in the frame or citywide flows. Rates in CSV are explicitly
labelled short-window extrapolations. Camera motion, vehicle occlusion and track
fragmentation can bias counts. Road mapping and capture timestamp are unknown;
`simulation_ready` remains false.

The model publisher states VisDrone has non-commercial dataset restrictions;
UIT-ADrone redistribution/commercial permissions were not established. This test
does not establish permission to package the dataset/model into a commercial product.
