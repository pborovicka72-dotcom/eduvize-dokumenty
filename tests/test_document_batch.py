import ast,asyncio,copy,unittest
from fastapi import HTTPException
from pathlib import Path
source=ast.parse((Path(__file__).resolve().parents[1]/'app.py').read_text())
names={'apply_document_changes','category_names','in_document_scope'}
module=ast.Module(body=[n for n in source.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names],type_ignores=[])
class BatchTest(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.reads=0;self.writes=[];self.data={'items':[{'id':'a','name':'A','category':'Test','title':''},{'id':'b','name':'B','category':'Test','title':''}],'categories':['Test'],'hidden_categories':['Hidden']}
  async def folder():return 'folder'
  async def manifest(folder):self.reads+=1;return copy.deepcopy(self.data)
  async def save(folder,items,**meta):self.writes.append((items,meta))
  self.scope={'HTTPException':HTTPException,'lock':asyncio.Lock(),'ensure_folder':folder,'manifest_data':manifest,'save_manifest':save,'DEFAULT_CATEGORIES':[]}
  exec(compile(module,'batch','exec'),self.scope)
 async def test_multiple_edits_read_and_write_once(self):
  await self.scope['apply_document_changes']([{'id':'a','title':'First'},{'id':'b','title':'Second'}]);self.assertEqual(self.reads,1);self.assertEqual(len(self.writes),1);self.assertEqual([x['title'] for x in self.writes[0][0]],['First','Second']);self.assertEqual(self.writes[0][1]['hidden_categories'],['Hidden'])
 async def test_invalid_edit_does_not_write_partial_batch(self):
  with self.assertRaises(HTTPException):await self.scope['apply_document_changes']([{'id':'a','title':'changed'},{'id':'missing','title':'bad'}])
  self.assertEqual(self.writes,[])
 async def test_invalid_category_not_saved(self):
  with self.assertRaises(HTTPException):await self.scope['apply_document_changes']([{'id':'a','category':'Unknown'}])
  self.assertEqual(self.writes,[])
if __name__=='__main__':unittest.main()
