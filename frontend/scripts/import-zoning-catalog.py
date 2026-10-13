"""Import the user-provided zoning catalog tables into the frontend fixture.

Usage: python scripts/import-zoning-catalog.py "path/to/Pasted text.txt"
The source document separates official land-use codes from proposed zoning types.
"""

import json
import re
import sys
from pathlib import Path


def main() -> None:
    source = Path(sys.argv[1]).read_text(encoding="utf-8")
    section = ""
    group = ""
    rows = []
    for line in source.splitlines():
        if line.startswith("## PHẦN A"):
            section = "land_use"
        elif line.startswith("## PHẦN B"):
            section = "zoning_type"
        elif line.startswith("## PHẦN C"):
            section = "zoning_subtype"
        elif line.startswith("## PHẦN D"):
            break
        elif section == "land_use" and line.startswith("### A"):
            group = line.split(". ", 1)[1]
        if not re.match(r"^\| `[^`]+` \|", line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        code = cells[0].strip("`")
        rows.append({"code": code, "name": cells[1], "description": cells[2],
                     "category": section, "group": group if section == "land_use" else "",
                     "land_use_codes": cells[3] if section == "zoning_type" else ""})
    counts = {category: sum(row["category"] == category for row in rows)
              for category in ("land_use", "zoning_type", "zoning_subtype")}
    assert counts["zoning_type"] == 22 and counts["zoning_subtype"] == 19, counts
    assert counts["land_use"] > 60, counts
    target = Path(__file__).resolve().parents[1] / "src/features/zoning/zoningCatalog.json"
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Imported {counts} into {target}")


if __name__ == "__main__":
    main()
