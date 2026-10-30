import asyncio
import unittest
import sys
import ast
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document_delivery import DocumentDelivery, AsyncCache

class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 0
        self.reads = self.downloads = 0
        self.data = {'items':[{'id':'one','file_id':'drive-one','name':'one.pdf','mime':'application/pdf','category':'A','visible':True}], 'hidden_categories':[]}
        async def manifest():
            self.reads += 1
            await asyncio.sleep(0)
            return self.data.copy() | {'items':[dict(item) for item in self.data['items']]}
        async def download(item):
            self.downloads += 1
            await asyncio.sleep(0)
            return b'%PDF-example'
        self.delivery = DocumentDelivery(manifest, download, clock=lambda:self.now)

    async def test_reuse_and_single_flight(self):
        results = await asyncio.gather(*(self.delivery.file('one') for _ in range(8)))
        self.assertEqual((self.reads,self.downloads),(1,1))
        self.assertEqual(len({asset.etag for _,asset in results}),1)
        first = await self.delivery.catalog();first['items'][0]['visible']=False
        self.assertEqual(len(await self.delivery.visible_items()),1)
        self.now=16
        await self.delivery.file('one')
        self.assertEqual((self.reads,self.downloads),(2,1))
        self.now=61
        await self.delivery.file('one')
        self.assertEqual((self.reads,self.downloads),(3,2))

    async def test_hiding_item_or_category_invalidates_cached_file(self):
        await self.delivery.file('one')
        self.data['items'][0]['visible']=False;self.delivery.invalidate()
        with self.assertRaises(KeyError):await self.delivery.file('one')
        self.data['items'][0]['visible']=True;self.data['hidden_categories']=['A'];self.delivery.invalidate()
        with self.assertRaises(KeyError):await self.delivery.file('one')
        self.assertEqual(self.downloads,1)

    async def test_invalidation_during_download_cannot_restore_hidden_file(self):
        started,finish=asyncio.Event(),asyncio.Event()
        async def delayed(item):
            started.set();await finish.wait();return b'old'
        self.delivery.download=delayed
        pending=asyncio.create_task(self.delivery.file('one'));await started.wait()
        self.data['items'][0]['visible']=False;self.delivery.invalidate();finish.set()
        with self.assertRaises(KeyError):await pending
        self.assertEqual(self.delivery.file_cache.used,0)

    async def test_lru_limits_and_failed_load_retry(self):
        cache=AsyncCache(10,5,weight=len,clock=lambda:self.now)
        async def three():return b'abc'
        await cache.get('a',three);await cache.get('b',three)
        self.assertEqual(list(cache.entries),['b']);self.assertEqual(cache.used,3)
        async def failed():raise RuntimeError('offline')
        with self.assertRaises(RuntimeError):await cache.get('bad',failed)
        self.assertEqual(await cache.get('bad',three),b'abc')

    async def test_file_route_revalidates_visibility_before_304(self):
        source=ast.parse((Path(__file__).resolve().parents[1]/'app.py').read_text())
        method=next(node for node in source.body if isinstance(node,ast.AsyncFunctionDef) and node.name=='get_file');method.decorator_list=[]
        class Response:
            def __init__(self,content=None,media_type=None,status_code=200,headers=None):self.content,self.status_code,self.headers=content,status_code,headers
        class HTTPException(Exception):
            def __init__(self,status_code,detail):self.status_code=status_code
        namespace={'Request':object,'Response':Response,'HTTPException':HTTPException,'document_delivery':self.delivery}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'route','exec'),namespace)
        route=namespace['get_file']
        first=await route('one',SimpleNamespace(headers={}))
        repeated=await route('one',SimpleNamespace(headers={'if-none-match':first.headers['ETag']}))
        self.assertEqual(repeated.status_code,304);self.assertIsNone(repeated.content)
        self.data['items'][0]['visible']=False;self.delivery.invalidate()
        with self.assertRaises(HTTPException) as error:await route('one',SimpleNamespace(headers={'if-none-match':first.headers['ETag']}))
        self.assertEqual(error.exception.status_code,404)
