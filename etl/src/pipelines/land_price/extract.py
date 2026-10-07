import hashlib
import re
from pathlib import Path
import pdfplumber
import numpy as np
from src.shared.data_io import data_dir, download, read_json, file_provenance
from .config import PDF_URL, FULL_PDF_URL, EFFECTIVE_FROM, REGIONS

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
        region = 'hcmc_previous'
        for page_index, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            annex = re.search(r'Phụ lục\s+(IV|III|II|V|I)\b',text)
            if annex:
                region = REGIONS.get(annex.group(1))
            title = re.search(r'BẢNG GIÁ ĐẤT (PHƯỜNG|XÃ|ĐẶC KHU)\s+([^\n]+)',text)
            ward = title.group(2).strip() if title else None
            if ward and ward != current_ward:
                if pending:
                    rejected.append({"page":pending[0],"cells":pending[1],"reason":"Unresolved page continuation"})
                current_ward = ward
                previous_road = None
                pending = None
            if not current_ward or region is None:
                continue
            tables = page.extract_tables()
            if not tables:
                try:
                    tables = [text_rows(page)]
                except ValueError as error:
                    rejected.append({'page':page_index+1,'ward':current_ward,'region_id':region,'reason':str(error)})
                    continue
            for table in tables:
                for cells in table:
                    cells = [(c or "").replace("\n", " ").strip() for c in cells]
                    if len(cells) != 7:
                        continue
                    if cells[0] in ('STT','(1)') or cells[2] in ('TỪ','ĐOẠN ĐƯỜNG'):
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
                    record = {"ward": current_ward, 'region_id':region, "road": road, "from": cells[2], "to": cells[3] or "TRỌN ĐƯỜNG",
                              "residential_1000_vnd_m2": int(cells[4].replace(".", "")),
                              "commercial_1000_vnd_m2": int(cells[5].replace(".", "")),
                              "other_nonagricultural_1000_vnd_m2": int(cells[6].replace(".", "")),
                              "pdf_page": page_index+1, "extraction_review_required": True,
                              "segment_scope": "whole_road" if whole_road else "between_endpoints"}
                    record["id"] = row_id(record)
                    records.append(record)
            if hasattr(page,'close'):
                page.close()
            if (page_index+1)%100==0:
                print(f'Land-price PDF: page {page_index+1}, {len(records)} candidate rows',flush=True)
        if pending:
            rejected.append({"page":pending[0],"cells":pending[1],"reason":"Unresolved page continuation"})
    # Text row grouping can include a clipped continuation at a page edge.
    # Such rows remain explicitly review-required rather than asserted correct.
    if not records:
        raise ValueError('No supported road-price table extracted; supply reviewed JSON rows')
    unique = {}
    for record in records:
        if record['id'] in unique:
            rejected.append({'page':record['pdf_page'],'reason':'Duplicate segment identity needs manual review','record':record})
            unique[record['id']]['duplicate_identity_review_required'] = True
        else:
            unique[record['id']] = record
    return {"source_url": source_url, "effective_from": EFFECTIVE_FROM, "published_unit": "1000 VND/m2",
            "records": list(unique.values()), "rejected": rejected,
            'region_counts':{region:sum(r['region_id']==region for r in unique.values()) for region in REGIONS.values()},
            'scope':'HCMC expanded; extracted candidates require review',
            'limitations':'Road-price tables only. Rejected layouts and unreviewed rows are not map-ready prices.'}

def cached_pdf(path,url):
    provenance = file_provenance(path,url)
    cache = data_dir()/f'review/land_price_pdf_v2_{provenance["sha256"][:16]}.json'
    if cache.exists():
        return read_json(cache)
    rows = parse_pdf(path,url)
    rows['source_pdf_sha256'] = provenance['sha256']
    rows['local_source_name'] = Path(path).name
    from src.shared.data_io import write_json
    write_json(cache,rows)
    return rows

def run(source=None, full_city=False, refresh_source=False):
    if source:
        path = Path(source)
        rows = read_json(path) if path.suffix.lower() == '.json' else cached_pdf(path,FULL_PDF_URL if full_city else PDF_URL)
        return rows, [file_provenance(path,rows["source_url"])]
    path = data_dir()/'raw/land_price'/('official-full-2026.pdf' if full_city else 'official-annex-2026.pdf')
    url = FULL_PDF_URL if full_city else PDF_URL
    provenance = file_provenance(path,url) if path.exists() and not refresh_source else download(url,path)
    return cached_pdf(path,url),[provenance]
