"""Generated output links stored in the selected school's existing OneDrive profile."""
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from fastapi import HTTPException, Request

APP_NAMES={'day-progress':'Průběh dne','kiosk':'Kiosek','documents':'Dokumenty školy','weather':'Počasí','holidays':'Svátky a jmeniny','transport':'Jízdní řády','wisdom':'Moudrost dne','news':'Aktuality školy','school-systems':'Školní informační systémy','menu':'Jídelníček'}
HOSTS={'eduvize-prubeh-dne.onrender.com':'day-progress','eduvize-kiosek.onrender.com':'kiosk','eduvize-dokumenty-api.onrender.com':'documents','eduvize-weather.onrender.com':'weather','eduvize-aktuality.onrender.com':'news','eduvize-skolni-systemy.onrender.com':'school-systems','eduvize-jidelnicek.onrender.com':'menu'}
REPOS={'eduvize-prubeh-dne':'day-progress','eduvize-kiosek':'kiosk','eduvize-dokumenty':'documents','eduvize-pocasi':'weather','eduvize-aktuality':'news','eduvize-svatky':'holidays','eduvize-jizdni-rady':'transport','eduvize-moudrost-dne':'wisdom','eduvize-skolni-systemy':'school-systems','eduvize-jidelnicek':'menu'}
NOISE={'v','preview','ev_inner','eduvize_ui_version','build'}
FORBIDDEN={'token','access_token','refresh_token','password','secret','key','admin_key','edu-auth-code','authorization'}

def stamp():return datetime.now(timezone.utc).isoformat()

def describe_url(value):
    if not isinstance(value,str) or len(value)>200000:raise HTTPException(422,'Neplatný výstupní odkaz.')
    try:
        u=urlsplit(value);query=dict(parse_qsl(u.query,keep_blank_values=True));fragment=dict(parse_qsl(u.fragment));port=u.port
    except ValueError:raise HTTPException(422,'Neplatný výstupní odkaz.') from None
    if u.scheme not in ('https','http') or u.username or u.password or any(k.lower() in FORBIDDEN for k in [*query,*fragment]):raise HTTPException(422,'Odkaz nesmí obsahovat přihlašovací údaje.')
    app=HOSTS.get(u.hostname)
    if u.hostname=='pborovicka72-dotcom.github.io':app=REPOS.get(u.path.strip('/').split('/')[0])
    if u.hostname in ('localhost','127.0.0.1') and port in (8765,8789,8790):app={8765:'kiosk',8789:'school-systems',8790:'menu'}[port]
    if not app or re.search(r'/(?:config(?:\.html)?|editor\.html|ucet\.html)(?:/|$)',u.path) or '/api/' in u.path:raise HTTPException(422,'Vyberte výstup aplikace Eduvize, nikoli administraci.')
    mode='web' if query.get('viewMode')=='web' or query.get('output')=='web' else 'kiosk' if query.get('viewMode')=='kiosk' or query.get('output')=='kiosk' else 'nsp' if query.get('viewMode')=='nsp' or query.get('layout')=='signage' or 'segment_style' in query or ('orientation' in query and 'style' in query) or u.path.endswith('/signage.html') else 'kiosk' if app=='kiosk' else 'web'
    interaction='interactive' if app=='kiosk' or mode=='kiosk' else query.get('interaction') if query.get('interaction') in ('interactive','display') else 'interactive' if mode=='web' else 'display'
    def number(key,fallback):
        raw=query.get('segment_'+key,query.get(key,str(fallback)))
        try:n=int(raw)
        except (ValueError,TypeError):n=fallback
        return n if 1<=n<=20 else fallback
    orientation=query.get('segment_orientation',query.get('orientation','landscape'))
    orientation='portrait' if orientation=='portrait' else 'landscape'
    clean=urlunsplit((u.scheme,u.netloc,u.path,u.query,''))
    canonical=urlunsplit((u.scheme,u.netloc,u.path,urlencode(sorted((k,v)for k,v in parse_qsl(u.query,keep_blank_values=True)if k not in NOISE)),''))
    details=[]
    if app=='menu':details.append('Denní nabídka' if query.get('presentation')=='day' or query.get('days')=='1' else 'Přehled '+query.get('days','5')+' dnů');details.append('Jídelna '+query.get('canteen','11592'))
    for key,label in [('name','Název'),('misto','Lokalita'),('place','Lokalita'),('category','Kategorie')]:
        if query.get(key):details.append(label+': '+query[key][:120])
    return {'id':hashlib.sha256(canonical.encode()).hexdigest(),'url':clean,'app':app,'appName':APP_NAMES[app],'output':mode,'interaction':interaction,'interactive':interaction=='interactive','orientation':orientation if mode=='nsp' else 'responsive' if mode=='web' else 'screen','style':number('style',1)if mode=='nsp' else None,'segment':number('block',1)if mode=='nsp' else None,'details':' · '.join(details)[:400]}

