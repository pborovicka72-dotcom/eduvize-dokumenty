"""Short-lived capability-based kiosk control. No school/admin credentials are exposed."""
import hashlib, json, secrets, time
from contextlib import contextmanager
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
import psycopg
import qrcode
import qrcode.image.svg
import io

MOBILE = 'https://pborovicka72-dotcom.github.io/eduvize-kiosek/remote.html'
LEASE = 120
LIVE = 20
PAIR = 120

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def token(header):
    if not header or not header.startswith('Bearer ') or len(header) > 160:
        raise HTTPException(401, 'Spojení není platné. Načtěte QR kód znovu.')
    return digest(header[7:])

class Item(BaseModel):
    id: str = Field(max_length=80, pattern=r'^[a-zA-Z0-9_.:-]+$')
    label: str = Field(max_length=100)
    active: bool = False

class Snapshot(BaseModel):
    title: str = Field(default='Kiosek', max_length=100)
    revision: str = Field(max_length=64)
    items: list[Item] = Field(default_factory=list, max_length=100)

class PairCode(BaseModel):
    code: str = Field(pattern=r'^[0-9]{8}$')

class Heartbeat(BaseModel):
    snapshot: Snapshot
    ack: int = Field(default=0, ge=0)

class Command(BaseModel):
    id: str = Field(max_length=80, pattern=r'^[a-zA-Z0-9_.:-]+$')
    revision: str = Field(max_length=64)
    requestId: str = Field(min_length=16, max_length=64, pattern=r'^[a-zA-Z0-9-]+$')

