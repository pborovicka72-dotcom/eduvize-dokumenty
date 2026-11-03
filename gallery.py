"""School-isolated photo albums, private OneDrive storage and capability display links."""
import asyncio
import time
from collections import OrderedDict
import base64
import json
import re
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from fastapi import APIRouter, Header, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import RedirectResponse

MEDIA = {'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp',
         '.mp4':'video/mp4','.webm':'video/webm','.mp3':'audio/mpeg','.m4a':'audio/mp4','.wav':'audio/wav'}
MAX_FILE = 100 * 1024 * 1024

def settings(value):
    value = value if isinstance(value, dict) else {}
    def integer(key, default, low, high):
        try: return max(low, min(high, int(value.get(key, default))))
        except (TypeError, ValueError): return default
    return {'count':integer('count',4,1,6),'seconds':integer('seconds',8,3,120),
            'sort':value.get('sort') if value.get('sort') in ('date','name') else 'date',
            'viewMode':value.get('viewMode') if value.get('viewMode') in ('nsp','kiosk','web') else 'nsp',
            'segment':value.get('segment') if isinstance(value.get('segment'),dict) else {'orientation':'landscape','style':1,'block':1},
            'crop':integer('crop',10,0,15),'volume':integer('volume',30,0,100),
            'style':value.get('style') if value.get('style') in ('mosaic','rows','single') else 'mosaic',
            'transition':value.get('transition') if value.get('transition') in ('fade','slide','none') else 'fade',
            'smart':value.get('smart',True) is True,'header':value.get('header',True) is True,
            'videos':value.get('videos',True) is True,'videoSound':value.get('videoSound',False) is True,
            'music':str(value.get('music',''))[:100],
            'selection':list(dict.fromkeys(x for x in value.get('selection',[]) if isinstance(x,str)))[:1000]
                if isinstance(value.get('selection'),list) else [],'whole':value.get('whole',True) is True}

def verify_media(ext, data):
    return {'.jpg':data.startswith(b'\xff\xd8\xff'),'.jpeg':data.startswith(b'\xff\xd8\xff'),
      '.png':data.startswith(b'\x89PNG\r\n\x1a\n'),'.webp':data[:4]==b'RIFF' and data[8:12]==b'WEBP',
      '.mp4':data[4:8]==b'ftyp','.m4a':data[4:8]==b'ftyp',
      '.webm':data.startswith(bytes.fromhex('1a45dfa3')),
      '.mp3':data.startswith(b'ID3') or (len(data)>1 and data[0]==255 and data[1]&224==224),
      '.wav':data[:4]==b'RIFF' and data[8:12]==b'WAVE'}.get(ext,False)

class Albums:
    def __init__(self, graph, folder, child, read):
        self.graph,self.folder,self.child,self.read=graph,folder,child,read

    async def root(self,create=False):
        parent=await self.folder()
        item=await self.child(parent,'Fotogalerie')
        if item:
            if 'folder' not in item: raise HTTPException(409,'Fotogalerie musí být složka.')
            return item['id']
        if not create:raise HTTPException(404,'Galerie zatím neobsahuje žádné album.')
        return (await self.graph('POST',f'/me/drive/items/{parent}/children',json={
            'name':'Fotogalerie','folder':{},'@microsoft.graph.conflictBehavior':'fail'})).json()['id']

    async def all(self,create=False):
        folder=await self.root(create)
        item=await self.child(folder,'albums.json')
        data=await self.read(item) if item else {'albums':[]}
        if not isinstance(data,dict) or not isinstance(data.get('albums'),list):
            raise HTTPException(502,'Seznam alb na OneDrive má neplatný formát.')
        return folder,data

    async def save(self,folder,data):
        raw=json.dumps(data,ensure_ascii=False).encode()
        if len(raw)>4_000_000: raise HTTPException(413,'Galerie překračuje limit metadat.')
        await self.graph('PUT',f'/me/drive/items/{folder}:/albums.json:/content',content=raw,
                         headers={'Content-Type':'application/json'})

    async def album(self,album_id):
        folder,data=await self.all()
        album=next((a for a in data['albums'] if a['id']==album_id),None)
        if not album: raise HTTPException(404,'Album nebylo nalezeno.')
        return folder,data,album

