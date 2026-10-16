import json
from copy import deepcopy
import pytest
from shapely.geometry import shape

from app.services.agent import general_tools as g,store,tools
from app.services.simulation.planning.jobs import process_one
from test_zoning import rectangle


@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    monkeypatch.delenv('WAREHOUSE_PASSWORD',raising=False)
    monkeypatch.delenv('DATABASE_URL',raising=False)
    monkeypatch.setenv('AGENT_SQLITE_PATH',str(tmp_path/'agent.sqlite'))
    monkeypatch.setenv('PLANNING_SQLITE_PATH',str(tmp_path/'jobs.sqlite'))
    monkeypatch.setenv('SIMULATION_WORK_DIR',str(tmp_path/'solver'))
    monkeypatch.setenv('PLANNING_SYSTEM_SNAPSHOT_DIR',str(tmp_path/'snapshots'))
    monkeypatch.setenv('PLANNING_COUNTING_REFERENCE_DIR',str(tmp_path/'counting'))
    from app.services.simulation.planning import counting_reference
    monkeypatch.setattr(counting_reference,'default_identifier',lambda:None)


def sample(identifier='1',west=106.76):
    return {'id':identifier,'geometry':rectangle(west,10.82,west+.002,10.822),'land_use':'DSK'}


def test_street_lookup_prefers_exact_alley_to_numbered_branches(monkeypatch):
    from app.services.agent import street_location as streets
    geometry=json.dumps({'type':'LineString','coordinates':[[106.6902,10.8202],[106.6905,10.8209]]})
    monkeypatch.setattr(streets,'road_rows',lambda *a:[('Hẻm 114 Trần Quốc Tuấn',geometry,8),('Hẻm 114/14 Trần Quốc Tuấn',geometry,2)])
    session=store.create()
    result=g.choose_area(session,{'source':'street','query':'Hẻm 114 đường Trần Quốc Tuấn'})
    assert result['status']=='street_selected'
    assert result['street_name']=='Hẻm 114 Trần Quốc Tuấn'
    assert result['street_radius_m']==100
    assert len(result['street_matches'])==1
    assert result['street_matches'][0]['source_segment_count_for_name']==8
    assert 106.68<result['bbox'][0]<106.70
    assert session['map_actions'][-1]['type']=='focus'


def test_distant_street_homonyms_require_selection_without_changing_area(monkeypatch):
    from app.services.agent import street_location as streets
    geometry=json.dumps({'type':'MultiLineString','coordinates':[
        [[106.69,10.82],[106.691,10.821]],[[106.75,10.85],[106.751,10.851]]]})
    monkeypatch.setattr(streets,'road_rows',lambda *a:[('Trần Quốc Tuấn',geometry,4)])
    session=store.create();session['analysis_area']={'title':'Previous region'}
    result=g.choose_area(session,{'source':'street','query':'Trần Quốc Tuấn','match_index':None})
    assert result['status']=='ambiguous_street' and len(result['street_matches'])==2
    assert session['analysis_area']['title']=='Previous region'
    assert not session['map_actions']


def test_missing_street_does_not_search_unrelated_viewport(monkeypatch):
    from app.services.agent import street_location as streets
    monkeypatch.setattr(streets,'road_rows',lambda *a:[])
    session=store.create();session['workspace']={'viewport':[106.75,10.82,106.76,10.83]}
    with pytest.raises(ValueError,match='No named road/alley'):
        g.choose_area(session,{'source':'street','query':'Unknown source street'})
    assert 'analysis_area' not in session and not session['candidate_features']


def test_street_name_normalization_preserves_duong_family_name():
    from app.services.agent.street_location import normalize
    assert normalize('Hẻm 114 đường Trần Quốc Tuấn')=='hem 114 tran quoc tuan'
    assert normalize('Hẻm 114 Trần Quốc Tuấn')=='hem 114 tran quoc tuan'
    assert normalize('Đường Dương Quảng Hàm')=='duong quang ham'


