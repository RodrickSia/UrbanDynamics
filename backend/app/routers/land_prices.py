import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from src.pipelines.flood_history.transform import normalize

from app.repository import directory

from .layers import get_features

router = APIRouter(prefix="/api/v1", tags=["land prices"])


@router.get("/land-prices")
def prices(bbox: str | None = None, limit: int = Query(5000, ge=1, le=10000)):
    return get_features("land_price", bbox, limit=limit)


@router.get("/land-prices/rows")
def price_rows():
    path = directory() / "review" / "land_price_rows.json"
    if not path.exists():
        raise HTTPException(503, "Official price rows not loaded")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(503, "Official price rows unavailable or invalid") from None


@router.get('/land-prices/catalog')
def price_catalog(q: str = Query('', max_length=200), region_id: str | None = None,
                  status: str = Query('all', pattern='^(all|mapped|pending)$'),
                  offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=10000),
                  include_geometry: bool = False):
    """Published PDF rows retain their identities separately from road coverage."""
    source = price_rows()
    try:
        root = directory()
        path = root/'review/land_price_row_matches.geojson'
        layer = json.loads((path if path.exists() else root/'layers/land_price.geojson').read_text(encoding='utf-8'))
        queue = json.loads((root/'review/land_price_pending.json').read_text(encoding='utf-8'))
        rows = source['records']
        ids = [row['id'] for row in rows]
        mapped = {f['id']: f for f in layer['features']}
        pending = {r['id']: r for r in queue['pending']}
        if (len(set(ids)) != len(ids) or set(mapped) & set(pending)
                or set(mapped) | set(pending) != set(ids)
                or len(mapped) != len(layer['features']) or len(pending) != len(queue['pending'])):
            raise ValueError('Inconsistent price snapshots')
        needle = normalize(q)
        result = []
        for row in rows:
            feature = mapped.get(row['id'])
            if region_id and row.get('region_id') != region_id:
                continue
            if status == 'mapped' and feature is None or status == 'pending' and feature is not None:
                continue
            if needle and needle not in normalize(' '.join(str(row.get(k, '')) for k in ('ward','road','from','to'))):
                continue
            props = feature['properties'] if feature else {}
            if feature and any(props[c+'_vnd_m2'] != row[c+'_1000_vnd_m2'] * 1000
                               for c in ('residential','commercial','other_nonagricultural')):
                raise ValueError('Mapped prices differ from source')
            item = {**row, 'has_geometry': feature is not None,
                    'map_status': ('mapped_reviewed' if props.get('geometry_reviewed') is True
                                   and props.get('source_values_reviewed') is True else 'mapped_automatic')
                                  if feature else 'pending',
                    'pending_reason': pending[row['id']].get('unmatched_reason') if feature is None else None,
                    'source_pdf_url': '/api/v1/land-prices/source.pdf#page='+str(row.get('pdf_page',''))}
            for category in ('residential','commercial','other_nonagricultural'):
                item[category+'_vnd_m2'] = row[category+'_1000_vnd_m2'] * 1000
            if include_geometry:
                item['geometry'] = feature['geometry'] if feature else None
            result.append(item)
        return {'source_url':source['source_url'], 'effective_from':source.get('effective_from'),
                'unit':'VND/m2', 'snapshot_scope':'local_etl_files',
                'source_count':len(rows), 'mapped_count':len(mapped), 'pending_count':len(pending),
                'total':len(result), 'offset':offset, 'limit':limit,
                'records':result[offset:offset+limit],
                'limitations':layer.get('metadata',{}).get('limitations') or 'Published reference prices; automatic locations may be approximate.'}
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, 'Complete price catalogue unavailable or snapshots inconsistent') from None


@router.get('/land-prices/source.pdf')
def price_pdf():
    for name in ('official-full-2026.pdf','official-annex-2026.pdf'):
        path = directory()/'raw/land_price'/name
        if path.is_file():
            return FileResponse(path, media_type='application/pdf')
    raise HTTPException(503, 'Official price PDF not loaded')
