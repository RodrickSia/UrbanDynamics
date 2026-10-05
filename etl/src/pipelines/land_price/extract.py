import hashlib
import logging
import re
from pathlib import Path

import pdfplumber
import numpy as np

from src.shared.data_io import data_dir, download, read_json, file_provenance
from .config import EFFECTIVE_FROM, PDF_URL, PDF_URLS

logger = logging.getLogger(__name__)

def row_id(record):
    key = "|".join(str(record.get(k, "")).strip().upper() for k in ("ward", "road", "from", "to"))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]

def text_rows(page):
    """Read OCR words inside the scanned grid; all rows still need review."""
    words = page.extract_words()
    # The visible grid is part of a scanned image, so PDF vector edges are absent.
    # Detect the raster ruling instead of guessing row bounds from price centers.
    image = page.to_image(resolution=144).original.convert("L")
    pixels = np.asarray(image)
    scale = image.width / page.width
    dark = pixels[:, round(173*scale):round(540*scale)] < 170
    positions = np.flatnonzero(dark.mean(axis=1) > 0.85)
    groups = np.split(positions, np.flatnonzero(np.diff(positions)>2)+1)
    lines = [float(g.mean()/scale) for g in groups if len(g)]
    marker = next((w["top"] for w in words if w["text"] == "(1)"), None)
    if marker is None or len(lines) < 4:
        raise ValueError("Unsupported annex table grid; no snapshot published")
    boundaries = [55, 85, 172, 252, 335, 393, 455, 542]
    output = []
    for lower, upper in zip(lines, lines[1:]):
        if lower < marker:
            continue
        cells = []
        for column in range(7):
            selected = [w for w in words if lower < (w["top"]+w["bottom"])/2 < upper
                        and boundaries[column] <= w["x0"] < boundaries[column+1]]
            selected.sort(key=lambda w:(round(w["top"]/2),w["x0"]))
            cells.append(" ".join(w["text"] for w in selected))
        if any(cells):
            output.append(cells)
    return output

def parse_pdf(path, source_url=PDF_URL):
    records, rejected = [], []
    # Continue this ward across pages, stopping at the next explicitly titled ward.
    with pdfplumber.open(path) as pdf:
        current_ward = None
        previous_road = None
        pending = None
        for page_index, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            title = re.search(r"BẢNG GIÁ ĐẤT PHƯỜNG ([^\n]+)", text)
            if title:
                if pending:
                    rejected.append({"page":pending[0],"cells":pending[1],"reason":"Unresolved page continuation"})
                current_ward = title.group(1).strip()
                previous_road = None
                pending = None
            if current_ward != "AN KHÁNH":
                continue
            tables = page.extract_tables()
            if not tables:
                tables = [text_rows(page)]
            for table in tables:
                for cells in table:
                    cells = [(c or "").replace("\n", " ").strip() for c in cells]
                    if len(cells) != 7:
                        continue
                    if pending is not None:
                        if cells[0]:
                            rejected.append({"page":pending[0],"cells":pending[1],"reason":"Unresolved page continuation"})
                        else:
                            cells = [" ".join(filter(None,(a,b))) for a,b in zip(pending[1],cells)]
                        pending = None
                    if not all(re.fullmatch(r"\d{1,3}(?:\.\d{3})+|\d+", c) for c in cells[-3:]):
                        if cells[0] and re.fullmatch(r"\d+", cells[0]):
                            pending = (page_index+1,cells)
                        elif any(cells):
                            rejected.append({"page":page_index+1,"cells":cells,"reason":"Missing price triple"})
                        continue
                    road = cells[1] or previous_road
                    whole_road = cells[2] == "TRỌN ĐƯỜNG" and not cells[3]
                    if not road or not cells[2] or (not cells[3] and not whole_road):
                        rejected.append({"page": page_index+1, "cells": cells, "reason": "Incomplete road segment"})
                        continue
                    previous_road = road
                    record = {"ward": "AN KHÁNH", "road": road, "from": cells[2], "to": cells[3] or "TRỌN ĐƯỜNG",
                              "residential_1000_vnd_m2": int(cells[4].replace(".", "")),
                              "commercial_1000_vnd_m2": int(cells[5].replace(".", "")),
                              "other_nonagricultural_1000_vnd_m2": int(cells[6].replace(".", "")),
                              "pdf_page": page_index+1, "extraction_review_required": True,
                              "segment_scope": "whole_road" if whole_road else "between_endpoints"}
                    record["id"] = row_id(record)
                    records.append(record)
        if pending:
            rejected.append({"page":pending[0],"cells":pending[1],"reason":"Unresolved page continuation"})
    # Text row grouping can include a clipped continuation at a page edge.
    # Such rows remain explicitly review-required rather than asserted correct.
    if not records:
        raise ValueError("No supported An Khanh table extracted; use --source with reviewed JSON rows")
    return {"source_url": source_url, "effective_from": EFFECTIVE_FROM, "published_unit": "1000 VND/m2",
            "records": records, "rejected": rejected}

def run(source=None):
    if source:
        path = Path(source)
        rows = read_json(path) if path.suffix.lower() == ".json" else parse_pdf(path)
        return rows, [file_provenance(path,rows["source_url"])]
    path = data_dir() / "raw" / "land_price" / "official-annex-2026.pdf"
    failures = []
    for url in PDF_URLS:
        try:
            provenance = download(url, path)
            return parse_pdf(path, url), [provenance]
        except Exception as error:
            failures.append(f"{url}: {error}")
            if url != PDF_URLS[-1]:
                logger.warning(
                    "Land-price PDF download failed from %s; trying the next official source: %s",
                    url,
                    error,
                )
    raise RuntimeError(
        "Could not download the 2026 HCMC land-price resolution from any official source. "
        + " | ".join(failures)
    )
