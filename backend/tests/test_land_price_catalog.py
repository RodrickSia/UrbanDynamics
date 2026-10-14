import pytest
from fastapi.testclient import TestClient
from app.main import app
from src.shared.data_io import write_json


@pytest.fixture
def catalog_api(tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_DIR',str(tmp_path))
    rows = [{'id':str(i),'ward':'SÀI GÒN','road':name,'from':'A','to':'B','pdf_page':18,
             'region_id':'hcmc_previous','residential_1000_vnd_m2':10000,
             'commercial_1000_vnd_m2':6000,'other_nonagricultural_1000_vnd_m2':5000}
            for i,name in enumerate(['Lê Lợi','Nguyễn Huệ','Đường chờ'])]
    write_json(tmp_path/'review/land_price_rows.json',{'records':rows,'source_url':'https://fixture.test/source.pdf'})
    features = [{'type':'Feature','id':row['id'],'geometry':{'type':'LineString','coordinates':[[106.7,10.8],[106.71,10.8]]},
                 'properties':{'id':row['id'],'geometry_reviewed':False,'source_values_reviewed':False,
                   'residential_vnd_m2':10000000,'commercial_vnd_m2':6000000,'other_nonagricultural_vnd_m2':5000000}}
                for row in rows[:2]]
    write_json(tmp_path/'layers/land_price.geojson',{'features':features})
    write_json(tmp_path/'review/land_price_pending.json',{'pending':[{**rows[2],'unmatched_reason':'named_road_missing_in_ward'}]})
    return TestClient(app),tmp_path


def test_all_prices_survive_pagination_and_unlocated_geometry_stays_null(catalog_api):
    api, _ = catalog_api
    records = []
    for offset in range(3):
        response = api.get(f'/api/v1/land-prices/catalog?offset={offset}&limit=1&include_geometry=true')
        assert response.status_code == 200
        body = response.json()
        assert (body['source_count'],body['mapped_count'],body['pending_count'],body['total']) == (3,2,1,3)
        records.extend(body['records'])
    assert [row['id'] for row in records] == ['0','1','2']
    assert records[0]['map_status'] == 'mapped_automatic'
    assert records[2]['geometry'] is None and not records[2]['has_geometry']
    assert records[2]['pending_reason'] == 'named_road_missing_in_ward'
    assert records[2]['residential_vnd_m2'] == 10000000


def test_search_without_accents_and_filter_before_pagination(catalog_api):
    api, _ = catalog_api
    body = api.get('/api/v1/land-prices/catalog?q=nguyen%20hue').json()
    assert body['total'] == 1 and body['records'][0]['id'] == '1'
    assert 'geometry' not in body['records'][0]
    body = api.get('/api/v1/land-prices/catalog?status=pending').json()
    assert body['total'] == 1 and body['records'][0]['id'] == '2'
    assert api.get('/api/v1/land-prices/catalog?region_id=other').json()['total'] == 0


def test_inconsistent_snapshots_fail_instead_of_silently_losing_rows(catalog_api):
    api, root = catalog_api
    write_json(root/'review/land_price_pending.json',{'pending':[]})
    assert api.get('/api/v1/land-prices/catalog').status_code == 503


def test_road_coverage_does_not_replace_pdf_row_identities(catalog_api):
    api, root = catalog_api
    import json
    matches = json.loads((root/'layers/land_price.geojson').read_text())
    write_json(root/'review/land_price_row_matches.geojson', matches)
    coverage = {'features': [{**matches['features'][0], 'id':'osm:123'}]}
    write_json(root/'layers/land_price.geojson', coverage)
    body = api.get('/api/v1/land-prices/catalog?include_geometry=true').json()
    assert body['source_count'] == 3 and body['mapped_count'] == 2
    assert [r['id'] for r in body['records']] == ['0', '1', '2']
    assert body['records'][0]['geometry'] == matches['features'][0]['geometry']
