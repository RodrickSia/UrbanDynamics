"""Installable count evidence; short unmapped clips can support priors, never OD observations."""
import hashlib
import json
import math
import os
from pathlib import Path


def directory():
    default=Path(os.getenv('PLANNING_SYSTEM_SNAPSHOT_DIR','data/simulation_snapshots'))/'counting'
    return Path(os.getenv('PLANNING_COUNTING_REFERENCE_DIR',str(default)))


def load(identifier):
    from .system_demo import enabled
    if not enabled() or len(identifier)!=64 or any(c not in '0123456789abcdef' for c in identifier):
        raise ValueError('Counting reference requires enabled test demo and a valid installed ID')
    raw=(directory()/(identifier+'.json')).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=identifier:
        raise ValueError('Counting reference integrity check failed')
    document=json.loads(raw)
    if document.get('schema_version')!='traffic-counts-identity-repair-1' or document.get('simulation_ready') is not False:
        raise ValueError('Expected uncalibrated identity-repaired reference; do not promote it to observed OD')
    if not math.isfinite(document['observation']['duration_seconds']) or document['observation']['duration_seconds']<=0 or any(x['count']<0 for x in document['counts']):
        raise ValueError('Invalid counting reference duration/counts')
    if len({x['vehicle_class'] for x in document['counts']})!=len(document['counts']) or sum(x['count'] for x in document['counts'])!=document['repaired_crossings']:
        raise ValueError('Counting reference class totals do not conserve repaired events')
    if any(not isinstance(x['count'],int) for x in document['counts']):
        raise ValueError('Crossing counts must be integers')
    for key in ('source_sha256','tracks_sha256'):
        if len(document[key])!=64 or any(c not in '0123456789abcdef' for c in document[key]):
            raise ValueError('Counting reference requires source video/tracks hashes')
    return document


def default_identifier():
    """Opt-in installed demo policy; old catalogs remain unchanged."""
    identifier=os.getenv('PLANNING_DEFAULT_COUNTING_REFERENCE_ID')
    pointer=directory()/'default-reference.txt'
    if not identifier and pointer.is_file():
        identifier=pointer.read_text().strip()
    return identifier or None


def flow_default(identifier, road_id=None, observed_vehicles_hour=None):
    """A transferred road-level assumption, not a citywide observation or OD matrix."""
    document=load(identifier)
    seconds=document['observation']['duration_seconds']
    counts={r['vehicle_class']:r['count'] for r in document['counts']}
    factor=3600/seconds
    assumed=sum(counts.values())*factor
    observed=observed_vehicles_hour is not None
    if observed and (isinstance(observed_vehicles_hour,bool) or not math.isfinite(observed_vehicles_hour) or observed_vehicles_hour<0):
        raise ValueError('Observed road flow must be a finite nonnegative number')
    return {'road_id':road_id,'vehicles_hour':observed_vehicles_hour if observed else assumed,
        'basis':'both_directions_combined','source_kind':'observed' if observed else 'synthetic',
        'counting_reference_id':identifier,'sample_crossings':document['repaired_crossings'],
        'sample_duration_seconds':seconds,'sample_vehicles_hour_by_class':{k:v*factor for k,v in counts.items()},
        'sumo_supported_vehicles_hour':sum(counts.get(k,0) for k in ('car','motorcycle'))*factor,
        'policy':'Use the same transferred default for roads without observations; observed zero overrides the default.',
        'calibrated':False,'hourly_profile_observed':False,
        'limitations':['Short-clip rate extrapolated to an hour, not a measured hourly flow.',
            'No current road/time mapping or capacity calibration. Both directions combined, not per lane.',
            'Edge flow is not OD demand; SUMO uses a regional proxy once, not one injection per internal edge.',
            'The two-class SUMO proxy excludes bus/van/truck counts.']}


def prior(identifier, peak_vehicles_hour=None):
    from .models import TrafficPrior
    document=load(identifier)
    counts={r['vehicle_class']:r['count'] for r in document['counts']}
    cars,motorcycles=counts.get('car',0),counts.get('motorcycle',0)
    if not cars+motorcycles:
        raise ValueError('Counting reference has no supported car/motorcycle sample')
    if peak_vehicles_hour is None:
        factor=3600/document['observation']['duration_seconds']
        return TrafficPrior(cars=[round(cars*factor)]*24,motorcycles=[round(motorcycles*factor)]*24,
            source_kind='synthetic',counting_reference_id=identifier,
            source='City-road demo default: short-clip car/motorcycle counts extrapolated to an hour and transferred to roads without observations. Constant 24-hour profile is assumed, not observed. SUMO uses this as one regional OD proxy, never multiplied by internal edges. Bus/truck samples excluded; not calibrated city traffic.')
    # Generic bimodal daily shape; amplitude is explicitly a demo assumption.
    profile=[.15,.1,.08,.08,.1,.25,.6,1,.8,.65,.6,.65,.7,.65,.6,.7,.85,1,1,.8,.6,.45,.3,.2]
    totals=[round(peak_vehicles_hour*x) for x in profile]
    bikes=[round(n*motorcycles/(cars+motorcycles)) for n in totals]
    return TrafficPrior(cars=[n-b for n,b in zip(totals,bikes)],motorcycles=bikes,
        source_kind='estimated',counting_reference_id=identifier,
        source='UIT-ADrone short-clip conditional car/motorcycle mix transferred as an uncalibrated prior. Generic daily shape and peak amplitude are demo assumptions; edge counts are not observed OD departures. Bus/truck samples are excluded from this two-class solver prior.')
