"""Browser test source fixtures; production analytics/API remain real."""
from shapely.geometry import box, mapping

from development_testserver import app  # noqa: F401
from app.services.area_indicators import sources, transit
from app.services.zoning.geometry import projected

sources.population = lambda geometry: {'year': 2025, 'value': projected(geometry).area/100,
                                       'covered_m2': projected(geometry).area, 'files': ['fixture']}
sources.parcels = lambda geometry: [
    {'code': 'ODT', 'geometry': mapping(box(106.74,10.80,106.7615,10.84))},
    {'code': 'TMD', 'geometry': mapping(box(106.7615,10.80,106.78,10.84))}]
transit.proximity = lambda area, radius: {'status':'proxy','coverage_percent':75,'stop_count':3,
    'radius_m':radius,'source':'Test transit stops','captured_at':'2026-10-14','stops':[],'geometry':None}
