from collections import defaultdict
from math import isfinite

from psycopg import Error as DatabaseError
from shapely.geometry import GeometryCollection, shape
from shapely.ops import transform, unary_union

from . import sources, transit
from ..parcels import land_use, PALETTE
from ..zoning import baseline as building_baseline
from ..zoning.development import floor_stack
from ..zoning.geometry import TO_METERS, study_geometry, projected, geojson


def land_distribution(records, area):
    """Partition overlaps explicitly so percentages never double count land."""
    groups = defaultdict(list)
    for row in records:
        geom = transform(TO_METERS, shape(row['geometry'])).intersection(area)
        if geom.area > .01:
            groups[row['code']].append(geom)
    united = {code: unary_union(parts) for code, parts in groups.items()}
    seen, conflict = GeometryCollection(), GeometryCollection()
    for geom in united.values():
        conflict = conflict.union(seen.intersection(geom))
        seen = seen.union(geom)
    rows = []
    for code, geom in united.items():
        size = geom.difference(conflict).area
        if size > .01:
            rows.append({'code': code, 'label': PALETTE['entries'].get(code, {}).get('category') or code or 'Unknown use',
                         'color': land_use(code)['color'], 'area_m2': size, 'percent': size/area.area*100})
    for code, label, geom in [('conflict', 'Conflicting use', conflict), ('unmapped', 'Unmapped area', area.difference(seen))]:
        if geom.area > .01:
            rows.append({'code': code, 'label': label, 'color': '#94a3b8', 'area_m2': geom.area, 'percent': geom.area/area.area*100})
    return sorted(rows, key=lambda r: -r['area_m2'])


def proposal_metrics(scenario, area, a):
    residential = workplace = physical_residential = physical_workplace = 0
    unknown_workplace = unknown_demand = False
    count = 0
    for building in scenario.get('buildings', []):
        clipped = projected(building['geometry']).intersection(area).area
        if clipped <= .01:
            continue
        count += 1
        for floor in floor_stack(building):
            if floor['space_use_id'] == 'residential':
                physical_residential += clipped*a.net_area_factor
                if floor['counts_gfa']:
                    residential += clipped*a.net_area_factor
            elif floor['space_use_id'] in ('commercial', 'office'):
                physical_workplace += clipped*a.net_area_factor
                if floor['counts_gfa']:
                    workplace += clipped*a.net_area_factor
            else:
                unknown_workplace |= floor['counts_gfa']
                unknown_demand = True
    residents = residential/a.residential_m2_per_person
    jobs = workplace/a.work_m2_per_job
    physical_people = physical_residential/a.residential_m2_per_person
    physical_jobs = physical_workplace/a.work_m2_per_job
    needed = residents*a.labour_force_percent/100
    return {'buildings': count, 'population': residents, 'housing_capacity': residential/a.residential_m2_per_home,
            'jobs_capacity': None if unknown_workplace else jobs, 'jobs_needed': needed,
            'jobs_balance': None if unknown_workplace else jobs-needed,
            'energy_kwh_day': None if unknown_demand else physical_people*a.residential_kwh_person_day+physical_workplace*a.workplace_kwh_m2_day,
            'water_m3_day': None if unknown_demand else (physical_people*a.residential_l_person_day+physical_jobs*a.workplace_l_job_day)/1000,
            'waste_kg_day': None if unknown_demand else physical_people*a.residential_waste_kg_person_day+physical_jobs*a.workplace_waste_kg_job_day,
            'net_residential_m2': residential, 'net_workplace_m2': workplace}


def existing_building_metrics(records, area, a):
    """Housing capacity from the available generated residential model only."""
    if not records:
        return {'housing_capacity': None,
                'inventory': {'status': 'unavailable', 'count': 0, 'floor_area_m2': None,
                              'source': 'Generated residential 3D building model', 'coverage': 'unknown'}}
    floor_area = 0.0
    complete = True
    count = 0
    seen = set()
    for building in records:
        footprint = projected(building['geometry']).intersection(area)
        if footprint.area <= .01:
            continue
        fingerprint = footprint.normalize().wkb
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        count += 1
        floors = building.get('floors')
        if floors is None or not isfinite(floors) or floors <= 0:
            complete = False
            continue
        floor_area += footprint.area * floors
    if count == 0:
        return existing_building_metrics(None, area, a)
    status = 'estimated' if complete else 'partial'
    return {'housing_capacity': floor_area * a.net_area_factor / a.residential_m2_per_home if complete else None,
            'inventory': {'status': status, 'count': count,
                          'floor_area_m2': floor_area if complete else None,
                          'source': 'Generated residential 3D building model', 'coverage': 'unknown'}}


