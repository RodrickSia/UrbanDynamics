"""Clipped sampling cells do not imply native weather model resolution."""
import hashlib
import json
import math
from pyproj import Transformer
from shapely.geometry import box, mapping
from shapely.ops import transform
from src.shared.spatial import read_boundary
from src.shared.data_io import file_provenance

def build(settings):
    boundary = read_boundary(settings.boundary)
    forward = Transformer.from_crs(4326,32648,always_xy=True).transform
    reverse = Transformer.from_crs(32648,4326,always_xy=True).transform
    projected = transform(forward,boundary)
    west,south,east,north = projected.bounds
    cells = []
    step = settings.grid_m
    for x in range(math.floor(west/step)*step,math.ceil(east/step)*step,step):
        for y in range(math.floor(south/step)*step,math.ceil(north/step)*step,step):
            clipped = projected.intersection(box(x,y,x+step,y+step))
            if clipped.is_empty or clipped.area < 1:
                continue
            # Clip in original CRS so reprojection approximations cannot move
            # the outer administrative boundary or leave slivers along it.
            geometry = transform(reverse,box(x,y,x+step,y+step)).intersection(boundary)
            if geometry.is_empty or geometry.geom_type not in ('Polygon','MultiPolygon'):
                continue
            point = geometry.representative_point()
            cells.append({"id":f"rain-{step}-{x}-{y}","longitude":point.x,"latitude":point.y,
                          "geometry":mapping(geometry)})
    if not cells or len(cells)>2000:
        raise ValueError("Boundary produces zero or too many weather cells")
    provenance = file_provenance(settings.boundary)
    grid_id = hashlib.sha256((json.dumps(mapping(boundary),sort_keys=True)+str(step)+'clip-wgs84-v2').encode()).hexdigest()[:20]
    return cells,{"grid_id":grid_id,"sampling_spacing_m":step,
                  "boundary_provenance":provenance,"station_count":len(cells),
                  "limitations":"Sampling cells are display areas, not independent observations or native model resolution."}
