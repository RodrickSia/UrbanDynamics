"""Replay source frames with repaired track boxes and exact crossing-event counters.

Run on server 152 after run_counting.py. This is an offline visual review;
future overlap support can merge duplicate track IDs. It does not certify accuracy.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess

from recount_tracks import identities, recount, write_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import cv2
    cv2.setNumThreads(2)
    original = json.loads((args.input/'summary.json').read_text(encoding='utf-8'))
    raw_tracks = (args.input/'tracks.jsonl').read_bytes()
    records = [json.loads(line) for line in raw_tracks.splitlines()]
    events, bins, repairs = recount(records, original)
    aliases, _ = identities(records)
    events = sorted(events, key=lambda e:(e['frame'], e['track_id'], e['direction']))
    config = original['config']
    source = Path(original['source_video'])
    sha = hashlib.sha256()
    with source.open('rb') as stream:
        while chunk := stream.read(1024*1024):
            sha.update(chunk)
    if sha.hexdigest() != original['source_sha256']:
        raise ValueError('Source video hash differs from inference input')
    width, height, fps = [original['video'][key] for key in ('width','height','fps')]
    stride = original['observation']['frame_stride']
    if len(records) != original['observation']['processed_frames']:
        raise ValueError('Incomplete tracks observation window')
    if any(b['frame']-a['frame'] != stride for a,b in zip(records, records[1:])):
        raise ValueError('Track frames are not consecutive at the declared stride')
    args.output.mkdir(parents=True, exist_ok=False)
    capture = cv2.VideoCapture(str(source))
    capture.set(cv2.CAP_PROP_POS_FRAMES, records[0]['frame'])
    temporary = args.output/'annotated-mp4v.mp4'
    writer = cv2.VideoWriter(str(temporary), cv2.VideoWriter_fourcc(*'mp4v'), fps/stride, (width,height))
    if not capture.isOpened() or not writer.isOpened():
        raise RuntimeError('Video input or output could not be opened')
    colors = {'motorcycle':(70,230,70), 'car':(255,160,60), 'van':(255,160,60),
              'bus':(210,80,240), 'truck':(40,170,255)}
    counts = Counter()
    cursor = 0
    try:
        for index, record in enumerate(records):
            if index:
                for _ in range(stride-1):
                    capture.grab()
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError('Source ended before the inference window')
            while cursor < len(events) and events[cursor]['frame'] <= record['frame']:
                event = events[cursor]
                counts[event['direction'], event['vehicle_class']] += 1
                cursor += 1
            current = {}
            for track in record['tracks']:
                identifier = aliases[track['id']]
                if identifier not in current or track['confidence'] > current[identifier]['confidence']:
                    current[identifier] = track
            for identifier, track in sorted(current.items()):
                x1,y1,x2,y2 = [round(v) for v in track['box_xyxy']]
                color = colors.get(track['vehicle_class'], (200,200,200))
                cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)
                cv2.circle(frame,tuple(round(v) for v in track['center']),2,color,-1)
                label = f"ID {identifier} {track['vehicle_class']} {track['confidence']:.2f}"
                cv2.putText(frame,label,(x1,max(15,y1-5)),cv2.FONT_HERSHEY_SIMPLEX,.45,color,1,cv2.LINE_AA)
            for line in config['lines']:
                a,b = [tuple(round(v*d) for v,d in zip(line[key],(width,height))) for key in ('start','end')]
                cv2.line(frame,a,b,(0,230,255),3)
                cv2.putText(frame,line['name'],(a[0]+5,max(20,a[1]-10)),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,230,255),2)
            for event in events[max(0,cursor-10):cursor]:
                if record['frame']-event['frame'] <= fps*.5:
                    point = tuple(round(v) for v in event['crossing_xy'])
                    cv2.circle(frame,point,18,(0,0,255),3)
            hud_x = max(0,width-610)
            rows = [f"{direction} | {kind}: {number}" for (direction,kind),number in sorted(counts.items())]
            cv2.rectangle(frame,(hud_x,0),(width,115+len(rows)*25),(20,20,20),-1)
            hud = [f"t={record['frame']/fps:.2f}s   frame={record['frame']}",
                   f"TOTAL LINE CROSSINGS: {cursor}", 'Boxes = tracked vehicles; red circle = crossing']+rows
            for row,text in enumerate(hud):
                cv2.putText(frame,text,(hud_x+12,28+row*25),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1,cv2.LINE_AA)
            writer.write(frame)
            if index in (0,len(records)//2,len(records)-1):
                cv2.imwrite(str(args.output/f'preview-{index:04d}.jpg'),frame)
    finally:
        capture.release()
        writer.release()
    assert cursor == len(events) == sum(counts.values()) == sum(row['count'] for row in bins)
    final = args.output/'counting-bounding-boxes.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(temporary),'-c:v','libx264',
                    '-preset','fast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',str(final)],check=True)
    verify = cv2.VideoCapture(str(final))
    decoded = 0
    while verify.read()[0]:
        decoded += 1
    verify.release()
    assert decoded == len(records), 'Encoded video does not contain every reviewed frame'
    write_csv(args.output/'events.csv',events)
    write_csv(args.output/'counts.csv',bins)
    report = {'camera_id':original['camera_id'],'source_video_sha256':sha.hexdigest(),
        'tracks_sha256':hashlib.sha256(raw_tracks).hexdigest(),'frames':decoded,
        'duration_seconds':decoded/(fps/stride),'total_crossings':cursor,
        'counts':[{'direction':direction,'vehicle_class':kind,'count':number}
                  for (direction,kind),number in sorted(counts.items())],
        'raw_crossings':original['total_crossings'],'identity_repairs':repairs,
        'render_method':'offline_repaired_tracks_and_interpolated_crossing_events',
        'counting_accuracy_measured':False,'video':final.name,
        'output_video_sha256':hashlib.sha256(final.read_bytes()).hexdigest()}
    (args.output/'review-summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)


if __name__ == '__main__':
    main()