def test_model_scope_guard_blocks_implicit_old_area_and_allows_exact_named_alley():
    from app.services.agent.search_scope import check
    session={'analysis_area':{'street_name':'Hẻm 114 Trần Quốc Tuấn','title':'Old area'}}
    unspecified='tìm những khu vực gần bệnh viện, công viên để xây nhà'
    for tool,args in [('area_select',{'source':'street','query':'Hẻm 114 Trần Quốc Tuấn'}),
                      ('area_select',{'source':'viewport'}),('candidate_search',{}),('amenity_site_search',{})]:
        with pytest.raises(ValueError,match='scope'):check(tool,args,unspecified,session,False)
    check('area_select',{'source':'street','query':'Hẻm 114 Trần Quốc Tuấn'},
          'tìm khu vực để xây căn nhà 4 tầng ở hẻm 114 đường trần quốc tuấn quận gò vấp',session,False)
    check('candidate_search',{},unspecified,session,True)
    check('amenity_site_search',{},'tiếp tục tìm trong khu vực đó',session,False)
    check('amenity_site_search',{},'Find sites in the currently selected area',session,False)


def test_model_scope_guard_accepts_visible_map_only_when_requested():
    from app.services.agent.search_scope import check
    check('area_select',{'source':'viewport'},'Hãy chọn vùng map đang nhìn và tìm thửa đất',{},False)
    with pytest.raises(ValueError,match='scope'):
        check('candidate_search',{},'không tiếp tục vùng cũ, tìm gần công viên',{'analysis_area':{}},False)


def test_scope_gate_accepts_numeric_districts_and_provider_city_suffixes():
    from app.services.agent.search_scope import check
    check('area_select',{'source':'place','query':'Quận 3, Hồ Chí Minh, Việt Nam'},'Tìm đất ở quận 3',{},False)
    check('area_select',{'source':'place','query':'Gò Vấp, Hồ Chí Minh, Việt Nam'},'Tìm đất ở Gò Vấp',{},False)
    check('area_select',{'source':'place','query':'Bình Dương, Việt Nam'},'Tìm đất ở Bình Dương',{},False)


def test_price_query_finds_nearby_nonintersecting_road_preserves_provenance(monkeypatch):
    from app.services.agent import layer_tools as layers
    session=store.create();session['workspace']={'viewport':[106.76,10.82,106.762,10.822]}
    g.choose_area(session,{'source':'viewport'})
    road={'type':'Feature','id':'road1','geometry':{'type':'LineString','coordinates':[[106.7622,10.82],[106.7622,10.822]]},
          'properties':{'road':'Source road','residential_vnd_m2':123000,'unit':'VND/m2','geometry_reviewed':False,'effective_from':'2026-01-01'}}
    monkeypatch.setattr(layers.repository,'features',lambda *a,**kw:{'features':[road],'metadata':{'truncated':False}})
    assert layers.layer_query(session,{'layer':'land_price','radius_m':0})['records']==[]
    nearby=layers.layer_query(session,{'layer':'land_price','radius_m':100})
    assert 10<nearby['records'][0]['distance_m']<30
    assert nearby['records'][0]['properties']['geometry_reviewed'] is False
    assert nearby['records'][0]['properties']['residential_vnd_m2']==123000
    assert nearby['records'][0]['properties']['effective_from']=='2026-01-01'


def test_poi_parser_does_not_replace_hospital_with_clinic():
    from app.services.agent.layer_tools import parse_pois
    raw={'elements':[{'type':'node','id':1,'lat':10.82,'lon':106.76,'tags':{'amenity':'clinic'}},
                     {'type':'node','id':2,'lat':10.82,'lon':106.76,'tags':{'shop':'supermarket','name':'Actual market'}},
                     {'type':'way','id':3,'center':{'lat':10.82,'lon':106.76},'tags':{'amenity':'hospital','name':'Actual hospital'}}]}
    parsed=parse_pois(raw)
    assert {f['id'] for f in parsed}=={'node/2','way/3'}
    assert parsed[0]['properties']['name']=='Actual market'


def test_amenity_ranking_missing_hospital_cannot_pass_all_requirements():
    from app.services.agent.layer_tools import proximity_candidates,parse_pois
    features=[{'type':'Feature','id':'1','geometry':sample()['geometry'],'properties':{}}]
    pois=parse_pois({'elements':[{'type':'node','id':1,'lat':10.821,'lon':106.761,'tags':{'shop':'supermarket'}}]})
    selected,_=proximity_candidates(features,pois,{'supermarket':1000,'hospital':1000},3)
    assert selected[0]['amenities']['supermarket']['meets_proximity']
    assert selected[0]['amenities']['hospital']['distance_m'] is None
    assert selected[0]['meets_all'] is False


