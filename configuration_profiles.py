"""Private, versioned settings profiles on the already connected OneDrive."""
import asyncio
import copy
import json
import math
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

APPS = {'kiosk', 'documents', 'weather', 'holidays', 'transport', 'wisdom', 'news', 'styles', 'school-systems', 'generated-links', 'menu'}
MAX_BYTES = 2 * 1024 * 1024
FORBIDDEN = {'password', 'passwd', 'secret', 'clientsecret', 'token', 'accesstoken', 'refreshtoken', 'idtoken', 'authorization', 'adminkey', 'adminsecret', 'username', 'bakusername', 'bakpassword', 'microsoft', '__proto__', 'prototype', 'constructor'}


def ident(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
        raise HTTPException(422, 'Neplatný identifikátor profilu.')
    return value


def name(value):
    if not isinstance(value, str):
        raise HTTPException(422, 'Vyplňte název profilu.')
    value = ' '.join(value.split())
    if not 1 <= len(value) <= 80:
        raise HTTPException(422, 'Název profilu musí mít 1–80 znaků.')
    return value


def safe_config(value, app=None):
    count = 0
    def visit(item, depth=0):
        nonlocal count
        count += 1
        if depth > 30 or count > 60000:
            raise HTTPException(422, 'Konfigurace je příliš složitá.')
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > 100:
                    raise HTTPException(422, 'Neplatný klíč konfigurace.')
                normalized = re.sub(r'[^a-z_]', '', key.lower())
                if normalized in FORBIDDEN or normalized.replace('_', '') in FORBIDDEN:
                    raise HTTPException(422, 'Přihlašovací údaje do profilu nepatří.')
                visit(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, str):
            if re.match(r'\s*(?:javascript|vbscript|file):|\s*data:(?:text/html|application/xhtml)', item, re.I):
                raise HTTPException(422, 'Konfigurace obsahuje nepovolenou adresu.')
            if '://' in item:
                try:
                    u = urlsplit(item)
                    if u.scheme in ('http', 'https') and (u.username or u.password or any(re.sub(r'[^a-z]', '', k.lower()) in FORBIDDEN for k, _ in parse_qsl(u.query))):
                        raise HTTPException(422, 'Odkaz obsahuje přihlašovací údaj.')
                except ValueError:
                    raise HTTPException(422, 'Neplatný odkaz v konfiguraci.') from None
        elif item is not None and not isinstance(item, (bool, int, float)):
            raise HTTPException(422, 'Nepodporovaný typ nastavení.')
        elif isinstance(item, float) and not math.isfinite(item):
            raise HTTPException(422, 'Neplatné číslo v konfiguraci.')
    if not isinstance(value, dict) or type(value.get('schemaVersion')) is not int or value.get('schemaVersion') != 1:
        raise HTTPException(422, 'Nepodporovaný formát nastavení aplikace.')
    visit(value)
    if app == 'generated-links' and not value.get('empty'):
        from generated_links import validate_library
        validate_library(value)
    if app == 'styles' and not value.get('empty'):
        data = value.get('data')
        theme = data.get('theme') if isinstance(data, dict) else None
        if not isinstance(theme, dict) or not isinstance(theme.get('colors'), dict) or not theme['colors']:
            raise HTTPException(422, 'Chybí záloha stylu.')
        if any(not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color) for color in theme['colors'].values()):
            raise HTTPException(422, 'Neplatná barva v záloze stylu.')
        for group, keys in [('controls', ['heightPx', 'radiusPx']), ('cards', ['radiusPx']), ('icons', ['radiusPx'])]:
            for key in keys:
                number = theme.get(group, {}).get(key, 10 if group == 'icons' else None)
                if type(number) is not int or not 0 <= number <= (24 if group == 'icons' else 80):
                    raise HTTPException(422, 'Neplatná velikost v záloze stylu.')
    if len(json.dumps(value, ensure_ascii=False).encode()) > MAX_BYTES:
        raise HTTPException(413, 'Limit nastavení je 2 MB.')
    return copy.deepcopy(value)


def decode(raw):
    if len(raw) > MAX_BYTES + 16384:
        raise HTTPException(413, 'Požadavek je příliš velký.')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(422, 'Neplatný JSON konfigurace.') from None


def stamp():
    return datetime.now(timezone.utc).isoformat()


def metadata(profile):
    return {key: profile[key] for key in ('id', 'name', 'revision', 'updatedAt')} | {'apps': {key: {'revision': value['revision'], 'updatedAt': value['updatedAt']} for key, value in profile['apps'].items()}}


