import json
from copy import deepcopy

import pytest
from shapely.geometry import box, mapping, Point

from app.services.agent import dataset_query as d


def feature(identifier, geometry, **properties):
    return {'type': 'Feature', 'id': identifier, 'geometry': mapping(geometry), 'properties': properties}


@pytest.fixture
def session():
    return {'analysis_area': {'title': 'Explicit test area', 'geometry': mapping(box(106.70, 10.80, 106.71, 10.81))},
            'candidate_features': [], 'last_search_ids': []}


@pytest.fixture
def sources(monkeypatch):
    records = {'parcels': [feature('1', box(106.701,10.801,106.7011,10.8011), use='residential', n=10),
                            feature('2', box(106.705,10.805,106.7051,10.8051), use='office', n=None),
                            feature('3', box(106.709,10.809,106.7091,10.8091), use='residential', n=30)],
               'land_price': [feature('p', Point(106.701,10.801), residential_vnd_m2=30000000,
                                      geometry_reviewed=False, source_road='Source road', road='Mapped road')],
               'poi': [feature('hospital',Point(106.7012,10.8012),category='hospital')]}
    def fetch(source,region,session):
        return deepcopy(records.get(source.layer,[])), {'layer':source.layer,'metadata':{'fixture':True},
                                                       'truncated_or_at_limit':False}
    monkeypatch.setattr(d,'fetch_source',fetch)
    return records


def test_boolean_range_unknown_and_aggregate(session,sources):
    result=d.execute_query(session,{'layer':'parcels','where':{'any':[
        {'field':'n','op':'between','value':[10,20]}, {'field':'n','op':'gt','value':40}]},
        'aggregates':[{'op':'sum','field':'n'},{'op':'count'}]})
    assert [r['id'] for r in result['rows']]==['1']
    assert result['unknown_filter_rows']==1
    assert result['aggregates'][0]['metrics'][0]['value']==10


def test_not_unknown_is_not_true():
    expr={'not':{'field':'x','op':'gt','value':1}}
    d.validate_expression(expr,{'x':{}})
    assert d.evaluate(expr,{'x':None}) is None
    assert d.evaluate({'field':'x','op':'is_unknown'},{'x':None}) is True
    assert d.evaluate({'field':'x','op':'gt','value':1},{'x':'2,000'}) is None


def test_spatial_price_join_keeps_source_review_and_nulls(session,sources):
    result=d.execute_query(session,{'layer':'parcels','joins':[{'layer':'land_price','alias':'price','radius_m':50,
        'where':{'field':'residential_vnd_m2','op':'between','value':[20000000,40000000]}}],
        'where':{'field':'price.observed_match','op':'eq','value':True}})
    assert len(result['rows'])==1
    row=result['rows'][0]
    assert row['price.geometry_reviewed'] is False
    assert row['price.source_road'] != row['price.road']
    assert result['sources'][1]['association'].startswith('Nearest')
    assert 'parcel market prices' in ' '.join(result['interpretation'])


def test_two_joins_require_both_matches(session,sources):
    result=d.execute_query(session,{'layer':'parcels','joins':[
        {'layer':'land_price','alias':'p','radius_m':50},
        {'layer':'poi','alias':'h','radius_m':100,'where':{'field':'category','op':'eq','value':'hospital'}}],
        'where':{'all':[{'field':'p.observed_match','op':'eq','value':True},
                         {'field':'h.observed_match','op':'eq','value':True}]}})
    assert [r['id'] for r in result['rows']]==['1']


def test_refinement_requeries_full_fetch_preserves_old_filter(session,sources):
    old=d.execute_query(session,{'layer':'parcels','where':{'field':'n','op':'gte','value':10},'limit':1})
    result=d.refine(session,{'query_id':old['id'],'patch_json':json.dumps({'where':{'field':'n','op':'gt','value':20}})})
    assert result['rows'][0]['id']=='3'
    assert result['parent_query_id']==old['id']
    assert 'all' in result['query']['where']
    with pytest.raises(ValueError):
        d.refine(session,{'query_id':'other-session-id','patch_json':'{}'})
    session['analysis_area']['title']='Changed'
    with pytest.raises(ValueError,match='area changed'):
        d.refine(session,{'query_id':old['id'],'patch_json':'{}'})