def test_wrong_osm_category_cannot_qualify_pet_shop_as_supermarket():
    from app.services.agent.layer_tools import parse_pois,proximity_candidates,poi_conflict
    raw={'elements':[{'type':'node','id':1,'lat':10.821,'lon':106.761,
        'tags':{'shop':'supermarket','name':'Cửa Hàng Thú Cưng Haru'}}]}
    pois=parse_pois(raw)
    assert poi_conflict(pois[0])
    selected,_=proximity_candidates([{'type':'Feature','id':'1','geometry':sample()['geometry'],'properties':{}}],
                                  pois,{'supermarket':1000},3)
    assert selected[0]['amenities']['supermarket']['distance_m'] is None
    assert not selected[0]['meets_all']


def test_household_search_keeps_people_as_context_and_discloses_defaults(monkeypatch):
    from app.services.agent import layer_tools as layers
    session=store.create();session['workspace']={'viewport':[106.76,10.82,106.762,10.822]}
    g.choose_area(session,{'source':'viewport'})
    feature={'type':'Feature','id':'1','geometry':sample()['geometry'],'properties':{'area_m2':123,'land_use':'DSK'}}
    monkeypatch.setattr(layers,'parcel_pool',lambda *a:([feature],False))
    monkeypatch.setattr(layers,'load_pois',lambda *a:{'features':[],'source':'OSM fixture'})
    result=layers.amenity_site_search(session,{'requirements_json':'{"park":1000,"hospital":1000}',
        'household_people':4,'minimum_area_m2':None,'maximum_area_m2':None,'limit':3})
    assert result['household_people']==4
    assert result['area_interval_is_screening_default']
    assert result['status']=='no_all_criteria_match_in_sample'
    assert result['results'][0]['meets_all_proximity_requirements'] is False
    assert session['candidate_features'][0]['properties']['amenity_match'] is False


def test_amenity_source_failure_does_not_publish_fake_candidates(monkeypatch):
    from app.services.agent import layer_tools as layers
    session=store.create();session['workspace']={'viewport':[106.76,10.82,106.762,10.822]}
    g.choose_area(session,{'source':'viewport'})
    feature={'type':'Feature','id':'1','geometry':sample()['geometry'],'properties':{}}
    monkeypatch.setattr(layers,'parcel_pool',lambda *a:([feature],False))
    def unavailable(*args):raise ValueError('OSM unavailable')
    monkeypatch.setattr(layers,'load_pois',unavailable)
    with pytest.raises(ValueError,match='OSM unavailable'):
        layers.amenity_site_search(session,{'requirements_json':'{"park":1000}','limit':3})
    assert not session['candidate_features']


def test_system_poi_categories_do_not_guess_from_business_name():
    from app.services.agent.layer_tools import validate_map_pois,system_amenities
    features=[{'type':'Feature','id':str(i),'geometry':{'type':'Point','coordinates':[106.761,10.821]},'properties':p}
              for i,p in enumerate([{'name':'Actual market','class':'supermarket'},
                                    {'name':'Hospital Road Cafe','class':'cafe'},
                                    {'name':'Parking','class':'parking'},
                                    {'name':'Actual hospital','subclass':'hospital'}])]
    snapshot=validate_map_pois({'type':'FeatureCollection','features':features,'bbox':[106.76,10.82,106.762,10.822]})
    assert [f['properties']['category'] for f in system_amenities(snapshot)]==['supermarket','hospital']
    assert all(f['properties']['poi_source']=='System Points of Interest' for f in system_amenities(snapshot))
    features[0]['geometry']['coordinates']=[float('nan'),10.82]
    with pytest.raises(ValueError,match='finite'):validate_map_pois({'type':'FeatureCollection','features':features,'bbox':snapshot['bbox']})


