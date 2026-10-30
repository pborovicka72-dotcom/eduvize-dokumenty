import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kiosk_config_store import KioskConfigStore, configuration_file, configuration_name, MAX_BYTES

CONFIG = {'format':'eduvize-kiosk','version':1,'config':{'title':'Škola','pages':[{'id':'home','buttons':[]},{'id':'parents','buttons':[{'type':'document','target':'https://example.org/file'}],'content':{'intro':'Úvod','sections':[{'title':'Sekce','image':'https://example.org/img.png'}]}}]}}

class StoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.files = {}
        self.writes = []
        async def graph(method,path,**kwargs):
            if method == 'POST':
                self.files['Kiosek'] = {'id':'configs','folder':{}}
                return SimpleNamespace(json=lambda:self.files['Kiosek'])
            if method == 'PUT':
                filename = path.split(':/')[1]
                data = json.loads(kwargs['content'])
                self.files[filename] = {'id':filename,'name':filename,'data':data}
                self.writes.append(filename)
                return SimpleNamespace(json=lambda:{})
            return SimpleNamespace(json=lambda:{'value':[item for item in self.files.values() if 'name' in item]})
        async def parent(): return 'documents'
        async def system(parent): return 'system'
        async def child(parent,name):
            if name == '_Eduvize-system': return {'id':'system','folder':{}}
            return self.files.get(name)
        async def read(item): return item['data']
        self.store = KioskConfigStore(graph,parent,system,child,read,asyncio.Lock())

    async def test_round_trip_and_backup_not_in_catalog(self):
        self.assertEqual(await self.store.list(), [])
        self.assertIsNone(await self.store.load('missing'))
        await self.store.save('main', json.dumps(CONFIG).encode())
        first = await self.store.load('main')
        self.assertEqual(first['config'], CONFIG['config'])
        changed = json.loads(json.dumps(CONFIG)); changed['config']['title'] = 'Nový název'
        await self.store.save('main', json.dumps(changed).encode())
        self.assertEqual((await self.store.load('main'))['config']['title'], 'Nový název')
        self.assertEqual(self.files['main.previous.json']['data'], first)
        self.assertEqual([x['name'] for x in await self.store.list()], ['main'])
        self.assertEqual(self.writes, ['main.json','main.previous.json','main.json'])

    async def test_reject_invalid_before_writing(self):
        for raw in [b'{}', b'not json', b'x'*(MAX_BYTES+1), json.dumps({**CONFIG,'version':2}).encode()]:
            with self.assertRaises(ValueError): await self.store.save('main',raw)
        for name in ['../main','main.json','','x'*65,'a/b']:
            with self.assertRaises(ValueError): await self.store.save(name,json.dumps(CONFIG).encode())
        secret = json.loads(json.dumps(CONFIG)); secret['config']['token']='secret'
        with self.assertRaises(ValueError): configuration_file(json.dumps(secret))
        self.assertEqual(self.writes, [])

    async def test_failed_backup_preserves_current(self):
        await self.store.save('main',json.dumps(CONFIG).encode())
        original = await self.store.load('main')
        old_graph = self.store.graph
        async def fail(method,path,**kwargs):
            if '.previous.json' in path: raise RuntimeError('OneDrive unavailable')
            return await old_graph(method,path,**kwargs)
        self.store.graph = fail
        with self.assertRaises(RuntimeError): await self.store.save('main',json.dumps(CONFIG).encode())
        self.assertEqual(await self.store.load('main'), original)

if __name__ == '__main__': unittest.main()

class RouteAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_cloud_routes_authenticate_before_storage_or_body_reads(self):
        import ast
        source = ast.parse((Path(__file__).resolve().parents[1] / 'app.py').read_text())
        route_names = {'list_kiosk_configurations','load_kiosk_configuration','save_kiosk_configuration'}
        functions = [n for n in source.body if isinstance(n,ast.AsyncFunctionDef) and n.name in route_names]
        def reject(auth): raise PermissionError('unauthorized')
        scope = {'Header':lambda **kwargs:None,'Request':object,'check_admin':reject}
        for function in functions: function.decorator_list=[]
        exec(compile(ast.Module(body=functions,type_ignores=[]),'routes','exec'),scope)
        for name in route_names:
            kwargs={'authorization':'wrong'}
            if name != 'list_kiosk_configurations': kwargs['name']='main'
            if name == 'save_kiosk_configuration': kwargs['request']=object()
            with self.assertRaises(PermissionError): await scope[name](**kwargs)
