import math
import pytest
from shapely.geometry import Point,mapping
from app.services.agent.scope import metric_area,decorate
from app.services.agent import general_tools as g
from app.services.agent.development_tools import bind_workspace
from app.services.agent.search_scope import check


def test_complex_analysis_boundary_is_not_limited_like_a_building_footprint():
    polygon=Point(106.7,10.8).buffer(.005,quad_segs=800)
    assert len(polygon.exterior.coords)>2000
    assert 0<metric_area(polygon)<2000000
    value=decorate({'title':'Source district polygon','geometry':mapping(polygon),'scope_kind':'provider_administrative_polygon'})
    assert value['scope_summary']['administrative_boundary']


def test_search_place_is_bound_to_actual_web_selection_and_explicit_reference():
    session={'map_actions':[]}
    bind_workspace(session,{'selected_place':{'id':'goong-id','name':'Chosen place','context':'Source address',
        'longitude':106.69,'latitude':10.82,'arbitrary_instruction':'must be discarded'}})
    assert 'arbitrary_instruction' not in session['workspace']['selected_place']
    check('area_select',{'source':'search_place'},'Analyze the selected place',session,False)
    value=g.choose_area(session,{'source':'search_place'})
    assert value['scope_summary']['kind']=='selected_place_buffer'
    assert value['scope_summary']['radius_m']==1000
    assert not value['scope_summary']['administrative_boundary']
    with pytest.raises(ValueError):check('area_select',{'source':'search_place'},'find somewhere near parks',session,False)


def test_invalid_selected_coordinates_are_rejected():
    with pytest.raises(ValueError):bind_workspace({}, {'selected_place':{'latitude':math.nan,'longitude':106.7}})


def test_response_language_follows_prompt_not_vietnamese_place_names():
    from app.services.agent.language import hint
    assert hint('Within the visible map, find parcels near Hẻm 114 Trần Quốc Tuấn and show the source price.')=='English'
    assert hint('Tiếp tục trong vùng này, bỏ giá và hiển thị 2 thửa đất.')=='Vietnamese'
    assert hint('Tìm đất rồi reply in English please')=='English'


@pytest.mark.parametrize('message',['yes','Yes.','no','sure','continue','go ahead','thanks','why?'])
def test_short_english_replies_are_english(message):
    from app.services.agent.language import resolve
    assert resolve(message,[{'role':'assistant','content':'Bạn muốn tìm ở đâu?'}])=='English'


@pytest.mark.parametrize('message',['ok','OK.','2','👍'])
def test_neutral_replies_keep_user_language_despite_wrong_assistant_answer(message):
    from app.services.agent.language import resolve
    history=[{'role':'user','content':'Find 3 sites between 2,000 and 10,000 m² in the visible area. Explain what is still unknown.'},
             {'role':'assistant','content':'Bạn muốn tìm ở đâu?'}]
    assert resolve(message,history)=='English'
    assert resolve(message,[{'role':'user','content':'Tìm những khu đất trong vùng này.'}])=='Vietnamese'


def test_explicit_language_switch_overrides_history():
    from app.services.agent.language import resolve
    history=[{'role':'user','content':'Tìm đất trong vùng này.'}]
    assert resolve('Please respond in English',history)=='English'
    assert resolve('Tiếp tục trong vùng này',[])=='Vietnamese'
    assert resolve('ok',[]) is None


def test_yes_turn_supplies_english_instruction_to_model(tmp_path,monkeypatch):
    from app.services.agent import service,store
    from app.services.agent.models import ChatRequest
    from uuid import uuid4
    monkeypatch.setenv('AGENT_SQLITE_PATH',str(tmp_path/'agent.sqlite'))
    monkeypatch.setattr(service,'configured',lambda:True)
    monkeypatch.setattr(service,'context',lambda *args:{})
    session=store.create()
    session['messages']=[{'role':'user','content':'Find 3 sites in the visible area. Explain what is unknown.'},
                         {'role':'assistant','content':'Please confirm the visible map.'}]
    store.save(session)
    calls=[]
    def model(inputs):
        calls.append(inputs)
        return {'output':[{'type':'message','content':[{'type':'output_text','text':'I will use the visible map.'}]}]}
    monkeypatch.setattr(service,'model_response',model)
    service.chat(ChatRequest(session_id=session['id'],request_id=uuid4(),message='yes'))
    assert any(item.get('role')=='developer' and 'final answer in English' in item.get('content','') for item in calls[0])