def test_offline_poi_extract_requires_covering_polygon(monkeypatch,tmp_path):
    from app.services.agent.layer_tools import load_pois
    root=tmp_path/'agent-pois';root.mkdir()
    (root/'offline-bbbike-saigon.json').write_text(json.dumps({'schema_version':1,
        'coverage_geometry':rectangle(106.74,10.80,106.78,10.84),'features':[],
        'source':'verified local extract','captured_at':'2026-10-10T00:00:00+00:00'}))
    result=load_pois(shape(sample()['geometry']),100)
    assert result['source']=='verified local extract' and result['cache_hit']


def test_population_layer_preserves_requested_year_and_unknown_total(monkeypatch):
    from app.services.agent.layer_tools import layer_query
    from app.services.area_indicators import sources
    session=store.create();session['workspace']={'viewport':[106.76,10.82,106.762,10.822]}
    g.choose_area(session,{'source':'viewport'})
    years=[]
    def value(geometry,year):
        years.append(year);return {'value':100,'covered_m2':1}
    monkeypatch.setattr(sources,'population',value)
    result=layer_query(session,{'layer':'population','population_year':2024,'radius_m':0})
    assert years==[2024]
    properties=result['records'][0]['properties']
    assert properties['estimated_people'] is None and properties['partial_sum_people']==100


def test_source_catalog_covers_every_system_dataset_layer():
    session=store.create()
    catalog=tools.execute('source_catalog',{},session,False)
    ids={row['id'] for row in catalog['queryable_layers']}
    assert {'population','flood_risk','flood_history','flood_satellite','land_price','parcels',
            'synthetic_buildings','traffic','sumo_network','sumo_simulation','poi'}<=ids


def test_cached_sumo_layer_reads_existing_period_without_starting_a_job(monkeypatch):
    from app.services.agent.layer_tools import special_dataset
    from app.services import traffic_sumo_prediction
    from app.routers import traffic_sumo
    identifier='53f714eb-7d10-4401-92bb-726b0024b2dd'
    calls=[]
    def cached(weekday,period):
        calls.append((weekday,period));return {'run_id':identifier}
    monkeypatch.setattr(traffic_sumo_prediction,'cached_scenario',cached)
    monkeypatch.setattr(traffic_sumo,'get_run_features',lambda run_id:{'features':[]})
    region=shape(sample()['geometry'])
    result=special_dataset('sumo_simulation',region,region,{'traffic_weekday':3,'traffic_hour':8},{})
    assert calls==[(3,'08:00')]
    assert result['metadata']['source_run_id']==identifier
    assert result['metadata']['existing_cache'] is True


def test_system_pois_remain_queryable_when_supplemental_provider_is_down(monkeypatch):
    from app.services.agent import layer_tools as layers
    session=store.create();session['workspace']={'viewport':[106.76,10.82,106.762,10.822]}
    g.choose_area(session,{'source':'viewport'})
    session['map_pois']=layers.validate_map_pois({'type':'FeatureCollection','bbox':[106.76,10.82,106.762,10.822],
        'features':[{'type':'Feature','id':'market','geometry':{'type':'Point','coordinates':[106.761,10.821]},
                     'properties':{'name':'System market','class':'supermarket'}}]})
    feature={'type':'Feature','id':'1','geometry':sample()['geometry'],'properties':{}}
    monkeypatch.setattr(layers,'parcel_pool',lambda *a:([feature],False))
    def unavailable(*args):raise ValueError('provider unavailable')
    monkeypatch.setattr(layers,'load_pois',unavailable)
    result=layers.amenity_site_search(session,{'requirements_json':'{"supermarket":1000}','limit':3})
    assert result['results'][0]['meets_all_proximity_requirements']
    assert result['results'][0]['amenities']['supermarket']['source']=='System Points of Interest'


def test_general_area_works_without_open_plan_and_no_data_is_unknown(monkeypatch):
    session=store.create();session['workspace']={'viewport':[106.76,10.82,106.762,10.822]}
    g.choose_area(session,{'source':'viewport'})
    monkeypatch.setattr(g.repository,'features',lambda *a,**kw:{'features':[]})
    report=g.analyze_area(session,{'population_year':2026})
    assert report['population']['estimated_people'] is None
    assert report['capacity']['water'] is None
    assert report['layers']['flood_history']['status']=='no_matching_records'
    assert not session['workspace'].get('plan_id')
    assert g.report_bundle(session)['areas'][0]['population']['year']==2026


