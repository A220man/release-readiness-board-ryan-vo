import pytest
from fastapi.testclient import TestClient
from app.core.config import get_settings
from app.main import create_app

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+str(tmp_path/'api.db'))
    monkeypatch.setenv('DEMO_MODE','true');monkeypatch.setenv('APP_ENV','test');monkeypatch.setenv('COOKIE_SECURE','false')
    get_settings.cache_clear()
    with TestClient(create_app()) as c:yield c
    get_settings.cache_clear()

def login(client,who):
    user=client.post('/api/auth/demo?identity='+who).json();client.headers['X-CSRF-Token']=user['csrf_token'];return user

def test_missing_session_and_forged_demo_role(client):
    assert client.get('/api/releases/?demo_role=admin').status_code==401

def test_csrf_enforced_and_logout_revokes(client):
    login(client,'reviewer');token=client.headers.pop('X-CSRF-Token')
    assert client.post('/api/releases/',json={'name':'App','version':'1.0'}).status_code==403
    client.headers['X-CSRF-Token']=token
    assert client.post('/api/releases/',json={'name':'App','version':'1.0'}).status_code==201
    assert client.post('/api/auth/logout').status_code==204
    assert client.get('/api/releases/').status_code==401

def test_full_release_api_lifecycle(client):
    login(client,'analyst')
    r=client.post('/api/releases/',json={'name':'API Release','version':'1.0.0'});assert r.status_code==201,r.text
    rid=r.json()['id']
    criterion=client.post('/api/criteria/',json={'release_id':rid,'name':'Security regression','category':'security'});assert criterion.status_code==201,criterion.text
    cid=criterion.json()['id']
    assert client.put('/api/criteria/'+cid,json={'evidence':'Security regression job 23 passed'}).status_code==200
    assert client.post('/api/criteria/'+cid+'/review',json={'status':'passed'}).status_code==200
    assert client.post('/api/releases/'+rid+'/transition',json={'status':'in_review'}).status_code==200
    login(client,'reviewer')
    response=client.post('/api/approvals/',json={'release_id':rid,'decision':'approved','comment':'Independently inspected evidence'});assert response.status_code==201,response.text
    login(client,'admin')
    response=client.post('/api/releases/'+rid+'/transition',json={'status':'approved'});assert response.status_code==200,response.text
    assert client.post('/api/releases/'+rid+'/transition',json={'status':'released'}).status_code==200
    for fmt in ['json','markdown','csv']:assert client.get('/api/releases/'+rid+'/export/'+fmt).status_code==200
    assert client.put('/api/releases/'+rid,json={'name':'Altered after release'}).status_code!=200
