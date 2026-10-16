"""Parameterized query algebra; filtering, joins, counts and ordering precede LIMIT.

Application-owned source adapters only. Model field names are JSON keys bound as
values, never SQL identifiers. All SQL runs in one read-only snapshot/timeout.
"""
import json
import os
import math
import logging
from copy import deepcopy
from uuid import uuid4

from psycopg import Error as DatabaseError
from psycopg.types.json import Jsonb
from shapely.geometry import mapping, shape

from app import repository
from src.shared.database import connect_to_warehouse
from . import dataset_query as d, layer_tools


class Compiler:
    def __init__(self):
        self.params={}

    def bind(self,value):
        key='p'+str(len(self.params))
        self.params[key]=value
        return '%('+key+')s'

    def value(self,field,alias='v'):
        return f"NULLIF({alias}.vals -> {self.bind(field)}, 'null'::jsonb)"

    def number(self,field,alias='v'):
        value=self.value(field,alias)
        return f"(CASE WHEN jsonb_typeof({value})='number' THEN ({value} #>> '{{}}')::numeric END)"

    def predicate(self,expr,alias='v'):
        if expr is None:return 'TRUE'
        if 'not' in expr:return '(NOT '+self.predicate(expr['not'],alias)+')'
        for key,op in [('all',' AND '),('any',' OR ')]:
            if key in expr:return '('+op.join(self.predicate(child,alias) for child in expr[key])+')'
        field,op,target=expr['field'],expr['op'],expr.get('value')
        value=self.value(field,alias)
        if op=='is_known':return f'({value} IS NOT NULL)'
        if op=='is_unknown':return f'({value} IS NULL)'
        if op=='between':return f'({self.number(field,alias)} BETWEEN {self.bind(target[0])} AND {self.bind(target[1])})'
        if op in ('gt','gte','lt','lte'):
            symbol={'gt':'>','gte':'>=','lt':'<','lte':'<='}[op]
            return f'({self.number(field,alias)} {symbol} {self.bind(target)})'
        if op=='contains':
            return f"(strpos(lower(CASE WHEN jsonb_typeof({value})='string' THEN {value} #>> '{{}}' END),lower({self.bind(target)}))>0)"
        if op=='in':return '('+' OR '.join(f'{value} = {self.bind(Jsonb(item))}::jsonb' for item in target)+')'
        return f"({value} {'<>' if op=='ne' else '='} {self.bind(Jsonb(target))}::jsonb)"


def root_predicate(expr):
    """Safe partial pushdown: never split an OR with joined-field conditions."""
    if expr is None:return None
    if 'all' in expr:
        children=[root_predicate(e) for e in expr['all']]
        children=[e for e in children if e is not None]
        return {'all':children} if children else None
    if any(k in expr for k in ('any','not')):
        def uses_join(e):
            if 'field' in e:return '.' in e['field']
            return any(uses_join(c) for k,v in e.items() for c in ([v] if k=='not' else v))
        return None if uses_join(expr) else expr
    return expr if '.' not in expr['field'] else None


def native(layer):
    return layer in repository.LAYER_INFO or layer in ('sumo_network','traffic')


