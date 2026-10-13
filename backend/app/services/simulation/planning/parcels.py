"""Stable physical identities for mutually exclusive designs on one parcel."""
from shapely.geometry import shape


def registry(study):
    representatives, project_to_parcel = {}, {}
    for project in sorted(study.projects, key=lambda item: item.id):
        key = shape(project.site.model_dump()).normalize().wkb_hex
        physical_id = representatives.setdefault(key, project.id)
        project_to_parcel[project.id] = physical_id
    return project_to_parcel