def validate_library(config):
    items=config.get('items',[])
    if not isinstance(items,list) or len(items)>500:raise HTTPException(422,'Seznam může obsahovat nejvýše 500 odkazů.')
    for item in items:
        if not isinstance(item,dict):raise HTTPException(422,'Neplatný záznam odkazu.')
        info=describe_url(item.get('url'))
        if item.get('id')!=info['id'] or item.get('app')!=info['app']:raise HTTPException(422,'Nesouhlasí identifikace odkazu.')
        if not isinstance(item.get('label',''),str) or len(item.get('label',''))>120:raise HTTPException(422,'Název odkazu může mít nejvýše 120 znaků.')
    return config

def segment_key(item):
    info=describe_url(item['url'])
    return (info['app'],info['output'],info['orientation'],info['style'],info['segment'],info['interaction']) if info['output']=='nsp' else (info['id'],)

def latest_segments(items):
    newest={}
    for item in sorted(items,key=lambda x:x.get('copiedAt',''),reverse=True):
        newest.setdefault(segment_key(item),{**item,**describe_url(item['url'])})
    return list(newest.values())

def upsert(items,url,label='',now=None,capture_id=None):
    info=describe_url(url);now=now or stamp();old=next((x for x in latest_segments(items) if segment_key(x)==segment_key(info)),None)
    if capture_id and old and old.get('captureId')==capture_id:return items,old
    record={**info,'label':old.get('label','') if old else str(label or '')[:120],'createdAt':old['createdAt']if old else now,'copiedAt':now,'copies':int(old.get('copies',0))+1 if old else 1}
    if capture_id:record['captureId']=str(capture_id)[:80]
    result=[record]+[x for x in latest_segments(items) if segment_key(x)!=segment_key(record)]
    validate_library({'items':result})
    return result,record

def add_routes(router,store):
    async def read(profile_id):
        profile=await store.read(profile_id);entry=profile['apps'].get('generated-links',{})
        config=entry.get('config',{});items=[] if config.get('empty') else config.get('items',[])
        return profile,entry,latest_segments(items)
    async def change(profile_id,operation):
        for attempt in range(4):
            profile,entry,items=await read(profile_id);items,result=operation(items)
            try:
                await store.save_app(profile_id,'generated-links',{'schemaVersion':1,'items':items},entry.get('revision',0))
                return result
            except HTTPException as error:
                if error.status_code!=409 or attempt==3:raise
    @router.get('/{profile_id}/generated-links')
    async def list_links(profile_id:str):
        profile,entry,items=await read(profile_id)
        return {'profileId':profile_id,'profileName':profile['name'],'items':items,'revision':entry.get('revision',0)}
    @router.post('/{profile_id}/generated-links')
    async def create_link(profile_id:str,request:Request):
        from configuration_profiles import decode
        body=decode(await request.body())
        return await change(profile_id,lambda items:upsert(items,body.get('url'),body.get('label',''),capture_id=body.get('captureId')))
    @router.patch('/{profile_id}/generated-links/{link_id}')
    async def rename_link(profile_id:str,link_id:str,request:Request):
        from configuration_profiles import decode
        body=decode(await request.body());label=body.get('label')
        if not isinstance(label,str) or len(label)>120:raise HTTPException(422,'Název odkazu může mít nejvýše 120 znaků.')
        def rename(items):
            found=next((x for x in items if x['id']==link_id),None)
            if not found:raise HTTPException(404,'Odkaz nebyl nalezen.')
            result={**found,'label':label.strip()}
            return [result if x['id']==link_id else x for x in items],result
        return await change(profile_id,rename)
    @router.delete('/{profile_id}/generated-links/{link_id}')
    async def delete_link(profile_id:str,link_id:str):
        return await change(profile_id,lambda items:([x for x in items if x['id']!=link_id],{'deleted':True}))
