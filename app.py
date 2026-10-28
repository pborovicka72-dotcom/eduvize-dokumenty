"""Eduvize Dokumenty: Microsoft OneDrive-backed test deployment."""
import os, json, time, uuid, secrets, asyncio
from pathlib import Path
from urllib.parse import urlencode, quote
import httpx
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.middleware.cors import CORSMiddleware

ROOT=Path(__file__).resolve().parent
CLIENT=os.getenv("MICROSOFT_CLIENT_ID","")
SECRET=os.getenv("MICROSOFT_CLIENT_SECRET","")
TENANT=os.getenv("MICROSOFT_TENANT_ID","common")
ADMIN=os.getenv("DOCUMENTS_ADMIN_TOKEN","")
BASE=os.getenv("PUBLIC_BASE_URL","").rstrip("/")
SCOPES="offline_access User.Read Files.ReadWrite"
AUTH=f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0"
GRAPH="https://graph.microsoft.com/v1.0"
FOLDER="Eduvize-Dokumenty"
MAX_SIZE=20*1024*1024
TYPES={".pdf":"application/pdf",".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".webp":"image/webp"}
pending={}
tokens={}
lock=asyncio.Lock()
app=FastAPI(title="Eduvize – Dokumenty / OneDrive")
app.add_middleware(CORSMiddleware,allow_origins=["https://pborovicka72-dotcom.github.io"],allow_methods=["GET","POST","PATCH","DELETE"],allow_headers=["Authorization","Content-Type"])

def check_admin(auth):
    if not ADMIN:raise HTTPException(503,"Set DOCUMENTS_ADMIN_TOKEN in Render Environment")
    if not auth or not secrets.compare_digest(auth,"Bearer "+ADMIN):raise HTTPException(401,"Neplatný administrační klíč")
def require_config():
    if not (CLIENT and SECRET and BASE):raise HTTPException(503,"Set MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET and PUBLIC_BASE_URL")
def redirect_uri():return BASE+"/auth/microsoft/callback"
def connected():
    if not tokens.get("refresh_token"):raise HTTPException(503,"OneDrive není připojen. Přihlaste se v administraci.")
async def access_token():
    connected()
    if tokens.get("access_token") and time.time()<tokens.get("expires",0)-90:return tokens["access_token"]
    async with httpx.AsyncClient(timeout=25) as client:
        r=await client.post(AUTH+"/token",data={"client_id":CLIENT,"client_secret":SECRET,"grant_type":"refresh_token","refresh_token":tokens["refresh_token"],"scope":SCOPES})
    if r.status_code!=200:raise HTTPException(503,"OneDrive připojení vypršelo, přihlaste se znovu")
    t=r.json();tokens.update(access_token=t["access_token"],refresh_token=t.get("refresh_token",tokens["refresh_token"]),expires=time.time()+t.get("expires_in",3600))
    return tokens["access_token"]
async def graph(method,path,**kwargs):
    token=await access_token()
    async with httpx.AsyncClient(timeout=45,follow_redirects=False) as client:
        r=await client.request(method,GRAPH+path,headers={"Authorization":"Bearer "+token,**kwargs.pop("headers",{})},**kwargs)
    if r.status_code>=400:raise HTTPException(502,"Microsoft Graph error ("+str(r.status_code)+"): "+r.text[:220])
    return r
async def ensure_folder():
    r=await graph("GET","/me/drive/root/children",params={"$select":"id,name,folder","$top":200})
    for item in r.json().get("value",[]):
        if item["name"]==FOLDER and "folder" in item:return item["id"]
    r=await graph("POST","/me/drive/root/children",json={"name":FOLDER,"folder":{},"@microsoft.graph.conflictBehavior":"fail"})
    return r.json()["id"]
async def child_named(parent, name):
    # Read folder children; do not silently replace metadata if the lookup fails.
    r = await graph("GET", f"/me/drive/items/{parent}/children", params={"$select":"id,name,folder", "$top":200})
    return next((x for x in r.json().get("value", []) if x["name"] == name), None)

async def system_folder(folder):
    item = await child_named(folder, "_Eduvize-system")
    if item:
        if "folder" not in item:
            raise HTTPException(409, "Systémový adresář koliduje se souborem")
        return item["id"]
    r = await graph("POST", f"/me/drive/items/{folder}/children",
                    json={"name":"_Eduvize-system","folder":{},"@microsoft.graph.conflictBehavior":"fail"})
    return r.json()["id"]

async def read_manifest_item(item):
    response = await graph("GET", f"/me/drive/items/{item['id']}/content")
    if response.status_code in (301,302,303,307,308):
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(response.headers["location"])
            response.raise_for_status()
    data = response.json()
    if not isinstance(data,dict) or not isinstance(data.get("items"),list):
        raise HTTPException(502,"Neplatná struktura systémového manifestu")
    return data["items"]

async def manifest(folder):
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
    return []

async def save_manifest(folder,items):
    system = await system_folder(folder)
    data = json.dumps({"items":items},ensure_ascii=False).encode()
    await graph("PUT", f"/me/drive/items/{system}:/manifest.json:/content",
                content=data,headers={"Content-Type":"application/json"})
    # Only remove legacy metadata after the replacement was saved successfully.
    legacy = await child_named(folder,"manifest.json")
    if legacy:
        await graph("DELETE",f"/me/drive/items/{legacy['id']}")
async def all_items():
    folder=await ensure_folder()
    return folder,await manifest(folder)
def public_items(items):
    return sorted([{k:v for k,v in item.items() if k!="file_id"} for item in items if item.get("visible",True)],key=lambda x:(x.get("position",0),x["name"]))
@app.get("/health")
def health():return {"status":"ok","onedrive_configured":bool(CLIENT and SECRET and BASE),"onedrive_connected":bool(tokens.get("refresh_token")),"admin_configured":bool(ADMIN)}
@app.get("/")
@app.get("/display")
def display():return FileResponse(ROOT/"index.html")
@app.get("/config")
def config():return FileResponse(ROOT/"config.html")
@app.post("/api/admin/microsoft/start")
def auth_start(authorization:str|None=Header(default=None)):
    check_admin(authorization);require_config()
    state=secrets.token_urlsafe(32);pending[state]=time.time()+600
    params={"client_id":CLIENT,"response_type":"code","redirect_uri":redirect_uri(),"response_mode":"query","scope":SCOPES,"state":state}
    return {"url":AUTH+"/authorize?"+urlencode(params)}
@app.get("/auth/microsoft/callback")
async def auth_callback(code:str="",state:str="",error:str=""):
    expiry=pending.pop(state,None)
    if error or not code or not expiry or expiry<time.time():raise HTTPException(400,"Přihlášení bylo zrušeno nebo vypršelo")
    async with httpx.AsyncClient(timeout=25) as client:
        r=await client.post(AUTH+"/token",data={"client_id":CLIENT,"client_secret":SECRET,"code":code,"redirect_uri":redirect_uri(),"grant_type":"authorization_code","scope":SCOPES})
    if r.status_code!=200:raise HTTPException(400,"Nepodařilo se získat přístupový token: "+r.text[:200])
    t=r.json()
    tokens.update(access_token=t["access_token"],refresh_token=t.get("refresh_token"),expires=time.time()+t.get("expires_in",3600))
    if not tokens.get("refresh_token"):raise HTTPException(400,"Microsoft nevrátil obnovovací token")
    return RedirectResponse("/config?connected=1")
@app.get("/api/admin/status")
def status(authorization:str|None=Header(default=None)):
    check_admin(authorization);return {"connected":bool(tokens.get("refresh_token"))}
@app.get("/api/documents")
async def list_public():
    _,items=await all_items()
    return {"items":public_items(items)}
@app.get("/api/admin/documents")
async def list_admin(authorization:str|None=Header(default=None)):
    check_admin(authorization);_,items=await all_items()
    return {"items":sorted(items,key=lambda x:(x.get("position",0),x["name"]))}
@app.post("/api/admin/documents")
async def upload(file:UploadFile=File(...),category:str=Form("Ostatní"),authorization:str|None=Header(default=None)):
    check_admin(authorization)
    ext=Path(file.filename or "").suffix.lower()
    if ext not in TYPES:raise HTTPException(415,"Povoleny PDF, PNG, JPG a WebP")
    data=await file.read(MAX_SIZE+1)
    if not data or len(data)>MAX_SIZE:raise HTTPException(413,"Limit je 20 MB")
    checks={".pdf":data.startswith(b"%PDF-"),".png":data.startswith(bytes.fromhex("89504e470d0a1a0a")),".jpg":data.startswith(bytes.fromhex("ffd8ff")),".jpeg":data.startswith(bytes.fromhex("ffd8ff")),".webp":data.startswith(b"RIFF") and data[8:12]==b"WEBP"}
    if not checks[ext]:raise HTTPException(415,"Neplatný formát souboru")
    async with lock:
        folder,items=await all_items()
        doc_id=uuid.uuid4().hex
        name=doc_id+ext
        r=await graph("PUT",f"/me/drive/items/{folder}:/{name}:/content",content=data,headers={"Content-Type":TYPES[ext]})
        entry={"id":doc_id,"file_id":r.json()["id"],"name":Path(file.filename or "Dokument").name[:180],"category":category.strip()[:80] or "Ostatní","mime":TYPES[ext],"position":max([x.get("position",0) for x in items],default=-1)+1,"visible":True}
        items.append(entry)
        await save_manifest(folder,items)
    return {"id":doc_id,"name":entry["name"]}
@app.patch("/api/admin/documents/{doc_id}")
async def edit(doc_id:str,request:Request,authorization:str|None=Header(default=None)):
    check_admin(authorization);body=await request.json()
    async with lock:
        folder,items=await all_items()
        item=next((x for x in items if x["id"]==doc_id),None)
        if not item:raise HTTPException(404,"Dokument nenalezen")
        for key in ("name","category"):
            if key in body:item[key]=str(body[key]).strip()[:180 if key=="name" else 80] or "Ostatní"
        if "position" in body:item["position"]=int(body["position"])
        if "visible" in body:item["visible"]=bool(body["visible"])
        await save_manifest(folder,items)
    return {"ok":True}
@app.delete("/api/admin/documents/{doc_id}")
async def delete(doc_id:str,authorization:str|None=Header(default=None)):
    check_admin(authorization)
    async with lock:
        folder,items=await all_items()
        item=next((x for x in items if x["id"]==doc_id),None)
        if not item:raise HTTPException(404,"Dokument nenalezen")
        await graph("DELETE",f"/me/drive/items/{item['file_id']}")
        await save_manifest(folder,[x for x in items if x["id"]!=doc_id])
    return {"ok":True}
@app.get("/api/documents/{doc_id}/file")
async def get_file(doc_id:str):
    _,items=await all_items()
    item=next((x for x in items if x["id"]==doc_id and x.get("visible",True)),None)
    if not item:raise HTTPException(404,"Dokument nenalezen")
    r=await graph("GET",f"/me/drive/items/{item['file_id']}/content")
    if r.status_code in (301,302,303,307,308):
        async with httpx.AsyncClient(timeout=45) as client:
            r=await client.get(r.headers["location"])
            if r.status_code!=200:raise HTTPException(502,"Nepodařilo se načíst soubor")
    return Response(content=r.content,media_type=item["mime"],headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})