class RemoteStore:
    def __init__(self, database_url):
        self.url, self.ready = database_url, False

    @contextmanager
    def transaction(self):
        if not self.url:
            raise HTTPException(503, 'Mobilní ovládání není nakonfigurováno.')
        try:
            with psycopg.connect(self.url, connect_timeout=5) as db:
                if not self.ready:
                    db.execute('CREATE TABLE IF NOT EXISTS eduvize_kiosk_remote (id TEXT PRIMARY KEY, expires DOUBLE PRECISION NOT NULL, data JSONB NOT NULL)')
                    db.execute('CREATE INDEX IF NOT EXISTS eduvize_kiosk_remote_expiry ON eduvize_kiosk_remote(expires)')
                yield db
            self.ready = True
        except psycopg.Error:
            raise HTTPException(503, 'Mobilní ovládání je dočasně nedostupné.') from None

    def pair_code(self, db, now):
        # Unique among live, unconsumed codes; short lifetime and throttled redemption.
        db.execute("SELECT pg_advisory_xact_lock(68713426)")
        for _ in range(20):
            code = f'{secrets.randbelow(100000000):08d}'
            if not db.execute("SELECT id FROM eduvize_kiosk_remote WHERE data->>'pairCode'=%s AND expires>%s AND (data->>'pairUntil')::double precision>%s", (code,now,now)).fetchone():
                return code
        raise HTTPException(503, 'Párovací kód se nepodařilo vytvořit. Zkuste to znovu.')

    def join_code(self, code):
        now = time.time()
        with self.transaction() as db:
            row = db.execute("SELECT id,data FROM eduvize_kiosk_remote WHERE data->>'pairCode'=%s AND expires>%s AND (data->>'pairUntil')::double precision>%s", (code,now,now)).fetchone()
            if not row or now-row[1]['seen'] > LIVE or not row[1].get('pairToken'):
                raise HTTPException(410, 'Párovací kód není platný. Zadejte aktuální kód z obrazovky.')
            sid, pair = row[0], row[1]['pairToken']
        # update locks the row and consumes both QR and manual capability atomically.
        return dict(session=sid, **self.update(sid,'pair','Bearer '+pair,'join'))

    def create(self, snapshot):
        now = time.time()
        sid, owner, pair = secrets.token_urlsafe(24), secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        data = dict(owner=digest(owner), pair=digest(pair), pairToken=pair, pairUntil=now+PAIR, controller=None,
                    controllerUntil=0, seen=now, snapshot=snapshot, commands=[], sequence=0, requests=[], lastCommand=0)
        with self.transaction() as db:
            db.execute('DELETE FROM eduvize_kiosk_remote WHERE expires < %s', (now,))
            # Bound public, anonymous session allocation; never touch school configuration data.
            db.execute("SELECT pg_advisory_xact_lock(68713425)")
            if db.execute('SELECT count(*) FROM eduvize_kiosk_remote').fetchone()[0] >= 2000:
                raise HTTPException(429, 'Služba je vytížená. Zkuste to později.')
            data['pairCode'] = self.pair_code(db, now)
            db.execute('INSERT INTO eduvize_kiosk_remote VALUES (%s,%s,%s::jsonb)', (sid, now+60, json.dumps(data)))
        return dict(id=sid, owner=owner)

    def update(self, sid, role, auth, action, payload=None):
        if len(sid) > 64:
            raise HTTPException(404, 'Spojení již skončilo.')
        key, now = token(auth), time.time()
        with self.transaction() as db:
            row = db.execute('SELECT data,expires FROM eduvize_kiosk_remote WHERE id=%s FOR UPDATE', (sid,)).fetchone()
            if not row or row[1] < now:
                raise HTTPException(410, 'Spojení skončilo. Načtěte QR kód znovu.')
            d = row[0]
            if not secrets.compare_digest(d.get(role) or '', key):
                raise HTTPException(401, 'Spojení není platné. Načtěte QR kód znovu.')
            if role != 'owner' and now-d['seen'] > LIVE:
                raise HTTPException(410, 'Kiosek není připojený.')
            if role == 'controller' and d['controllerUntil'] < now:
                raise HTTPException(410, 'Ovládání skončilo po nečinnosti. Načtěte QR kód znovu.')
            result = {}
            if action == 'join':
                if d['pairUntil'] < now:
                    raise HTTPException(410, 'QR kód vypršel. Načtěte nový z obrazovky.')
                if d['controller'] and d['controllerUntil'] > now:
                    raise HTTPException(409, 'Kiosek právě ovládá jiný telefon.')
                credential = secrets.token_urlsafe(32)
                d.update(controller=digest(credential), controllerUntil=now+LEASE, pair='', pairToken='', pairCode='', commands=[], requests=[])
                result = dict(controller=credential, snapshot=d['snapshot'], expiresIn=LEASE)
            elif action == 'heartbeat':
                d.update(seen=now, snapshot=payload['snapshot'])
                d['commands'] = [c for c in d['commands'] if c['sequence'] > payload['ack'] and now-c['created'] < 5]
                connected = bool(d['controller'] and d['controllerUntil'] > now)
                if not connected and (not d['pairToken'] or d['pairUntil'] < now):
                    pair = secrets.token_urlsafe(32)
                    d.update(pair=digest(pair), pairToken=pair, pairCode=self.pair_code(db,now), pairUntil=now+PAIR, controller=None, commands=[])
                if not connected and not d.get('pairCode'):
                    d['pairCode'] = self.pair_code(db,now)
                result = dict(connected=connected, commands=d['commands'], pairToken=None if connected else d['pairToken'], pairUntil=d['pairUntil'], pairCode=None if connected else d['pairCode'])
            elif action == 'state':
                result = dict(snapshot=d['snapshot'], expiresIn=max(0,int(d['controllerUntil']-now)))
            elif action == 'command':
                if payload['requestId'] in d['requests']:
                    return dict(accepted=True)
                if payload['revision'] != d['snapshot']['revision'] or payload['id'] not in [i['id'] for i in d['snapshot']['items']]:
                    raise HTTPException(409, 'Nabídka se změnila. Vyberte položku znovu.')
                if now-d['lastCommand'] < .3 or len(d['commands']) >= 8:
                    raise HTTPException(429, 'Počkejte na dokončení předchozí volby.')
                d['sequence'] += 1
                d['commands'].append(dict(sequence=d['sequence'], id=payload['id'], revision=payload['revision'], created=now))
                d.update(controllerUntil=now+LEASE, lastCommand=now, requests=(d['requests']+[payload['requestId']])[-32:])
                result = dict(accepted=True)
            elif action in ('leave', 'disconnect'):
                d.update(controller=None, controllerUntil=0, commands=[], pairUntil=0, pairToken='', pairCode='')
                result = dict(disconnected=True)
            db.execute('UPDATE eduvize_kiosk_remote SET data=%s::jsonb,expires=%s WHERE id=%s', (json.dumps(d),now+60,sid))
            return result

    def qr(self, sid, auth):
        now = time.time()
        with self.transaction() as db:
            row = db.execute('SELECT data,expires FROM eduvize_kiosk_remote WHERE id=%s',(sid,)).fetchone()
            if not row or row[1] < now or not secrets.compare_digest(row[0]['owner'], token(auth)):
                raise HTTPException(401, 'Neplatné spojení.')
            d = row[0]
            if not d['pairToken'] or d['pairUntil'] < now:
                raise HTTPException(410, 'QR kód již není aktivní.')
            url = MOBILE+'#'+sid+'.'+d['pairToken']
        code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
        code.add_data(url); code.make(fit=True)
        output = io.BytesIO(); code.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(output)
        return output.getvalue()

