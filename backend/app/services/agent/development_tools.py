"""Bounded agent tools using the same saved Development plans and simulation path as the web."""
import json
import hashlib
from copy import deepcopy
from uuid import UUID, uuid4

from fastapi import HTTPException
from psycopg import Error as DatabaseError
from pydantic import ValidationError
from shapely.geometry import shape, box
from shapely.ops import unary_union

from app.routers import zoning
from app.services import parcels
from app.services.zoning import engine, store, baseline
from app.services.zoning.models import PlanInput, Command, BuildingInput
from app.services.zoning.simulation import SimulationRunInput, SimulationInput
from app.services.simulation.planning import store as runs
from app.services.simulation.planning.context import canonical_input, preflight
from app.services.simulation.planning.models import PlanningStudy
from src.shared.database import connect_to_warehouse, warehouse_configured

NAMES = {'workspace_read', 'plan_list', 'plan_open', 'plan_create', 'zoning_edit', 'scenario_select', 'scenario_duplicate',
         'building_save', 'site_select', 'source_catalog', 'site_search', 'site_context',
         'map_control', 'simulation_prepare', 'simulation_start', 'simulation_latest',
         'simulation_results', 'simulation_verify'}


def bind_workspace(session, value):
    allowed = {'plan_id', 'revision', 'scenario_id', 'parcel_id', 'building_id', 'dirty', 'viewport', 'map_pois','selected_place'}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError('Invalid workspace binding')
    binding = {k: v for k, v in value.items() if v is not None}
    if 'map_pois' in binding:
        from .layer_tools import validate_map_pois
        session['map_pois']=validate_map_pois(binding.pop('map_pois'))
    if binding.get('viewport'):
        from .models import Search
        Search(bbox=binding['viewport'])
    if binding.get('selected_place'):
        from app.services.goong_places import coordinates
        place=binding['selected_place']
        if not isinstance(place,dict):raise ValueError('Invalid selected place')
        coordinates([place.get('longitude'),place.get('latitude')])
        binding['selected_place']={key:str(place.get(key,''))[:500] for key in ('id','name','context','source','previous_address')}
        binding['selected_place'].update(longitude=place['longitude'],latitude=place['latitude'])
    for key in ('plan_id', 'scenario_id'):
        if binding.get(key):
            binding[key] = str(UUID(binding[key]))
    if binding.get('plan_id'):
        plan = zoning.require_plan(binding['plan_id'])
        if plan['revision'] != binding.get('revision'):
            raise ValueError('Plan changed. Reload the plan before asking the assistant.')
        engine.find(plan['scenarios'], binding.get('scenario_id'))
    session['workspace'] = binding


def current(session, editing=False):
    w = session.get('workspace', {})
    if not w.get('plan_id'):
        raise ValueError('Open a plan on the map or create one first')
    plan = zoning.require_plan(w['plan_id'])
    if plan['revision'] != w.get('revision'):
        raise ValueError('Plan changed during this request. Reload before continuing; saved jobs remain available.')
    scenario = engine.find(plan['scenarios'], w.get('scenario_id'))
    if editing:
        if w.get('dirty'):
            raise ValueError('Save or discard the unsaved map proposal before asking the assistant to edit or run')
        engine.editable(plan, scenario['id'])
    return plan, scenario


def workspace_view(session):
    if not session.get('workspace', {}).get('plan_id'):
        return {'selection': session.get('workspace', {}), 'status': 'no_open_plan'}
    plan, scenario = current(session)
    buildings = scenario.get('buildings', [])
    return {'selection': session['workspace'], 'plan': {k: plan.get(k) for k in ('id','name','revision','horizon','area_m2','study_area')},
            'scenario': {k: scenario.get(k) for k in ('id','name','kind','locked')},
            'scenarios': [{k:s.get(k) for k in ('id','name','kind','locked')} for s in plan['scenarios']],
            'buildings': [{k:b.get(k) for k in ('id','name','parcel_id','geometry','floors','floor_height','space_use_id','counts_gfa','counts_far','floor_overrides','height_m','footprint_m2')} for b in buildings[:40]],
            'building_count':len(buildings), 'limits':'Plan limits are user proposals unless explicitly verified. Missing inventory does not establish vacancy.',
            'zoning_types':plan.get('types',[]), 'zones':scenario.get('zones',[]),
            'supported_uses':['residential','commercial','office','school','other'],
            'occupancy':'Development derives demand from floor area and explicitly labelled m²/person or staff assumptions. No surveyed baseline occupancy or capacity is implied.'}


