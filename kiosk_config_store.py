"""Private kiosk configuration files, separate from the public document catalog."""
import json
import re
from datetime import datetime, timezone

MAX_BYTES = 2 * 1024 * 1024
CONFIG_KEYS = {'tileCount','logoUrl','showLogo','tileColumns','tileRows','showInfoPanel','title','subtitle','idleSeconds','pages','school','menuLayout','menuPosition','defaultApp','keyboardMode','layoutOrientation','layoutStyle','layoutBlock','outputType'}

def configuration_name(name):
    if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', name):
        raise ValueError('Název smí obsahovat 1–64 písmen bez diakritiky, číslic, pomlček a podtržítek.')
    return name

def configuration_file(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError('Limit konfigurace je 2 MB.')
    def pairs(items):
        if any(k in {'__proto__','constructor','prototype','token','password','secret','authorization'} for k, _ in items):
            raise ValueError('Konfigurace obsahuje nepovolený klíč nebo přihlašovací údaj.')
        return dict(items)
    data = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(data, dict) or data.get('format') != 'eduvize-kiosk' or data.get('version') != 1:
        raise ValueError('Nepodporovaný formát konfigurace.')
    config = data.get('config')
    if not isinstance(config, dict):
        raise ValueError('Chybí konfigurace kiosku.')
    pages = config.get('pages')
    if not isinstance(pages, list) or not 1 <= len(pages) <= 200:
        raise ValueError('Neplatný seznam podstránek.')
    ids = set()
    total = 0
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get('id'), str) or not page['id'] or page['id'] in ids:
            raise ValueError('Podstránky musí mít jedinečné identifikátory.')
        ids.add(page['id'])
        buttons = page.get('buttons')
        if not isinstance(buttons, list) or len(buttons) > 200:
            raise ValueError('Neplatný seznam tlačítek.')
        total += len(buttons)
        for button in buttons:
            if not isinstance(button, dict) or button.get('type') not in ('page','url','app','document') or not isinstance(button.get('target'), str):
                raise ValueError('Neplatná akce tlačítka.')
        content = page.get('content')
        if content is not None and (not isinstance(content, dict) or not isinstance(content.get('sections'), list) or len(content['sections']) > 100):
            raise ValueError('Neplatná struktura obsahu.')
    if 'home' not in ids or total > 5000:
        raise ValueError('Chybí hlavní nabídka nebo je překročen počet tlačítek.')
    return {'format':'eduvize-kiosk', 'version':1,
            'savedAt':datetime.now(timezone.utc).isoformat(),
            'config':{key:value for key,value in config.items() if key in CONFIG_KEYS}}

class KioskConfigStore:
    def __init__(self, graph, ensure_folder, system_folder, child_named, read_json, lock):
        self.graph, self.ensure_folder, self.system_folder = graph, ensure_folder, system_folder
        self.child_named, self.read_json, self.lock = child_named, read_json, lock

    async def folder(self, create=False):
        parent = await self.ensure_folder()
        system = await self.system_folder(parent) if create else await self.child_named(parent, '_Eduvize-system')
        if not system:
            return None
        if isinstance(system, dict):
            if 'folder' not in system:
                raise ValueError('Systémový adresář koliduje se souborem.')
            system = system['id']
        folder = await self.child_named(system, 'Kiosek')
        if folder:
            if 'folder' not in folder:
                raise ValueError('Adresář konfigurací koliduje se souborem.')
            return folder['id']
        if not create:
            return None
        response = await self.graph('POST', f'/me/drive/items/{system}/children', json={'name':'Kiosek','folder':{},'@microsoft.graph.conflictBehavior':'fail'})
        return response.json()['id']

    async def list(self):
        folder = await self.folder()
        if not folder:
            return []
        response = await self.graph('GET', f'/me/drive/items/{folder}/children', params={'$select':'name,lastModifiedDateTime', '$top':200})
        return sorted([{'name':item['name'][:-5], 'modifiedAt':item.get('lastModifiedDateTime','')}
                       for item in response.json().get('value', [])
                       if re.fullmatch(r'[a-zA-Z0-9_-]{1,64}\.json', item['name'])], key=lambda item:item['name'])

    async def load(self, name):
        configuration_name(name)
        folder = await self.folder()
        item = await self.child_named(folder, name+'.json') if folder else None
        if not item:
            return None
        return await self.read_json(item)

    async def save(self, name, raw):
        configuration_name(name)
        data = configuration_file(raw)
        async with self.lock:
            folder = await self.folder(create=True)
            previous = await self.child_named(folder, name+'.json')
            if previous:
                backup = await self.read_json(previous)
                await self.graph('PUT', f'/me/drive/items/{folder}:/{name}.previous.json:/content',
                                 content=json.dumps(backup, ensure_ascii=False).encode(), headers={'Content-Type':'application/json'})
            await self.graph('PUT', f'/me/drive/items/{folder}:/{name}.json:/content',
                             content=json.dumps(data, ensure_ascii=False).encode(), headers={'Content-Type':'application/json'})
        return {'name':name, 'savedAt':data['savedAt']}
