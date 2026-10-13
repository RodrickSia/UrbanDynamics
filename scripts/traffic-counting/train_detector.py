"""Small domain adaptation experiment, no official benchmark accuracy claim."""
import argparse
from pathlib import Path
import torch
from ultralytics import YOLO

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--epochs", type=int, default=30)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
torch.set_num_threads(4)
model = YOLO(root / "models/yolo11s.pt")
model.train(data=str(root / "training-subset/dataset.yaml"), epochs=args.epochs,
            imgsz=960, batch=12, device=0, workers=2, cache="ram", seed=2026,
            project=str(root / "training-runs"), name="uit-demo", exist_ok=False,
            patience=15, close_mosaic=5, degrees=180, fliplr=.5, flipud=.5,
            save=True, plots=True, verbose=False)
