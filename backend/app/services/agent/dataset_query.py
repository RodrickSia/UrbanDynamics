"""Read-only, bounded query algebra over the application's existing dataset adapters.

No model-provided SQL, URLs or Python. Null predicates use three-valued logic;
spatial associations are evidence links, never cadastral price assignments.
"""
import json
import math
from copy import deepcopy
from uuid import uuid4

from pydantic import Field, model_validator
from shapely.geometry import mapping, shape
from shapely.ops import transform
from shapely.strtree import STRtree

from .models import Strict
from . import layer_tools
from app import repository
from app.services.simulation.integrated.context import projection
from app.services.zoning.geometry import projected

SPECIAL = {'population', 'traffic', 'sumo_network', 'sumo_simulation', 'poi'}
MAX_FETCH = 2000
MAX_COMPARISONS = 300000


class Source(Strict):
    layer: str
    start_date: str | None = None
    end_date: str | None = None
    population_year: int = Field(default=2026, ge=2010, le=2040)
    traffic_weekday: int = Field(default=2, ge=1, le=7)
    traffic_hour: int = Field(default=18, ge=0, le=23)
    run_id: str | None = None


class Join(Source):
    alias: str = Field(pattern=r'^[a-z][a-z0-9_]{0,23}$')
    relation: str = 'near'
    radius_m: float = Field(default=1000, ge=0, le=5000)
    where: dict | None = None
    required: bool = True

    @model_validator(mode='after')
    def relation_valid(self):
        if self.relation not in ('near', 'intersects', 'within'):
            raise ValueError('Join relation must be near, intersects or within')
        if self.layer == 'population':
            raise ValueError('Population adapter is an area total; query it separately, not as a parcel-level join')
        return self


class Order(Strict):
    field: str
    direction: str = 'asc'

    @model_validator(mode='after')
    def valid(self):
        if self.direction not in ('asc', 'desc'):
            raise ValueError('Sort direction must be asc or desc')
        return self


class Aggregate(Strict):
    op: str
    field: str | None = None

    @model_validator(mode='after')
    def valid(self):
        if self.op not in ('count', 'sum', 'avg', 'min', 'max'):
            raise ValueError('Unsupported aggregate')
        if self.op != 'count' and not self.field:
            raise ValueError('Numeric aggregate requires a field')
        return self


class Query(Source):
    spatial: str = 'intersects'
    buffer_m: float = Field(default=0, ge=0, le=5000)
    where: dict | None = None
    joins: list[Join] = Field(default_factory=list, max_length=3)
    order_by: list[Order] = Field(default_factory=list, max_length=3)
    select: list[str] = Field(default_factory=list, max_length=20)
    group_by: list[str] = Field(default_factory=list, max_length=2)
    aggregates: list[Aggregate] = Field(default_factory=list, max_length=8)
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode='after')
    def valid(self):
        if self.spatial not in ('intersects', 'within'):
            raise ValueError('Spatial scope must be intersects or within')
        if len({j.alias for j in self.joins}) != len(self.joins):
            raise ValueError('Join aliases must be unique')
        return self


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def normalize_units(specification):
    """Only explicit units are converted; source strings and bare user text are not guessed."""
    value=deepcopy(specification)
    def visit(expr,depth=0):
        if expr is None:return
        if not isinstance(expr,dict) or depth>5:raise ValueError('Invalid or overly deep filter')
        for group in ('all','any','not'):
            if group in expr:
                children=[expr[group]] if group=='not' else expr[group]
                if not isinstance(children,list):raise ValueError('Boolean group must contain filters')
                for child in children:visit(child,depth+1)
                return
        unit_value=expr.get('value')
        if not isinstance(unit_value,dict) or 'unit' not in unit_value:return
        field=expr.get('field','')
        families=({'vnd_per_m2':1,'million_vnd_per_m2':1000000} if field.endswith('_vnd_m2') else
                  {'m2':1,'ha':10000} if field.endswith('area_m2') else
                  {'m':1,'km':1000} if field.endswith(('distance_m','route_m')) else
                  {'s':1,'min':60} if field.endswith(('duration_s','travel_seconds')) else {})
        unit=unit_value.get('unit')
        if unit not in families:raise ValueError('Unit is not compatible with the source field; use dataset_describe')
        keys=('min','max') if expr.get('op')=='between' else ('amount',)
        if set(unit_value)!={'unit',*keys} or not all(numeric(unit_value.get(k)) for k in keys):
            raise ValueError('Explicit unit range requires min/max; scalar requires amount')
        converted=[unit_value[k]*families[unit] for k in keys]
        if not all(numeric(n) for n in converted):raise ValueError('Converted unit value is nonfinite')
        expr['value']=converted if len(converted)==2 else converted[0]
    visit(value.get('where'))
    for join in value.get('joins',[]):visit(join.get('where'))
    return value


