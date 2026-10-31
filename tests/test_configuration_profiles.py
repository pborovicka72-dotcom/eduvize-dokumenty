"""Isolated OneDrive contract tests: no account, tokens or network access."""
import asyncio
import copy
import json
import sys
import unittest
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configuration_profiles import ProfileStore, decode, safe_config, profile_router
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


class Drive:
    def __init__(self):
        self.items = {'root': {'id': 'root', 'name': 'Documents', 'folder': {}, 'parent': None}}
        self.locks = defaultdict(asyncio.Lock)
        self.fail_archive = False
    async def root(self): return 'root'
    async def system(self, root):
        item = next((v for v in self.items.values() if v['name'] == '_Eduvize-system'), None)
        return item['id'] if item else (await self.graph('POST', '/me/drive/items/root/children', json={'name':'_Eduvize-system','folder':{}})).json()['id']
    @asynccontextmanager
    async def lock(self, key):
        async with self.locks[key]: yield
    async def read(self, item): return copy.deepcopy(self.items[item['id']]['data'])
    async def graph(self, method, path, **kw):
        from types import SimpleNamespace
        def response(data): return SimpleNamespace(json=lambda:copy.deepcopy(data))
        folder = path.split('/items/')[1].split('/')[0].split(':')[0]
        if method == 'GET':
            return response({'value':[v for v in self.items.values() if v['parent']==folder]})
        if method == 'POST':
            data=kw['json']; item={'id':str(len(self.items)), 'parent':folder, 'name':data['name'],'folder':{}}
        elif method == 'PUT':
            filename=path.split(':/')[1].split(':/')[0]
            if self.fail_archive and self.items[folder]['name'].endswith('-historie'): raise HTTPException(502,'Backup failed')
            item=next((v for v in self.items.values() if v['parent']==folder and v['name']==filename),None) or {'id':str(len(self.items)), 'parent':folder, 'name':filename}
            item['data']=json.loads(kw['content']);item['lastModifiedDateTime']='2026-10-31T12:00:00Z'
        else: raise AssertionError(method)
        self.items[item['id']]=item
        return response(item)
    def store(self): return ProfileStore(self.graph,self.root,self.system,self.read,self.lock)


class Profiles(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.drive=Drive();self.store=self.drive.store();self.profile=await self.store.create('Škola · hlavní obrazovka');self.id=self.profile['id']
    async def test_save_copy_and_private_storage(self):
        await self.store.save_app(self.id,'weather',{'schemaVersion':1,'values':{'place':'Praha'}},0)
        copied=await self.store.create('Škola · druhá obrazovka',self.id)
        self.assertEqual((await self.store.read(copied['id']))['apps']['weather']['config']['values']['place'],'Praha')
        self.assertEqual(len(await self.store.list()),2)
        self.assertTrue(all(v['parent'] != 'root' for v in self.drive.items.values() if 'data' in v))
        with self.assertRaises(HTTPException) as e: await self.store.create(' ŠKOLA · HLAVNÍ obrazovka ')
        self.assertEqual(e.exception.status_code,409)
    async def test_concurrent_apps_merge_and_same_app_conflict(self):
        config={'schemaVersion':1,'values':{'choice':'a'}}
        await asyncio.gather(self.store.save_app(self.id,'weather',config,0), self.store.save_app(self.id,'holidays',config,0))
        current=await self.store.read(self.id)
        self.assertEqual(set(current['apps']),{'weather','holidays'})
        with self.assertRaises(HTTPException) as e: await self.store.save_app(self.id,'weather',config,0)
        self.assertEqual(e.exception.status_code,409)
        self.assertEqual((await self.store.read(self.id))['revision'],3)
    async def test_restore_keeps_monotonic_revisions_and_archives_current(self):
        await self.store.save_app(self.id,'weather',{'schemaVersion':1,'values':{'place':'Praha'}},0)
        await self.store.save_app(self.id,'weather',{'schemaVersion':1,'values':{'place':'Brno'}},1)
        await self.store.restore(self.id,2,3)
        current=await self.store.read(self.id)
        self.assertEqual(current['apps']['weather']['config']['values']['place'],'Praha')
        self.assertEqual(current['apps']['weather']['revision'],3)
        await self.store.restore(self.id,1,4)
        self.assertTrue((await self.store.read(self.id))['apps']['weather']['config']['empty'])
        with self.assertRaises(HTTPException): await self.store.save_app(self.id,'weather',{'schemaVersion':1},0)
        self.assertEqual([v['revision'] for v in await self.store.history(self.id)],[4,3,2,1])
    async def test_backup_failure_preserves_current(self):
        self.drive.fail_archive=True
        with self.assertRaises(HTTPException): await self.store.save_app(self.id,'news',{'schemaVersion':1},0)
        self.assertEqual((await self.store.read(self.id))['revision'],1)
    async def test_invalid_ids_and_corrupt_cloud_file(self):
        with self.assertRaises(HTTPException): await self.store.read('../documents')
        item=next(v for v in self.drive.items.values() if v['name']==self.id+'.json')
        del item['data']['name']
        with self.assertRaises(HTTPException) as e: await self.store.read(self.id)
        self.assertEqual(e.exception.status_code,502)
    async def test_unsafe_pagination_rejected(self):
        async def graph(*args,**kwargs):
            from types import SimpleNamespace
            return SimpleNamespace(json=lambda:{'value':[],'@odata.nextLink':'https://evil.example/token'})
        self.store.graph=graph
        with self.assertRaises(HTTPException): await self.store.children('root')


class Validation(unittest.TestCase):
    def test_secret_and_executable_urls_rejected(self):
        for value in [{'password':'x'},{'access_token':'x'},{'bakUsername':'x'},{'url':'https://example.test/?adminKey=x'},{'url':'https://a:b@example.test'},{'url':'javascript:alert(1)'},{'__proto__':{}}]:
            with self.subTest(value=value),self.assertRaises(HTTPException): safe_config({'schemaVersion':1,'data':value})
    def test_json_limits_and_duplicate_keys(self):
        for raw in [b'{"a":1,"a":2}',b'{"x":NaN}',b'[]',b'{',b'x'*(2*1024*1024+16385)]:
            with self.assertRaises(HTTPException):decode(raw)
        with self.assertRaises(HTTPException):safe_config({'schemaVersion':True})
    def test_style_css_injection_rejected(self):
        with self.assertRaises(HTTPException):safe_config({'schemaVersion':1,'data':{'theme':{'colors':{'text':'</style><script>alert(1)</script>'}}}},'styles')
        with self.assertRaises(HTTPException):safe_config({'schemaVersion':1,'data':[]},'styles')
    def test_api_requires_authorization_and_is_not_cached(self):
        drive=Drive()
        async def authorize(header):
            if header!='Bearer test-profile-only':raise HTTPException(401,'Sign in')
        app=FastAPI();app.include_router(profile_router(drive.store(),authorize));client=TestClient(app)
        self.assertEqual(client.get('/api/admin/configuration-profiles').status_code,401)
        response=client.post('/api/admin/configuration-profiles',headers={'Authorization':'Bearer test-profile-only'},json={'name':'Test'})
        self.assertEqual(response.status_code,200);self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertEqual(client.get('/api/admin/configuration-profiles/'+response.json()['id']).status_code,401)

if __name__=='__main__':unittest.main()