def analyze(body, plan=None):
    area = study_geometry(body.geometry)
    a = body.assumptions
    issues = []

    def read(name, operation):
        try:
            return operation()
        except (DatabaseError, OSError, ValueError, KeyError, TypeError):
            issues.append(f'{name} unavailable')
            return None

    pop = read('Population', lambda: sources.population(body.geometry))
    records = read('Parcel land use', lambda: sources.parcels(body.geometry))
    access = read('Transit', lambda: transit.proximity(area, a.transit_radius_m))
    coverage = min(100, pop['covered_m2']/area.area*100) if pop else 0
    # A partial raster sum is not the total population of the selected area.
    people = float(pop['value']) if pop and coverage >= 99 else None
    baseline = {'population': people, 'energy_kwh_day': None, 'water_m3_day': None, 'waste_kg_day': None,
                'jobs_needed': None, 'jobs_capacity': None, 'jobs_balance': None, 'housing_capacity': None}
    if people is not None:
        baseline.update(energy_kwh_day=people*a.residential_kwh_person_day,
                        water_m3_day=people*a.residential_l_person_day/1000,
                        waste_kg_day=people*a.residential_waste_kg_person_day,
                        jobs_needed=people*a.labour_force_percent/100)
    buildings = read('Existing residential building model', lambda: building_baseline.buildings(
        {'id': 'zone:indicator-existing', 'geometry': body.geometry}, body.geometry))
    existing = existing_building_metrics(buildings, area, a)
    baseline['housing_capacity'] = existing['housing_capacity']
    proposal, zones = None, []
    scenario = next((s for s in plan['scenarios'] if s['id'] == str(body.scenario_id)), None) if plan else None
    if plan and scenario is None:
        raise ValueError('Scenario not found')
    if body.include_scenario and scenario and scenario['kind'] == 'proposal':
        proposal = proposal_metrics(scenario, area, a)
        types = {t['id']: t for t in plan['types']}
        grouped = defaultdict(list)
        for zone in scenario['zones']:
            grouped[zone['type_id']].append(projected(zone['geometry']).intersection(area))
        for identifier, geometries in grouped.items():
            size = unary_union(geometries).area
            if size > .01:
                kind = types[identifier]
                zones.append({'code': kind['code'], 'label': kind['name'], 'color': kind['color'],
                              'area_m2': size, 'percent': size/area.area*100})
    return {'area_m2': area.area, 'geometry': geojson(area), 'model_version': 'area-indicators-2',
            'plan_id': plan['id'] if plan else None, 'revision': plan['revision'] if plan else None,
            'scenario_id': scenario['id'] if scenario else None, 'include_scenario': body.include_scenario,
            'baseline': baseline, 'existing_buildings': existing['inventory'], 'proposal': proposal, 'zoning': zones,
            'land_use': land_distribution(records, area) if records is not None else None,
            'population_source': {'status': 'estimated' if people is not None else 'partial' if pop else 'missing',
                                  'year': pop['year'] if pop else None, 'coverage_percent': coverage,
                                  'covered_population': float(pop['value']) if pop else None,
                                  'source': 'WorldPop · area-weighted raster cells'},
            'transit': access or {'status': 'missing', 'coverage_percent': None, 'stops': [], 'geometry': None},
            'assumptions': a.model_dump(), 'issues': issues,
            'notes': ['Baseline population loads use WorldPop. Existing housing capacity uses the generated residential 3D model; its citywide completeness is unknown.',
                      'No existing commercial / office inventory is available for baseline jobs capacity or balance.',
                      'Scenario values are proposed capacity and demand, not net change. Existing occupancy and demolition losses are unknown.',
                      'Capacity uses net GFA; physical floors excluded from GFA still contribute demand.',
                      'Workplace rates apply to commercial and office floors. Other floor uses make aggregate jobs or demand unknown.',
                      'Defaults are illustrative assumptions, not measured consumption or regulatory limits.']}