class CapabilityResponse(JSONResponse):
    def __init__(self, *args, **kwargs):
        headers = dict(kwargs.pop('headers',None) or {})
        headers['Cache-Control'] = 'no-store'
        super().__init__(*args, headers=headers, **kwargs)

def remote_router(database_url):
    limits = {}
    store, router = RemoteStore(database_url), APIRouter(prefix='/api/kiosk-remote', tags=['Kiosk mobile control'], default_response_class=CapabilityResponse)
    @router.post('/sessions')
    def create(body: Snapshot, request: Request):
        now = time.monotonic()
        identity = request.client.host if request.client else 'unknown'
        # Bound memory and throttle repeated anonymous allocation independently of credentials.
        for key in list(limits):
            if limits[key][0] < now-60:
                del limits[key]
        start, count = limits.get(identity, (now,0))
        if count >= 10 or len(limits) >= 10000:
            raise HTTPException(429, 'Příliš mnoho připojení. Zkuste to za minutu.')
        limits[identity] = (start,count+1)
        return store.create(body.model_dump())
    code_limits = {}
    @router.post('/join-code')
    def join_code(body: PairCode, request: Request):
        now = time.monotonic()
        identity = request.client.host if request.client else 'unknown'
        for key in list(code_limits):
            if code_limits[key][0] < now-60:
                del code_limits[key]
        start, count = code_limits.get(identity, (now,0))
        if count >= 5 or len(code_limits) >= 10000:
            raise HTTPException(429, 'Příliš mnoho pokusů. Zkuste nový kód za minutu.')
        code_limits[identity] = (start,count+1)
        return store.join_code(body.code)
    @router.post('/sessions/{sid}/heartbeat')
    def heartbeat(sid: str, body: Heartbeat, authorization: str | None = Header(None)):
        return store.update(sid,'owner',authorization,'heartbeat',body.model_dump())
    @router.get('/sessions/{sid}/qr')
    def qr(sid: str, authorization: str | None = Header(None)):
        return Response(store.qr(sid,authorization),media_type='image/svg+xml',headers={'Cache-Control':'no-store'})
    @router.post('/sessions/{sid}/join')
    def join(sid: str, authorization: str | None = Header(None)):
        return store.update(sid,'pair',authorization,'join')
    @router.get('/sessions/{sid}/state')
    def state(sid: str, authorization: str | None = Header(None)):
        return store.update(sid,'controller',authorization,'state')
    @router.post('/sessions/{sid}/commands')
    def command(sid: str, body: Command, authorization: str | None = Header(None)):
        return store.update(sid,'controller',authorization,'command',body.model_dump())
    @router.post('/sessions/{sid}/leave')
    def leave(sid: str, authorization: str | None = Header(None)):
        return store.update(sid,'controller',authorization,'leave')
    @router.post('/sessions/{sid}/disconnect')
    def disconnect(sid: str, authorization: str | None = Header(None)):
        return store.update(sid,'owner',authorization,'disconnect')
    return router

