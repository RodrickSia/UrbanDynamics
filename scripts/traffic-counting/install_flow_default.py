"""Install a reviewed clip as a hash-addressed default; never overwrite old evidence."""
import argparse, hashlib, json
from pathlib import Path

def install(review, destination):
    summary=json.loads((review/'review-summary.json').read_text(encoding='utf-8'))
    config=json.loads((review/'config.json').read_text(encoding='utf-8'))
    counts={}
    for row in summary['counts']:
        counts[row['vehicle_class']]=counts.get(row['vehicle_class'],0)+row['count']
    if sum(counts.values())!=summary['total_crossings']:
        raise ValueError('Review counts do not conserve events')
    document={'schema_version':'traffic-counts-identity-repair-1','simulation_ready':False,
        'camera_id':summary['camera_id'],'source_sha256':summary['source_video_sha256'],
        'tracks_sha256':summary['tracks_sha256'],'config':config,
        'observation':{'duration_seconds':summary['duration_seconds'],'processed_frames':summary['frames']},
        'repaired_crossings':summary['total_crossings'],
        'counts':[{'vehicle_class':k,'count':v} for k,v in sorted(counts.items())],
        'identity_repairs':summary['identity_repairs'],
        'validation':{'status':'requires_independent_counting_labels'},
        'review_video_sha256':summary['output_video_sha256'],
        'limitations':['User-selected city-road demo default; not measured current city traffic.',
            'Short historical clip; no hourly/day profile, road mapping, lane or capacity calibration.']}
    raw=json.dumps(document,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
    identifier=hashlib.sha256(raw).hexdigest()
    destination.mkdir(parents=True,exist_ok=True)
    path=destination/(identifier+'.json')
    if path.exists() and path.read_bytes()!=raw:
        raise ValueError('Existing reference bytes differ')
    path.write_bytes(raw)
    (destination/'default-reference.txt').write_text(identifier+'\n',encoding='utf-8')
    return identifier

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--review',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps({'default_reference_id':install(args.review,args.destination)}))
