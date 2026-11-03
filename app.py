"""Document content service. Shared administration is owned by eduvize-admin."""
import os, json, time, uuid, secrets, asyncio
from pathlib import Path
from collections import OrderedDict
import httpx
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from document_delivery import DocumentDelivery, AsyncCache
from eduvize_admin import runtime as administration
from eduvize_admin.runtime import (check_admin, graph, ensure_folder, child_named, system_folder,
    read_drive_json, profile_write_lock, microsoft_login_db, school_accounts, microsoft_login,
    check_profile_admin, load_tokens, persist_tokens, current_tokens, token_cipher, connected,
    access_token, restore_tokens, save_school_connection, legacy_graph, storage_key, school_context)
ROOT=Path(__file__).resolve().parent
DEFAULT_CATEGORIES=["Oznámení","Akce a události","Výuka a vzdělávání","Úspěchy školy","Kroužky a aktivity","Jídelna","Dokumenty a formuláře","Ostatní"]
MAX_SIZE=100*1024*1024
TYPES={".pdf":"application/pdf",".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".webp":"image/webp",".mp4":"video/mp4",".webm":"video/webm"}
app=FastAPI(title="Eduvize – Dokumenty")
app.add_middleware(CORSMiddleware,allow_origins=["https://eduvize-prubeh-dne.onrender.com","https://pborovicka72-dotcom.github.io","https://eduvize-weather.onrender.com","https://eduvize-aktuality.onrender.com","https://eduvize-design-system-api.onrender.com","https://eduvize-skolni-systemy.onrender.com","http://127.0.0.1:8789","https://eduvize-jidelnicek.onrender.com","http://127.0.0.1:8790"],
    allow_methods=['GET','POST','PUT','PATCH','DELETE'],allow_headers=['Authorization','Content-Type'])
administration.install_admin(app)
lock=asyncio.Lock()
async def read_manifest_item(item):
    data = await read_drive_json(item)
    if not isinstance(data,dict) or not isinstance(data.get("items"),list):
        raise HTTPException(502,"Neplatná struktura systémového manifestu")
    return data

async def manifest_data(folder):
    system = await child_named(folder, "_Eduvize-system")
    if system and "folder" not in system:
        raise HTTPException(409,"Systémový adresář koliduje se souborem")
    if system:
        current = await child_named(system["id"],"manifest.json")
        if current:
            return await read_manifest_item(current)
    # Backwards compatibility: old installations stored manifest.json beside documents.
    legacy = await child_named(folder,"manifest.json")
    if legacy:
        return await read_manifest_item(legacy)
    return {"items":[],"categories":[],"hidden_categories":[]}

async def manifest(folder):
    return (await manifest_data(folder))["items"]

def category_names(data,scope="documents"):
    extra=data.get("categories",[]) if scope=="documents" else []
    names=DEFAULT_CATEGORIES+list(extra)+[x.get("category","") for x in data["items"] if in_document_scope(x,scope)]
    return list(dict.fromkeys(x for x in names if isinstance(x,str) and x.strip()))

async def categories(folder,scope="documents"):
    return category_names(await manifest_data(folder),scope)

async def save_manifest(folder,items,category_names=None,hidden_categories=None):
    system = await system_folder(folder)
    if category_names is None or hidden_categories is None:
        current = await manifest_data(folder)
        if category_names is None:category_names = current.get("categories",[])
        if hidden_categories is None:hidden_categories = current.get("hidden_categories",[])
    data = json.dumps({"items":items,"categories":category_names,"hidden_categories":hidden_categories},ensure_ascii=False).encode()
    await graph("PUT", f"/me/drive/items/{system}:/manifest.json:/content",
                content=data,headers={"Content-Type":"application/json"})
    current_delivery().invalidate()
    # Only remove legacy metadata after the replacement was saved successfully.
    legacy = await child_named(folder,"manifest.json")
    if legacy:
        await graph("DELETE",f"/me/drive/items/{legacy['id']}")
async def all_items():
    folder=await ensure_folder()
    return folder,await manifest(folder)
def document_scope(value):
    if value not in ('documents','kiosk'):
        raise HTTPException(422,"Neplatné určení dokumentu")
    return value

def in_document_scope(item,scope):
    return item.get("scope","documents")==scope

def public_items(items):
    return sorted([{k:v for k,v in item.items() if k!="file_id"} for item in items if item.get("visible",True)],key=lambda x:(x.get("position",0),x["name"]))
@app.get("/health")
def health():return {"status":"ok","central_admin_sessions":True,"school_accounts":True,"microsoft_multitenant":True,"onedrive_configured":bool(administration.CLIENT and administration.SECRET and administration.BASE),"token_storage_configured":bool(administration.DATABASE_URL and administration.TOKEN_ENCRYPTION_KEY),"onedrive_connected_in_memory":bool(administration.tokens.get("refresh_token")),"admin_configured":bool(administration.ADMIN)}
@app.get("/")
@app.get("/display")
def display():return FileResponse(ROOT/"index.html")
@app.get("/config")
def config():return FileResponse(ROOT/"config.html")

# Legacy editor URL remains as a redirect; styles are managed by the standalone service.
@app.get("/design-system")
@app.get("/design-system/")
def design_system_redirect():
    return RedirectResponse("https://eduvize-design-system-api.onrender.com/",status_code=307)

@app.get("/api/document-categories")
async def public_categories():
    folder,items=await all_items()
    data=await manifest_data(folder)
    hidden=set(data.get("hidden_categories",[]))
    visible={x.get("category","Ostatní") for x in items if x.get("visible",True)}
    return {"categories":[name for name in await categories(folder) if name in visible and name not in hidden]}

@app.patch("/api/admin/categories/visibility")
async def category_visibility(request:Request,authorization:str|None=Header(default=None)):
    await check_admin(authorization)
    body=await request.json()
    name=body.get("name")
    visible=body.get("visible")
    if not isinstance(name,str) or not isinstance(visible,bool):
        raise HTTPException(422,"Neplatná změna viditelnosti")
    async with lock:
        folder=await ensure_folder()
        data=await manifest_data(folder)
        items=data["items"]
        if name not in category_names(data):raise HTTPException(404,"Kategorie nenalezena")
        hidden=set(data.get("hidden_categories",[]))
        if visible:hidden.discard(name)
        else:hidden.add(name)
        await save_manifest(folder,items,category_names=data.get("categories",[]),hidden_categories=sorted(hidden))
    return {"ok":True}

@app.get("/api/documents")
async def list_public(scope:str="documents"):
    if scope!="all":document_scope(scope)
    items=await current_delivery().visible_items()
    return {"items":public_items(items if scope=="all" else [x for x in items if in_document_scope(x,scope)])}
@app.get("/api/admin/documents")
async def list_admin(authorization:str|None=Header(default=None),scope:str="documents"):
    await check_admin(authorization);document_scope(scope);_,items=await all_items();items=[x for x in items if in_document_scope(x,scope)]
    return {"items":sorted(items,key=lambda x:(x.get("position",0),x["name"]))}
@app.get("/api/admin/categories")
async def list_categories(authorization:str|None=Header(default=None),scope:str="documents"):
    await check_admin(authorization)
    folder=await ensure_folder()
    data=await manifest_data(folder)
    return {"categories":category_names(data,document_scope(scope)),"hidden_categories":data.get("hidden_categories",[])}

@app.post("/api/admin/categories")
async def create_category(request:Request,authorization:str|None=Header(default=None)):
    await check_admin(authorization)
    payload=await request.json()
    name=str(payload.get("name","")).strip()
    if not name or len(name)>80 or any(ord(c)<32 for c in name):
        raise HTTPException(422,"Název kategorie musí mít 1–80 znaků")
    async with lock:
        folder,items=await all_items()
        existing=await categories(folder)
        if any(x.casefold()==name.casefold() for x in existing):
            raise HTTPException(409,"Kategorie již existuje")
        current=(await manifest_data(folder)).get("categories",[])
        await save_manifest(folder,items,current+[name])
    return {"name":name}

@app.post("/api/admin/documents")
async def upload(file:UploadFile=File(...),category:str=Form("Ostatní"),scope:str=Form("documents"),authorization:str|None=Header(default=None)):
    await check_admin(authorization)
    document_scope(scope)
    ext=Path(file.filename or "").suffix.lower()
    if ext not in TYPES:raise HTTPException(415,"Povoleny jsou PDF, obrázky, MP4 a WebM. Word a PowerPoint nejprve exportujte do PDF.")
    data=await file.read(MAX_SIZE+1)
    if not data:raise HTTPException(422,"Soubor je prázdný. Vyberte neprázdný soubor.")
    if len(data)>MAX_SIZE:raise HTTPException(413,"Soubor je příliš velký. Maximální povolená velikost je 100 MB.")
    checks={".mp4":len(data)>12 and data[4:8]==b"ftyp",".webm":data.startswith(bytes.fromhex("1a45dfa3")),".pdf":data.startswith(b"%PDF-"),".png":data.startswith(bytes.fromhex("89504e470d0a1a0a")),".jpg":data.startswith(bytes.fromhex("ffd8ff")),".jpeg":data.startswith(bytes.fromhex("ffd8ff")),".webp":data.startswith(b"RIFF") and data[8:12]==b"WEBP"}
    if not checks[ext]:raise HTTPException(415,"Neplatný formát souboru")
    async with lock:
        folder,items=await all_items()
        allowed=await categories(folder,scope)
        if category not in allowed:raise HTTPException(422,"Vyberte kategorii ze seznamu")
        doc_id=uuid.uuid4().hex
        name=doc_id+ext
        r=await graph("PUT",f"/me/drive/items/{folder}:/{name}:/content",content=data,headers={"Content-Type":TYPES[ext]})
        entry={"scope":scope,"id":doc_id,"file_id":r.json()["id"],"name":Path(file.filename or "Dokument").name[:180],"category":category.strip()[:80] or "Ostatní","mime":TYPES[ext],"position":max([x.get("position",0) for x in items],default=-1)+1,"visible":True}
        items.append(entry)
        await save_manifest(folder,items)
    return {"id":doc_id,"name":entry["name"]}
@app.post("/api/admin/documents/reorder")
async def reorder_documents(request:Request,authorization:str|None=Header(default=None),scope:str="documents"):
    await check_admin(authorization)
    body=await request.json()
    order=body.get("ids")
    if not isinstance(order,list) or not all(isinstance(x,str) for x in order) or len(order)!=len(set(order)):
        raise HTTPException(422,"Neplatné pořadí dokumentů")
    async with lock:
        folder,items=await all_items()
        document_scope(scope)
        if set(order)!={x["id"] for x in items if in_document_scope(x,scope)}:
            raise HTTPException(409,"Seznam dokumentů se změnil, načtěte jej znovu")
        positions={doc_id:i for i,doc_id in enumerate(order)}
        for item in items:
            if item["id"] in positions:item["position"]=positions[item["id"]]
        await save_manifest(folder,items)
    return {"ok":True}

async def apply_document_changes(changes):
    if not isinstance(changes,list) or not 1<=len(changes)<=100:
        raise HTTPException(422,"Neplatný počet změn dokumentů")
    async with lock:
        folder=await ensure_folder()
        data=await manifest_data(folder)
        items=data["items"]
        by_id={item["id"]:item for item in items}
        allowed=category_names(data)
        for change in changes:
            if not isinstance(change,dict):raise HTTPException(422,"Neplatná změna dokumentu")
            item=by_id.get(change.get("id"))
            if not item:raise HTTPException(404,"Dokument nenalezen")
            for key in ("name","category","title"):
                if key in change:item[key]=str(change[key]).strip()[:180 if key in ("name","title") else 80] or ("" if key=="title" else "Ostatní")
            if "category" in change and item["category"] not in allowed:raise HTTPException(422,"Neznámá kategorie")
            if "position" in change:item["position"]=int(change["position"])
            if "visible" in change:item["visible"]=bool(change["visible"])
        await save_manifest(folder,items,category_names=data.get("categories",[]),hidden_categories=data.get("hidden_categories",[]))
    return {"ok":True}

@app.patch("/api/admin/documents/batch")
async def edit_batch(request:Request,authorization:str|None=Header(default=None)):
    await check_admin(authorization)
    body=await request.json()
    return await apply_document_changes(body.get("changes") if isinstance(body,dict) else None)

@app.patch("/api/admin/documents/{doc_id}")
async def edit(doc_id:str,request:Request,authorization:str|None=Header(default=None)):
    await check_admin(authorization)
    body=await request.json()
    return await apply_document_changes([{**body,"id":doc_id}])
@app.delete("/api/admin/documents/{doc_id}")
async def delete(doc_id:str,authorization:str|None=Header(default=None)):
    await check_admin(authorization)
    async with lock:
        folder,items=await all_items()
        item=next((x for x in items if x["id"]==doc_id),None)
        if not item:raise HTTPException(404,"Dokument nenalezen")
        await graph("DELETE",f"/me/drive/items/{item['file_id']}")
        current_delivery().invalidate()
        await save_manifest(folder,[x for x in items if x["id"]!=doc_id])
    return {"ok":True}
async def load_public_manifest():
    return await manifest_data(await ensure_folder())

async def download_document(item):
    response = await graph("GET", f"/me/drive/items/{item['file_id']}/content")
    if response.status_code in (301,302,303,307,308):
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.get(response.headers["location"])
            if response.status_code != 200:
                raise HTTPException(502,"Nepodařilo se načíst soubor")
    return response.content

school_file_cache=AsyncCache(60,64*1024*1024,weight=lambda asset:len(asset.data))
document_delivery = DocumentDelivery(load_public_manifest, download_document,file_cache=school_file_cache,namespace='legacy')
deliveries=OrderedDict()
def current_delivery():
    school=school_context.get()
    if not school or school['legacy']:return document_delivery
    if school['id'] not in deliveries:
        while len(deliveries)>=64:deliveries.popitem(last=False)
        deliveries[school['id']]=DocumentDelivery(load_public_manifest,download_document,file_cache=school_file_cache,namespace=school['id'])
    deliveries.move_to_end(school['id'])
    return deliveries[school['id']]

@app.get("/api/documents/{doc_id}/file")
async def get_file(doc_id:str, request:Request):
    try:
        item, asset = await current_delivery().file(doc_id)
    except KeyError:
        raise HTTPException(404,"Dokument nenalezen")
    headers = {"Cache-Control":"private, no-cache", "ETag":asset.etag, "X-Content-Type-Options":"nosniff"}
    validators = [value.strip().removeprefix('W/') for value in request.headers.get('if-none-match', '').split(',')]
    if asset.etag in validators or '*' in validators:
        return Response(status_code=304, headers=headers)
    return Response(content=asset.data, media_type=item['mime'], headers=headers)


# Old gallery API URLs delegate to the separate photo gallery package.
from eduvize_gallery.gallery import gallery_router
app.include_router(gallery_router(graph, ensure_folder, child_named, read_drive_json,
                                 check_admin, profile_write_lock, storage_key))
def storage_changed(school):
    if school['legacy']:document_delivery.invalidate()
    deliveries.pop(school['id'],None)
administration.storage_change_handlers.append(storage_changed)

# Capability-scoped kiosk mobile control; no administration access.
from kiosk_remote import remote_router
app.include_router(remote_router(administration.DATABASE_URL))
