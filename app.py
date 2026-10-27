"""Eduvize Documents: minimal server-side Google OAuth prototype.
Production deployment needs persistent encrypted token storage, school admin authorization,
CSRF protection for publishing, and a per-school tenant model.
"""
import os, secrets, time
from urllib.parse import urlencode
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app=FastAPI(title="Eduvize Documents OAuth")
FRONTEND=os.getenv("FRONTEND_URL","https://pborovicka72-dotcom.github.io/eduvize-dokumenty/config.html")
ORIGIN="https://pborovicka72-dotcom.github.io"
CLIENT_ID=os.getenv("GOOGLE_CLIENT_ID","")
CLIENT_SECRET=os.getenv("GOOGLE_CLIENT_SECRET","")
BASE=os.getenv("PUBLIC_BASE_URL","").rstrip("/")
SCOPES="openid email profile https://www.googleapis.com/auth/drive.readonly"
pending={}
sessions={}
app.add_middleware(CORSMiddleware,allow_origins=[ORIGIN],allow_credentials=True,allow_methods=["GET","POST"],allow_headers=["Content-Type"])

@app.get("/health")
def health():
    return {"status":"ok","google_configured":bool(CLIENT_ID and CLIENT_SECRET and BASE)}

@app.get("/auth/google/start")
def start():
    if not (CLIENT_ID and CLIENT_SECRET and BASE):
        raise HTTPException(503,"Google OAuth is not configured on server")
    state=secrets.token_urlsafe(32)
    pending[state]=time.time()+600
    params=dict(client_id=CLIENT_ID,redirect_uri=BASE+"/auth/google/callback",response_type="code",scope=SCOPES,state=state,access_type="offline",prompt="consent")
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?"+urlencode(params))

@app.get("/auth/google/callback")
async def callback(code:str="",state:str="",error:str=""):
    expiry=pending.pop(state,None)
    if error or not code or not expiry or expiry<time.time():
        raise HTTPException(400,"Invalid or expired OAuth authorization")
    async with httpx.AsyncClient(timeout=20) as client:
        r=await client.post("https://oauth2.googleapis.com/token",data=dict(code=code,client_id=CLIENT_ID,client_secret=CLIENT_SECRET,redirect_uri=BASE+"/auth/google/callback",grant_type="authorization_code"))
        if r.status_code!=200: raise HTTPException(400,"Google token exchange failed")
        token=r.json()
        u=await client.get("https://www.googleapis.com/oauth2/v3/userinfo",headers={"Authorization":"Bearer "+token["access_token"]})
        if u.status_code!=200: raise HTTPException(400,"Google identity check failed")
        profile=u.json()
        if not profile.get("email_verified"): raise HTTPException(403,"Google email is not verified")
    sid=secrets.token_urlsafe(32)
    sessions[sid]={"email":profile["email"],"name":profile.get("name",""),"token":token,"expires":time.time()+int(token.get("expires_in",3600))}
    response=RedirectResponse(FRONTEND+"#google-connected")
    response.set_cookie("eduvize_docs_session",sid,httponly=True,secure=True,samesite="none",max_age=3600)
    return response

@app.get("/api/me")
def me(request:Request):
    s=sessions.get(request.cookies.get("eduvize_docs_session",""))
    if not s:return JSONResponse({"connected":False})
    return {"connected":True,"email":s["email"],"name":s["name"]}

@app.post("/auth/logout")
def logout(request:Request):
    sessions.pop(request.cookies.get("eduvize_docs_session",""),None)
    response=JSONResponse({"connected":False})
    response.delete_cookie("eduvize_docs_session",secure=True,samesite="none")
    return response

@app.get("/api/folders")
async def folders(request:Request,folder_id:str="root"):
    s=sessions.get(request.cookies.get("eduvize_docs_session",""))
    if not s:raise HTTPException(401,"Sign in required")
    if time.time()>=s["expires"]:raise HTTPException(401,"Session expired; sign in again")
    safe=folder_id.replace("'","\\'")
    query=f"'{safe}' in parents and trashed = false"
    async with httpx.AsyncClient(timeout=20) as client:
        r=await client.get("https://www.googleapis.com/drive/v3/files",params={"q":query,"fields":"nextPageToken,files(id,name,mimeType,modifiedTime)","page_size":100},headers={"Authorization":"Bearer "+s["token"]["access_token"]})
    if r.status_code!=200:raise HTTPException(502,"Unable to read Google Drive folder")
    return r.json()