def native_source(source,region,c):
    """Return id/geom/props without a row limit, using existing warehouse tables."""
    extent=c.bind(json.dumps(mapping(region)))
    spatial=f"geom && ST_Envelope(ST_SetSRID(ST_GeomFromGeoJSON({extent}),4326)) AND ST_Intersects(geom,ST_SetSRID(ST_GeomFromGeoJSON({extent}),4326))"
    layer=source.layer
    temporal=repository.LAYER_INFO.get(layer,{}).get('time_enabled',False)
    if (source.start_date or source.end_date) and not temporal:
        raise ValueError('This source does not support date filters')
    for value in (source.start_date,source.end_date):
        if value:
            from datetime import date
            date.fromisoformat(value)
    if source.start_date and source.end_date and source.start_date>source.end_date:
        raise ValueError('Start date must precede end date')
    if layer=='parcels':
        text="SELECT id::text,geom,jsonb_strip_nulls(jsonb_build_object('uniq_id',uniq_id,'tinh',tinh,'quan',quan,'phuong',phuong,'to_ban_do',to_ban_do,'thua',thua,'mdsdd',mdsdd,'loai_dat_qh',loai_dat_qh,'quyet_dinh',quyet_dinh,'do_an',do_an)) props FROM parcels.plot WHERE "+spatial
        info=repository.metadata(layer)
    elif layer=='synthetic_buildings':
        text="SELECT parcel_id::text id,geom,jsonb_build_object('parcel_id',parcel_id,'mdsdd',mdsdd,'height_m',height_m,'floors',floors,'inset_m',inset_m,'height_source',height_source,'generator_version',generator_version) props FROM buildings.synthetic_residential WHERE "+spatial
        info=repository.metadata(layer)
    elif layer=='sumo_network':
        text="SELECT edge_id::text id,geom,jsonb_build_object('edge_id',edge_id,'name',name,'road_type',road_type,'lane_count',lane_count,'speed_limit_kmh',(SELECT round((avg(NULLIF((lane->>'speed_mps')::numeric,0))*3.6),1) FROM jsonb_array_elements(lanes) lane)) props FROM transport.sumo_edge WHERE "+spatial
        info={'source':'transport.sumo_edge','kind':'Static network, not traffic observations'}
    elif layer=='traffic':
        from app.routers.traffic import _prediction_ctes
        raw=_prediction_ctes()
        for value in (source.traffic_weekday,source.traffic_hour*2,source.traffic_weekday):
            raw=raw.replace('%s',c.bind(value),1)
        props="jsonb_build_object('edge_id',e.edge_id,'name',e.name,'road_type',e.road_type,'predicted_los',p.predicted_los,'sample_dates',p.sample_dates,'sample_rows',p.sample_rows,'congestion_score',p.congestion_score,'los_mode_share',p.los_mode_share,'confidence',p.confidence,'prediction_basis',p.prediction_basis,'inference_distance_m',p.inference_distance_m)"
        text=f"{raw} SELECT e.edge_id::text id,e.geom,{props} props FROM edge_predictions p JOIN transport.sumo_edge e USING(edge_id) WHERE "+spatial.replace('geom','e.geom')
        info={'source':'Historical traffic adapter SQL','weekday':source.traffic_weekday,'hour':source.traffic_hour,'interpretation':'Historical LOS with labelled spatial inference, not live traffic'}
    else:
        clauses=[spatial,'layer='+c.bind(layer)]
        if source.start_date:clauses.append(repository.time_expression(layer)+' >= '+c.bind(source.start_date))
        if source.end_date:clauses.append(repository.time_expression(layer)+' < '+c.bind(source.end_date))
        text='SELECT feature_id::text id,geom,properties props FROM public.layer_features WHERE '+' AND '.join(clauses)
        info=repository.metadata(layer)
    # Use the same projected CRS as the existing HCMC geometry calculations.
    sql="SELECT id,geom,props || jsonb_build_object('id',id,'area_m2',round(ST_Area(ST_Transform(geom,32648))::numeric,2)) vals FROM ("+text+") raw"
    evidence={'layer':layer,'metadata':info,'query_engine':'postgis','truncated_or_at_limit':False,
              'fetch_limit':None,'coverage':'All installed warehouse records intersecting the declared region; source coverage may be incomplete'}
    return sql,evidence


def source(source,region,session,c):
    from .scope import metric_area
    if metric_area(region)>650_000_000:raise ValueError('Narrow query and join buffers to 650 km²')
    if native(source.layer):return native_source(source,region,c)
    features,info=d.fetch_source(source,region,session)
    # Finite loaded POI snapshots/area totals/saved-result adapters are values,
    # never SQL identifiers; their coverage limits remain explicit in evidence.
    payload=[{'id':str(f.get('id','')),'geometry':f['geometry'],'properties':f.get('properties') or {}} for f in features]
    table=f"SELECT id,ST_SetSRID(ST_GeomFromGeoJSON(geometry),4326) geom,properties FROM jsonb_to_recordset({c.bind(Jsonb(payload))}::jsonb) AS item(id text,geometry jsonb,properties jsonb)"
    sql="SELECT id,geom,properties || jsonb_build_object('id',id,'area_m2',round(ST_Area(ST_Transform(geom,32648))::numeric,2)) vals FROM ("+table+") raw"
    return sql,{**info,'query_engine':'postgis_over_bounded_adapter','coverage':info.get('coverage','Bounded external/derived adapter')}


