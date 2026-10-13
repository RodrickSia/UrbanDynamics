"""Offline overlap-supported identity repair; never substitutes for count labels."""
import argparse
from collections import Counter
import csv
import hashlib
import itertools
import json
from pathlib import Path

from count_core import Line, aggregate


def iou(a, b):
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0]))*max(0, min(a[3], b[3])-max(a[1], b[1]))
    union = max(0, a[2]-a[0])*max(0, a[3]-a[1])+max(0, b[2]-b[0])*max(0, b[3]-b[1])-intersection
    return intersection/union if union else 0


def identities(records, threshold=.85, min_frames=3):
    if not .5 <= threshold <= 1 or min_frames < 1:
        raise ValueError("Require IoU threshold .5–1 and at least one supporting frame")
    support = Counter()
    parent = {t['id']: t['id'] for r in records for t in r['tracks']}
    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for r in records:
        for a,b in itertools.combinations(r['tracks'],2):
            if a['vehicle_class'] == b['vehicle_class'] and iou(a['box_xyxy'],b['box_xyxy']) >= threshold:
                support[tuple(sorted((a['id'],b['id'])))] += 1
    repaired = []
    for (a,b), frames in sorted(support.items()):
        if frames >= min_frames:
            x,y = root(a),root(b)
            parent[max(x,y)] = min(x,y)
            repaired.append({'raw_ids':[a,b], 'supporting_frames':frames})
    return {key:root(key) for key in parent}, repaired


def recount(records, summary, threshold=.85, min_frames=3):
    aliases, repairs = identities(records, threshold, min_frames)
    config = summary['config'];width=summary['video']['width'];height=summary['video']['height'];fps=summary['video']['fps']
    lines = [Line(x['name'],(x['start'][0]*width,x['start'][1]*height),(x['end'][0]*width,x['end'][1]*height),
        x.get('negative_to_positive','negative_to_positive'),x.get('positive_to_negative','positive_to_negative'),config.get('line_margin_pixels',3)) for x in config['lines']]
    max_gap=max(1,round(config.get('max_tracking_gap_seconds',1)*fps))
    events=[]
    for r in records:
        tracks={}
        for t in r['tracks']:
            identifier=aliases[t['id']]
            if identifier not in tracks or t['confidence']>tracks[identifier]['confidence']:
                tracks[identifier]=t
        for identifier,t in sorted(tracks.items()):
            for line in lines:
                event=line.update(identifier,t['center'],r['frame'],max_gap)
                if event:
                    event.update(video_seconds=event['frame']/fps,vehicle_class=t['vehicle_class'],
                                 raw_track_id=t['id'],identity_kind='overlap_supported_track_group')
                    events.append(event)
        for line in lines:
            line.prune(r['frame'],max_gap)
    bins=aggregate(events,summary['observation']['start_video_seconds'],summary['observation']['end_video_seconds'],config.get('bin_seconds',15))
    return events,bins,repairs


def write_csv(path, rows):
    with path.open('w',newline='',encoding='utf-8') as stream:
        columns=list(rows[0]) if rows else ['line_id','direction','vehicle_class','count']
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader();writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--iou',type=float,default=.85)
    parser.add_argument('--min-frames',type=int,default=3)
    args=parser.parse_args()
    source=args.input/'tracks.jsonl';raw=source.read_bytes();records=[json.loads(line) for line in raw.splitlines()]
    original=json.loads((args.input/'summary.json').read_text(encoding='utf-8'))
    events,bins,repairs=recount(records,original,args.iou,args.min_frames)
    args.output.mkdir(parents=True,exist_ok=False)
    write_csv(args.output/'events.csv',events);write_csv(args.output/'counts.csv',bins)
    report={'schema_version':'traffic-counts-identity-repair-1','camera_id':original['camera_id'],
        'source_sha256':original['source_sha256'],'tracks_sha256':hashlib.sha256(raw).hexdigest(),
        'observation':original['observation'],'config':original['config'],
        'raw_crossings':original['total_crossings'],'repaired_crossings':len(events),
        'identity_repairs':repairs,'iou_threshold':args.iou,'min_supporting_frames':args.min_frames,
        'counts':[{'vehicle_class':key,'count':value} for key,value in sorted(Counter(e['vehicle_class'] for e in events).items())],
        'simulation_ready':False,'validation':{'status':'requires_independent_counting_labels'},
        'limitations':['Repeated highly overlapping same-class boxes support ID merging but do not prove physical identity.',
            'Does not repair nonoverlapping ID fragmentation, missed detections or image motion.',
            'Original videos retain original overlays; this report is a separate offline correction.',
            'Short historical clip rates are not current road traffic or observed OD.']}
    (args.output/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    assert sum(b['count'] for b in bins)==len(events)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
