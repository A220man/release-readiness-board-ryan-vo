import json,time
from urllib.parse import urlparse,parse_qs
import httpx,jwt,pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from app.core.session_auth import OIDCClient
from app.core.session_config import Settings
from app.core.errors import AppError
from app.core.config import get_settings
from app.main import create_app

@pytest.fixture
def identity():
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()));jwk.update(kid='fixture',use='sig',alg='RS256')
    issuer='https://id.example/realms/releases';claims={'sub':'external-reviewer','iss':issuer,'aud':'release-board','iat':int(time.time()),'exp':int(time.time())+300,'nonce':'expected','realm_access':{'roles':['reviewer']}}
    calls=[]
    def handler(request):
        calls.append(request)
        if request.url.path.endswith('openid-configuration'):return httpx.Response(200,json={'issuer':issuer,'authorization_endpoint':issuer+'/authorize','token_endpoint':issuer+'/token','jwks_uri':issuer+'/keys'})
        if request.url.path.endswith('/keys'):return httpx.Response(200,json={'keys':[jwk]})
        if request.url.path.endswith('/token'):return httpx.Response(200,json={'id_token':jwt.encode(claims,key,algorithm='RS256',headers={'kid':'fixture'})})
        return httpx.Response(404)
    return issuer,claims,httpx.MockTransport(handler),calls

@pytest.mark.parametrize('field,value',[('aud','wrong'),('iss','https://wrong.example'),('exp',1),('nonce','wrong'),('iat',9999999999)])
def test_signed_claim_mismatch_rejected(identity,field,value):
    issuer,claims,transport,calls=identity;claims[field]=value
    settings=Settings(environment='test',oidc_client_id='release-board',oidc_discovery_url=issuer+'/.well-known/openid-configuration')
    with pytest.raises(AppError):OIDCClient(settings,transport).exchange('code','expected','verifier')

def test_code_exchange_session_and_state_replay(identity,tmp_path,monkeypatch):
    issuer,claims,transport,calls=identity
    for k,v in {'DATABASE_URL':'sqlite:///'+str(tmp_path/'oidc.db'),'DEMO_MODE':'false','APP_ENV':'test','COOKIE_SECURE':'false','OIDC_ISSUER_URL':issuer,'OIDC_CLIENT_ID':'release-board'}.items():monkeypatch.setenv(k,v)
    get_settings.cache_clear();app=create_app();app.state.oidc=OIDCClient(app.state.settings,transport)
    with TestClient(app) as client:
        redirect=client.get('/api/auth/login',follow_redirects=False);assert redirect.status_code in [302,307]
        params=parse_qs(urlparse(redirect.headers['location']).query);assert params['code_challenge_method']==['S256'];claims['nonce']=params['nonce'][0]
        callback='/api/auth/callback?state='+params['state'][0]+'&code=fixture-code'
        assert client.get(callback,follow_redirects=False).status_code in [302,303,307]
        me=client.get('/api/auth/me').json();assert me['subject']=='external-reviewer'
        assert client.get('/api/releases/').status_code==200
        assert b'code_verifier=' in next(r for r in calls if r.method=='POST').content
        assert client.get(callback,follow_redirects=False).status_code==401
    get_settings.cache_clear()