def discover(connection,sql,c,layer):
    rows=connection.execute('SELECT vals FROM ('+sql+') discovered LIMIT 100',c.params).fetchall()
    schema=d.fields([{'properties':r[0]} for r in rows])
    for key in repository.LAYER_INFO.get(layer,{}).get('fields',[]):
        schema.setdefault(key,{'description':'Declared source field; values may be missing'})
    return schema


def compile_query(connection,query,region,session):
    c=Compiler()
    sql,info=source(query,region,session,c)
    schema=discover(connection,sql,c,query.layer)
    region_param=c.bind(json.dumps(mapping(region)))
    relation='ST_Covers' if query.spatial=='within' else 'ST_Intersects'
    scope=f"{relation}(ST_SetSRID(ST_GeomFromGeoJSON({region_param}),4326),r.geom)"
    ctes=[f'base_source AS NOT MATERIALIZED ({sql})',f'base AS MATERIALIZED (SELECT * FROM base_source r WHERE {scope})']
    join_sql=[];pieces=['b.vals'];requirements=[];sources=[info]
    for i,join in enumerate(query.joins):
        extent=layer_tools.buffered(region,join.radius_m if join.relation=='near' else 0)
        src,evidence=source(join,extent,session,c)
        join_schema=discover(connection,src,c,join.layer)
        d.validate_expression(join.where,join_schema)
        alias='j'+str(i)
        ctes.append(f'raw_source_{i} AS NOT MATERIALIZED ({src})')
        ctes.append(f"source_{i} AS MATERIALIZED (SELECT * FROM raw_source_{i} s WHERE ({c.predicate(join.where,'s')}) IS TRUE)")
        geom='s.geom'
        distance=f'ST_Distance(b.geom::geography,{geom}::geography)'
        if join.relation=='near':
            # Conservative degree envelope is cheap/indexable. Avoid constructing
            # a geodesic buffer for every parcel/source pair; exact geography
            # DWithin below still decides membership, so no distance is guessed.
            maximum_lat=min(89,max(abs(region.bounds[1]),abs(region.bounds[3]))+.1)
            x_pad=join.radius_m/(100000*max(.01,math.cos(math.radians(maximum_lat))))
            y_pad=join.radius_m/100000
            predicate=f"{geom} && ST_Expand(b.geom,{c.bind(x_pad)},{c.bind(y_pad)}) AND ST_DWithin(b.geom::geography,{geom}::geography,{c.bind(join.radius_m)})"
            if join.radius_m==0:predicate=f'ST_Intersects(b.geom,{geom})'
        elif join.relation=='within':predicate=f'ST_Covers({geom},b.geom)'
        else:predicate=f'ST_Intersects(b.geom,{geom})'
        join_sql.append(f"LEFT JOIN LATERAL (SELECT s.id,s.vals,{distance} distance_m,count(*) OVER() n FROM source_{i} s WHERE {predicate} ORDER BY distance_m,s.id LIMIT 1) {alias} ON TRUE")
        prefix=c.bind(join.alias+'.')
        pieces.append(f"COALESCE((SELECT jsonb_object_agg({prefix} || key,value) FROM jsonb_each({alias}.vals)), '{{}}'::jsonb)")
        pieces.append(f"jsonb_build_object({c.bind(join.alias+'.observed_match')}::text,{alias}.id IS NOT NULL,{c.bind(join.alias+'.match_count')}::text,COALESCE({alias}.n,0),{c.bind(join.alias+'.distance_m')}::text,round({alias}.distance_m::numeric,1))")
        if join.required:requirements.append(f'{alias}.id IS NOT NULL')
        schema.update({join.alias+'.'+key:value for key,value in join_schema.items()})
        for field in ('distance_m','observed_match','match_count'):schema[join.alias+'.'+field]={'description':'Mapped source association'}
        sources.append({**evidence,'alias':join.alias,'relation':join.relation,'radius_m':join.radius_m,'required':join.required,
                        'association':'Nearest qualifying mapped feature; not parcel valuation, frontage or verified access'})
    d.validate_expression(query.where,schema)
    requested=query.select+query.group_by+[o.field for o in query.order_by]+[a.field for a in query.aggregates if a.field]
    if any(field not in schema for field in requested):raise ValueError('Unknown query field; use dataset_describe')
    preliminary=c.predicate(root_predicate(query.where),'b')
    ctes.append('enriched AS MATERIALIZED (SELECT b.id,b.geom,'+' || '.join(pieces)+' vals,('+(' AND '.join(requirements) or 'TRUE')+') joins_ok FROM base b '+' '.join(join_sql)+' WHERE ('+preliminary+') IS DISTINCT FROM FALSE)')
    ctes.append('evaluated AS MATERIALIZED (SELECT v.*,CASE WHEN joins_ok THEN '+c.predicate(query.where)+' ELSE FALSE END qualifies FROM enriched v)')
    ctes.append('matched AS MATERIALIZED (SELECT * FROM evaluated WHERE qualifies IS TRUE)')
    ordering=[]
    for order in query.order_by:
        value=c.value(order.field)
        ordering += [f"CASE WHEN {value} IS NULL THEN NULL WHEN jsonb_typeof({value})='number' THEN 0 ELSE 1 END ASC NULLS LAST",
                     c.number(order.field)+' '+order.direction+' NULLS LAST',f"({value} #>> '{{}}') {order.direction} NULLS LAST"]
    ordering.append('v.id ASC')
    ctes.append('displayed AS (SELECT v.*,row_number() OVER(ORDER BY '+','.join(ordering)+') ordinal FROM matched v ORDER BY '+','.join(ordering)+' LIMIT '+c.bind(query.limit)+')')
    groups=[]
    if query.aggregates:
        grouping=[c.value(key) for key in query.group_by]
        group_object='jsonb_build_object('+','.join(c.bind(key)+'::text,'+expr for key,expr in zip(query.group_by,grouping))+')' if grouping else "'{}'::jsonb"
        metrics=[]
        for aggregate in query.aggregates:
            number=c.number(aggregate.field) if aggregate.field else 'NULL::numeric'
            known=f'count({number})'
            value=('count(*)' if not aggregate.field else f'count({c.value(aggregate.field)})') if aggregate.op=='count' else f'{aggregate.op}({number})'
            metrics.append(f"jsonb_build_object('op',{c.bind(aggregate.op)}::text,'field',{c.bind(aggregate.field)}::text,'value',{value},'known_numeric',{known},'unknown_or_nonnumeric',"+(f'count(*)-{known}' if aggregate.field else '0')+')')
        summaries="SELECT "+group_object+" grp,count(*) rows,jsonb_build_array("+','.join(metrics)+") metrics FROM matched v"+(' GROUP BY '+','.join(grouping) if grouping else '')
        ctes.append('summaries AS MATERIALIZED ('+summaries+')')
        aggregate_result="(SELECT COALESCE(jsonb_agg(jsonb_build_object('group',grp,'rows',rows,'metrics',metrics)),'[]'::jsonb) FROM (SELECT * FROM summaries ORDER BY grp::text LIMIT 100) limited)"
        group_count='(SELECT count(*) FROM summaries)'
    else:aggregate_result="'[]'::jsonb";group_count='0'
    final="WITH "+',\n'.join(ctes)+" SELECT jsonb_build_object('scoped_rows',(SELECT count(*) FROM base),'join_evaluated_rows',(SELECT count(*) FROM enriched),'matched',(SELECT count(*) FROM matched),'unknown',(SELECT count(*) FROM evaluated WHERE qualifies IS NULL),'unmatched_required',(SELECT count(*) FROM enriched WHERE NOT joins_ok),'rows',(SELECT COALESCE(jsonb_agg(jsonb_build_object('id',id,'geometry',ST_AsGeoJSON(geom)::jsonb,'values',vals) ORDER BY ordinal),'[]'::jsonb) FROM displayed),'aggregates',"+aggregate_result+",'group_count',"+group_count+")"
    return final,c.params,schema,sources


