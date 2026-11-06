"""Exercise the real Documents route bodies against isolated SQL storage."""
import ast
import json
import tempfile
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.testclient import TestClient
from fastapi.responses import Response
from material_fixtures import Connection
from eduvize_admin.cloud_storage import CloudStorage

class DeletionAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();path=str(Path(self.temp.name)/'db')
        self.store=CloudStorage(lambda:Connection(path));self.school='a'*32;self.foreign='f'*32
        for school in [self.school,self.foreign]:self.store.initialize(school)
        self.root=self.store.root(self.school)
        def put(name,value,mime='application/json'):
            data=value if isinstance(value,bytes) else json.dumps(value).encode()
            return self.store.request(self.school,'PUT',f'/me/drive/items/{self.root}:/{name}:/content',content=data,headers={'Content-Type':mime}).json()['id']
        self.file=put('document.pdf',b'%PDF-test','application/pdf');self.doc='d'*32
        put('manifest.json',{'items':[{'id':self.doc,'file_id':self.file,'name':'Test.pdf'}]})
        self.put=put;self.active=self.school;self.invalidations=0
        async def check(auth):
            if auth not in ('Bearer own','Bearer foreign'):raise HTTPException(401,'Přihlaste se.')
            self.active=self.foreign if auth=='Bearer foreign' else self.school
        async def folder():return self.store.root(self.active)
        def invalidate():self.invalidations+=1
        async def cached_file(ident):return ({'file_id':self.file,'mime':'application/pdf'},SimpleNamespace(data=b'%PDF-test',etag='\"cached\"'))
        app=FastAPI()
        namespace={'app':app,'Header':Header,'Request':Request,'Response':Response,'HTTPException':HTTPException,'administration':SimpleNamespace(ensure_cloud=lambda:(self.store,self.active)),
                   'check_admin':check,'ensure_folder':folder,'school_context':SimpleNamespace(get=lambda:{'id':self.active}),
                   'current_delivery':lambda:SimpleNamespace(invalidate=invalidate,file=cached_file)}
        tree=ast.parse((Path(__file__).parents[1]/'app.py').read_text())
        nodes=[node for node in tree.body if isinstance(node,ast.AsyncFunctionDef) and node.name in ('document_usage','delete','get_file')]
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'document-routes','exec'),namespace)
        self.client=TestClient(app);self.headers={'Authorization':'Bearer own'};self.url='/api/admin/documents/'+self.doc
    def tearDown(self):self.temp.cleanup()
    def test_auth_and_cross_school_preflight(self):
        for path in [self.url,self.url+'/usage']:
            response=self.client.get(path) if path.endswith('usage') else self.client.request('DELETE',path,json={})
            self.assertIn(response.status_code,(401,405))
        response=self.client.get(self.url+'/usage',headers={'Authorization':'Bearer foreign'})
        self.assertEqual(response.status_code,404);self.assertNotIn('items',response.json())
    def test_confirmed_delete_and_no_body_or_wrong_confirmation(self):
        usage=self.client.get(self.url+'/usage',headers=self.headers).json()
        for body in [{},{'confirm':'wrong','expectedRevision':usage['revision']}]:
            self.assertEqual(self.client.request('DELETE',self.url,headers=self.headers,json=body).status_code,428)
        response=self.client.request('DELETE',self.url,headers=self.headers,json={'confirm':self.doc,'expectedRevision':usage['revision']})
        self.assertEqual(response.status_code,200);self.assertEqual(self.invalidations,1)
        self.assertEqual(self.client.get(self.url+'/usage',headers=self.headers).status_code,404)
    def test_new_use_after_dialog_returns_structured_locations(self):
        usage=self.client.get(self.url+'/usage',headers=self.headers).json()
        self.put('kiosk.json',{'format':'eduvize-kiosk','config':{'title':'Hala','pages':[{'title':'Řády','target':'/api/documents/'+self.doc+'/file'}]}})
        response=self.client.request('DELETE',self.url,headers=self.headers,json={'confirm':self.doc,'expectedRevision':usage['revision']})
        self.assertEqual(response.status_code,409)
        detail=response.json()['detail'];self.assertEqual(detail['code'],'material_in_use')
        self.assertTrue(any('Řády' in x['location'] for x in detail['items']));self.assertEqual(self.invalidations,0)
    def test_failed_preflight_does_not_claim_unused(self):
        with self.store.db() as conn:self.store.insert(conn,self.school,'broken',self.root,'broken.json',False,'application/json',b'{')
        response=self.client.get(self.url+'/usage',headers=self.headers)
        self.assertEqual(response.status_code,503);self.assertNotIn('canDelete',response.json())

    def test_another_workers_warm_cache_does_not_return_deleted_file_or_304(self):
        url='/api/documents/'+self.doc+'/file'
        self.assertEqual(self.client.get(url).status_code,200)
        usage=self.client.get(self.url+'/usage',headers=self.headers).json()
        self.assertEqual(self.client.request('DELETE',self.url,headers=self.headers,json={'confirm':self.doc,'expectedRevision':usage['revision']}).status_code,200)
        response=self.client.get(url,headers={'If-None-Match':'"cached"'})
        self.assertEqual(response.status_code,404)

if __name__=='__main__':unittest.main()
