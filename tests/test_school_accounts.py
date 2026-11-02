"""Isolation tests: independent identities, profile authorization, drive tokens and public outputs."""
import asyncio
import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch,AsyncMock
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from school_accounts import SchoolAccounts,SchoolProfileStore,school_context,storage_key,LEGACY_PROFILE
from configuration_profiles import profile_router
import app as documents

class Connection:
 def __init__(self,path):self.conn=sqlite3.connect(path,timeout=10)
 def execute(self,sql,args=()):
  if sql.startswith('SELECT pg_advisory'):return self.conn.execute('SELECT 1')
  return self.conn.execute(sql.replace('%s','?'),args)
 def __enter__(self):return self
 def __exit__(self,typ,*args):
  if typ:self.conn.rollback()
  else:self.conn.commit()
  self.conn.close()

class RegistryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.registry=SchoolAccounts(lambda:Connection(str(Path(self.temp.name)/'schools.db')))
 def tearDown(self):self.temp.cleanup()
 def test_provider_identity_is_stable_and_independent_of_storage(self):
  first=self.registry.resolve('microsoft','school-one');second=self.registry.resolve('microsoft','school-two')
  self.assertEqual(self.registry.resolve('microsoft','school-one'),first)
  self.assertNotEqual(first['id'],second['id']);self.assertNotEqual(first['profileId'],second['profileId'])
  self.assertEqual(self.registry.identity(first['id'],'microsoft'),'school-one')
  self.assertNotEqual(self.registry.resolve('google','school-one')['id'],first['id'])
 def test_legacy_owner_preserves_existing_profile_and_original_drive_key(self):
  self.assertEqual(self.registry.remember_legacy_subject('owner'),'owner')
  self.assertEqual(self.registry.remember_legacy_subject('different'),'owner')
  original=self.registry.resolve('microsoft','owner',legacy=True)
  self.assertEqual(original['profileId'],LEGACY_PROFILE);self.assertEqual(storage_key(original),'microsoft')
  new=self.registry.resolve('microsoft','new');self.assertNotEqual(storage_key(new),'microsoft')
  self.assertEqual(self.registry.public_profile(original['profileId'])['id'],original['id'])
 def test_unknown_school_or_profile_never_falls_back_to_legacy(self):
  with self.assertRaises(HTTPException):self.registry.get('a'*32)
  with self.assertRaises(HTTPException):self.registry.public_profile('a'*32)
  with self.assertRaises(HTTPException):self.registry.public_profile('../legacy')

@asynccontextmanager
async def lock(key):yield

class MemoryProfiles:
 def __init__(self):self.data={}
 async def read(self,pid):
  key=(school_context.get()['id'],pid)
  if key not in self.data:raise HTTPException(404,'not found')
  return copy.deepcopy(self.data[key])
 async def folder(self,*args):return 'folder'
 async def put(self,folder,filename,value):self.data[(school_context.get()['id'],value['id'])]=copy.deepcopy(value)
 async def save_app(self,pid,app,value,expected):
  profile=await self.read(pid);profile['apps'][app]={'config':value,'revision':expected+1,'updatedAt':'now'}
  self.data[(school_context.get()['id'],pid)]=profile
  return profile['apps'][app]
 async def history(self,pid):await self.read(pid);return []

