"""Write source rows that did not find an OSM road-name match."""

import argparse
from src.shared.data_io import read_json, write_json
from .extract import row_id

def run(rows, matched_ids, path):
    pending = [{**row, "id": row.get("id") or row_id(row),
                "unmatched_reason": "No exact normalized OSM road-name match"}
               for row in rows if (row.get("id") or row_id(row)) not in matched_ids]
    write_json(path, {"pending": pending, "matched": len(matched_ids)})
    return len(pending)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export price rows without an OSM road-name match")
    parser.add_argument("source")
    parser.add_argument("output")
    args = parser.parse_args()
    print(run(read_json(args.source)["records"], set(), args.output))