def fields(features):
    result = {'id': {'types': ['string'], 'description': 'Source feature identifier'},
              'area_m2': {'types': ['number'], 'description': 'Computed geometry area; not floor area'}}
    for f in features:
        for key, value in (f.get('properties') or {}).items():
            if not isinstance(key, str) or '.' in key or key in ('id','area_m2'):
                continue
            kind = ('null' if value is None else 'boolean' if isinstance(value, bool) else
                    'number' if numeric(value) else 'string' if isinstance(value, str) else 'object')
            entry = result.setdefault(key, {'types': [], 'examples': []})
            if kind not in entry['types']:
                entry['types'].append(kind)
            if kind in ('string', 'number', 'boolean') and len(entry['examples']) < 3 and value not in entry['examples']:
                entry['examples'].append(value[:160] if isinstance(value, str) else value)
    return result


def fetch_source(source, region, session):
    layer = source.layer
    if layer not in repository.LAYER_INFO and layer not in SPECIAL:
        raise ValueError('Unknown layer; use source_catalog')
    from .scope import metric_area
    if metric_area(region) > 650_000_000:
        raise ValueError('Query and join buffers must fit within 650 km²; narrow the area')
    temporal = repository.LAYER_INFO.get(layer, {}).get('time_enabled', False)
    if (source.start_date or source.end_date) and not temporal:
        raise ValueError('This source does not support date filters; no date restriction was applied')
    for value in (source.start_date, source.end_date):
        if value:
            from datetime import date
            date.fromisoformat(value)
    if source.start_date and source.end_date and source.start_date > source.end_date:
        raise ValueError('Start date must precede end date')
    try:
        if layer in SPECIAL:
            document = layer_tools.special_dataset(layer, region, region, source.model_dump(), session)
        else:
            document = repository.features(layer, list(region.bounds), source.start_date, source.end_date, limit=MAX_FETCH)
    except repository.LayerUnavailable:
        raise ValueError('Dataset '+layer+' is not installed; no substitute was invented') from None
    raw = document.get('features', [])
    usable = [f for f in raw[:MAX_FETCH] if f.get('geometry')]
    metadata = document.get('metadata') or {}
    return usable, {'layer': layer, 'metadata': metadata, 'status': document.get('status'),
                    'fetch_limit': MAX_FETCH, 'fetched': len(usable),
                    'truncated_or_at_limit': bool(metadata.get('truncated') or len(raw) >= MAX_FETCH),
                    'coverage': 'Mapped records in a bounded fetch; no completeness or real-world absence guarantee',
                    'filters': source.model_dump()}


def row_values(feature, geometry):
    # Derived fields cannot be overridden by source properties.
    return {**(feature.get('properties') or {}), 'id': str(feature.get('id', '')),
            'area_m2': round(geometry.area, 2)}


