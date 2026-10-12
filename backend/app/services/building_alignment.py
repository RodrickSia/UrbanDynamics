"""Match complete building footprints in EPSG:3857, never the nearest parcel.

Overture geometry is accepted only with a unique source identity or strong
existing overlap, an uncontested reference, and at least 90% parcel coverage.
No translation/rotation search: repeated terrace shapes are not identities.
"""

from collections import Counter
from dataclasses import dataclass

from shapely import STRtree, union_all
from shapely.geometry.base import BaseGeometry

MAX_MATCH_DISTANCE = 50.0  # projected metres; bounds all candidate searches
MIN_PARCEL_COVERAGE = 0.9
MIN_OVERLAP = 0.75
COMPETING_OVERLAP = 0.5


@dataclass(frozen=True)
class Building:
    feature_id: str
    height_m: float
    geometry: BaseGeometry
    source: str | None = None
    source_id: str | None = None


@dataclass(frozen=True)
class Reference:
    overture_id: str
    geometry: BaseGeometry
    sources: list[dict]


@dataclass(frozen=True)
class AlignedBuilding:
    feature_id: str
    height_m: float
    geometry: BaseGeometry
    parcel_fit: str
    parcel_coverage: float | None
    overture_id: str | None = None
    match_method: str | None = None
    geometry_status: str = 'unverified'


def _valid(geometry):
    return (geometry.geom_type in ('Polygon', 'MultiPolygon') and geometry.is_valid
            and not geometry.is_empty and geometry.area > 0)


def _same_identity(building: Building, reference: Reference) -> bool:
    # GBA's Google id is the full source plus code. Do not compare truncated
    # plus codes, Overture GERS ids, or provenance of an unrelated attribute.
    return bool(building.source == 'google' and building.source_id and any(
        source.get('dataset') == 'Google Open Buildings'
        and source.get('property') in ('', '/geometry')
        and source.get('record_id') == building.source_id
        for source in reference.sources
    ))


def align_buildings(buildings: list[Building], references: list[Reference],
                    parcels: list[BaseGeometry]) -> list[AlignedBuilding]:
    references = [r for r in references if _valid(r.geometry)]
    parcel_tree = STRtree([p for p in parcels if _valid(p)])
    reference_tree = STRtree([r.geometry for r in references])

    def covered(geometry):
        indices = parcel_tree.query(geometry, predicate='intersects')
        if not len(indices):
            nearby = parcel_tree.query(geometry.buffer(MAX_MATCH_DISTANCE), predicate='intersects')
            return (0.0 if len(nearby) else None), None
        intersections = [geometry.intersection(parcel_tree.geometries[i]) for i in indices]
        # A parcel may only touch an edge: don't put line/point remnants into
        # a building MultiPolygon after the polygonal part passes coverage.
        parts = [part for intersection in intersections
                 for part in (intersection.geoms if intersection.geom_type == 'GeometryCollection'
                              else [intersection])
                 if part.geom_type in ('Polygon', 'MultiPolygon')]
        inside = union_all(parts)
        return inside.area / geometry.area, inside

    candidates = []
    observations = []
    claims = Counter()
    for building in buildings:
        plausible = []
        nearby_references = []
        corroboration = 0.0
        if _valid(building.geometry):
            for i in reference_tree.query(building.geometry.buffer(MAX_MATCH_DISTANCE)):
                reference = references[i]
                if building.geometry.centroid.distance(reference.geometry.centroid) > MAX_MATCH_DISTANCE:
                    continue
                nearby_references.append(int(i))
                intersection = building.geometry.intersection(reference.geometry).area
                identity = _same_identity(building, reference)
                corroboration = max(corroboration, 1.0 if identity else intersection / building.geometry.area)
                ratio = building.geometry.area / reference.geometry.area
                if not 0.5 <= ratio <= 2:
                    continue
                overlap = intersection / (building.geometry.area + reference.geometry.area - intersection)
                if identity or overlap >= COMPETING_OVERLAP:
                    plausible.append((int(i), identity, overlap))
                    claims[int(i)] += 1
        candidates.append(plausible)
        observations.append((nearby_references, corroboration))

    reference_coverage = {}

    def reference_cover(index):
        if index not in reference_coverage:
            reference_coverage[index] = covered(references[index].geometry)
        return reference_coverage[index]

    results = []
    for building, plausible, (nearby, corroboration) in zip(buildings, candidates, observations):
        geometry = building.geometry
        coverage, inside = covered(geometry) if _valid(geometry) else (None, None)
        fit = 'matched' if coverage is not None and coverage >= MIN_PARCEL_COVERAGE else 'source_unmatched'
        overture_id = method = None
        if len(plausible) == 1:
            index, identity, overlap = plausible[0]
            if claims[index] == 1 and (identity or overlap >= MIN_OVERLAP):
                reference = references[index]
                cover, reference_inside = reference_cover(index)
                if cover is not None and cover >= MIN_PARCEL_COVERAGE:
                    geometry = reference_inside
                    overture_id = reference.overture_id
                    method = 'source_identity' if identity else 'spatial_overlap'
                    fit = 'matched'
        if overture_id is None and fit == 'matched':
            geometry = inside
        status = 'overture_matched' if overture_id else 'parcel_matched' if fit == 'matched' else 'unverified'
        # Suppress only a strong disagreement, not mere absence of a match.
        # Overture must confirm a parcel-covered building in the neighborhood,
        # while neither dataset supports most of this source footprint.
        if (fit != 'matched' and coverage is not None and coverage < 0.5
                and corroboration < 0.25
                and any((reference_cover(i)[0] or 0) >= MIN_PARCEL_COVERAGE for i in nearby)):
            status = 'outside_parcels'
        results.append(AlignedBuilding(building.feature_id, building.height_m, geometry,
                                       fit, coverage, overture_id, method, status))
    return results
