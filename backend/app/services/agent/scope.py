"""Shared, explicit description of analysis geometry, independent of its provider."""
import math
from pyproj import Transformer
from shapely import get_num_coordinates
from shapely.geometry import shape
from shapely.ops import transform

TO_METERS=Transformer.from_crs(4326,32648,always_xy=True).transform


def metric_area(geometry):
    if geometry.is_empty or not geometry.is_valid or get_num_coordinates(geometry)>30000:
        raise ValueError('Analysis geometry is empty, invalid or exceeds 30,000 vertices')
    west,south,east,north=geometry.bounds
    if not all(math.isfinite(n) for n in geometry.bounds) or not -180<=west<=east<=180 or not -85<=south<=north<=85:
        raise ValueError('Invalid WGS84 analysis bounds')
    return transform(TO_METERS,geometry).area


def decorate(area):
    if not area:return area
    geometry=shape(area['geometry'])
    kind=area.get('scope_kind') or ('street_buffer' if area.get('street_name') else 'declared_geometry')
    area['scope_summary']={'name':area.get('title'),'kind':kind,'bbox':list(geometry.bounds),
        'area_m2':round(metric_area(geometry),1),'radius_m':area.get('radius_m'),
        'source':area.get('source'),
        'administrative_boundary':kind=='provider_administrative_polygon',
        'limitation':'Provider geometry is not legal approval; point/road buffers and viewports are not administrative boundaries.'}
    return area
