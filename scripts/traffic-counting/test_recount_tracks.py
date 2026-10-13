import pytest
from recount_tracks import identities, iou, recount


def track(identifier,box,kind='car'):
    return {'id':identifier,'box_xyxy':box,'vehicle_class':kind,'confidence':.9,
            'center':[(box[0]+box[2])/2,(box[1]+box[3])/2]}


def test_only_repeated_strong_same_class_overlap_merges():
    records=[{'frame':i,'tracks':[track(8,[0,0,20,20]),track(11,[.1,0,20.1,20]),
        track(12,[30,0,50,20]),track(13,[0,0,20,20],'motorcycle')]} for i in range(3)]
    aliases,repair=identities(records)
    assert aliases[8]==aliases[11]==8
    assert aliases[12]==12 and aliases[13]==13
    assert repair==[{'raw_ids':[8,11],'supporting_frames':3}]
    assert not identities(records[:2])[1]
    assert iou([0,0,1,1],[2,2,3,3])==0


def test_repaired_track_counts_once_but_adjacent_vehicles_remain():
    records=[{'frame':i,'tracks':[track(8,[0,y,10,y+4]),track(11,[.01,y,10.01,y+4]),track(12,[20,y,30,y+4])]} for i,y in enumerate((0,2,12,14))]
    summary={'video':{'width':100,'height':100,'fps':2},'observation':{'start_video_seconds':0,'end_video_seconds':2},
        'config':{'lines':[{'name':'g','start':[0,.1],'end':[1,.1]}],'line_margin_pixels':1}}
    events,bins,repairs=recount(records,summary)
    assert len(events)==2 and {e['track_id'] for e in events}=={8,12}
    assert sum(x['count'] for x in bins)==2
    assert repairs[0]['supporting_frames']==4
    with pytest.raises(ValueError):
        identities(records,threshold=.1)