def test_unknown_metrics_never_improve_candidate_score():
    reports=[{'parcel_id':'1','area_m2':1000,'roads':{'nearest_mapped_road_m':20},'population':{'density_people_km2':100}},
             {'parcel_id':'2','area_m2':2000,'roads':{'nearest_mapped_road_m':40},'population':{'density_people_km2':None}}]
    criteria=[g.Criterion(metric='road_distance_m',direction='minimize',weight=1),
              g.Criterion(metric='population_density',direction='maximize',weight=1)]
    result=g.rank_reports(reports,criteria)
    assert result['excluded_from_all_scores']==['population_density']
    assert result['ranking_status']=='insufficient_common_criteria'
    assert all(r['priority_order'] is None for r in result['rows'])
    assert result['rows'][0]['parcel_id']=='1'


def test_declared_weights_thresholds_and_equal_values_are_transparent():
    reports=[{'parcel_id':'1','area_m2':1000,'roads':{'nearest_mapped_road_m':20}},
             {'parcel_id':'2','area_m2':1000,'roads':{'nearest_mapped_road_m':200}}]
    c=[g.Criterion(metric='area_m2',direction='maximize',weight=1),
       g.Criterion(metric='road_distance_m',direction='minimize',weight=3,threshold=100)]
    result=g.rank_reports(reports,c)
    assert result['ranking_status']=='screening_priority'
    assert result['rows'][0]['score']==87.5
    assert result['rows'][1]['failed_thresholds']==['road_distance_m']
    assert result['rows'][0]['legal_approval']=='unknown'


def test_same_school_program_stays_inside_every_site_and_runs(monkeypatch):
    sources=[sample('1'),sample('2',106.764)]
    program=g.ComparisonProgram(use='school',floors=3,floor_area_m2=1800,staff=25,daily_users=300,service_capacity=300)
    study=g.build_study(sources,program,'screening',60)
    assert study.mode=='site_selection' and len(study.options)==2
    for source,project in zip(sources,study.projects):
        assert project.development.buildings[0].gross_floor_area_m2==1800
        assert project.development.buildings[0].service_capacity==300
        assert shape(source['geometry']).buffer(1e-9).covers(shape(project.development.buildings[0].footprint.model_dump()))
        assert project.baseline_occupancy=='unknown'
    from app.services.simulation.planning.context import canonical_input,preflight
    ready=preflight(study)
    saved,job=g.runs.start_study(canonical_input(study),ready['context_hash'],'test-general','screening','general-agent-school-test')
    result=process_one()
    assert result['id']==job['id'] and result['status']=='succeeded',result
    document=g.runs.load_document(result['result_id'],'run')
    assert len(document['options'])==2


def test_program_does_not_silently_shrink_when_it_cannot_fit():
    program=g.ComparisonProgram(use='residential',floors=1,floor_area_m2=100000,residents=1000,housing_units=400)
    with pytest.raises(ValueError,match='does not fit'):
        g.fitted_building(sample(),program)


def test_missing_program_and_invalid_criteria_are_rejected():
    with pytest.raises(ValueError,match='staff and daily users'):
        g.ComparisonProgram(use='school',floors=3,floor_area_m2=1800,service_capacity=300)
    with pytest.raises(ValueError,match='Unsupported metric'):
        g.Criterion(metric='legal_suitability',direction='maximize',weight=1)
    with pytest.raises(ValueError):
        g.bounds([106.0,10,110,14])


def test_owned_study_submission_reuses_job_and_requires_native_opt_in(monkeypatch):
    monkeypatch.setattr(g,'parcel',lambda i:sample(i,106.76 if i=='1' else 106.764))
    session=store.create()
    prepared=g.prepare_study(session,{'parcel_ids':['1','2'],'program_json':json.dumps({'use':'office','floors':3,'floor_area_m2':1200,'staff':60,'daily_users':20})})
    args={'study_id':prepared['study_id'],'mode':'screening'}
    a=g.start_study(session,args,False);b=g.start_study(session,args,False)
    assert a['job']['id']==b['job']['id']
    with pytest.raises(ValueError,match='opt-in'):
        g.start_study(session,{**args,'mode':'native'},False)
    with pytest.raises(ValueError,match='owned'):
        g.read_results(session,{'job_ids':['unrelated-job']})