def gallery_router(graph, folder, child, read, check_admin, write_lock, namespace):
    router=APIRouter()
    store=Albums(graph,folder,child,read)
    def lock(): return write_lock('gallery:'+namespace())

    public_cache=OrderedDict()
    read_locks=[asyncio.Lock() for _ in range(16)]
    def invalidate(album_id):public_cache.pop((namespace(),album_id),None)
    async def public(album_id, token):
        key=(namespace(),album_id)
        async with read_locks[hash(key)%len(read_locks)]:
            cached=public_cache.get(key)
            if cached and time.monotonic()-cached[0]<3:a=cached[1]
            else:
                _,_,a=await store.album(album_id)
                if len(public_cache)>=128:public_cache.popitem(last=False)
                public_cache[key]=(time.monotonic(),a)
        if not token or not secrets.compare_digest(str(token),a['token']):
            raise HTTPException(404,'Album nebylo nalezeno.')
        return a

    def visible(a):
        s=a['settings']
        return [i for i in a['items'] if (s['whole'] or i['id'] in s['selection'] or i['id']==s['music'])]

    @router.post('/api/admin/gallery/{album_id}/links')
    async def add_links(album_id:str,request:Request,authorization:str=Header(default='')):
        await check_admin(authorization);payload=await request.json();items=payload.get('items',[])
        if not isinstance(items,list) or len(items)>100:raise HTTPException(422,'Nejvýše 100 odkazů najednou.')
        async with lock():
            parent,data,a=await store.album(album_id)
            for i in items:
                url=str(i.get('url',''));p=urlparse(url)
                if p.scheme!='https' or not p.hostname or p.username or p.password:raise HTTPException(422,'Použijte veřejný HTTPS odkaz.')
                if not str(i.get('mime','')).startswith(('image/','video/','audio/')):raise HTTPException(422,'Nepodporovaný typ média.')
                a['items'].append({'id':uuid.uuid4().hex,'file':'','external':url,'name':str(i.get('name','Soubor'))[:180],
                    'mime':i['mime'],'width':max(1,min(50000,int(i.get('width',1)))),
                    'height':max(1,min(50000,int(i.get('height',1)))),'date':str(i.get('date',''))[:40]})
            if len(a['items'])>1000:raise HTTPException(422,'Album může mít nejvýše 1000 souborů.')
            await store.save(parent,data);invalidate(a['id'])
        return a

    async def download_url(item):
        if item.get('external'):return item['external']
        path=f"/drives/{item['drive']}/items/{item['file']}" if item.get('drive') else f"/me/drive/items/{item['file']}"
        info=(await graph('GET',path)).json();url=info.get('@microsoft.graph.downloadUrl','')
        if not url.startswith('https://'):raise HTTPException(503,'OneDrive nyní neposkytuje soubor.')
        return url

    @router.get('/api/admin/gallery/{album_id}/files/{item_id}')
    async def admin_media(album_id:str,item_id:str,authorization:str=Header(default='')):
        await check_admin(authorization);_,_,a=await store.album(album_id)
        item=next((i for i in a['items'] if i['id']==item_id),None)
        if not item:raise HTTPException(404,'Soubor nebyl nalezen.')
        return {'url':await download_url(item)}

    @router.get('/api/admin/gallery')
    async def list_albums(authorization:str=Header(default='')):
        await check_admin(authorization)
        _,data=await store.all(True)
        return {'albums':data['albums']}

    @router.post('/api/admin/gallery')
    async def create_album(request:Request,authorization:str=Header(default='')):
        await check_admin(authorization)
        payload=await request.json();name=str(payload.get('name','')).strip()
        if not name or len(name)>120:raise HTTPException(422,'Zadejte název alba do 120 znaků.')
        async with lock():
            parent,data=await store.all(True)
            if len(data['albums'])>=200:raise HTTPException(422,'Nejvýše 200 alb.')
            album_id=uuid.uuid4().hex
            target=(await graph('POST',f'/me/drive/items/{parent}/children',json={
                'name':album_id,'folder':{},'@microsoft.graph.conflictBehavior':'fail'})).json()
            a={'id':album_id,'name':name,'token':secrets.token_urlsafe(32),'folder':target['id'],
               'created':datetime.now(timezone.utc).isoformat(),'items':[],'settings':settings({})}
            data['albums'].append(a);await store.save(parent,data);invalidate(a['id'])
        return a

    @router.put('/api/admin/gallery/{album_id}')
    async def update_album(album_id:str,request:Request,authorization:str=Header(default='')):
        await check_admin(authorization);payload=await request.json()
        async with lock():
            folder,data,a=await store.album(album_id)
            if 'name' in payload:
                name=str(payload['name']).strip()
                if not name or len(name)>120:raise HTTPException(422,'Neplatný název alba.')
                a['name']=name
            if 'settings' in payload:a['settings']=settings(payload['settings'])
            if 'order' in payload:
                order=payload['order']
                if not isinstance(order,list) or len(order)!=len(a['items']) or set(order)!={x['id'] for x in a['items']}:
                    raise HTTPException(409,'Seznam souborů se změnil. Obnovte album.')
                a['items'].sort(key=lambda x:order.index(x['id']))
            await store.save(folder,data);invalidate(a['id'])
        return a

    @router.post('/api/admin/gallery/{album_id}/files')
    async def upload(album_id:str,file:UploadFile=File(...),metadata:str=Form('{}'),authorization:str=Header(default='')):
        await check_admin(authorization)
        ext=Path(file.filename or '').suffix.lower()
        if ext not in MEDIA:raise HTTPException(415,'Podporovány jsou JPG, PNG, WebP, MP4, WebM a hudba MP3, M4A, WAV.')
        content=await file.read(MAX_FILE+1)
        if not content or len(content)>MAX_FILE:raise HTTPException(413,'Soubor musí mít 1 B až 100 MB.')
        if not verify_media(ext,content):raise HTTPException(415,'Obsah neodpovídá typu souboru.')
        try:meta=json.loads(metadata)
        except ValueError:raise HTTPException(422,'Neplatné údaje o souboru.')
        if not isinstance(meta,dict):raise HTTPException(422,'Neplatné údaje o souboru.')
        def dim(k):
            try:return max(1,min(50000,int(meta.get(k,1))))
            except (ValueError,TypeError,AttributeError):return 1
        async with lock():
            parent,data,a=await store.album(album_id)
            if len(a['items'])>=1000:raise HTTPException(422,'Album může mít nejvýše 1000 souborů.')
            item_id=uuid.uuid4().hex
            uploaded=(await graph('PUT',f"/me/drive/items/{a['folder']}:/{item_id}{ext}:/content",
                                  content=content,headers={'Content-Type':MEDIA[ext]})).json()
            item={'id':item_id,'file':uploaded['id'],'name':Path(file.filename).name[:180],
                  'mime':MEDIA[ext],'width':dim('width'),'height':dim('height'),
                  'date':str(meta.get('date',''))[:40],'size':len(content)}
            a['items'].append(item);await store.save(parent,data);invalidate(a['id'])
        return item

    @router.post('/api/admin/gallery/{album_id}/import')
    async def import_folder(album_id:str,request:Request,authorization:str=Header(default='')):
        await check_admin(authorization);body=await request.json();link=str(body.get('url',''))
        host=(urlparse(link).hostname or '').lower()
        if not (host in ('1drv.ms','onedrive.live.com') or host.endswith('.sharepoint.com')):
            raise HTTPException(422,'Vložte odkaz na složku OneDrive nebo SharePoint.')
        share='u!'+base64.urlsafe_b64encode(link.encode()).decode().rstrip('=')
        source=(await graph('GET',f'/shares/{share}/driveItem')).json()
        if 'folder' not in source:raise HTTPException(422,'Odkaz musí vést na složku.')
        drive=source.get('parentReference',{}).get('driveId')
        if not drive:raise HTTPException(422,'Nelze určit úložiště složky.')
        found=[];path=f"/drives/{drive}/items/{source['id']}/children"
        for _ in range(10):
            page=(await graph('GET',path,params={'$top':100} if '?' not in path else {})).json()
            found.extend(page.get('value',[]))
            nxt=page.get('@odata.nextLink')
            if not nxt:break
            if not nxt.startswith('https://graph.microsoft.com/v1.0/'):raise HTTPException(502,'Neplatné stránkování OneDrive.')
            path=nxt.removeprefix('https://graph.microsoft.com/v1.0')
        async with lock():
            parent,data,a=await store.album(album_id);seen={(i.get('drive'),i['file']) for i in a['items']}
            for f in found:
                mime=f.get('file',{}).get('mimeType','')
                if not mime.startswith(('image/','video/','audio/')) or (drive,f['id']) in seen:continue
                if len(a['items'])>=1000:break
                image=f.get('image') or f.get('video') or {}
                a['items'].append({'id':uuid.uuid4().hex,'file':f['id'],'drive':drive,'name':f['name'],
                    'mime':mime,'width':image.get('width',1),'height':image.get('height',1),
                    'date':f.get('photo',{}).get('takenDateTime') or f.get('createdDateTime',''),'size':f.get('size',0)})
            await store.save(parent,data);invalidate(a['id'])
        return a

    @router.get('/api/gallery/{album_id}')
    async def display(album_id:str,token:str=''):
        a=await public(album_id,token)
        return {'id':a['id'],'name':a['name'],'items':[{k:v for k,v in i.items() if k not in ('file','drive','external')} for i in visible(a)],
                'settings':a['settings']}

    @router.get('/api/gallery/{album_id}/files/{item_id}')
    async def media(album_id:str,item_id:str,token:str=''):
        a=await public(album_id,token)
        item=next((i for i in visible(a) if i['id']==item_id),None)
        if not item:raise HTTPException(404,'Soubor nebyl nalezen.')
        url=await download_url(item)
        return RedirectResponse(url,status_code=307,headers={'Cache-Control':'private, no-store','Referrer-Policy':'no-referrer'})
    return router