class ProfileIsolationTests(unittest.TestCase):
 def setUp(self):
  self.schools={'one':{'id':'a'*32,'profileId':'b'*32,'name':'Škola A'},'two':{'id':'c'*32,'profileId':'d'*32,'name':'Škola B'}}
  self.backend=MemoryProfiles();self.store=SchoolProfileStore(self.backend,lock)
  api=FastAPI()
  @api.middleware('http')
  async def reset(request,call_next):
   token=school_context.set(None)
   try:return await call_next(request)
   finally:school_context.reset(token)
  async def authorize(value):
   school=self.schools.get(value)
   if not school:raise HTTPException(401,'not signed in')
   school_context.set(school)
  api.include_router(profile_router(self.store,authorize));self.client=TestClient(api)
 def test_one_profile_is_created_once_and_other_school_is_inaccessible(self):
  api='/api/admin/configuration-profiles'
  for auth,pid in [('one','b'*32),('two','d'*32)]:
   for _ in range(2):
    response=self.client.get(api,headers={'Authorization':auth})
    self.assertEqual(response.status_code,200);self.assertEqual([x['id'] for x in response.json()['items']],[pid])
   self.assertEqual(self.client.post(api,json={'name':'Second profile'},headers={'Authorization':auth}).status_code,409)
  own='/'+('b'*32);other='/'+('d'*32)
  for path in [other,other+'/history',other+'/generated-links']:
   self.assertEqual(self.client.get(api+path,headers={'Authorization':'one'}).status_code,404)
  self.assertEqual(self.client.put(api+other+'/apps/weather',json={'expectedRevision':0,'config':{}},headers={'Authorization':'one'}).status_code,404)
  self.assertEqual(self.client.get(api+own,headers={'Authorization':'one'}).json()['name'],'Škola A')
  self.assertEqual(len(self.backend.data),2)
 def test_unauthenticated_access_is_denied(self):
  self.assertEqual(self.client.get('/api/admin/configuration-profiles').status_code,401)

class RuntimeIsolationTests(unittest.IsolatedAsyncioTestCase):
 async def test_school_login_and_new_school_refresh_use_common_authority(self):
  self.assertEqual(documents.microsoft_login.authority,'https://login.microsoftonline.com/common/oauth2/v2.0')
  reset=school_context.set(None)
  try:
   with patch.object(documents,'AUTH','https://login.microsoftonline.com/original-tenant/oauth2/v2.0'):
    self.assertIn('original-tenant',documents.token_authority())
    school_context.set({'id':'a'*32,'legacy':False})
    self.assertIn('/common/',documents.token_authority())
    school_context.set({'id':'b'*32,'legacy':True})
    self.assertIn('original-tenant',documents.token_authority())
  finally:school_context.reset(reset)
 async def test_parallel_requests_never_share_oauth_tokens(self):
  async def request(school_id):
   token=school_context.set({'id':school_id,'legacy':False})
   try:
    first=documents.current_tokens();await asyncio.sleep(0)
    return first['access_token'],documents.current_tokens()['access_token']
   finally:school_context.reset(token)
  with patch.object(documents,'load_tokens',side_effect=lambda key:{'access_token':key}):
   results=await asyncio.gather(request('a'*32),request('b'*32))
  self.assertEqual(results[0][0],results[0][1]);self.assertEqual(results[1][0],results[1][1]);self.assertNotEqual(results[0][0],results[1][0])
 async def test_document_caches_are_per_school_and_legacy_is_preserved(self):
  reset=school_context.set(None)
  try:
   legacy=documents.current_delivery()
   school_context.set({'id':'a'*32,'legacy':False});one=documents.current_delivery()
   school_context.set({'id':'b'*32,'legacy':False});two=documents.current_delivery()
   self.assertIsNot(one,two);self.assertIsNot(one,legacy)
   school_context.set({'id':'a'*32,'legacy':True});self.assertIs(documents.current_delivery(),legacy)
  finally:school_context.reset(reset)

class SharedCacheTests(unittest.IsolatedAsyncioTestCase):
 async def test_identical_remote_file_ids_in_different_drives_do_not_share_bytes(self):
  from document_delivery import DocumentDelivery,AsyncCache
  cache=AsyncCache(60,100,weight=lambda asset:len(asset.data))
  async def manifest():return {'items':[{'id':'document','file_id':'same-remote-id','visible':True}]}
  async def one(item):return b'school-one'
  async def two(item):return b'school-two'
  first=DocumentDelivery(manifest,one,file_cache=cache,namespace='one')
  second=DocumentDelivery(manifest,two,file_cache=cache,namespace='two')
  self.assertEqual((await first.file('document'))[1].data,b'school-one')
  self.assertEqual((await second.file('document'))[1].data,b'school-two')
  self.assertEqual(cache.used,20)
if __name__=='__main__':unittest.main()
