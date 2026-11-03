"""Durable school update preferences; public responses expose timing only."""
import time
import httpx
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from school_accounts import school_context, LEGACY_PROFILE

ZONE=ZoneInfo("Europe/Prague")
APPS={
 "weather":("Počasí",300),"transport":("Jízdní řády",30),
 "news":("Aktuality",300),"menu":("Jídelníček",1800),
 "documents":("Dokumenty",300),"kiosk":("Kiosek",300),
 "wisdom":("Moudrost dne",3600),"holidays":("Svátky",60),
 "styles":("Správa stylů",300),"school-systems":("Školní systémy",120),
 "day-progress":("Průběh dne",60),
}
FREQUENCIES={"off","weekly","monthly","quarterly","yearly"}
STATUS_URL="https://pborovicka72-dotcom.github.io/eduvize-styly/design-system/update-status.json"
_status_cache={"time":0,"data":{}}
def maintenance_status():
    if time.monotonic()-_status_cache["time"]<60:return _status_cache["data"]
    try:
        response=httpx.get(STATUS_URL,timeout=6);response.raise_for_status()
        data=response.json()
        if not isinstance(data.get("apps"),dict):raise ValueError("Invalid status")
        _status_cache.update(time=time.monotonic(),data=data["apps"])
    except (httpx.HTTPError,ValueError):
        _status_cache["time"]=time.monotonic()
    return _status_cache["data"]


def next_due(frequency,after):
    if frequency=="off":return None
    after=datetime.fromisoformat(after.replace("Z","+00:00")).astimezone(ZONE)
    day=after.replace(hour=9,minute=0,second=0,microsecond=0)
    for _ in range(370):
        if day>after and (frequency=="weekly" and day.weekday()==0 or
          frequency=="monthly" and day.day==1 or
          frequency=="quarterly" and day.day==1 and day.month in (1,4,7,10) or
          frequency=="yearly" and day.day==1 and day.month==1):
            return day.isoformat()
        day+=timedelta(days=1)
    raise ValueError("Unsupported frequency")

def validate(body):
    seconds=body.get("refreshSeconds")
    if seconds is not None and (type(seconds) is not int or seconds not in (0,30,60,120,300,600,900,1800,3600)):
        raise HTTPException(422,"Neplatná četnost obnovování obsahu.")
    frequency=body.get("maintenanceFrequency","off")
    if frequency not in FREQUENCIES:raise HTTPException(422,"Neplatná četnost údržby.")
    if type(body.get("expectedRevision")) is not int:raise HTTPException(422,"Chybí revize nastavení.")
    return seconds,frequency

class UpdatePlans:
    def __init__(self,connect):self.connect=connect
    def db(self):
        conn=self.connect()
        conn.execute("CREATE TABLE IF NOT EXISTS eduvize_update_plans_v1 (school_id TEXT NOT NULL,app TEXT NOT NULL,refresh_seconds INTEGER,maintenance_frequency TEXT NOT NULL,revision INTEGER NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(school_id,app))")
        return conn
    def read(self,school,app):
        if app not in APPS:raise HTTPException(404,"Aplikace není podporována.")
        with self.db() as conn:
            row=conn.execute("SELECT refresh_seconds,maintenance_frequency,revision,updated_at FROM eduvize_update_plans_v1 WHERE school_id=%s AND app=%s",(school,app)).fetchone()
        return self.result(app,row)
    def result(self,app,row=None):
        seconds,frequency,revision,updated=row if row else (None,"quarterly" if app=="holidays" else "off",0,"2026-11-03T00:00:00+01:00")
        status=maintenance_status().get(app,{})
        last=status.get("lastSuccess")
        after=max((updated,last),key=lambda v:datetime.fromisoformat(v.replace("Z","+00:00"))) if isinstance(last,str) else updated
        return {"app":app,"name":APPS[app][0],"refreshSeconds":seconds,"defaultRefreshSeconds":APPS[app][1],
                "maintenanceFrequency":frequency,"revision":revision,"updatedAt":updated,
                "maintenanceNextRun":next_due(frequency,after),"lastMaintenanceCheck":last,"maintenanceStatus":status.get("state","not-run"),"maintenanceMessage":status.get("message",""),"maintenanceTimeZone":"Europe/Prague",
                "maintenanceExecutor":"Codex"}
    def save(self,school,app,body):
        if app not in APPS:raise HTTPException(404,"Aplikace není podporována.")
        seconds,frequency=validate(body)
        with self.db() as conn:
            # Serialize absent-row creation and subsequent edits across workers.
            import hashlib
            key=int.from_bytes(hashlib.sha256((school+":"+app).encode()).digest()[:8],"big",signed=True)
            conn.execute("SELECT pg_advisory_xact_lock(%s)",(key,))
            row=conn.execute("SELECT revision FROM eduvize_update_plans_v1 WHERE school_id=%s AND app=%s",(school,app)).fetchone()
            if (row[0] if row else 0)!=body["expectedRevision"]:raise HTTPException(409,"Nastavení změnil jiný správce. Obnovte stav.")
            revision=body["expectedRevision"]+1
            updated=datetime.now(timezone.utc).isoformat()
            conn.execute("INSERT INTO eduvize_update_plans_v1 VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(school_id,app) DO UPDATE SET refresh_seconds=EXCLUDED.refresh_seconds,maintenance_frequency=EXCLUDED.maintenance_frequency,revision=EXCLUDED.revision,updated_at=EXCLUDED.updated_at",
                         (school,app,seconds,frequency,revision,updated))
        return self.result(app,(seconds,frequency,revision,updated))
    def maintenance(self):
        with self.db() as conn:
            rows=conn.execute("SELECT app,maintenance_frequency,updated_at FROM eduvize_update_plans_v1").fetchall()
        plans=[]
        for app in APPS:
            requested=[self.result(app,(None,f,0,stamp)) for a,f,stamp in rows if a==app]
            if not requested:requested=[self.result(app)]
            active=[p for p in requested if p["maintenanceNextRun"]]
            plan=min(active,key=lambda p:datetime.fromisoformat(p["maintenanceNextRun"])) if active else self.result(app,(None,"off",0,datetime.now(timezone.utc).isoformat()))
            plans.append({k:plan[k] for k in ("app","name","maintenanceFrequency","maintenanceNextRun","maintenanceTimeZone","maintenanceExecutor")})
        return {"items":plans,"statusUrl":"https://pborovicka72-dotcom.github.io/eduvize-styly/design-system/update-status.json"}

def update_plan_router(store,authorize,accounts):
    router=APIRouter()
    def no_cache(response:Response):response.headers["Cache-Control"]="no-store"
    async def access(authorization:str=Header(default="")):await authorize(authorization)
    def school():
        value=school_context.get()
        return "legacy" if not value or value.get("legacy") else value["id"]
    @router.get("/api/update-plans/maintenance",dependencies=[Depends(no_cache)])
    def maintenance():return store.maintenance()
    @router.get("/api/update-plans/{app}",dependencies=[Depends(no_cache)])
    def public_plan(app:str,profile:str=LEGACY_PROFILE):
        value=accounts.public_profile(profile)
        return store.read("legacy" if not value or value.get("legacy") else value["id"],app)
    @router.get("/api/admin/update-plans/{app}",dependencies=[Depends(access),Depends(no_cache)])
    def get_plan(app:str):return store.read(school(),app)
    @router.put("/api/admin/update-plans/{app}",dependencies=[Depends(access),Depends(no_cache)])
    async def put_plan(app:str,request:Request):
        from configuration_profiles import decode
        return store.save(school(),app,decode(await request.body()))
    return router
