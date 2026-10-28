"""Eduvize Dokumenty: upload-based school signage, no Google integration."""
import os, sqlite3, secrets, uuid, mimetypes
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

BASE=Path(__file__).resolve().parent
STORE=Path(os.environ.get("DOCUMENTS_STORAGE_DIR","/tmp/eduvize-documents"))
STORE.mkdir(parents=True,exist_ok=True)
DB=STORE/"documents.sqlite3"
TOKEN=os.environ.get("DOCUMENTS_ADMIN_TOKEN","")
MAX_SIZE=20*1024*1024
TYPES={".pdf":"application/pdf",".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".webp":"image/webp"}
app=FastAPI(title="Eduvize – Dokumenty")
app.add_middleware(CORSMiddleware,allow_origins=["https://pborovicka72-dotcom.github.io"],allow_methods=["GET","POST","PATCH","DELETE"],allow_headers=["Authorization","Content-Type"])
@contextmanager
def database():
    con=sqlite3.connect(DB)
    con.row_factory=sqlite3.Row
    try:
        yield con
        con.commit()
    finally:con.close()
with database() as db:
    db.execute("CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'Ostatní', filename TEXT NOT NULL, mime TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0, visible INTEGER NOT NULL DEFAULT 1)")
def admin(authorization):
    if not TOKEN:raise HTTPException(503,"Set DOCUMENTS_ADMIN_TOKEN before enabling administration")
    if not authorization or not secrets.compare_digest(authorization,"Bearer "+TOKEN):
        raise HTTPException(401,"Neplatný administrační klíč")
def rows():
    with database() as db:
        return [dict(x) for x in db.execute("SELECT id,name,category,mime,position,visible FROM documents ORDER BY position,name")]
@app.get("/health")
def health():return {"status":"ok","storage":str(STORE),"admin_configured":bool(TOKEN)}
@app.get("/")
def home():return FileResponse(BASE/"index.html")
@app.get("/display")
def display():return FileResponse(BASE/"index.html")
@app.get("/config")
def config():return FileResponse(BASE/"config.html")
@app.get("/api/documents")
def documents():return {"items":[x for x in rows() if x["visible"]]}
@app.get("/api/admin/documents")
def admin_documents(authorization:str|None=Header(default=None)):
    admin(authorization);return {"items":rows()}
@app.post("/api/admin/documents")
async def upload(file:UploadFile=File(...),category:str=Form("Ostatní"),authorization:str|None=Header(default=None)):
    admin(authorization)
    suffix=Path(file.filename or "").suffix.lower()
    if suffix not in TYPES:raise HTTPException(415,"Povoleny jsou PDF, PNG, JPG a WebP")
    data=await file.read(MAX_SIZE+1)
    if not data or len(data)>MAX_SIZE:raise HTTPException(413,"Soubor musí mít nejvýše 20 MB")
    signatures={".pdf":data.startswith(b"%PDF-"),".png":data.startswith(b"\x89PNG\r\n\x1a\n"),".jpg":data.startswith(b"\xff\xd8\xff"),".jpeg":data.startswith(b"\xff\xd8\xff"),".webp":data.startswith(b"RIFF") and data[8:12]==b"WEBP"}
    if not signatures[suffix]:raise HTTPException(415,"Obsah souboru neodpovídá příponě")
    doc_id=uuid.uuid4().hex
    filename=doc_id+suffix
    (STORE/filename).write_bytes(data)
    name=Path(file.filename or "Dokument").name[:180]
    with database() as db:
        pos=db.execute("SELECT COALESCE(MAX(position),-1)+1 FROM documents").fetchone()[0]
        db.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,1)",(doc_id,name,category.strip()[:80] or "Ostatní",filename,TYPES[suffix],pos))
    return {"id":doc_id,"name":name}
@app.patch("/api/admin/documents/{doc_id}")
async def edit(doc_id:str,request:Request,authorization:str|None=Header(default=None)):
    admin(authorization)
    body=await request.json()
    changes={k:body[k] for k in ("name","category","position","visible") if k in body}
    if not changes:raise HTTPException(400,"Žádné změny")
    if "name" in changes:changes["name"]=str(changes["name"]).strip()[:180] or "Dokument"
    if "category" in changes:changes["category"]=str(changes["category"]).strip()[:80] or "Ostatní"
    if "position" in changes:changes["position"]=int(changes["position"])
    if "visible" in changes:changes["visible"]=int(bool(changes["visible"]))
    with database() as db:
        row=db.execute("SELECT id FROM documents WHERE id=?",(doc_id,)).fetchone()
        if not row:raise HTTPException(404,"Dokument nenalezen")
        db.execute("UPDATE documents SET "+",".join(k+"=?" for k in changes)+" WHERE id=?",(*changes.values(),doc_id))
    return {"ok":True}
@app.delete("/api/admin/documents/{doc_id}")
def delete(doc_id:str,authorization:str|None=Header(default=None)):
    admin(authorization)
    with database() as db:
        row=db.execute("SELECT filename FROM documents WHERE id=?",(doc_id,)).fetchone()
        if not row:raise HTTPException(404,"Dokument nenalezen")
        db.execute("DELETE FROM documents WHERE id=?",(doc_id,))
    (STORE/row["filename"]).unlink(missing_ok=True)
    return {"ok":True}
@app.get("/api/documents/{doc_id}/file")
def file(doc_id:str):
    with database() as db:
        row=db.execute("SELECT * FROM documents WHERE id=? AND visible=1",(doc_id,)).fetchone()
    if not row:raise HTTPException(404,"Dokument nenalezen")
    path=STORE/row["filename"]
    if not path.is_file():raise HTTPException(404,"Soubor nenalezen")
    return FileResponse(path,media_type=row["mime"],headers={"Content-Security-Policy":"default-src 'none'; sandbox","X-Content-Type-Options":"nosniff","Cache-Control":"no-store"})
