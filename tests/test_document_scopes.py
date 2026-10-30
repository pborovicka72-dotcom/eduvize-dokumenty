import ast
import __future__
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace

source=ast.parse((Path(__file__).resolve().parents[1]/'app.py').read_text())
names={'document_scope','in_document_scope','public_items','list_public','list_admin','reorder_documents'}
nodes=[x for x in source.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and x.name in names]
for node in nodes:node.decorator_list=[]
class APIError(Exception):
 def __init__(self,status,detail):self.status_code=status
scope={'HTTPException':APIError,'Header':lambda **kw:None,'Request':object}
exec(compile(ast.Module(body=nodes,type_ignores=[]),'app.py','exec',flags=__future__.annotations.compiler_flag),scope)

class ScopeTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.items=[{'id':'old','name':'Old'},{'id':'doc','name':'Doc','scope':'documents'},{'id':'kiosk','name':'Kiosk','scope':'kiosk'}]
  async def visible():return self.items
  async def all_items():return 'folder',self.items
  scope.update(document_delivery=SimpleNamespace(visible_items=visible),all_items=all_items,check_admin=lambda token:None)
 async def test_default_catalog_excludes_kiosk(self):
  result=await scope['list_public']();self.assertEqual({x['id'] for x in result['items']},{'old','doc'})
 async def test_kiosk_catalog_is_separate(self):
  result=await scope['list_public']('kiosk');self.assertEqual([x['id'] for x in result['items']],['kiosk'])
 async def test_direct_links_can_resolve_both_catalogs(self):
  result=await scope['list_public']('all');self.assertEqual(len(result['items']),3)
 async def test_admin_list_is_scoped(self):
  result=await scope['list_admin']('token');self.assertEqual({x['id'] for x in result['items']},{'old','doc'})
 async def test_invalid_scope_rejected(self):
  with self.assertRaises(APIError):await scope['list_public']('other')
 async def test_scoped_reorder_preserves_other_owner(self):
  scope['lock']=asyncio.Lock()
  async def save(folder,items):pass
  scope['save_manifest']=save
  async def json():return {'ids':['doc','old']}
  await scope['reorder_documents'](SimpleNamespace(json=json),'token')
  self.assertEqual(self.items[0]['position'],1);self.assertNotIn('position',self.items[2])
if __name__=='__main__':unittest.main()
