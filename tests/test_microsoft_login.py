import asyncio
import copy
import secrets
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from microsoft_login import MicrosoftLogin,challenge,COOKIE

class MemoryStore:
 def __init__(self):self.rows={}
 def put(self,kind,key,value,ttl):self.rows[kind,key]=copy.deepcopy(value)
 def take(self,kind,key):
  if (kind,key) not in self.rows:raise HTTPException(401,'expired')
  return self.rows.pop((kind,key))

class LoginTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.store=MemoryStore();self.owner='owner-id';self.user='owner-id';self.posts=[]
  async def graph(*a,**kw):return SimpleNamespace(json=lambda:{'id':self.owner})
  self.login=MicrosoftLogin(self.store,'client','secret','https://login.microsoftonline.com/common/oauth2/v2.0',lambda:'https://docs.example/auth/microsoft/callback',lambda:None,graph)
  self.verifier=secrets.token_urlsafe(48)
  response=await self.login.start(challenge(self.verifier),True)
  self.params=parse_qs(urlsplit(response.headers['location']).query);self.state=self.params['state'][0]
  outer=self
  class Client:
   def __init__(self,**kw):pass
   async def __aenter__(self):return self
   async def __aexit__(self,*a):pass
   async def post(self,url,**kw):outer.posts.append(kw['data']);return SimpleNamespace(is_success=True,json=lambda:{'access_token':'temporary-graph-token','refresh_token':'must-not-save'})
   async def get(self,url,**kw):return SimpleNamespace(is_success=True,json=lambda:{'id':outer.user,'displayName':'Owner'})
  self.client=Client
 def request(self,cookie=None):return SimpleNamespace(cookies={COOKIE:cookie or self.state})
 async def complete(self):
  with patch('microsoft_login.httpx.AsyncClient',self.client):return await self.login.callback(self.request(),'auth-code',self.state,'')
 async def test_owner_signin_and_single_use_browser_bound_ticket(self):
  self.assertEqual(self.params['code_challenge_method'],['S256']);self.assertEqual(self.params['scope'],['User.Read'])
  result=await self.complete();self.assertIn('#edu-ms-ticket=',result.headers['location'])
  ticket=parse_qs(urlsplit(result.headers['location']).fragment)['edu-ms-ticket'][0]
  verified=self.login.exchange(ticket,self.verifier);self.assertTrue(verified['authenticated']);self.assertTrue(verified['remember'])
  self.assertEqual(verified['accountId'],'owner-id');self.assertIn('code_verifier',self.posts[0]);self.assertNotIn('access_token',verified)
  with self.assertRaises(HTTPException):self.login.exchange(ticket,self.verifier)
  with self.assertRaises(HTTPException):await self.complete()
 async def test_different_microsoft_account_rejected(self):
  self.user='attacker'
  with self.assertRaises(HTTPException) as error:await self.complete()
  self.assertEqual(error.exception.status_code,403);self.assertFalse(any(k[0]=='ticket' for k in self.store.rows))
 async def test_missing_or_wrong_browser_cookie_rejected(self):
  for request in [SimpleNamespace(cookies={}),self.request('wrong')]:
   with self.assertRaises(HTTPException) as error:await self.login.callback(request,'code',self.state,'')
   self.assertEqual(error.exception.status_code,401)
 async def test_ticket_proof_mismatch_rejected(self):
  response=await self.complete();ticket=parse_qs(urlsplit(response.headers['location']).fragment)['edu-ms-ticket'][0]
  with self.assertRaises(HTTPException):self.login.exchange(ticket,secrets.token_urlsafe(48))
 async def test_cancelled_signin_creates_no_ticket(self):
  with self.assertRaises(HTTPException):await self.login.callback(self.request(),'',self.state,'access_denied')
  self.assertFalse(any(k[0]=='ticket' for k in self.store.rows))
 async def test_owner_changed_during_signin_rejected(self):
  self.owner='new-owner'
  with self.assertRaises(HTTPException) as error:await self.complete()
  self.assertEqual(error.exception.status_code,409)
if __name__=='__main__':unittest.main()