def test_population_year_is_explicit_not_latest_projection(monkeypatch):
    from app.services.area_indicators import sources
    seen=[]
    def pop(geometry,year):
        seen.append(year)
        return {'value':50,'year':year,'covered_m2':g.projected(geometry).area,'files':['worldpop_2026.tif']}
    monkeypatch.setattr(sources,'population',pop)
    monkeypatch.setattr(g.repository,'features',lambda *a,**kw:{'features':[]})
    report=g.profile(shape(sample()['geometry']),2026,False)
    assert seen==[2026] and report['population']['estimated_people']==50
    assert report['population']['kind']=='modelled_population_not_census'


def test_source_numeric_and_timestamp_types_persist_without_losing_unknowns():
    from decimal import Decimal
    from datetime import datetime,timezone
    s=store.create()
    s['area_reports']={'one':{'population':Decimal('12.5'),'queried_at':datetime.now(timezone.utc),'capacity':None}}
    store.save(s)
    saved=store.get(s['id'])['area_reports']['one']
    assert saved['population']==12.5 and saved['capacity'] is None


def test_place_lookup_is_cached_and_not_a_legal_boundary(monkeypatch):
    session=store.create();calls=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):return [{'display_name':'Thu Duc test place','boundingbox':['10.82','10.822','106.76','106.762']}]
    def fetch(*a,**kw):calls.append(kw);return Response()
    monkeypatch.setattr(g.requests,'get',fetch)
    args={'source':'place','query':'Thu Duc test place','match_index':0}
    first=g.choose_area(session,args);g.choose_area(session,args)
    assert len(calls)==1 and calls[0]['params']['countrycodes']=='vn'
    assert 'not a cadastral' in first['source']


def test_profile_accepts_source_multipolygon_landcover(monkeypatch):
    from shapely.geometry import MultiPolygon,mapping
    region=MultiPolygon([shape(sample()['geometry'])])
    monkeypatch.setattr(g.simulation_context,'available_document',lambda *a:{'osm':{},'landcover':{'features':[],'metadata':{}}})
    monkeypatch.setattr(g.repository,'features',lambda *a,**kw:{'features':[]})
    report=g.profile(region,2026,False)
    assert report['ground_cover']['unclassified_surface_m2']>0
    assert report['ground_cover']['mapped_green_m2']==0


def test_first_search_selection_preserves_search_order(monkeypatch):
    monkeypatch.setattr(g,'parcel',lambda i:sample(i,106.76+int(i)*.003))
    s=store.create();s['last_search_ids']=['3','1','2']
    result=g.prepare_study(s,{'selection':'first_search','take':2,'parcel_ids':[],
        'program_json':json.dumps({'use':'school','floors':3,'floor_area_m2':600,'staff':10,'daily_users':100,'service_capacity':100})})
    assert result['parcel_ids']==['3','1']


def test_native_preparation_keeps_frozen_program_and_source_parcels(monkeypatch):
    monkeypatch.setattr(g,'parcel',lambda i:sample(i,106.76+int(i)*.003))
    s=store.create()
    p=g.prepare_study(s,{'parcel_ids':['1','2'],'program_json':json.dumps({'use':'school','floors':3,'floor_area_m2':600,'staff':10,'daily_users':100,'service_capacity':100})})
    frozen=deepcopy(s['general_studies'][p['study_id']]['inputs'])
    monkeypatch.setattr(g,'parcel',lambda *a:(_ for _ in ()).throw(AssertionError('Do not reload parcel geometry after prepare')))
    monkeypatch.setattr(g.simulation_context,'acquire_network',lambda *a:('f'*64,{'source':'Frozen local OSM','captured_at':g.now()}))
    monkeypatch.setattr(g,'preflight',lambda study:{'context_hash':'e'*64,'native_work_estimate':{'sumo_runs':8}})
    seen=[]
    def start(inputs,*args):
        seen.append(inputs);return {'id':'native-study'},{'id':'native-test-job','status':'queued'}
    monkeypatch.setattr(g.runs,'start_study',start)
    g.start_study(s,{'study_id':p['study_id'],'mode':'native'},True)
    assert seen[0]['projects']==frozen['projects']
    assert seen[0]['traffic_prior']==frozen['traffic_prior']
    assert seen[0]['traffic_snapshot_id']=='f'*64