def validate_profile(value, profile_id):
    if (not isinstance(value, dict) or value.get('format') != 'eduvize-profile'
            or value.get('version') != 1 or value.get('id') != profile_id
            or not isinstance(value.get('name'), str) or not 1 <= len(value['name']) <= 80
            or type(value.get('revision')) is not int or value['revision'] < 1
            or not isinstance(value.get('updatedAt'), str) or not isinstance(value.get('apps'), dict)):
        raise HTTPException(502, 'Uložený profil má neplatný formát.')
    for app, entry in value['apps'].items():
        if (app not in APPS or not isinstance(entry, dict) or type(entry.get('revision')) is not int
                or entry['revision'] < 1 or not isinstance(entry.get('updatedAt'), str)):
            raise HTTPException(502, 'Uložený profil obsahuje neplatné nastavení aplikace.')
        safe_config(entry.get('config'), app)
    return value


class ProfileStore:
    def __init__(self, graph, ensure_folder, system_folder, read_json, write_lock):
        self.graph, self.ensure_folder, self.system_folder, self.read_json, self.write_lock = graph, ensure_folder, system_folder, read_json, write_lock

    async def children(self, folder):
        if not folder:
            return []
        path, params, result = f'/me/drive/items/{folder}/children', {'$select': 'id,name,folder,lastModifiedDateTime', '$top': 200}, []
        for _ in range(50):
            page = (await self.graph('GET', path, params=params)).json()
            result.extend(page.get('value', []))
            link = page.get('@odata.nextLink')
            if not link:
                return result
            u = urlsplit(link)
            if u.scheme != 'https' or u.netloc != 'graph.microsoft.com' or not u.path.startswith('/v1.0/'):
                raise HTTPException(502, 'OneDrive vrátil neplatné stránkování.')
            path, params = u.path[len('/v1.0'):], dict(parse_qsl(u.query))
        raise HTTPException(502, 'Seznam konfigurací je příliš rozsáhlý.')

    async def child(self, folder, child_name):
        return next((v for v in await self.children(folder) if v['name'] == child_name), None)

    async def subfolder(self, parent, child_name, create=False):
        existing = await self.child(parent, child_name)
        if existing:
            if 'folder' not in existing:
                raise HTTPException(409, 'Složka profilů koliduje se souborem.')
            return existing['id']
        if not create:
            return None
        return (await self.graph('POST', f'/me/drive/items/{parent}/children', json={'name': child_name, 'folder': {}, '@microsoft.graph.conflictBehavior': 'fail'})).json()['id']

    async def folder(self, create=False):
        root = await self.ensure_folder()
        if create:
            system = await self.system_folder(root)
        else:
            item = await self.child(root, '_Eduvize-system')
            system = item['id'] if item and 'folder' in item else None
        return await self.subfolder(system, 'Profily', create) if system else None

    async def read(self, profile_id):
        profile_id = ident(profile_id)
        folder = await self.folder()
        item = await self.child(folder, profile_id + '.json')
        if not item:
            raise HTTPException(404, 'Profil nebyl na OneDrive nalezen.')
        value = await self.read_json(item)
        return validate_profile(value, profile_id)

    async def list(self):
        files = [item for item in await self.children(await self.folder()) if re.fullmatch(r'[a-f0-9]{32}\.json', item['name']) and 'folder' not in item]
        semaphore = asyncio.Semaphore(4)
        async def one(item):
            async with semaphore:
                return metadata(await self.read(item['name'][:-5]))
        return sorted(await asyncio.gather(*(one(item) for item in files)), key=lambda v: v['name'].casefold())

    async def put(self, folder, filename, value):
        await self.graph('PUT', f'/me/drive/items/{folder}:/{filename}:/content', content=json.dumps(value, ensure_ascii=False, allow_nan=False).encode(), headers={'Content-Type': 'application/json'})

    async def create(self, title, source_id=None):
        title = name(title)
        # All writers use a database advisory transaction lock, shared across workers.
        async with self.write_lock('profiles-create'):
            key = unicodedata.normalize('NFKC', title).casefold()
            if any(unicodedata.normalize('NFKC', item['name']).casefold() == key for item in await self.list()):
                raise HTTPException(409, 'Profil s tímto názvem již existuje.')
            apps = copy.deepcopy((await self.read(source_id))['apps']) if source_id else {}
            now = stamp()
            for value in apps.values():
                value.update(revision=1, updatedAt=now)
            profile = {'format': 'eduvize-profile', 'version': 1, 'id': uuid.uuid4().hex, 'name': title, 'revision': 1, 'updatedAt': now, 'apps': apps}
            await self.put(await self.folder(True), profile['id'] + '.json', profile)
            return metadata(profile)

    async def archive(self, profile):
        history = await self.subfolder(await self.folder(True), profile['id'] + '-historie', True)
        await self.put(history, str(profile['revision']) + '.json', profile)

    async def save_app(self, profile_id, app, config, expected):
        ident(profile_id)
        if app not in APPS or type(expected) is not int or expected < 0:
            raise HTTPException(422, 'Neplatná aplikace nebo revize.')
        config = safe_config(config, app)
        async with self.write_lock(profile_id):
            profile = await self.read(profile_id)
            current = profile['apps'].get(app, {}).get('revision', 0)
            if current != expected:
                raise HTTPException(409, 'Nastavení mezitím změnil jiný správce. Načtěte aktuální verzi před uložením.')
            await self.archive(profile)
            now = stamp()
            profile['apps'][app] = {'revision': current + 1, 'updatedAt': now, 'config': config}
            profile.update(revision=profile['revision'] + 1, updatedAt=now)
            await self.put(await self.folder(True), profile_id + '.json', profile)
            return profile['apps'][app]

    async def history(self, profile_id):
        await self.read(profile_id)
        history = await self.subfolder(await self.folder(), ident(profile_id) + '-historie')
        return sorted([{'revision': int(v['name'][:-5]), 'updatedAt': v.get('lastModifiedDateTime', '')} for v in await self.children(history) if re.fullmatch(r'[0-9]+\.json', v['name'])], key=lambda v: v['revision'], reverse=True)

    async def restore(self, profile_id, revision, expected):
        ident(profile_id)
        if type(revision) is not int or revision < 1 or type(expected) is not int:
            raise HTTPException(422, 'Neplatná verze profilu.')
        async with self.write_lock(profile_id):
            current = await self.read(profile_id)
            if current['revision'] != expected:
                raise HTTPException(409, 'Profil se mezitím změnil. Obnovte seznam verzí.')
            history = await self.subfolder(await self.folder(), profile_id + '-historie')
            item = await self.child(history, str(revision) + '.json')
            if not item:
                raise HTTPException(404, 'Požadovaná verze nebyla nalezena.')
            previous = validate_profile(await self.read_json(item), profile_id)
            now, apps = stamp(), {}
            for app, entry in previous['apps'].items():
                if app not in APPS:
                    raise HTTPException(502, 'Neplatná aplikace v záloze.')
                apps[app] = {'config': safe_config(entry['config'], app), 'revision': current['apps'].get(app, {}).get('revision', 0) + 1, 'updatedAt': now}
            await self.archive(current)
            # Retain a monotonic generation even for apps absent from an older version.
            for app, entry in current['apps'].items():
                if app not in apps:
                    apps[app] = {'config': {'schemaVersion': 1, 'empty': True}, 'revision': entry['revision'] + 1, 'updatedAt': now}
            current.update(apps=apps, revision=current['revision'] + 1, updatedAt=now)
            await self.put(await self.folder(True), profile_id + '.json', current)
            return metadata(current)


