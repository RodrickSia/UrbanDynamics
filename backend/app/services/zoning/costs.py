"""Scenario construction budget. All areas use metric geometry, never land area as GFA."""
from decimal import Decimal, ROUND_HALF_UP

from shapely.ops import unary_union

from . import baseline
from .cost_models import CostSettings
from .geometry import geojson, projected


def money(value):
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def demolition(plan, scenario, settings):
    masks = scenario.get('demolition_masks', [])
    if not masks:
        return [], 0, 'none', []
    if settings.demolition_included:
        return [], 0, 'included', []
    warnings = []
    if settings.demolition_area_m2 is not None:
        rows = [{'id': 'manual-demolition', 'name': 'Demolition scope',
                 'area_m2': settings.demolition_area_m2, 'source': settings.demolition_source}]
        complete, basis = True, 'user_area'
    else:
        region = unary_union([projected(m['geometry']) for m in masks]).intersection(projected(plan['study_area']))
        if region.is_empty:
            return [], 0, 'none', []
        # One inventory query across the union prevents overlapping parcel/zone masks double charging.
        records = baseline.buildings({'id': 'zone:cost-scope', 'geometry': geojson(region)}, plan['study_area'])
        rows, shapes = [], []
        seen = set()
        for record in records or []:
            shape = projected(record['geometry']).intersection(region)
            fingerprint = shape.normalize().wkb
            if fingerprint in seen or shape.area <= .01:
                continue
            seen.add(fingerprint)
            shapes.append(shape)
            floors = record.get('floors')
            floor_source = ''
            if not floors or floors <= 0:
                floors = max(1, round((record.get('height_m') or 6.4) / 3.2))
                floor_source = '; assumed floors from height / 3.2 m, default 2 floors'
            rows.append({'id': record['id'], 'name': f"Existing building {len(rows)+1}",
                         'area_m2': shape.area * floors,
                         'source': (record.get('source') or 'Generated baseline; estimated floors') + floor_source})
        basis = 'generated_scoped_floors'
        warnings.append('Demolition uses generated buildings within the masks; verify coverage and floor area.')
        missing_masks = [projected(mask['geometry']).intersection(region) for mask in masks
                         if not any(shape.intersection(projected(mask['geometry'])).area > .01 for shape in shapes)]
        if missing_masks:
            missing = unary_union(missing_masks).difference(unary_union(shapes))
            if missing.area > .01:
                rows.append({'id':'assumed-demolition', 'name':'Assumed existing buildings in unmapped demolition area',
                             'area_m2':missing.area * .6 * 2,
                             'source':'Demo assumption: 60% building coverage and 2 floors in demolition masks without building records; not surveyed.'})
                basis = 'mixed_inventory_and_demo' if shapes else 'demo_assumed_floors'
                warnings.append('Unmapped demolition area uses a demo assumption: 60% coverage × 2 floors. Replace with a surveyed area when available.')
        complete = bool(rows) and all(row['area_m2'] is not None for row in rows)
    if settings.demolition_rate is None:
        warnings.append('Enter a demolition rate in VND/m².')
        complete = False
    for row in rows:
        row['cost'] = (money(row['area_m2'] * settings.demolition_rate)
                       if row['area_m2'] is not None and settings.demolition_rate is not None else None)
    return rows, sum(row['cost'] or 0 for row in rows) if complete else None, basis, warnings


def calculate(plan, scenario, settings: CostSettings):
    # Deleted buildings may still have quotes for development undo. Do not expose
    # those stale overrides in the editable form or save validation will reject it.
    active_ids = {item['id'] for item in scenario.get('buildings', [])}
    settings = settings.model_copy(update={'building_overrides': {
        key: value for key, value in settings.building_overrides.items() if key in active_ids}})
    reference = scenario['kind'] == 'reference'
    rows, warnings = [], []
    if not reference and scenario.get('demolition_masks') and not settings.demolition_included and settings.demolition_rate is None:
        settings = settings.model_copy(update={'demolition_rate':200000,
            'demolition_source':'Demo assumption: 200,000 VND per m² of demolished floor area; replace with a contractor quote.'})
        warnings.append('Demolition rate assumes 200,000 VND/m² for this demo. It is not a contractor quote or an official rate.')
    for building in [] if reference else scenario.get('buildings', []):
        profile = settings.building_overrides.get(building['id'], settings.profile)
        footprint = projected(building['geometry']).area
        # A floor excluded from regulatory GFA/FAR still costs money to build.
        floors = footprint * building['floors'] if profile.floor_area_m2 is None else profile.floor_area_m2
        components = [{'name': 'Floors', 'area_m2': floors, 'factor': 1},
                      {'name': 'Foundation', 'area_m2': footprint, 'factor': profile.foundation_factor},
                      {'name': 'Roof', 'area_m2': footprint, 'factor': profile.roof_factor},
                      *[item.model_dump() for item in profile.additional_areas]]
        converted = sum(item['area_m2'] * item['factor'] for item in components)
        adjustment = profile.location_factor * profile.access_factor * profile.complexity_factor
        base = money(converted * profile.unit_price * adjustment) if profile.unit_price is not None else None
        rows.append({'id': building['id'], 'name': building['name'], 'parcel_id': building['parcel_id'],
                     'physical_floor_m2': floors, 'converted_m2': converted, 'components': components,
                     'unit_price': profile.unit_price, 'adjustment': adjustment, 'base': base,
                     'source': profile.rate_source, 'area_source': profile.area_source})
        if base is None:
            warnings.append(f"Enter a unit price for {building['name']}.")
        if building['floors'] > 6 or building.get('space_use_id') != 'residential':
            warnings.append('Townhouse presets need a project-specific quote for high-rise or non-residential buildings.')
    demolition_rows, demolition_cost, basis, demolition_warnings = (
        ([], 0, 'none', []) if reference else demolition(plan, scenario, settings))
    warnings.extend(demolition_warnings)
    construction = sum(row['base'] or 0 for row in rows)
    extras = 0 if reference else sum(money(item.amount) for item in settings.extras.values() if not item.included)
    known_demolition = sum(row['cost'] or 0 for row in demolition_rows)
    subtotal = construction + extras + known_demolition
    vat = 0 if settings.vat_included else money(subtotal * settings.vat_pct / 100)
    reserve = money((subtotal + vat) * settings.reserve_pct / 100)
    multiplier = (1 + (0 if settings.vat_included else settings.vat_pct) / 100) * (1 + settings.reserve_pct / 100)
    for row in rows:
        row['total'] = money(row['base'] * multiplier) if row['base'] is not None else None
    for row in demolition_rows:
        row['total'] = money(row['cost'] * multiplier) if row['cost'] is not None else None
    complete = demolition_cost is not None and all(row['base'] is not None for row in rows)
    return {'settings': settings.model_dump(), 'currency': 'VND', 'status': 'estimate' if complete else 'incomplete',
            'buildings': rows, 'demolitions': demolition_rows, 'demolition_basis': basis,
            'construction': construction, 'demolition': demolition_cost, 'extras': extras,
            'subtotal': subtotal, 'vat': vat, 'reserve': reserve, 'known_total': subtotal + vat + reserve,
            'total': subtotal + vat + reserve if complete else None, 'warnings': list(dict.fromkeys(warnings))}