def validate_expression(expr, allowed, depth=0, budget=None):
    if expr is None:
        return
    budget = budget if budget is not None else [0]
    budget[0] += 1
    if depth > 5 or budget[0] > 80 or not isinstance(expr, dict):
        raise ValueError('Filter is too complex or malformed')
    groups = [k for k in ('all', 'any', 'not') if k in expr]
    if groups:
        if len(groups) != 1 or len(expr) != 1:
            raise ValueError('Use one boolean group per filter node')
        key = groups[0]
        children = [expr[key]] if key == 'not' else expr[key]
        if not isinstance(children, list) or not 1 <= len(children) <= 20:
            raise ValueError('Boolean groups require 1..20 conditions')
        for child in children:
            if child is None:
                raise ValueError('Boolean group children must be filter objects')
            validate_expression(child, allowed, depth+1, budget)
        return
    if set(expr) - {'field', 'op', 'value'} or expr.get('field') not in allowed:
        raise ValueError('Unknown filter field; call dataset_describe and use an actual field name')
    op = expr.get('op')
    if op not in ('eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'between', 'in', 'contains', 'is_known', 'is_unknown'):
        raise ValueError('Unsupported filter operator')
    value = expr.get('value')
    if op == 'between' and (not isinstance(value, list) or len(value) != 2 or not all(numeric(v) for v in value) or value[0] > value[1]):
        raise ValueError('between requires two ascending finite numbers in source units')
    if op in ('gt', 'gte', 'lt', 'lte') and not numeric(value):
        raise ValueError('Numeric comparison requires a finite number')
    if op == 'in' and (not isinstance(value, list) or not 1 <= len(value) <= 30):
        raise ValueError('in requires 1..30 values')
    if op == 'contains' and (not isinstance(value, str) or len(value) > 160):
        raise ValueError('contains requires bounded literal text, not a regex')
    if op in ('eq', 'ne') and (value is None or not isinstance(value, (str, int, float, bool))):
        raise ValueError('Use is_unknown for null; equality requires a scalar')


def evaluate(expr, values):
    if expr is None:
        return True
    if 'not' in expr:
        v = evaluate(expr['not'], values)
        return None if v is None else not v
    for group in ('all', 'any'):
        if group in expr:
            outcomes = [evaluate(e, values) for e in expr[group]]
            if group == 'all':
                return False if False in outcomes else None if None in outcomes else True
            return True if True in outcomes else None if None in outcomes else False
    value, op, target = values.get(expr['field']), expr['op'], expr.get('value')
    known = value is not None and not (isinstance(value, float) and not math.isfinite(value))
    if op == 'is_known':
        return known
    if op == 'is_unknown':
        return not known
    if not known:
        return None
    if op in ('gt', 'gte', 'lt', 'lte', 'between'):
        if not numeric(value):
            return None  # Do not guess units or parse ambiguous formatted numeric strings.
        if op == 'between':
            return target[0] <= value <= target[1]
        return {'gt': value > target, 'gte': value >= target, 'lt': value < target, 'lte': value <= target}[op]
    if op == 'contains':
        return target.casefold() in value.casefold() if isinstance(value, str) else None
    if op == 'in':
        return any(type(value) is type(v) and value == v for v in target)
    equal = type(value) is type(target) and value == target
    if numeric(value) and numeric(target):
        equal = value == target
    return equal if op == 'eq' else not equal


def describe(session, args):
    from .general_tools import selection
    source = Source(layer=args['layer'])
    buffer_m = args.get('buffer_m') or 0
    if not numeric(buffer_m) or not 0 <= buffer_m <= 5000:
        raise ValueError('Schema discovery buffer must be 0..5000 m')
    features, evidence = fetch_source(source, layer_tools.buffered(selection(session), buffer_m), session)
    schema = fields(features)
    return {'layer': source.layer, 'fields': schema, 'evidence': evidence, 'buffer_m': buffer_m,
            'schema_scope': 'Observed fields in current bounded area; an empty source has no inferred property schema',
            'query_format': {'layer': source.layer, 'where': {'field': 'ACTUAL_FIELD', 'op': 'between', 'value': [20, 40]},
                             'joins': [{'layer': 'land_price', 'alias': 'price', 'relation': 'near', 'radius_m': 1000}],
                             'order_by': [{'field': 'area_m2', 'direction': 'asc'}], 'limit': 20},
            'operators': ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'between', 'in', 'contains', 'is_known', 'is_unknown'],
            'boolean_groups': ['all', 'any', 'not'],
            'join_fields': 'alias.<source field>, alias.distance_m, alias.observed_match, alias.match_count. Attributes belong to the nearest qualifying source feature, not the parcel.',
            'units': 'Use source units from field names/properties/metadata; never infer VND vs million VND',
            'limits': {'fetch': MAX_FETCH, 'joins': 3, 'returned': 100, 'area_km2': 650}}