def profile_router(store, authorize):
    def private(response: Response):
        response.headers['Cache-Control'] = 'no-store'
    router = APIRouter(prefix='/api/admin/configuration-profiles', dependencies=[Depends(private)])
    async def access(authorization: str = Header(default='')):
        await authorize(authorization)
    router.dependencies.append(Depends(access))
    @router.get('')
    async def list_profiles():
        return {'items': await store.list()}
    @router.post('')
    async def create_profile(request: Request):
        body = decode(await request.body())
        return await store.create(body.get('name'), body.get('copyFrom'))
    @router.get('/{profile_id}')
    async def get_profile(profile_id: str):
        return await store.read(profile_id)
    @router.put('/{profile_id}/apps/{app}')
    async def save_profile_app(profile_id: str, app: str, request: Request):
        body = decode(await request.body())
        return await store.save_app(profile_id, app, body.get('config'), body.get('expectedRevision'))
    @router.get('/{profile_id}/history')
    async def list_history(profile_id: str):
        return {'items': await store.history(profile_id)}
    @router.post('/{profile_id}/restore')
    async def restore_profile(profile_id: str, request: Request):
        body = decode(await request.body())
        return await store.restore(profile_id, body.get('revision'), body.get('expectedRevision'))
    from generated_links import add_routes
    add_routes(router, store)
    return router

