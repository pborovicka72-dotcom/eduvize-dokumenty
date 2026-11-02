"""Microsoft sign-in for the existing OneDrive owner; never replaces drive tokens."""
import base64
import hashlib
import json
import re
import secrets
import time
from urllib.parse import urlencode
import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

ACCOUNT='https://pborovicka72-dotcom.github.io/eduvize-styly/ucet.html'
COOKIE='__Host-eduvize-ms-login'
SCOPES='User.Read'

def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def challenge(value):return base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest()).decode().rstrip('=')

class LoginStore:
    def __init__(self,connect):self.connect=connect
    def put(self,kind,key,value,ttl):
        with self.connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS eduvize_ms_login_v1 (kind TEXT NOT NULL, key_hash TEXT PRIMARY KEY, value JSONB NOT NULL, expires DOUBLE PRECISION NOT NULL)')
            conn.execute('DELETE FROM eduvize_ms_login_v1 WHERE expires<=%s',(time.time(),))
            conn.execute('INSERT INTO eduvize_ms_login_v1 VALUES (%s,%s,%s::jsonb,%s)',(kind,digest(key),json.dumps(value),time.time()+ttl))
    def take(self,kind,key):
        with self.connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS eduvize_ms_login_v1 (kind TEXT NOT NULL, key_hash TEXT PRIMARY KEY, value JSONB NOT NULL, expires DOUBLE PRECISION NOT NULL)')
            row=conn.execute('DELETE FROM eduvize_ms_login_v1 WHERE kind=%s AND key_hash=%s AND expires>%s RETURNING value',(kind,digest(key),time.time())).fetchone()
        if not row:raise HTTPException(401,'Přihlášení vypršelo nebo již bylo použito. Zkuste to znovu.')
        return row[0]

class MicrosoftLogin:
    def __init__(self,store,client_id,client_secret,authority,redirect_uri,require_config,graph):
        self.store,self.client_id,self.client_secret,self.authority,self.redirect_uri,self.require_config,self.graph=store,client_id,client_secret,authority,redirect_uri,require_config,graph
    async def start(self,proof,remember):
        self.require_config()
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}',proof):raise HTTPException(422,'Neplatné zahájení přihlášení.')
        # A fresh server-to-server Graph read pins the identity before starting OAuth.
        owner=(await self.graph('GET','/me',params={'$select':'id'})).json().get('id')
        if not owner:raise HTTPException(503,'Nejprve připojte OneDrive správy Eduvize.')
        state=secrets.token_urlsafe(32);pkce=secrets.token_urlsafe(48)
        self.store.put('state',state,{'proof':proof,'remember':remember,'pkce':pkce,'owner':owner},600)
        params={'client_id':self.client_id,'response_type':'code','redirect_uri':self.redirect_uri(),'response_mode':'query','scope':SCOPES,'state':state,'code_challenge':challenge(pkce),'code_challenge_method':'S256','prompt':'select_account'}
        response=RedirectResponse(self.authority+'/authorize?'+urlencode(params),status_code=303)
        response.set_cookie(COOKIE,state,max_age=600,secure=True,httponly=True,samesite='lax',path='/')
        response.headers['Cache-Control']='no-store';response.headers['Referrer-Policy']='no-referrer'
        return response
    async def callback(self,request,code,state,error):
        cookie=request.cookies.get(COOKIE,'')
        if not cookie or not state or not secrets.compare_digest(cookie,state):raise HTTPException(401,'Přihlášení nebylo zahájeno v tomto prohlížeči.')
        pending=self.store.take('state',state)
        if error or not code:raise HTTPException(400,'Přihlášení Microsoftem bylo zrušeno. Vraťte se do účtu Eduvize.')
        async with httpx.AsyncClient(timeout=30,follow_redirects=False) as client:
            r=await client.post(self.authority+'/token',data={'client_id':self.client_id,'client_secret':self.client_secret,'code':code,'redirect_uri':self.redirect_uri(),'grant_type':'authorization_code','scope':SCOPES,'code_verifier':pending['pkce']})
            if not r.is_success:raise HTTPException(401,'Microsoft přihlášení se nepodařilo ověřit. Zkuste to znovu.')
            access=r.json().get('access_token')
            if not access:raise HTTPException(401,'Microsoft nevrátil ověřovací token.')
            me=await client.get('https://graph.microsoft.com/v1.0/me',params={'$select':'id,displayName'},headers={'Authorization':'Bearer '+access})
            if not me.is_success:raise HTTPException(401,'Identitu Microsoft účtu se nepodařilo ověřit.')
            user=me.json()
        # Match immutable Microsoft identity, never a user-supplied email/name.
        if not isinstance(user.get('id'),str) or not secrets.compare_digest(user['id'],pending['owner']):raise HTTPException(403,'Tento Microsoft účet není vlastníkem připojeného OneDrivu Eduvize.')
        current=(await self.graph('GET','/me',params={'$select':'id'})).json().get('id')
        if current!=pending['owner']:raise HTTPException(409,'Připojený účet se mezitím změnil. Přihlášení zopakujte.')
        ticket=secrets.token_urlsafe(32)
        self.store.put('ticket',ticket,{'proof':pending['proof'],'remember':pending['remember'],'accountId':user['id']},120)
        response=RedirectResponse(ACCOUNT+'?edu-login-return='+secrets.token_urlsafe(12)+'#'+urlencode({'edu-ms-ticket':ticket}),status_code=303)
        response.delete_cookie(COOKIE,path='/',secure=True,httponly=True,samesite='lax')
        response.headers['Cache-Control']='no-store';response.headers['Referrer-Policy']='no-referrer'
        return response
    def exchange(self,ticket,verifier):
        if not isinstance(ticket,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',ticket) or not isinstance(verifier,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43,128}',verifier):raise HTTPException(401,'Neplatné předání přihlášení.')
        data=self.store.take('ticket',ticket)
        if not secrets.compare_digest(challenge(verifier),data['proof']):raise HTTPException(401,'Přihlášení patří jinému prohlížeči. Zkuste to znovu.')
        return {'authenticated':True,'accountId':data['accountId'],'remember':data['remember']}

def login_router(login):
    router=APIRouter()
    @router.get('/auth/microsoft/login')
    async def start(proof:str='',remember:bool=False):return await login.start(proof,remember)
    @router.post('/auth/microsoft/login/exchange')
    async def exchange(request:Request,response:Response):
        response.headers['Cache-Control']='no-store'
        body=await request.json();return login.exchange(body.get('ticket'),body.get('verifier'))
    return router