def changed(session, plan, scenario_id=None):
    w = session.setdefault('workspace', {})
    w.update(plan_id=plan['id'], revision=plan['revision'], scenario_id=scenario_id or w.get('scenario_id'), dirty=False)
    session['workspace_changed'] = True
    return {'plan_id':plan['id'], 'revision':plan['revision'], 'scenario_id':w['scenario_id'], 'saved':True}


def settings(session, args):
    plan, scenario = current(session, True)
    values = json.loads(args.get('settings_json', '{}'))
    if not isinstance(values, dict):
        raise ValueError('settings_json must be an object')
    allowed = {'residential_m2_per_person','work_m2_per_staff','visitors_per_100m2_day','green_open_percent',
               'rainfall_mm','landscape_mode','traffic_radius_m','school_m2_per_student','school_students_per_staff'}
    if set(values) - allowed:
        raise ValueError('Unsupported simulation settings; identifiers are bound to the selected workspace')
    scope = args.get('scope', 'scenario')
    parcel_id = session['workspace'].get('parcel_id') if scope == 'parcel' else None
    if scope not in ('parcel','scenario') or scope == 'parcel' and not parcel_id:
        raise ValueError('Choose a parcel or use whole scenario')
    return SimulationInput(revision=plan['revision'], scenario_id=scenario['id'], parcel_id=parcel_id, **values)


def prepare(session, args):
    body = settings(session, args)
    value = zoning.simulation_study(UUID(session['workspace']['plan_id']), body)
    identifier = value['id']
    inputs = body.model_dump(mode='json')
    session.setdefault('prepared_runs', {})[identifier] = {'plan_id':session['workspace']['plan_id'],
        'revision':body.revision, 'scenario_id':str(body.scenario_id), 'parcel_id':body.parcel_id, 'settings':inputs,
        'context_hash':value['context_hash'], 'native_work_estimate':value['native_work_estimate']}
    return {'prepared_id':identifier, **value, 'assumptions':inputs,
            'note':'Frozen Development inputs. Detailed start prepares the local OSM network; both states use the same network and background.'}


def start(session, args, allow_native):
    mode = args.get('mode','screening')
    if mode not in ('screening','native'):
        raise ValueError('Unsupported solver mode')
    if mode == 'native' and not allow_native:
        raise ValueError('Enable detailed SUMO/SWMM runs in the assistant before starting native')
    key = args.get('prepared_id')
    saved = session.get('prepared_runs', {}).get(key)
    plan, scenario = current(session, True)
    if not saved or saved['plan_id'] != plan['id'] or saved['scenario_id'] != scenario['id'] or saved['revision'] != plan['revision']:
        raise ValueError('Prepared inputs are absent or stale; prepare again for the current plan/scenario/revision')
    jobs = session.setdefault('development_runs', {})
    for identifier, metadata in jobs.items():
        if metadata.get('prepared_id') == key and metadata['mode'] == mode:
            return {'job':runs.get_job(identifier), 'reused':True}
    if len(jobs) >= 12:
        raise ValueError('Session job limit reached; use a new assistant session')
    if mode == 'native' and saved['native_work_estimate']['sumo_runs'] > 24:
        raise ValueError('Detailed workload exceeds the bounded 24-SUMO-run budget')
    # Native uses the same endpoint as Development, including local network preparation.
    body = SimulationRunInput(**saved['settings'], mode=mode,
        idempotency_key='agent-'+hashlib.sha256((session['id']+key+mode).encode()).hexdigest())
    result = zoning.simulation_run(UUID(plan['id']), body)
    jobs[result['job']['id']] = {**saved, 'prepared_id':key, 'mode':mode}
    return {**result, 'next':'Asynchronous job; inspect status later. Do not claim completion or improvement.'}


def latest(session):
    plan, scenario = current(session)
    result = zoning.latest_simulation(UUID(plan['id']), SimulationInput(revision=plan['revision'],scenario_id=scenario['id'],
        parcel_id=session['workspace'].get('parcel_id')))
    if result['job'] is None and session['workspace'].get('parcel_id'):
        result = zoning.latest_simulation(UUID(plan['id']), SimulationInput(revision=plan['revision'],scenario_id=scenario['id']))
    if result['job']:
        job = result['job']
        session.setdefault('development_runs', {})[job['id']] = {'plan_id':plan['id'], 'revision':plan['revision'],
            'scenario_id':scenario['id'], 'mode':job.get('mode'), 'imported_saved_run':True}
    return result


