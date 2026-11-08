"""Documents library snapshots in the existing OutputRegistry; no alternate registry/API."""
import json
import os
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, StrictBool

MIMES={'application/pdf','image/png','image/jpeg','image/webp','video/mp4','video/webm'}
class Payload(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    selection: Literal['visible-library']
    videoSound: StrictBool

def validate(payload,presentation):
    return Payload.model_validate(payload).model_dump()

def prepare(actor,payload,connection):
    from eduvize_admin.output_registry import fail,ident
    from eduvize_admin.output_media import prepare_asset
    settings=validate(payload,None);ident(actor.school)
    # Target assembly/profile/lifecycle/entitlements remain enforced by OutputRegistry.
    # Library ownership is always the verified actor school, never a payload field.
    def child(parent,name,folder):
        rows=connection.execute('SELECT id FROM eduvize_cloud_files_v1 WHERE owner=%s AND parent=%s AND name=%s AND folder=%s AND deleted=FALSE',(actor.school,parent,name,folder)).fetchall()
        if len(rows)>1:fail(409,'AMBIGUOUS_LIBRARY','Školní knihovna není jednoznačná.')
        return rows[0][0] if rows else None
    root=child('@root','Eduvize-Dokumenty',True)
    if not root:fail(404,'NOT_FOUND','Školní knihovna nebyla nalezena.')
    system=child(root,'_Eduvize-system',True)
    manifest=child(system,'manifest.json',False) if system else None
    if not manifest:manifest=child(root,'manifest.json',False)
    if not manifest:fail(404,'NOT_FOUND','Katalog dokumentů nebyl nalezen.')
    row=connection.execute('SELECT content FROM eduvize_cloud_files_v1 WHERE owner=%s AND id=%s AND folder=FALSE AND deleted=FALSE',(actor.school,manifest)).fetchone()
    if not row or len(row[0])>2*1024*1024:fail(422,'INVALID_LIBRARY','Neplatný katalog dokumentů.')
    try:catalog=json.loads(bytes(row[0]))
    except (ValueError,TypeError):fail(422,'INVALID_LIBRARY','Nečitelný katalog dokumentů.')
    if not isinstance(catalog,dict) or not isinstance(catalog.get('items'),list) or not isinstance(catalog.get('hidden_categories',[]),list):fail(422,'INVALID_LIBRARY','Neplatný katalog dokumentů.')
    hidden=catalog.get('hidden_categories',[])
    if any(not isinstance(v,str) for v in hidden):fail(422,'INVALID_LIBRARY','Neplatné kategorie.')
    items=[];manifest_entries={};seen=set();total=0
    for item in catalog['items']:
        if not isinstance(item,dict):fail(422,'INVALID_LIBRARY','Neplatný záznam dokumentu.')
        if item.get('scope','documents')!='documents' or item.get('visible',True) is False:continue
        if not isinstance(item.get('visible',True),bool):fail(422,'INVALID_LIBRARY','Neplatná viditelnost.')
        category=item.get('category','Ostatní')
        if category in hidden:continue
        id=item.get('id');ident(id)
        if id in seen:fail(422,'INVALID_LIBRARY','Duplicitní dokument.')
        seen.add(id)
        if len(seen)>100:fail(422,'LIBRARY_LIMIT','Výstup podporuje nejvýše 100 viditelných dokumentů.')
        for key,value,limit in [('name',item.get('name'),180),('title',item.get('title',''),300),('category',category,80)]:
            if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 for c in value):fail(422,'INVALID_LIBRARY','Neplatný popis dokumentu.')
        file_id=item.get('file_id')
        if not isinstance(file_id,str) or not re.fullmatch(r'[A-Za-z0-9!._-]{1,256}',file_id):fail(422,'INVALID_LIBRARY','Neplatná vazba souboru.')
        tombstone=connection.execute('SELECT 1 FROM eduvize_material_deleted_v1 WHERE owner=%s AND material_id=%s',(actor.school,id)).fetchone()
        if tombstone:fail(409,'MEDIA_CHANGED','Dokument byl odstraněn.')
        source=connection.execute('SELECT mime,LENGTH(content) FROM eduvize_cloud_files_v1 WHERE owner=%s AND id=%s AND parent=%s AND folder=FALSE AND deleted=FALSE',(actor.school,file_id,root)).fetchone()
        if not source or source[0] not in MIMES or source[0]!=item.get('mime') or not 0<source[1]<=100*1024*1024:fail(409,'MEDIA_CHANGED','Soubor není dostupný nebo se změnil.')
        total+=source[1]
        if total>256*1024*1024:fail(422,'LIBRARY_LIMIT','Výstup překročil celkový limit 256 MB.')
        entry=prepare_asset(connection,actor.school,file_id)
        if entry['metadata']['mime']!=source[0] or entry['metadata']['size']!=source[1]:fail(409,'MEDIA_CHANGED','Soubor se změnil.')
        manifest_entries[entry['metadata']['id']]=entry
        position=item.get('position',0)
        if not isinstance(position,int) or isinstance(position,bool):fail(422,'INVALID_LIBRARY','Neplatné pořadí.')
        items.append({'id':id,'mediaId':entry['metadata']['id'],'name':item['name'],'title':item.get('title',''),'category':category,'mime':source[0],'position':position})
    if not items:fail(422,'EMPTY_LIBRARY','Nejprve zpřístupněte alespoň jeden dokument.')
    items.sort(key=lambda v:(v['position'],v['name'],v['id']))
    return {'videoSound':settings['videoSound'],'items':items},list(manifest_entries.values())

def get_output_adapters():
    import psycopg
    from eduvize_admin.output_registry import Adapter
    from eduvize_admin.output_media import read_asset
    def connect():return psycopg.connect(os.environ['DATABASE_URL'],connect_timeout=10)
    return {'documents':Adapter(validate,'/eduvize-dokumenty/published.html',prepare,lambda entry,request:read_asset(connect,entry,request))}