def execute_query(session, specification, parent_id=None):
    from .general_tools import selection
    query = Query.model_validate(normalize_units(specification))
    from src.shared.database import warehouse_configured
    if warehouse_configured():
        from .query_postgis import execute
        return execute(session, query, parent_id)
    selected_area = selection(session)
    region = layer_tools.buffered(selected_area, query.buffer_m)
    forward, _ = projection(region)
    metric_region = transform(forward, region)
    features, evidence = fetch_source(query, region, session)
    schema = fields(features)
    prepared = []
    for feature in features:
        geometry = transform(forward, shape(feature['geometry']))
        if (metric_region.covers(geometry) if query.spatial == 'within' else metric_region.intersects(geometry)):
            prepared.append((feature, geometry, row_values(feature, geometry)))
    sources = [evidence]
    comparisons = 0
    for join in query.joins:
        extent = layer_tools.buffered(region, join.radius_m if join.relation == 'near' else 0)
        join_features, info = fetch_source(join, extent, session)
        join_schema = fields(join_features)
        validate_expression(join.where, join_schema)
        joined = []
        for feature in join_features:
            geom = transform(forward, shape(feature['geometry']))
            values = row_values(feature, geom)
            if evaluate(join.where, values) is True:
                joined.append((geom, values))
        schema.update({join.alias+'.'+key: value for key, value in join_schema.items()})
        for key in ('distance_m', 'observed_match', 'match_count'):
            schema[join.alias+'.'+key] = {'description': 'Bounded source association, not proof of real-world absence'}
        tree = STRtree([g for g, _ in joined]) if joined else None
        for _, geom, values in prepared:
            indices = tree.query(geom.buffer(join.radius_m) if join.relation == 'near' and join.radius_m > 0 else geom) if tree is not None else []
            matches = []
            comparisons += len(indices)
            if comparisons > MAX_COMPARISONS:
                raise ValueError('Spatial join work limit reached; narrow the area/radius or source filters')
            for index in indices:
                other, attrs = joined[int(index)]
                distance = geom.distance(other)
                valid = (distance <= join.radius_m if join.relation == 'near' else
                         other.covers(geom) if join.relation == 'within' else geom.intersects(other))
                if valid:
                    matches.append((distance, str(attrs['id']), attrs))
            matches.sort(key=lambda item: (item[0], item[1]))
            values.update({join.alias+'.'+key: None for key in join_schema})
            values.update({join.alias+'.observed_match': bool(matches), join.alias+'.match_count': len(matches),
                           join.alias+'.distance_m': round(matches[0][0], 1) if matches else None})
            if matches:
                values.update({join.alias+'.'+key: value for key, value in matches[0][2].items()})
        sources.append({**info, 'alias': join.alias, 'relation': join.relation, 'radius_m': join.radius_m,
                        'required': join.required,
                        'association': 'Nearest qualifying mapped feature; its attributes are not assigned to the base parcel'})
    validate_expression(query.where, schema)
    requested = query.select + query.group_by + [o.field for o in query.order_by] + [a.field for a in query.aggregates if a.field]
    if any(field not in schema for field in requested):
        raise ValueError('Unknown selected/sorted/grouped/aggregate field; call dataset_describe')
    def qualifies(values):
        if any(j.required and not values[j.alias+'.observed_match'] for j in query.joins):
            return False
        return evaluate(query.where, values)
    outcomes = [(item, qualifies(item[2])) for item in prepared]
    matching = [item for item, outcome in outcomes if outcome is True]
    # Stable, null-last sorting; different scalar types have deterministic order.
    for order in reversed(query.order_by):
        present = [item for item in matching if item[2].get(order.field) is not None]
        missing = [item for item in matching if item[2].get(order.field) is None]
        present.sort(key=lambda item: (0, item[2][order.field]) if numeric(item[2][order.field]) else (1, str(item[2][order.field])), reverse=order.direction == 'desc')
        matching = present + missing
    groups = {}
    if query.aggregates:
        for _, _, values in matching:
            key = tuple(json.dumps(values.get(k), sort_keys=True, ensure_ascii=False) for k in query.group_by)
            groups.setdefault(key, []).append(values)
        if not matching and not query.group_by:
            groups[()] = []
    summaries = []
    for key, members in groups.items():
        summary = {'group': {name: json.loads(v) for name, v in zip(query.group_by, key)}, 'rows': len(members), 'metrics': []}
        for aggregate in query.aggregates:
            numbers = [v[aggregate.field] for v in members if numeric(v.get(aggregate.field))] if aggregate.field else []
            if aggregate.op == 'count':
                value = len(members) if not aggregate.field else sum(v.get(aggregate.field) is not None for v in members)
            else:
                value = None if not numbers else {'sum': sum, 'avg': lambda n: sum(n)/len(n), 'min': min, 'max': max}[aggregate.op](numbers)
            summary['metrics'].append({**aggregate.model_dump(), 'value': value, 'known_numeric': len(numbers),
                                       'unknown_or_nonnumeric': len(members)-len(numbers) if aggregate.field else 0})
        summaries.append(summary)
    selected = matching[:query.limit]
    columns = list(query.select)
    if columns:
        columns = list(dict.fromkeys(['id'] + columns))
        for join in query.joins:
            columns += [join.alias+'.'+key for key in ('observed_match','distance_m') if join.alias+'.'+key not in columns]
        # A terse projection must not hide price quality and applicability flags.
        price_prefixes = ([''] if query.layer == 'land_price' else []) + [j.alias+'.' for j in query.joins if j.layer == 'land_price']
        for prefix in price_prefixes:
            columns += [key for key in schema if key.startswith(prefix) and any(t in key[len(prefix):] for t in
                        ('reviewed','source','confidence','effective','unit','currency','road','vnd')) and key not in columns]
    identifier = uuid4().hex
    result = {'id': identifier, 'parent_query_id': parent_id, 'query': query.model_dump(),
              'area': deepcopy(session.get('analysis_area')), 'analysis_geometry': mapping(selected_area), 'sources': sources, 'fields': schema,
              'matched_in_bounded_fetch': len(matching), 'unknown_filter_rows': sum(v is None for _, v in outcomes),
              'scoped_rows': len(prepared), 'returned': len(selected), 'result_limited': len(matching) > query.limit,
              'unmatched_required_join_rows':sum(any(j.required and not values[j.alias+'.observed_match'] for j in query.joins) for _,_,values in prepared),
              'source_truncated': any(s['truncated_or_at_limit'] for s in sources),
              'rows': [{k: values.get(k) for k in columns} if columns else values for _, _, values in selected],
              'aggregates': summaries[:100], 'aggregate_groups_limited': len(summaries) > 100,
              'interpretation': ['Counts and aggregates describe fetched mapped records, not an exhaustive census.',
                 'Missing values remain unknown; numeric strings are not guessed or converted.',
                 'Near means shortest straight-line geometry distance, not walking/travel distance.',
                 'No matching flood/POI records does not prove safety or real-world absence.',
                 'Land prices are road reference evidence, not parcel market prices, compensation or purchase cost; preserve date, unit and review flags.']}
    return publish(session, result, [feature for feature,_,_ in selected])


