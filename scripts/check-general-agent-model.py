"""Natural-language area -> search -> weighted comparison -> equal-program school run."""
import json
import time
from pathlib import Path
from uuid import uuid4
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'test-results'/'general-agent'
BASE='http://127.0.0.1:8192'

def main():
    evidence=json.loads((OUT/'live-result.json').read_text(encoding='utf-8'))
    session=requests.post(BASE+'/api/v1/agent/sessions',json={},timeout=30).json()
    records=[]
    def chat(message):
        start=time.monotonic()
        r=requests.post(BASE+'/api/v1/agent/chat',json={'session_id':session['session_id'],
            'request_id':str(uuid4()),'workspace':{'viewport':evidence['viewport']},'message':message,'allow_native':False},timeout=240)
        value=r.json()
        records.append({'elapsed_seconds':round(time.monotonic()-start,2),'response':value})
        (OUT/'model-workflow.json').write_text(json.dumps({'session_id':session['session_id'],'turns':records},ensure_ascii=False,indent=2),encoding='utf-8')
        assert r.ok,(r.status_code,value)
        return value
    first=chat('Không mở plan. Hãy chọn vùng map đang nhìn, phân tích dân số năm 2026 và dữ liệu nền, tìm 3 thửa diện tích 2.000–100.000 m². So sánh cả 3 theo diện tích lớn hơn, mật độ dân số cao hơn (chỉ là proxy nhu cầu), và khoảng cách đường nhỏ hơn; trọng số mỗi tiêu chí là 1. Ghi rõ tiêu chí thiếu và không coi đất là trống. Thực hiện bằng công cụ rồi tóm tắt ngắn.')
    successful={t['tool'] for t in first['trace'] if t['status']=='succeeded'}
    assert {'area_select','area_analyze','candidate_search','candidate_compare'}<=successful,first['trace']
    second=chat('Dùng hai ứng viên đầu trong danh sách tìm kiếm vừa rồi. Chuẩn bị và chạy quick estimate cho cùng trường học 100 chỗ, 3 tầng, tổng sàn 600 m², 10 nhân viên, 100 người sử dụng mỗi ngày, cao mỗi tầng 3,2 m, khoảng lùi giả định 1 m, mưa 60 mm. Giữ đúng chương trình ở cả hai đất, không mở plan, chưa cần native. Nếu fit test không đạt thì nói rõ, không giảm quy mô. Trả lời ngắn trạng thái job.')
    successful={t['tool'] for t in second['trace'] if t['status']=='succeeded'}
    assert {'candidate_study_prepare','candidate_study_start'}<=successful,second['trace']
    expected=first['last_search_ids'][:2]
    actual=list(second['development_runs'].values())[-1]['parcel_ids']
    assert actual==expected,{'expected':expected,'actual':actual}
    print(json.dumps({'passed':True,'session_id':session['session_id'],'turns':[{'elapsed_seconds':x['elapsed_seconds'],'trace':x['response']['trace']} for x in records]}))

if __name__=='__main__':main()
