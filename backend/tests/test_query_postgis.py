import json
import os
from copy import deepcopy

import pytest
from psycopg import connect
from shapely.geometry import box,mapping

from app.services.agent import dataset_query as d, query_postgis as pg


def test_field_names_and_literal_values_are_bound_not_sql():
    compiler=pg.Compiler()
    dangerous="x'); DROP TABLE parcels.plot; --"
    sql=compiler.predicate({'field':dangerous,'op':'eq','value':dangerous})
    assert dangerous not in sql
    assert dangerous in compiler.params.values()
    assert 'NULLIF' in sql


def test_safe_partial_predicate_does_not_split_mixed_or():
    leaf={'field':'area_m2','op':'gt','value':100}
    joined={'field':'price.observed_match','op':'eq','value':True}
    assert pg.root_predicate({'any':[leaf,joined]}) is None
    assert pg.root_predicate({'all':[leaf,joined]})=={'all':[leaf]}


def test_explicit_units_are_converted_once_without_guessing():
    query={'layer':'land_price','where':{'field':'residential_vnd_m2','op':'between',
                                      'value':{'min':20,'max':40,'unit':'million_vnd_per_m2'}}}
    normalized=d.normalize_units(query)
    assert normalized['where']['value']==[20000000,40000000]
    assert query['where']['value']['unit']=='million_vnd_per_m2'
    assert d.normalize_units(normalized)==normalized
    with pytest.raises(ValueError):
        d.normalize_units({'where':{'field':'area_m2','op':'gt','value':{'amount':20,'unit':'million_vnd_per_m2'}}})


@pytest.fixture
def real_database(monkeypatch):
    url=os.getenv('AGENT_TEST_DATABASE_URL')
    if not url:pytest.skip('Requires disposable PostGIS test database')
    assert 'agent-query-test-db' in url, 'Integration tests must never target the team warehouse'
    with connect(url,autocommit=True) as connection:
        connection.execute('CREATE EXTENSION IF NOT EXISTS postgis')
        connection.execute('CREATE TABLE IF NOT EXISTS agent_query_test_features (layer text,id text,geom geometry(Geometry,4326),props jsonb)')
        connection.execute('TRUNCATE agent_query_test_features')
        connection.execute("""INSERT INTO agent_query_test_features SELECT 'parcels',i::text,
            ST_MakeEnvelope(106.7+i*.000001,10.8,106.7000005+i*.000001,10.800001,4326),
            jsonb_build_object('n',i,'group',CASE WHEN i%2=0 THEN 'even' ELSE 'odd' END,
                'optional',CASE WHEN i%3=0 THEN NULL ELSE i END)
            FROM generate_series(1,2600) i""")
        connection.execute("""INSERT INTO agent_query_test_features VALUES ('land_price','road',ST_SetSRID(ST_Point(106.7013,10.8),4326),
            '{"residential_vnd_m2":30000000,"geometry_reviewed":false,"source_values_reviewed":false,"source_road":"Source road","road":"Mapped road"}'::jsonb)""")
        connection.execute('CREATE INDEX IF NOT EXISTS agent_query_test_geom_idx ON agent_query_test_features USING gist(geom)')
    def source(source,region,session,compiler):
        sql="SELECT id,geom,props || jsonb_build_object('id',id,'area_m2',round(ST_Area(ST_Transform(geom,32648))::numeric,2)) vals FROM agent_query_test_features WHERE layer="+compiler.bind(source.layer)
        return sql,{'layer':source.layer,'query_engine':'postgis','metadata':{'test':True},'truncated_or_at_limit':False}
    monkeypatch.setattr(pg,'connect_to_warehouse',lambda:connect(url))
    monkeypatch.setattr(pg,'source',source)
    monkeypatch.setattr('src.shared.database.warehouse_configured',lambda:True)
    return {'analysis_area':{'title':'Disposable test geometry','geometry':mapping(box(106.69,10.79,106.72,10.82))}}


def test_filter_beyond_2000_rows_aggregate_before_limit(real_database):
    value=d.execute_query(real_database,{'layer':'parcels','where':{'field':'n','op':'between','value':[2500,2600]},
        'order_by':[{'field':'n','direction':'desc'}],'limit':3,
        'aggregates':[{'op':'count'},{'op':'avg','field':'n'}]})
    assert value['matched_count']==101 and value['scoped_rows']==2600
    assert [r['n'] for r in value['rows']]==[2600,2599,2598]
    assert value['aggregates'][0]['metrics'][1]['value']==2550
    assert not value['source_truncated']


def test_required_spatial_join_units_and_provenance(real_database):
    value=d.execute_query(real_database,{'layer':'parcels','where':{'field':'n','op':'gte','value':2500},
        'joins':[{'layer':'land_price','alias':'price','radius_m':500,
            'where':{'field':'residential_vnd_m2','op':'between','value':{'min':20,'max':40,'unit':'million_vnd_per_m2'}}}],
        'select':['n'],'limit':2,'aggregates':[{'op':'count'}]})
    assert value['matched_count']==101
    assert all(r['price.observed_match'] and r['price.geometry_reviewed'] is False for r in value['rows'])
    assert value['rows'][0]['price.source_road']!='Mapped road'
    assert value['query']['joins'][0]['where']['value']==[20000000,40000000]


def test_sql_null_not_and_grouped_averages(real_database):
    expr={'not':{'field':'optional','op':'gt','value':1000}}
    expected=sum(d.evaluate(expr,{'optional':None if n%3==0 else n}) is True for n in range(1,2601))
    value=d.execute_query(real_database,{'layer':'parcels','where':expr,'group_by':['group'],
        'aggregates':[{'op':'count'},{'op':'avg','field':'optional'}]})
    assert value['matched_count']==expected
    assert value['unknown_filter_rows']==2600//3
    assert sum(group['rows'] for group in value['aggregates'])==expected


def test_failure_does_not_publish_partial_query(real_database):
    previous=deepcopy(real_database)
    with pytest.raises(ValueError):
        d.execute_query(real_database,{'layer':'parcels','where':{'field':'invented','op':'gt','value':1}})
    assert real_database==previous