def publish(session, result, features):
    """Publish only a completely executed query; failed SQL never changes the map."""
    identifier=result['id']
    layer=result['query']['layer']
    result['summary']=query_summary(result['query'],result.get('area'))
    session.setdefault('structured_queries', []).append(result)
    session['structured_queries'] = session['structured_queries'][-5:]
    session['query_features'] = {'type': 'FeatureCollection', 'features': [
        {**feature, 'properties': {**feature.get('properties', {}), 'query_layer': layer,
                                 'query_id': identifier}} for feature in features]}
    if layer == 'parcels':
        session['candidate_features'] = features
        session['last_search_ids'] = [str(feature.get('id')) for feature in features]
    return result


def query_summary(query,area):
    labels={'area_m2':'Geometry area (m²)','residential_vnd_m2':'Residential reference price (VND/m²)',
            'commercial_vnd_m2':'Commercial reference price (VND/m²)','distance_m':'Geometry distance (m)',
            'duration_s':'Provider travel time (seconds)','mdsdd':'Source land-use code'}
    def expression(node):
        if node is None:return 'No additional attribute filter'
        for key,word in [('all',' AND '),('any',' OR ')]:
            if key in node:return '('+word.join(expression(n) for n in node[key])+')'
        if 'not' in node:return 'NOT '+expression(node['not'])
        field=node.get('field','');prefix,_,name=field.rpartition('.')
        label=(prefix+': ' if prefix else '')+labels.get(name or field,(name or field).replace('_',' '))
        op=node.get('op');value=node.get('value')
        if op=='between':return f'{label}: {value[0]:,} to {value[1]:,}'
        if op in ('is_known','is_unknown'):return label+(' is known' if op=='is_known' else ' is unknown')
        return label+' '+str(op)+' '+str(value)
    return {'area':(area or {}).get('title','Explicit workspace area'),
            'scope':(area or {}).get('scope_summary'), 'base_dataset':query['layer'],
            'conditions':[expression(query.get('where'))]+[
                f"{j['alias']}: {j['relation']} {j['layer']} within {j['radius_m']} m; "+('required match; ' if j['required'] else 'optional evidence; ')+expression(j.get('where')) for j in query.get('joins',[])],
            'order':query.get('order_by',[]),'display_limit':query['limit']}


