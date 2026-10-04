import argparse
from src.shared.data_io import read_json, write_json
from .extract import row_id

def run(rows, matched_ids, path):
    pending = [{**row, "id": row.get("id") or row_id(row),
                "review_reason": "Need verified road/from/to geometry and checked PDF values"}
               for row in rows if (row.get("id") or row_id(row)) not in matched_ids]
    write_json(path, {"pending": pending, "matched": len(matched_ids)})
    return len(pending)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export price rows for manual road matching")
    parser.add_argument("source")
    parser.add_argument("output")
    args = parser.parse_args()
    print(run(read_json(args.source)["records"], set(), args.output))