def results(session, args):
    ids = args.get('job_ids') or list(session.get('development_runs', {}))[-2:]
    if not ids or len(ids) > 6 or not set(ids) <= session.get('development_runs', {}).keys():
        raise ValueError('Read only this session\'s jobs or import the current plan\'s saved run first')
    output, documents = [], []
    for identifier in ids:
        meta = session['development_runs'][identifier]
        job = runs.get_job(identifier)
        plan = store.load(meta['plan_id'])
        row = {'job_id':identifier, 'status':job['status'], 'error':job.get('error'), 'captured':meta,
               'stale_plan_revision':plan is None or plan['revision'] != meta['revision']}
        if job['status'] == 'succeeded' and job.get('result_id'):
            doc = runs.load_document(job['result_id'],'run')
            documents.append(doc)
            options = []
            for option in doc.get('options', []):
                comparisons = deepcopy(option.get('comparison', [])+option.get('traffic_comparison', [])+option.get('drainage_comparison', []))
                for comparison in comparisons:
                    if comparison.get('metric','').endswith('delay_seconds') and comparison.get('trip_population_complete') is False:
                        comparison['delta'] = None
                        comparison['agent_note'] = 'Completed-trip delay cannot establish improvement while trips remain unfinished'
                options.append({'id':option['id'],'comparisons':comparisons})
            row['results'] = {'run_id':doc['id'], 'mode':doc['mode'], 'options':options,
                'sources':doc.get('context',{}).get('development_context'), 'limitations':doc.get('limitations',[]),
                'note':'Unknown baseline is unknown, never zero. Unfinished trips invalidate an improvement claim from completed-trip delay alone.'}
        output.append(row)
    audit = None
    if len(documents) == 2:
        left,right = deepcopy(documents[0]['inputs']),deepcopy(documents[1]['inputs'])
        programs = lambda x:[p['development'].get('buildings',[]) for p in x['projects']]
        controls = ('efficient_fixtures','efficient_equipment','storage_m3','stagger_hours')
        same_program = programs(left) == programs(right)
        for item in (left,right):
            for project in item['projects']:
                for control in controls:
                    project['development'].pop(control,None)
        audit = {'same_building_program':same_program,'same_inputs_except_design_controls':left==right,
                 'basis':'Full canonical inputs compared after removing the four supported design controls. Other differences require separate interpretation.'}
    return {'jobs':output,'paired_input_audit':audit}


def verify(session, args, allow_native):
    key = args['prepared_id']
    original = session.get('prepared_runs', {}).get(key)
    plan,scenario = current(session, True)
    if not original or (original['plan_id'],original['revision'],original['scenario_id']) != (plan['id'],plan['revision'],scenario['id']):
        raise ValueError('Prepare current saved plan first')
    goal,mode = args['goal'],args['mode']
    controls = {'water':('efficient_fixtures',True),'power':('efficient_equipment',True),'runoff':('storage_m3',50),'traffic':('stagger_hours',2)}
    if goal not in controls or mode not in ('screening','native'):
        raise ValueError('Unsupported verification goal/mode')
    if mode == 'native' and not allow_native or goal == 'traffic' and mode != 'native':
        raise ValueError('Traffic verification needs authorized native runs; screening does not calculate delay/queues')
    jobs=session.setdefault('development_runs',{})
    pair_key=f'{key}:{goal}:{mode}'
    existing=[{'job_id':i,'status':runs.get_job(i)['status']} for i,m in jobs.items() if m.get('pair_key')==pair_key]
    if len(existing)==2:
        return {'jobs':existing,'reused':True}
    if len(jobs)>10:
        raise ValueError('Not enough job budget for paired verification')
    control,value=controls[goal]
    # Freeze the detailed source/network ONCE, before modifying a single design control.
    from app.services.zoning.simulation import study_from_plan
    cfg=SimulationRunInput(**original['settings'],mode=mode,idempotency_key='prepare-pair-'+uuid4().hex)
    if cfg.parcel_id:
        parcel=zoning.selected_site(plan,cfg.parcel_id,scenario['id'])
        plan.setdefault('parcels',{})[parcel['id']]=parcel
    inputs=canonical_input(study_from_plan(plan,cfg))
    out=[]
    for variant in (False,True):
        document=deepcopy(inputs)
        if variant:
            for p in document['projects']:
                previous=p['development'].get(control,0)
                p['development'][control]=max(previous,value) if isinstance(value,int) and not isinstance(value,bool) else value
        study=PlanningStudy(**document)
        ready=preflight(study)
        saved,job=runs.start_study(canonical_input(study),ready['context_hash'],f'zoning:{plan["id"]}:{scenario["id"]}',mode,
            'verify-'+hashlib.sha256((session['id']+pair_key+str(variant)).encode()).hexdigest())
        jobs[job['id']]={**original,'mode':mode,'pair_key':pair_key,'variant':variant,'changed_control':control}
        out.append({'job_id':job['id'],'status':job['status'],'variant':variant})
    return {'jobs':out,'changed_control':control,'program_preserved':True,
            'note':'Hypothetical design controls, not saved building edits or observed upgrades. Compare both completed jobs; benefit is not guaranteed.'}