def run(session, args):
    raw = args.get('query_json', '')
    if len(raw) > 16000:
        raise ValueError('Query specification too large')
    return execute_query(session, json.loads(raw))


def refine(session, args):
    from .general_tools import selection
    old = next((q for q in session.get('structured_queries', []) if q['id'] == args['query_id']), None)
    if old is None:
        raise ValueError('Choose an owned query ID from the last five queries')
    if old.get('area') != session.get('analysis_area') or not shape(old['analysis_geometry']).equals(selection(session)):
        raise ValueError('Selected area changed; start a new query instead of silently moving the old query')
    raw = args.get('patch_json', '')
    if len(raw) > 16000:
        raise ValueError('Query patch too large')
    patch = json.loads(raw)
    if not isinstance(patch, dict):
        raise ValueError('Query patch must be an object')
    specification = deepcopy(old['query'])
    # where is additive; other keys replace explicitly. Re-query all source rows,
    # never filter only the previously displayed top N.
    if specification.get('where') and patch.get('where'):
        patch['where'] = {'all': [specification['where'], patch['where']]}
    elif 'where' in patch and patch['where'] is None and specification.get('where'):
        raise ValueError('Refinement cannot erase prior filters; use dataset_query for a fresh search')
    specification.update(patch)
    return execute_query(session, specification, old['id'])
