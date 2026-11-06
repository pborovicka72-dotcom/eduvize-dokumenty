"""Disposable browser acceptance service, never a production entry point."""
import json,os,re,sys,time
from pathlib import Path
import psycopg
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.responses import FileResponse,Response
assert os.environ['PUBLIC_BASE_URL']=='https://test.skola.eduvize.cz'
original=os.environ['DATABASE_URL'];info=psycopg.conninfo.conninfo_to_dict(original)
assert info.get('dbname')=='eduvize_test' and info.get('host') in ('db','eduvize-test-db','172.29.240.10')
SCHEMA=os.environ['MATERIAL_ACCEPTANCE_SCHEMA'];assert re.fullmatch('material_browser_[a-f0-9]{32}',SCHEMA)
with psycopg.connect(original,autocommit=True) as c:c.execute('CREATE SCHEMA '+SCHEMA)
os.environ['DATABASE_URL']=psycopg.conninfo.make_conninfo(original,options='-c search_path='+SCHEMA+' -c lock_timeout=8000')
os.environ['SESSIONS_DATABASE_URL']=os.environ['DATABASE_URL']
os.environ['TOKEN_ENCRYPTION_KEY']=Fernet.generate_key().decode()
os.environ['EDUVIZE_CENTRAL_URL']='http://127.0.0.1:8000'
os.environ['EDUVIZE_DOCUMENTS_INTERNAL_URL']='http://127.0.0.1:8000'
os.environ['EDUVIZE_OUTPUT_API_ENABLED']='0'
PUBLIC=Path('/public');os.environ['EDUVIZE_STYLES_ROOT']=str(PUBLIC/'eduvize-styly')
sys.path.insert(0,'/acceptance/documents')
import app as documents
from eduvize_admin import runtime,license_api,styles_api
from eduvize_admin.admin_sessions import SessionStore,require_session
from eduvize_admin.licenses import Licenses,SchoolRegistry
from eduvize_admin.broadcast_license import broadcast_router
sessions=SessionStore(runtime.microsoft_login_db)
async def local_identity(auth,scope='documents'):
    if not auth or not auth.startswith('Bearer edu_'):return False
    row=require_session(sessions,auth,scope)
    return {'valid':True,'scope':scope,**row}
# Test-only transport replacement; same real durable session validation and scopes.
runtime.central_admin=local_identity;license_api.central_admin=local_identity
app=documents.app
app.include_router(styles_api.app.router)
licenses=Licenses(runtime.school_accounts,SchoolRegistry())
app.include_router(license_api.license_router(licenses,runtime.microsoft_login))
app.include_router(broadcast_router(licenses))
fixtures=[]
for n,ico in [(1,'00000027'),(2,'00000035')]:
    school=runtime.school_accounts.resolve('eduvize','material-browser-'+SCHEMA+'-'+str(n),legacy=False)
    with runtime.school_accounts.db() as c:c.execute('UPDATE eduvize_schools_v1 SET name=%s,storage_provider=%s WHERE id=%s',('TEST Dokumenty '+str(n),'eduvize',school['id']))
    runtime.cloud_storage().initialize(school['id'])
    issued=licenses.issue(None,12,'material-acceptance',organization={'ico':ico,'name':'TEST Dokumenty '+str(n),'address':'Testovací 1','municipality':'Test','postal_code':'00000'})
    with licenses.db() as c:c.execute('UPDATE eduvize_licenses_v1 SET school_id=%s,activated=%s,expires=%s,revision=revision+1 WHERE id=%s',(school['id'],time.time(),time.time()+86400,issued['license']['id']))
    session=sessions.create({'documents','configurations','styles'})
    sessions.bind_school(session['token'],school['id'],school['profileId'])
    fixtures.append({**session,'schoolId':school['id'],'profileId':school['profileId']})
htmlroot=Path('/tmp/material-documents-html');htmlroot.mkdir(exist_ok=True)
HOSTS=('https://pborovicka72-dotcom.github.io','https://eduvize-dokumenty-api.onrender.com','https://eduvize-design-system-api.onrender.com','https://eduvize-admin.onrender.com')
def relocate(text):
    for host in HOSTS:text=text.replace(host,'')
    return text
for name in ('config.html','index.html'):(htmlroot/name).write_text(relocate((Path('/acceptance/documents')/name).read_text()))
documents.ROOT=htmlroot
@app.middleware('http')
async def baseline_page(request,call_next):
    if request.url.path=='/config' and request.query_params.get('acceptance-baseline')=='1':
        return Response(relocate((Path('/acceptance/documents')/'config.baseline.html').read_text()),media_type='text/html')
    return await call_next(request)
@app.get('/_acceptance/fixtures')
def test_fixtures():return fixtures
@app.get('/_acceptance/ready')
def ready():return {'environment':'isolated test container','schema':SCHEMA,'productionEligible':False}
@app.on_event('shutdown')
def cleanup():
    with psycopg.connect(original,autocommit=True) as c:c.execute('DROP SCHEMA '+SCHEMA+' CASCADE')
@app.get('/{asset:path}')
def static_asset(asset:str):
    path=(PUBLIC/asset).resolve()
    if not path.is_relative_to(PUBLIC) or not path.is_file():raise HTTPException(404,'Asset not found')
    if path.suffix in ('.html','.js','.css'):
        content=relocate(path.read_text().replace('https://test.skola.eduvize.cz','').replace('https://skola.eduvize.cz',''))
        return Response(content,media_type={'.html':'text/html','.js':'application/javascript','.css':'text/css'}[path.suffix])
    return FileResponse(path)