def execute(name,args,session,allow_native):
    try:
        return dispatch(name,args,session,allow_native)
    except HTTPException as error:
        raise ValueError(str(error.detail)) from None
    except (ValidationError,DatabaseError) as error:
        raise ValueError('Invalid input or data source unavailable; no result was inferred') from None


def dispatch(name,args,session,allow_native):
    if name=='workspace_read':
        return workspace_view(session)
    if name=='plan_list':
        return {'plans':store.listing()[:40]}
    if name=='plan_open':
        if session.get('workspace',{}).get('dirty'):
            raise ValueError('Save or discard the current map draft first')
        plan=zoning.require_plan(str(UUID(args['plan_id'])))
        session['workspace']={}
        changed(session,plan,next((s['id'] for s in plan['scenarios'] if s['kind']=='proposal'),plan['scenarios'][0]['id']))
        return workspace_view(session)
    if name=='plan_create':
        # Geometry must come from an explicitly selected source parcel, not invented coordinates.
        ids=args['parcel_ids']
        if not ids or len(ids)>6 or len(set(ids))!=len(ids):
            raise ValueError('Choose 1..6 unique source parcels')
        sources=[parcels.development_parcel(int(i)) for i in ids]
        if not all(sources):
            raise ValueError('Source parcel not found')
        site=unary_union([shape(s['geometry']) for s in sources])
        if site.geom_type not in ('Polygon','MultiPolygon'):
            raise ValueError('Invalid site geometry')
        from shapely.geometry import mapping
        plan=store.save_new(engine.create(PlanInput(name=args['name'],study_area=mapping(site))))
        session['workspace']={}
        changed(session,plan,plan['scenarios'][1]['id'])
        return workspace_view(session)
    if name in ('scenario_select','scenario_duplicate'):
        plan,scenario=current(session, name=='scenario_duplicate')
        if session['workspace'].get('dirty'):
            raise ValueError('Save or discard the current map draft first')
        if name=='scenario_select':
            scenario=engine.find(plan['scenarios'],args['scenario_id'])
            session['workspace'].update(scenario_id=scenario['id'],building_id=None,parcel_id=None)
            session['workspace_changed']=True
        else:
            plan=zoning.change_plan(UUID(plan['id']),Command(revision=plan['revision'],scenario_id=scenario['id'],action='add_scenario',payload={'name':args['name']}))
            changed(session,plan,plan['scenarios'][-1]['id'])
            session['workspace'].update(building_id=None,parcel_id=None)
        return workspace_view(session)
    if name=='zoning_edit':
        plan,scenario=current(session,True)
        if args['action'] not in ('add_type','edit_type','draw','assign'):
            raise ValueError('Unsupported zoning action; removal and shared-type updates are not agent operations')
        payload=json.loads(args['payload_json'])
        if args['action']=='edit_type' and payload.get('confirm_shared'):
            raise ValueError('Shared zoning type edits require the manual workspace')
        new=zoning.change_plan(UUID(plan['id']),Command(revision=plan['revision'],scenario_id=scenario['id'],action=args['action'],payload=payload))
        changed(session,new)
        return {'saved':True,'workspace':session['workspace'],'rule_basis':'User-proposed rules, not authoritative zoning approval','types':new['types'],'zones':engine.find(new['scenarios'],scenario['id'])['zones']}
    if name=='site_select':
        plan,scenario=current(session)
        if session['workspace'].get('dirty'):
            raise ValueError('Save or discard the current map draft first')
        parcel=zoning.selected_site(plan,args['parcel_id'],scenario['id'])
        session['workspace'].update(parcel_id=parcel['id'],building_id=None)
        session['workspace_changed']=True
        return {'parcel':parcel,'vacancy':'not_established'}
    if name=='building_save':
        plan,scenario=current(session,True)
        patch=json.loads(args['patch_json'])
        if not isinstance(patch,dict) or set(patch)-set(BuildingInput.model_fields):
            raise ValueError('Unsupported building fields')
        identifier=args.get('building_id') or session['workspace'].get('building_id')
        if identifier:
            building=engine.find(scenario.get('buildings',[]),identifier)
            payload={k:v for k,v in building.items() if k in BuildingInput.model_fields}
            payload.update(patch,id=identifier)
        else:
            payload={**patch,'parcel_id':session['workspace'].get('parcel_id')}
            payload.pop('id',None)
            if not payload.get('geometry'):
                raise ValueError('Draw a footprint in Development first; no building geometry was invented')
        new=zoning.change_plan(UUID(plan['id']),Command(revision=plan['revision'],scenario_id=scenario['id'],action='save_building',payload=payload))
        changed(session,new)
        selected=next((b for b in engine.find(new['scenarios'],scenario['id']).get('buildings',[]) if b['id']==identifier),None)
        if selected is None:
            previous={b['id'] for b in scenario.get('buildings',[])}
            selected=next(b for b in engine.find(new['scenarios'],scenario['id'])['buildings'] if b['id'] not in previous)
        session['workspace'].update(building_id=selected['id'],parcel_id=selected['parcel_id'])
        return {'saved_building':selected,'workspace':session['workspace'],'result_status':'Previous simulations use old inputs; run again'}
    if name=='source_catalog':
        from app.routers import layers,population,traffic,traffic_sumo
        output={}
        # These routes share the same real data/configuration as the map, with no external model access.
        from app.repository import readiness
        try:
            output['readiness']=readiness()
        except (OSError,ValueError,DatabaseError):
            output['readiness']={'status':'unavailable'}
        if warehouse_configured():
            try:
                with connect_to_warehouse() as c:
                    c.execute('SET LOCAL statement_timeout=5000')
                    output['layers']=[{'id':r[0],'updated_at':str(r[1])} for r in c.execute('SELECT layer,updated_at FROM public.layer_snapshots').fetchall()]
                    output['building_sources']=[r[0] for r in c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='buildings'").fetchall()]
            except DatabaseError:
                output['layers']={'status':'unavailable'}
        from app import repository
        output['queryable_layers']=[{'id':name,'tool':'layer_query','title':info.get('title',name)} for name,info in repository.LAYER_INFO.items()]
        output['queryable_layers'] += [{'id':name,'tool':'layer_query','note':note} for name,note in (
            ('population','Explicit WorldPop year; modeled population and raster coverage'),
            ('traffic','Historical profile, not live traffic; explicit weekday/hour'),
            ('sumo_network','Static OSM-derived simulation network'),
            ('sumo_simulation','Saved run features or catalog; no solver launch'),
            ('poi','System Points of Interest from loaded basemap tiles, with bounded coverage'))]
        output['map_poi_snapshot']={k:v for k,v in session.get('map_pois',{}).items() if k!='features'}
        output['map_poi_count']=len(session.get('map_pois',{}).get('features',[]))
        return {**output,'capacity':'Unknown unless explicitly surveyed; a layer or facility location does not establish spare capacity',
                'inventory':'Current simulation uses generated buildings and supplied map tiles; other warehouse building tables are not automatically used by this engine'}
    if name=='site_search':
        if not session.get('workspace',{}).get('plan_id'):
            # Compatibility for older callers; the model now sees candidate_search only.
            from .general_tools import search_candidates
            return search_candidates(session,args)
        from .models import Search
        body=Search(**args)
        plan,_=current(session)
        bounds=body.bbox or list(shape(plan['study_area']).bounds)
        # Bounded spatial search, explicit area/use filters only. It does not rank legal suitability.
        if (bounds[2]-bounds[0])*(bounds[3]-bounds[1])>0.01:
            raise ValueError('Search area too large; choose a smaller map extent')
        with connect_to_warehouse() as c:
            c.execute('SET LOCAL statement_timeout=8000')
            table='plot' if c.execute("SELECT to_regclass('parcels.plot')").fetchone()[0] else 'land_plot'
            columns=[r[0] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='parcels' AND table_name=%s",(table,)).fetchall()]
            use='mdsdd' if 'mdsdd' in columns else None
            if body.land_use_codes and not use:
                raise ValueError('Land-use filter is unavailable in source schema')
            query='SELECT id,ST_AsGeoJSON(geom),ST_Area(geom::geography) FROM parcels.'+table+' WHERE geom && ST_MakeEnvelope(%s,%s,%s,%s,4326) AND ST_Intersects(geom,ST_MakeEnvelope(%s,%s,%s,%s,4326)) AND ST_Area(geom::geography) BETWEEN %s AND %s'
            params=[*bounds,*bounds,body.minimum_area_m2,body.maximum_area_m2]
            if use:
                query+=' AND (%s OR mdsdd=ANY(%s))'
                params.extend([not body.land_use_codes,body.land_use_codes])
            query+=' ORDER BY ST_Area(geom::geography),id LIMIT %s'
            params.append(body.limit)
            rows=c.execute(query,params).fetchall()
        features=[{'type':'Feature','id':str(i),'geometry':json.loads(g),'properties':{'parcel_id':str(i),'area_m2':a}} for i,g,a in rows]
        session['candidate_features']=features
        session['map_actions'].append({'type':'focus','bbox':bounds})
        return {'candidates':features,'source':'Team PostGIS parcels.land_plot','ordering':'Area then ID','vacancy_and_approval':'not_established'}
    if name=='site_context':
        plan,scenario=current(session)
        identifier=args.get('parcel_id') or session['workspace'].get('parcel_id')
        if not identifier:
            raise ValueError('Select a parcel first')
        parcel=zoning.selected_site(plan,identifier,scenario['id'])
        current_report=zoning.parcel_development_report(UUID(plan['id']),identifier,scenario['id'])
        output={'parcel':parcel,'development':current_report,'layers':{},'capacity':'unknown'}
        from app.services.zoning import simulation_context
        from app.services.simulation.integrated.background import osm_features
        from app.services.simulation.integrated.context import projection
        from shapely.ops import transform
        site=shape(parcel['geometry'])
        document=simulation_context.available_document(site)
        if document:
            forward,_=projection(site)
            region=transform(forward,site).buffer(1000)
            facilities=[f for f in osm_features(document.get('osm',{}))[2]
                        if f.get('geometry') and transform(forward,shape(f['geometry'])).intersects(region)]
            output['nearby_services']={'features':facilities[:10],'matching_count':len(facilities),'buffer_m':1000,
                'captured_at':document.get('captured_at'),'capacity':'unknown; facility location does not establish available seats/service capacity'}
        else:
            output['nearby_services']={'status':'no_installed_source_covers_site','capacity':'unknown'}
        bounds=list(shape(parcel['geometry']).bounds)
        from app.repository import features, LayerUnavailable
        for layer in ('land_price','flood_history','flood_risk'):
            try:
                output['layers'][layer]=features(layer,bounds,limit=6)
            except (TypeError,ValueError,OSError,DatabaseError,LayerUnavailable):
                output['layers'][layer]={'status':'unavailable','note':'No safe inference about risk/price from missing records'}
        return output
    if name=='map_control':
        ids=args.get('layer_ids',[])
        allowed={'population','parcels','land-price','flood-history','flood-satellite','flood','traffic','sumo-network','sumo-simulation','synthetic-buildings'}
        if not set(ids)<=allowed:
            raise ValueError('Unsupported map layer')
        bounds=args.get('bbox')
        from .models import Search
        Search(bbox=bounds)
        session['map_actions'].append({'type':'layers','layer_ids':ids})
        if bounds:
            session['map_actions'].append({'type':'focus','bbox':bounds})
        return {'status':'requested','note':'Frontend checks actual availability; a request does not prove a layer was displayed'}
    if name=='simulation_prepare':
        return prepare(session,args)
    if name=='simulation_start':
        return start(session,args,allow_native)
    if name=='simulation_latest':
        return latest(session)
    if name=='simulation_results':
        return results(session,args)
    if name=='simulation_verify':
        return verify(session,args,allow_native)
    raise ValueError('Unknown Development tool')
