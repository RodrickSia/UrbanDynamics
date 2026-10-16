import json
import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.services import goong_places as g
from app.routers import places


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv('GOONG_REST_API_KEY','private-test-key')
    g.CACHE.clear()


def test_search_and_detail_hide_key_and_preserve_unknown_weather(monkeypatch):
    calls=[]
    class Response:
        status_code=200
        def __init__(self,value):self.value=value
        def json(self):return self.value
    def get(url,params,**kwargs):
        assert params['api_key']=='private-test-key'
        calls.append(url)
        if url.endswith('autocomplete'):
            return Response({'status':'OK','predictions':[{'place_id':'id-1','structured_formatting':{'main_text':'Test alley','secondary_text':'Go Vap'}}]})
        return Response({'status':'OK','result':{'name':'Test alley','geometry':{'location':{'lat':10.82,'lng':106.69}}}})
    monkeypatch.setattr(g.requests,'get',get)
    app=FastAPI();app.include_router(places.router)
    client=TestClient(app)
    search=client.get('/api/v1/places/search',params={'q':'Test alley'})
    detail=client.get('/api/v1/places/detail',params={'place_id':search.json()['results'][0]['id']})
    assert detail.status_code==200
    assert detail.json()['latitude']==10.82
    assert detail.json()['temperatureC'] is None
    assert 'private-test-key' not in search.text+detail.text
    g.search('Test alley')
    assert len(calls)==2


def test_provider_failure_does_not_echo_key_in_exception(monkeypatch):
    def get(*args,**kwargs):raise requests.Timeout('https://example/?api_key=private-test-key')
    monkeypatch.setattr(g.requests,'get',get)
    with pytest.raises(ValueError) as error:g.search('test area')
    assert 'private-test-key' not in str(error.value)


def test_invalid_coordinates_and_unknown_endpoint_rejected(monkeypatch):
    monkeypatch.setattr(g,'request',lambda *a:{'result':{'geometry':{'location':{'lat':float('nan'),'lng':106}}}})
    with pytest.raises(ValueError):g.detail('id')


def test_goong_agent_match_requires_choice_and_labels_point_buffer(monkeypatch):
    from app.services.agent import general_tools as agent
    monkeypatch.setattr(g,'search',lambda q:{'results':[{'id':'1','name':'A','context':'A address'},{'id':'2','name':'B','context':'B address'}]})
    monkeypatch.setattr(g,'detail',lambda i:{'longitude':106.69,'latitude':10.82,'name':'A','context':'A address'})
    session={'map_actions':[]}
    result=agent.choose_area(session,{'source':'goong_place','query':'test address','match_index':None})
    assert result['status']=='ambiguous_goong_place' and 'analysis_area' not in session
    result=agent.choose_area(session,{'source':'goong_place','query':'test address','match_index':0})
    assert '1000m buffer' in result['source']
    assert len(session['map_actions'])==1