def test_grouping_known_counts_and_null_last_sort(session,sources):
    result=d.execute_query(session,{'layer':'parcels','order_by':[{'field':'n','direction':'desc'}],
        'group_by':['use'],'aggregates':[{'op':'avg','field':'n'},{'op':'count'}]})
    assert [r['id'] for r in result['rows']]==['3','1','2']
    residential=next(g for g in result['aggregates'] if g['group']['use']=='residential')
    assert residential['metrics'][0]['value']==20
    office=next(g for g in result['aggregates'] if g['group']['use']=='office')
    assert office['metrics'][0]['value'] is None


@pytest.mark.parametrize('patch',[
    {'where':{'field':'invented_price','op':'gt','value':1}},
    {'where':{'field':'n','op':'between','value':[30,10]}},
    {'where':{'field':'n','op':'regex','value':'.*'}},
    {'order_by':[{'field':'n','direction':'SQL'}]},
    {'sql':'DROP TABLE parcels'},
    {'limit':1000},
    {'joins':[{'layer':'population','alias':'pop'}]},
    {'joins':[{'layer':'poi','alias':'x'},{'layer':'poi','alias':'x'}]},
])
def test_invalid_queries_do_not_mutate_session(session,sources,patch):
    before=deepcopy(session)
    with pytest.raises(ValueError):
        d.execute_query(session,{'layer':'parcels',**patch})
    assert session==before


def test_within_excludes_boundary_crossing(session,sources):
    sources['parcels'].append(feature('outside',box(106.7099,10.8099,106.72,10.82),n=1))
    result=d.execute_query(session,{'layer':'parcels','spatial':'within'})
    assert len(result['rows'])==3


def test_nonparcel_query_overlay_does_not_become_candidate_ids(session,sources):
    result=d.execute_query(session,{'layer':'land_price'})
    assert result['rows'][0]['id']=='p'
    assert session['last_search_ids']==[]
    assert session['query_features']['features'][0]['properties']['query_layer']=='land_price'


def test_truncated_sources_are_explicit(session,sources,monkeypatch):
    original=d.fetch_source
    def fetch(*args):
        features,evidence=original(*args)
        evidence['truncated_or_at_limit']=True
        return features,evidence
    monkeypatch.setattr(d,'fetch_source',fetch)
    result=d.execute_query(session,{'layer':'parcels','limit':1})
    assert result['source_truncated'] and result['result_limited']
    assert result['matched_in_bounded_fetch']==3


def test_unknown_layer_and_unsupported_time_rejected(session):
    with pytest.raises(ValueError,match='Unknown layer'):
        d.describe(session,{'layer':'arbitrary_sql_table'})
    layer=next(k for k,v in d.repository.LAYER_INFO.items() if not v.get('time_enabled'))
    with pytest.raises(ValueError,match='date filters'):
        d.fetch_source(d.Source(layer=layer,start_date='2026-01-01'),box(106.70,10.80,106.701,10.801),session)


def test_discovered_source_id_and_area_do_not_override_derived_fields():
    schema=d.fields([feature('x',Point(106.7,10.8),id=123,area_m2='source text')])
    assert schema['id']['types']==['string']
    assert schema['area_m2']['types']==['number']


def test_refine_model_scope_requires_explicit_continuation(session):
    from app.services.agent.search_scope import check
    with pytest.raises(ValueError,match='explicit continuation'):
        check('dataset_query_refine',{},'find places near parks',session,False)
    check('dataset_query_refine',{},'Tiếp tục lọc các kết quả này dưới 150 m²',session,False)


def test_zero_radius_point_join_keeps_exact_intersections(session,sources):
    sources['land_price'][0]['geometry']=deepcopy(sources['poi'][0]['geometry'])
    result=d.execute_query(session,{'layer':'poi','joins':[{'layer':'land_price','alias':'p','radius_m':0}],
                                  'where':{'field':'p.observed_match','op':'eq','value':True}})
    assert len(result['rows'])==1 and result['rows'][0]['p.distance_m']==0


def test_required_join_filters_without_extra_root_predicate(session,sources):
    result=d.execute_query(session,{'layer':'parcels','joins':[{'layer':'land_price','alias':'p','radius_m':50}],
                                  'aggregates':[{'op':'count'}]})
    assert result['matched_in_bounded_fetch']==1
    assert result['aggregates'][0]['metrics'][0]['value']==1
    assert result['unmatched_required_join_rows']==2
    optional=d.execute_query(session,{'layer':'parcels','joins':[{'layer':'land_price','alias':'p','radius_m':50,'required':False}]})
    assert optional['matched_in_bounded_fetch']==3
