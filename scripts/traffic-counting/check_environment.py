import json
import importlib.metadata
from pathlib import Path
import torch

data = {"torch": torch.__version__, "cuda_runtime": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "packages": {name: importlib.metadata.version(name) for name in
                     ("ultralytics", "torchvision", "numpy", "opencv-python", "scipy", "lap", "pytest", "gdown")}}
print(json.dumps(data, indent=2))
root = Path(__file__).resolve().parents[1]
(root / "outputs/environment.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
if not torch.cuda.is_available():
    raise RuntimeError("GPU environment is not ready")