def execute(session,query,parent_id):
    from .general_tools import selection
    selected_area=selection(session)
    region=layer_tools.buffered(selected_area,query.buffer_m)
    try:
        with connect_to_warehouse() as connection:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            connection.execute('SET LOCAL statement_timeout=20000')
            sql,params,schema,sources=compile_query(connection,query,region,session)
            value=connection.execute(sql,params).fetchone()[0]
    except repository.LayerUnavailable:
        raise ValueError('A requested warehouse dataset is not installed; no substitute source was used') from None
    except DatabaseError as error:
        logging.getLogger(__name__).warning('Agent query failure [%s]: %s',error.sqlstate,error.diag.message_primary)
        if 'agent-query-test-db' in os.getenv('AGENT_TEST_DATABASE_URL',''):
            raise ValueError('Disposable PostGIS test error: '+str(error.diag.message_primary)) from error
        raise ValueError('Warehouse query could not complete within its read-only query budget or a source is unavailable. Narrow the area/joins; no sampled fallback or partial result was substituted.') from None
    columns=list(dict.fromkeys(['id']+query.select)) if query.select else list(schema)
    for join in query.joins:
        for key in ('observed_match','distance_m'):
            if join.alias+'.'+key not in columns:columns.append(join.alias+'.'+key)
    prefixes=([''] if query.layer=='land_price' else [])+[j.alias+'.' for j in query.joins if j.layer=='land_price']
    for prefix in prefixes:
        columns += [key for key in schema if key.startswith(prefix) and any(t in key[len(prefix):] for t in ('reviewed','source','confidence','effective','unit','currency','road','vnd')) and key not in columns]
    identifier=uuid4().hex
    rows=[{key:row['values'].get(key) for key in columns} for row in value['rows']]
    bounded=any(s['truncated_or_at_limit'] for s in sources)
    result={'id':identifier,'parent_query_id':parent_id,'query':query.model_dump(),'area':deepcopy(session.get('analysis_area')),
            'analysis_geometry':mapping(selected_area),'sources':sources,'fields':schema,'query_engine':'postgis',
            'count_scope':'All installed warehouse records in scope, subject to disclosed coverage of any external/derived join source',
            'matched_count':value['matched'],'matched_in_bounded_fetch':value['matched'],
            'scoped_rows':value['scoped_rows'],'join_evaluated_rows':value['join_evaluated_rows'],
            'unknown_filter_rows':value['unknown'],'unmatched_required_join_rows':value['unmatched_required'],
            'returned':len(rows),'result_limited':value['matched']>len(rows),'source_truncated':bounded,'rows':rows,
            'aggregates':value['aggregates'],'aggregate_groups_limited':value['group_count']>100,
            'interpretation':['PostGIS applies filters, spatial joins, sorting and aggregates before the display limit; no 2000-row warehouse sampling.',
                 'Counts cover installed records in the declared geometry, not an exhaustive real-world census. External POI/derived adapters retain their own coverage limits.',
                 'Missing/nonnumeric values remain unknown; no observations do not prove absence of flood or services.',
                 'Spatial distances are shortest geodesic geometry distances, not travel routes or verified entrances.',
                 'Road reference prices are not parcel market values, frontage assignments, compensation or purchase costs.']}
    features=[{'type':'Feature','id':row['id'],'geometry':row['geometry'],'properties':row['values']} for row in value['rows']]
    return d.publish(session,result,features)
