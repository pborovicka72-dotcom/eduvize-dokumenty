import importlib.util,json,sqlite3,sys,types,hashlib,unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Denied(Exception):pass
def fail(status,code,message):raise Denied(code)
def ident(value):
 if not isinstance(value,str) or len(value)!=32 or any(c not in '0123456789abcdef' for c in value):fail(404,'NOT_FOUND','')
registry=types.ModuleType('eduvize_admin.output_registry');registry.fail=fail;registry.ident=ident
media=types.ModuleType('eduvize_admin.output_media')
def prepare_asset(c,owner,file):
 row=c.execute('SELECT content,mime FROM eduvize_cloud_files_v1 WHERE owner=%s AND id=%s',(owner,file)).fetchone()
 b=bytes(row[0]);return {'metadata':{'id':hashlib.sha256((owner+'\0'+file).encode()).hexdigest()[:32],'version':hashlib.sha256(b).hexdigest(),'mime':row[1],'size':len(b)},'reference':{'provider':'eduvize-output-assets','ownerId':owner,'fileId':file}}
media.prepare_asset=prepare_asset
spec=importlib.util.spec_from_file_location('documents_output_adapter',ROOT/'documents_output_adapter.py');adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
class DB:
 def __init__(self):
  self.db=sqlite3.connect(':memory:');self.db.executescript('CREATE TABLE eduvize_cloud_files_v1(owner TEXT,id TEXT,parent TEXT,name TEXT,folder BOOLEAN,deleted BOOLEAN,content BLOB,mime TEXT);CREATE TABLE eduvize_material_deleted_v1(owner TEXT,material_id TEXT);')
 def execute(self,q,args=()):return self.db.execute(q.replace('%s','?'),args)
class AdapterTests(unittest.TestCase):
 def setUp(self):
  self.modules=patch.dict(sys.modules,{'eduvize_admin':types.ModuleType('eduvize_admin'),'eduvize_admin.output_registry':registry,'eduvize_admin.output_media':media});self.modules.start();self.addCleanup(self.modules.stop)
  self.c=DB();self.owner='a'*32;self.actor=types.SimpleNamespace(school=self.owner);self.id='b'*32
  self.items=[{'id':self.id,'file_id':'pdf-file','name':'Test.pdf','title':'Řád','category':'Ostatní','mime':'application/pdf','visible':True,'scope':'documents'}]
  self.file('root','@root','Eduvize-Dokumenty',True);self.file('system','root','_Eduvize-system',True);self.file('manifest','system','manifest.json',False);self.file('pdf-file','root','source.pdf',False,b'%PDF-1.4\n','application/pdf');self.catalog()
 def file(self,id,parent,name,folder,content=b'',mime='application/json',owner=None):self.c.execute('INSERT INTO eduvize_cloud_files_v1 VALUES (%s,%s,%s,%s,%s,FALSE,%s,%s)',(owner or self.owner,id,parent,name,folder,content,mime))
 def catalog(self,hidden=[]):self.c.execute('UPDATE eduvize_cloud_files_v1 SET content=%s WHERE id=%s',(json.dumps({'items':self.items,'hidden_categories':hidden}).encode(),'manifest'))
 def prepare(self):return adapter.prepare(self.actor,{'selection':'visible-library','videoSound':False},self.c)
 def test_snapshot_public_has_no_storage_context(self):
  public,media=self.prepare();self.assertEqual(public['items'][0]['name'],'Test.pdf');self.assertEqual(media[0]['reference']['ownerId'],self.owner);self.assertNotIn('file_id',json.dumps(public));self.assertNotIn(self.owner,json.dumps(public));self.assertEqual(media[0]['metadata']['version'],hashlib.sha256(b'%PDF-1.4\n').hexdigest())
 def test_foreign_actor_cannot_read_library(self):
  self.actor.school='c'*32
  with self.assertRaisesRegex(Denied,'NOT_FOUND'):self.prepare()
 def test_foreign_file_denied(self):
  self.c.execute('UPDATE eduvize_cloud_files_v1 SET owner=%s WHERE id=%s',('c'*32,'pdf-file'))
  with self.assertRaisesRegex(Denied,'MEDIA_CHANGED'):self.prepare()
 def test_hidden_and_kiosk_files_excluded(self):
  self.items.append({**self.items[0],'id':'d'*32,'scope':'kiosk'});self.items.append({**self.items[0],'id':'e'*32,'visible':False});self.catalog();self.assertEqual(len(self.prepare()[0]['items']),1)
 def test_hidden_category_empty_fails_closed(self):
  self.catalog(['Ostatní'])
  with self.assertRaisesRegex(Denied,'EMPTY_LIBRARY'):self.prepare()
 def test_tombstone_and_deleted_file(self):
  self.c.execute('INSERT INTO eduvize_material_deleted_v1 VALUES (%s,%s)',(self.owner,self.id))
  with self.assertRaisesRegex(Denied,'MEDIA_CHANGED'):self.prepare()
  self.c.execute('DELETE FROM eduvize_material_deleted_v1');self.c.execute('UPDATE eduvize_cloud_files_v1 SET deleted=TRUE WHERE id=%s',('pdf-file',))
  with self.assertRaisesRegex(Denied,'MEDIA_CHANGED'):self.prepare()
 def test_wrong_mime_and_wrong_parent(self):
  self.c.execute('UPDATE eduvize_cloud_files_v1 SET mime=%s WHERE id=%s',('text/html','pdf-file'))
  with self.assertRaisesRegex(Denied,'MEDIA_CHANGED'):self.prepare()
  self.c.execute('UPDATE eduvize_cloud_files_v1 SET mime=%s,parent=%s WHERE id=%s',('application/pdf','other','pdf-file'))
  with self.assertRaisesRegex(Denied,'MEDIA_CHANGED'):self.prepare()
 def test_duplicate_and_invalid_manifest(self):
  self.items*=2;self.catalog()
  with self.assertRaisesRegex(Denied,'INVALID_LIBRARY'):self.prepare()
 def test_ambiguous_root_is_rejected(self):
  self.file('other-root','@root','Eduvize-Dokumenty',True)
  with self.assertRaisesRegex(Denied,'AMBIGUOUS_LIBRARY'):self.prepare()
 def test_malformed_catalog_fails_closed(self):
  self.c.execute('UPDATE eduvize_cloud_files_v1 SET content=%s WHERE id=%s',(b'{bad','manifest'))
  with self.assertRaisesRegex(Denied,'INVALID_LIBRARY'):self.prepare()
 def test_non_boolean_visibility_rejected(self):
  self.items[0]['visible']='yes';self.catalog()
  with self.assertRaisesRegex(Denied,'INVALID_LIBRARY'):self.prepare()
 def test_strict_payload(self):
  for value in [{'selection':'visible-library','videoSound':1},{'selection':'visible-library','videoSound':False,'ownerId':self.owner},{'selection':'arbitrary','videoSound':False}]:
   with self.assertRaises(Exception):adapter.validate(value,None)
if __name__=='__main__':unittest.main()
