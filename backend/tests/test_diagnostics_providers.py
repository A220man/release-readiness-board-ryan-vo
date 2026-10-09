import json
import httpx
import pytest
from fastapi import HTTPException
from app.core.config import get_settings
from app.services.llm_service import LLMService
from app.services.evaluation import evaluate
from .test_api_sessions import client,login

def test_diagnostic_corpus():
    result=evaluate();assert result['passed']==result['total']==7

def test_advice_requires_consent(client):
    login(client,'reviewer');r=client.post('/api/releases/',json={'name':'Test','version':'1'}).json()
    assert client.post('/api/llm/analyze/'+r['id']).status_code==422
    response=client.post('/api/llm/analyze/'+r['id'],json={'consent':True});assert response.status_code==200
    assert response.json()['provider']==''

def test_invalid_target_date_rejected(client):
    login(client,'reviewer');assert client.post('/api/releases/',json={'name':'Test','version':'1','target_date':'not-a-date'}).status_code==422

@pytest.mark.asyncio
@pytest.mark.parametrize('provider',['openai-compatible','anthropic','gemini','ollama'])
async def test_provider_protocols(monkeypatch,provider):
    monkeypatch.setenv('LLM_PROVIDER',provider);monkeypatch.setenv('LLM_API_KEY','fixture-only');monkeypatch.setenv('LLM_BASE_URL','https://model.example/v1');get_settings.cache_clear()
    output=json.dumps({'analysis':'Review evidence','suggestions':['Inspect the missing criteria'],'confidence':'low'})
    def handler(req):
        assert len(req.content)<40000
        if provider=='anthropic':
            assert req.headers['x-api-key']=='fixture-only';return httpx.Response(200,json={'content':[{'type':'text','text':output}]})
        if provider=='gemini':
            assert req.headers['x-goog-api-key']=='fixture-only';assert 'key=' not in str(req.url);return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':output}]}}]})
        assert req.url.path.endswith('/chat/completions');return httpx.Response(200,json={'choices':[{'message':{'content':output}}]})
    result=await LLMService(httpx.MockTransport(handler)).analyze_release_risks({'name':'demo'})
    assert result['provider']==provider and result['confidence']=='low';get_settings.cache_clear()

@pytest.mark.asyncio
async def test_malformed_provider_output_is_safe(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER','openai-compatible');monkeypatch.setenv('LLM_API_KEY','fixture-only');get_settings.cache_clear()
    with pytest.raises(HTTPException) as exc:
        await LLMService(httpx.MockTransport(lambda req:httpx.Response(200,json={'choices':[]}))).analyze_release_risks({})
    assert exc.value.status_code==502;assert 'saved work is unchanged' in exc.value.detail;get_settings.cache_clear()

def test_release_status_cannot_bypass_transition_endpoint(client):
    login(client,'admin');r=client.post('/api/releases/',json={'name':'Test','version':'1'}).json()
    assert client.put('/api/releases/'+r['id'],json={'status':'released'}).status_code==422
    assert client.get('/api/releases/'+r['id']).json()['status']=='draft'

def test_risk_gate_does_not_claim_readiness_without_independent_approval(client):
    login(client,'admin');r=client.post('/api/releases/',json={'name':'Test','version':'1'}).json()
    result=client.get('/api/releases/'+r['id']+'/risk-assessment').json()
    assert result['ready_for_release'] is False
