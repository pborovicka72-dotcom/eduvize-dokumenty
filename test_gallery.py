import copy
import importlib.util
import unittest
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from unittest.mock import patch
import json

spec=importlib.util.spec_from_file_location('gallery',__file__.replace('test_gallery.py','gallery.py'))
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)

class Gallery(unittest.TestCase):
    def setUp(self):
        self.data={'albums':[{'id':'a','name':'Výlet','folder':'folder','token':'secret',
            'settings':g.settings({'whole':False,'selection':['one']}),
            'items':[{'id':'one','file':'f1','name':'A','mime':'image/jpeg','width':600,'height':900},
                     {'id':'two','file':'f2','name':'B','mime':'image/jpeg','width':1600,'height':900}]}]}
        async def graph(method,path,**kw):
            if method=='PUT' and 'albums.json' in path:self.data=json.loads(kw['content'])
            class Result:
                def json(self):return {'id':'new','@microsoft.graph.downloadUrl':'https://example.com/media.jpg'}
            return Result()
        async def folder():return 'base'
        async def child(parent,name):return {'id':'gallery','folder':{}} if name=='Fotogalerie' else {'id':'manifest'}
        async def read(item):return copy.deepcopy(self.data)
        async def check(auth):
            if auth!='Bearer test':raise HTTPException(401,'login')
        @asynccontextmanager
        async def lock(key):yield
        app=FastAPI();app.include_router(g.gallery_router(graph,folder,child,read,check,lock,lambda:'school'))
        self.client=TestClient(app);self.headers={'Authorization':'Bearer test'}

    def test_admin_auth_required(self):
        self.assertEqual(self.client.get('/api/admin/gallery').status_code,401)
        self.assertEqual(self.client.get('/api/admin/gallery',headers=self.headers).status_code,200)

    def test_public_capability_and_selection(self):
        self.assertEqual(self.client.get('/api/gallery/a?token=wrong').status_code,404)
        response=self.client.get('/api/gallery/a?token=secret')
        self.assertEqual([i['id'] for i in response.json()['items']],['one'])
        self.assertNotIn('file',response.json()['items'][0])
        self.assertEqual(self.client.get('/api/gallery/a/files/two?token=secret',follow_redirects=False).status_code,404)
        self.assertEqual(self.client.get('/api/gallery/a/files/one?token=secret',follow_redirects=False).status_code,307)

    def test_crop_clamped_and_selection_persisted(self):
        response=self.client.put('/api/admin/gallery/a',headers=self.headers,json={'settings':{'crop':99,'count':99,'whole':False,'selection':['two']}})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['settings']['crop'],15)
        self.assertEqual(response.json()['settings']['count'],6)
        self.assertEqual(self.client.get('/api/gallery/a?token=secret').json()['items'][0]['id'],'two')

    def test_invalid_upload_and_import(self):
        response=self.client.post('/api/admin/gallery/a/files',headers=self.headers,files={'file':('test.jpg',b'not a photo','image/jpeg')})
        self.assertEqual(response.status_code,415)
        response=self.client.post('/api/admin/gallery/a/import',headers=self.headers,json={'url':'https://attacker.example.com/folder'})
        self.assertEqual(response.status_code,422)

    def test_media_signatures(self):
        self.assertTrue(g.verify_media('.jpg',b'\xff\xd8\xff\x00'))
        self.assertFalse(g.verify_media('.jpg',b'<html>'))
        self.assertFalse(g.verify_media('.mp4',b'1234567890'))

if __name__=='__main__':unittest.main()
