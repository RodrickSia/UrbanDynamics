"""Conservative identity checks before replacing a GBA footprint."""

from shapely.geometry import box

from app.services.building_alignment import Building, Reference, align_buildings


def test_replaces_a_unique_overlapping_footprint_and_keeps_gba_height():
    source = Building('gba', 46, box(0, 0, 20, 30))
    reference = Reference('overture', box(1, 0, 21, 30), [])
    result = align_buildings([source], [reference], [box(1, 0, 30, 40)])[0]
    assert result.geometry.equals(reference.geometry)
    assert result.height_m == 46
    assert result.overture_id == 'overture'
    assert result.match_method == 'spatial_overlap'


def test_shared_source_identity_can_correct_displacement_without_nearest_parcel():
    source = Building('gba', 35, box(0, 0, 10, 20), 'google', 'exact-id')
    reference = Reference('overture', box(25, 0, 35, 20), [
        {'dataset': 'Google Open Buildings', 'property': '', 'record_id': 'exact-id'},
    ])
    result = align_buildings([source], [reference], [box(20, -5, 40, 25)])[0]
    assert result.geometry.equals(reference.geometry)
    assert result.match_method == 'source_identity'


def test_similar_nearby_building_is_not_evidence_of_identity():
    source = Building('gba', 35, box(0, 0, 10, 20))
    reference = Reference('nearby', box(25, 0, 35, 20), [])
    result = align_buildings([source], [reference], [box(20, -5, 40, 25)])[0]
    assert result.geometry.equals(source.geometry)
    assert result.overture_id is None


def test_ambiguous_references_are_not_matched():
    source = Building('gba', 20, box(0, 0, 20, 20))
    refs = [Reference('a', box(1, 0, 21, 20), []), Reference('b', box(-1, 0, 19, 20), [])]
    result = align_buildings([source], refs, [box(-5, -5, 30, 30)])[0]
    assert result.overture_id is None


def test_two_gba_buildings_cannot_claim_the_same_reference():
    sources = [Building('a', 20, box(0, 0, 20, 20)), Building('b', 60, box(1, 0, 21, 20))]
    results = align_buildings(sources, [Reference('ref', box(0, 0, 20, 20), [])],
                             [box(-5, -5, 30, 30)])
    assert all(r.overture_id is None for r in results)


def test_missing_parcels_or_reference_outside_parcels_cannot_authorize_replacement():
    source = Building('gba', 20, box(0, 0, 20, 20))
    reference = Reference('ref', box(1, 0, 21, 20), [])
    for parcels in ([], [box(100, 100, 110, 110)]):
        result = align_buildings([source], [reference], parcels)[0]
        assert result.overture_id is None
        assert result.geometry.equals(source.geometry)


def test_attribute_only_source_id_does_not_authorize_geometry_replacement():
    source = Building('gba', 20, box(0, 0, 10, 20), 'google', 'id')
    reference = Reference('ref', box(25, 0, 35, 20), [
        {'dataset': 'Google Open Buildings', 'property': '/height', 'record_id': 'id'},
    ])
    assert align_buildings([source], [reference], [box(20, -5, 40, 25)])[0].overture_id is None


def test_clear_parcel_conflict_is_suppressed_without_moving_source_geometry():
    source = Building('road-block', 46, box(0, 0, 10, 30))
    ref = Reference('real-building', box(0, 25, 10, 55), [])
    result = align_buildings([source], [ref], [box(-5, 25, 15, 60)])[0]
    assert result.geometry_status == 'outside_parcels'
    assert result.geometry.equals(source.geometry)
    assert result.overture_id is None


def test_missing_reference_data_never_suppresses_a_building():
    source = Building('gba', 20, box(0, 0, 10, 20))
    ref = Reference('ref', box(25, 0, 35, 20), [])
    for refs, parcels in (([], [box(20, -5, 40, 25)]), ([ref], [])):
        result = align_buildings([source], refs, parcels)[0]
        assert result.geometry_status != 'outside_parcels'


def test_overture_corroboration_preserves_a_building_when_parcels_disagree():
    source = Building('gba', 20, box(0, 0, 10, 20))
    refs = [Reference('same', box(0, 0, 10, 20), []), Reference('next', box(25, 0, 35, 20), [])]
    result = align_buildings([source], refs, [box(20, -5, 40, 25)])[0]
    assert result.geometry_status != 'outside_parcels'


def test_ham_nghi_reported_road_blocks_are_excluded_but_never_relocated():
    import json
    from pathlib import Path

    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform

    fixture = json.loads((Path(__file__).parent / 'fixtures/building-alignment-ham-nghi.json')
                        .read_text(encoding='utf-8'))
    project = Transformer.from_crs(4326, 3857, always_xy=True).transform
    sources = [Building(f['properties']['feature_id'], f['properties']['height_m'],
                        transform(project, shape(f['geometry'])), 'google',
                        f['properties']['feature_id'].split(':')[0].removeprefix('google').removesuffix('VNM'))
               for f in fixture['buildings']]
    references = [Reference(f['properties']['overture_id'], transform(project, shape(f['geometry'])),
                            f['properties']['sources']) for f in fixture['references']]
    result = align_buildings(sources, references, [transform(project, shape(g)) for g in fixture['parcels']])
    for before, after in zip(sources, result):
        assert after.height_m == before.height_m
        if 'QPC3+W6P4' in before.feature_id:
            assert after.overture_id == '6fb73685-fb74-4723-84ea-bdb3d547f3af'
            assert after.match_method == 'source_identity'
            assert after.geometry_status == 'overture_matched'
        else:
            assert after.geometry_status == 'outside_parcels'
            assert after.overture_id is None
            assert after.geometry.equals(before.geometry)
