from contextlib import nullcontext

from app import repository


def test_old_snapshot_exposes_historical_and_current_names_without_changing_evidence():
    source = {
        'location': 'Phường Hiệp Bình Chánh, khu phố 3', 'depth_max_cm': 300,
        'geocoding_method': 'Area point', 'spatial_precision': 'Medium',
        'original_attributes': {
            'Ward': 'Phường Hiệp Bình Chánh', 'District_mentioned': 'Thủ Đức',
            'Current_admin_unit': 'Phường Hiệp Bình',
        },
    }
    result = repository.flood_location_context(source)
    assert result['reported_ward'] == 'Phường Hiệp Bình Chánh'
    assert result['current_admin_unit'] == 'Phường Hiệp Bình'
    assert result['location'] == source['location']
    assert result['depth_max_cm'] == 300
    assert result['geocoding_method'] == 'Area point'
    assert 'reported_ward' not in source
    assert repository.flood_location_context({'location': 'A'}) == {'location': 'A'}


def test_vector_tiles_keep_location_context_that_nested_properties_used_to_drop(monkeypatch):
    class Connection:
        def execute(self, sql, args):
            self.sql, self.args = sql, args
            return self

        def fetchone(self):
            return (b'tile',)

    connection = Connection()
    monkeypatch.setattr(repository, 'connect_to_warehouse', lambda: nullcontext(connection))
    assert repository.vector_tile('flood_history', 10, 815, 481) == b'tile'
    assert "f.layer = 'flood_history'" in connection.sql
    assert "'{original_attributes,Ward}'" in connection.sql
    assert "'{original_attributes,Current_admin_unit}'" in connection.sql
    assert 'ST_Transform(f.geom, 3857)' in connection.sql
    assert connection.args == (10, 815, 481, 'flood_history', 10, 815, 481)
