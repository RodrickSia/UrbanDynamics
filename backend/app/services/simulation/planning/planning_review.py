"""Screen source parcel attributes; never treats a GIS label as legal permission."""
from ..integrated.geometry import analyze


def review(project, properties):
    geometry = analyze(project.site, project.development)['metrics']
    land_use = properties.get('loai_dat_qh') or ''
    code = properties.get('mdsdd')
    residential = any(b.use == 'residential' for b in project.development.buildings)
    flags = []
    if residential and any(word in land_use.casefold() for word in ('cây xanh','thể dục thể thao','giao thông','ctcc')):
        flags.append('Proposed housing overlaps a parcel whose source planning labels include green/sports/road/public-service land; verify the actual sub-area polygons before selecting a buildable footprint.')
    if residential and code and code not in ('ODT','ONT','OTC'):
        flags.append('Source land-use code is not a confirmed residential code for this proposed housing program.')
    if not land_use:
        flags.append('Source parcel has no planning land-use label; permitted function is unresolved.')
    return {'project_id':project.id,'source_land_use_code':code,
        'source_planning_land_use':land_use or None,'source_plan':properties.get('do_an'),
        'source_decision':properties.get('quyet_dinh'),
        'status':'potential_conflict' if flags and land_use else 'requires_verification',
        'flags':flags,'proposed_density_percent':geometry['building_density_percent'],
        'proposed_far':geometry['far'],
        'permitted_density_percent':None,'permitted_far':None,'permitted_height_m':None,
        'planning_subarea_polygons_available':False,
        'legal_approval_established':False,
        'limitations':['Source GIS labels/decisions are context, not current verified legal conditions.',
            'Textual sub-area totals do not identify which part of the parcel permits a building.',
            'Density/FAR/height/setback limits have not been supplied; no compliance pass is issued.']}
