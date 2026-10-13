"""Generate schema-validated synthetic site-selection and portfolio fixtures."""
import argparse
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root/"backend"), str(root/"etl")]
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import demo_study, rehousing_study, inclusive_rehousing_study, single_site_study

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=root/"docs/samples")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
for mode, filename in (("site_selection", "planning-site-selection.json"), ("cumulative", "planning-cumulative.json")):
    payload = PlanningStudy(**demo_study(mode)).model_dump(mode="json")
    path = args.output/filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(path)
rehousing = PlanningStudy(**rehousing_study()).model_dump(mode="json")
rehousing_path = args.output/"planning-rehousing.json"
rehousing_path.write_text(json.dumps(rehousing, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
print(rehousing_path)
inclusive_path = args.output/"planning-inclusive-background.json"
inclusive_path.write_text(json.dumps(PlanningStudy(**inclusive_rehousing_study()).model_dump(mode="json"), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
print(inclusive_path)
single_path = args.output/"planning-single-site.json"
single_path.write_text(json.dumps(PlanningStudy(**single_site_study()).model_dump(mode="json"), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
print(single_path)
