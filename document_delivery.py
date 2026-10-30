"""Bounded process-local caches; visibility is checked before every file response."""
import asyncio
import copy
import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass

class AsyncCache:
    def __init__(self, ttl, max_weight, weight=lambda value: 1, clock=time.monotonic):
        self.ttl, self.max_weight, self.weight, self.clock = ttl, max_weight, weight, clock
        self.entries, self.pending, self.generation, self.used = OrderedDict(), {}, 0, 0

    def clear(self):
        self.generation += 1
        self.entries.clear()
        self.used = 0

    def _remove(self, key):
        entry = self.entries.pop(key, None)
        if entry:
            self.used -= entry[2]

    async def get(self, key, loader):
        now = self.clock()
        for expired, entry in list(self.entries.items()):
            if entry[0] <= now:
                self._remove(expired)
        if key in self.entries:
            entry = self.entries[key]
            self.entries.move_to_end(key)
            return entry[1]
        generation = self.generation
        pending = self.pending.get(key)
        if pending and pending[0] == generation:
            return await asyncio.shield(pending[1])

        async def load():
            try:
                value = await loader()
                weight = self.weight(value)
                if generation == self.generation and weight <= self.max_weight:
                    self._remove(key)
                    while self.entries and self.used + weight > self.max_weight:
                        self._remove(next(iter(self.entries)))
                    self.entries[key] = (self.clock() + self.ttl, value, weight)
                    self.used += weight
                return value
            finally:
                current = self.pending.get(key)
                if current and current[1] is asyncio.current_task():
                    self.pending.pop(key, None)
        task = asyncio.create_task(load())
        self.pending[key] = (generation, task)
        return await asyncio.shield(task)

@dataclass(frozen=True)
class Asset:
    data: bytes
    etag: str

class DocumentDelivery:
    def __init__(self, manifest, download, clock=time.monotonic):
        self.manifest, self.download = manifest, download
        self.catalog_cache = AsyncCache(15, 1, clock=clock)
        self.file_cache = AsyncCache(60, 64 * 1024 * 1024, weight=lambda asset: len(asset.data), clock=clock)

    def invalidate(self):
        self.catalog_cache.clear()
        self.file_cache.clear()

    async def catalog(self):
        return copy.deepcopy(await self.catalog_cache.get('catalog', self.manifest))

    async def visible_items(self):
        data = await self.catalog()
        hidden = set(data.get('hidden_categories', []))
        return [item for item in data['items'] if item.get('visible', True) and (item.get('scope','documents')=='kiosk' or item.get('category', 'Ostatní') not in hidden)]

    async def file(self, doc_id):
        generation = self.catalog_cache.generation
        item = next((item for item in await self.visible_items() if item['id'] == doc_id), None)
        if item is None:
            raise KeyError(doc_id)
        async def load():
            data = await self.download(item)
            return Asset(data, '"' + hashlib.sha256(data).hexdigest() + '"')
        asset = await self.file_cache.get(item['file_id'], load)
        if generation != self.catalog_cache.generation:
            return await self.file(doc_id)
        return item, asset
