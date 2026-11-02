"""School identity and storage binding. OAuth providers never determine the school ID."""
import json
import re
import uuid
from contextvars import ContextVar
from fastapi import HTTPException

school_context = ContextVar('eduvize_school', default=None)
LEGACY_PROFILE = 'c0e094dbb91b4139a150a86efc87001b'

class SchoolAccounts:
    def __init__(self, connect): self.connect = connect
    def db(self):
        conn = self.connect()
        conn.execute('SELECT pg_advisory_xact_lock(%s)',(7312458720,))
        conn.execute("CREATE TABLE IF NOT EXISTS eduvize_schools_v1 (id TEXT PRIMARY KEY, profile_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL, storage_provider TEXT NOT NULL, legacy BOOLEAN NOT NULL DEFAULT FALSE)")
        conn.execute("CREATE TABLE IF NOT EXISTS eduvize_identities_v1 (provider TEXT NOT NULL, subject TEXT NOT NULL, school_id TEXT NOT NULL REFERENCES eduvize_schools_v1(id), PRIMARY KEY(provider,subject))")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS eduvize_one_legacy_school ON eduvize_schools_v1(legacy) WHERE legacy=TRUE")
        conn.execute("CREATE TABLE IF NOT EXISTS eduvize_migration_v1 (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        return conn
    @staticmethod
    def row(row):
        return dict(zip(('id','profileId','name','storageProvider','legacy'), row)) if row else None
    def get(self, school_id):
        if not isinstance(school_id,str) or not re.fullmatch(r'[a-f0-9]{32}',school_id): raise HTTPException(403,'Neplatná škola.')
        with self.db() as conn:
            result=self.row(conn.execute('SELECT id,profile_id,name,storage_provider,legacy FROM eduvize_schools_v1 WHERE id=%s',(school_id,)).fetchone())
        if not result: raise HTTPException(403,'Škola nebyla nalezena.')
        return result
    def public_profile(self, profile_id):
        if not re.fullmatch(r'[a-f0-9]{32}',profile_id): raise HTTPException(404,'Profil nenalezen.')
        with self.db() as conn:
            row=conn.execute('SELECT id,profile_id,name,storage_provider,legacy FROM eduvize_schools_v1 WHERE profile_id=%s',(profile_id,)).fetchone()
        if not row:
            if profile_id==LEGACY_PROFILE:return None  # Existing display links before owner migration.
            raise HTTPException(404,'Profil nenalezen.')
        return self.row(row)
    def legacy_subject(self):
        with self.db() as conn:row=conn.execute("SELECT value FROM eduvize_migration_v1 WHERE key='legacy-microsoft-owner'").fetchone()
        return row[0] if row else None
    def remember_legacy_subject(self,subject):
        with self.db() as conn:
            conn.execute("INSERT INTO eduvize_migration_v1 VALUES ('legacy-microsoft-owner',%s) ON CONFLICT (key) DO NOTHING",(subject,))
        return self.legacy_subject()
    def resolve(self, provider, subject, legacy=False):
        # No linking by email: another provider can only be linked after both identities are verified.
        if provider not in ('microsoft','google','eduvize') or not isinstance(subject,str) or not subject or len(subject)>256:
            raise HTTPException(401,'Neplatná identita.')
        with self.db() as conn:
            # Serialize onboarding across workers; one subject always gets exactly one school.
            conn.execute('SELECT pg_advisory_xact_lock(%s)',(7312458721,))
            existing=conn.execute('SELECT school_id FROM eduvize_identities_v1 WHERE provider=%s AND subject=%s',(provider,subject)).fetchone()
            if existing: school_id=existing[0]
            else:
                school_id=uuid.uuid4().hex
                profile_id=LEGACY_PROFILE if legacy else uuid.uuid4().hex
                conn.execute('INSERT INTO eduvize_schools_v1 (id,profile_id,name,storage_provider,legacy) VALUES (%s,%s,%s,%s,%s)',(school_id,profile_id,'Profil školy','onedrive',legacy))
                conn.execute('INSERT INTO eduvize_identities_v1 VALUES (%s,%s,%s)',(provider,subject,school_id))
        return self.get(school_id)
    def identity(self, school_id, provider):
        with self.db() as conn:
            row=conn.execute('SELECT subject FROM eduvize_identities_v1 WHERE school_id=%s AND provider=%s',(school_id,provider)).fetchone()
        return row[0] if row else None

def storage_key(school=None):
    school=school if school is not None else school_context.get()
    return 'microsoft' if not school or school['legacy'] else 'school:'+school['id']+':microsoft'

class SchoolProfileStore:
    """Enforces one profile before delegating to the current storage adapter."""
    def __init__(self, store, write_lock):self.store,self.write_lock=store,write_lock
    def own(self, profile_id):
        school=school_context.get()
        if school and profile_id!=school['profileId']:raise HTTPException(404,'Profil nenalezen.')
        return school
    async def materialize(self):
        school=school_context.get()
        if not school:return
        from configuration_profiles import stamp
        async with self.write_lock('school-init:'+school['id']):
            try:await self.store.read(school['profileId']);return
            except HTTPException as error:
                if error.status_code!=404:raise
            value={'format':'eduvize-profile','version':1,'id':school['profileId'],'name':school['name'],'revision':1,'updatedAt':stamp(),'apps':{}}
            await self.store.put(await self.store.folder(True),school['profileId']+'.json',value)
    async def list(self):
        school=school_context.get()
        if not school:return await self.store.list()
        from configuration_profiles import metadata
        return [metadata(await self.read(school['profileId']))]
    async def read(self, profile_id):
        self.own(profile_id)
        try:return await self.store.read(profile_id)
        except HTTPException as error:
            if error.status_code!=404 or not school_context.get():raise
        await self.materialize()
        return await self.store.read(profile_id)
    async def create(self,*args):
        raise HTTPException(409,'Každá škola má jeden automaticky vytvořený profil.')
    async def save_app(self, profile_id,*args):
        self.own(profile_id)
        await self.materialize()
        return await self.store.save_app(profile_id,*args)
    async def history(self, profile_id):
        self.own(profile_id);return await self.store.history(profile_id)
    async def restore(self, profile_id,*args):
        self.own(profile_id);return await self.store.restore(profile_id,*args)
