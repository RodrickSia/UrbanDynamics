import re
import logging
from datetime import datetime,timezone,timedelta
from shapely.geometry import shape
from src.shared.data_io import data_dir, download, session, file_provenance,write_json
from .config import STAC_URL, FLOOD_ASSET, MASK_ASSET, MAX_ITEMS

def run(boundary, catalog_only=False, limit=MAX_ITEMS):
    client = session()
    now = datetime.now(timezone.utc)
    params = {'bbox':','.join(map(str,boundary.bounds)),'limit':100,
              'datetime':f'{(now-timedelta(days=30)).isoformat()}/{now.isoformat()}'}
    url,items,seen = STAC_URL,[],set()
    for page in range(20):
        response = client.get(url,params=params,timeout=(20,90)); response.raise_for_status()
        body = response.json()
        for item in body['features']:
            if item['id'] not in seen and shape(item['geometry']).intersects(boundary):
                items.append(item); seen.add(item['id'])
        link = next((x for x in body.get('links',[]) if x.get('rel')=='next'),None)
        if not link: break
        from urllib.parse import urljoin,urlparse
        url = urljoin(response.url,link['href'])
        if urlparse(url).netloc!=urlparse(STAC_URL).netloc:
            raise ValueError('Unexpected STAC pagination host')
        params = None
    else:
        raise ValueError('STAC pagination exceeded safety limit; narrow time range')
    items.sort(key=lambda i:i['properties'].get('datetime',''),reverse=True)
    if len(items)>limit:
        raise ValueError('Too many scenes for configured limit; increase limit instead of silently dropping coverage')
    write_json(data_dir()/'raw/flood_satellite/catalog-latest.json',
               {'queried_at':now.isoformat(),'bbox':list(boundary.bounds),'lookback_days':30,'features':items})
    results = []
    for index,item in enumerate(items,1):
        logging.getLogger(__name__).info('GFM scene %s/%s %s',index,len(items),item['id'])
        identifier = re.sub(r"[^a-zA-Z0-9_-]", "_", item["id"])
        paths, provenance = {}, []
        if not catalog_only:
            for key in (FLOOD_ASSET, MASK_ASSET):
                if key not in item.get("assets", {}):
                    if key == MASK_ASSET:
                        continue
                    raise ValueError(f"Missing {key}; cannot verify observed flood pixels")
                path = data_dir() / "raw" / "flood_satellite" / identifier / f"{key}.tif"
                asset_url = item['assets'][key]['href']
                provenance.append(file_provenance(path,asset_url) if path.exists() else download(asset_url,path))
                paths[key] = path
        results.append({"item": item, "paths": paths, "provenance": provenance})
    return results
