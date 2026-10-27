"""Bounded optional embedding index. Raw sources are never sent for indexing."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import sqlite3
import time
from collections import OrderedDict

from .security import safe_text, PRIVATE


def unit_vector(values, dimensions):
    if not isinstance(values, (list, tuple)) or len(values) != dimensions:
        raise ValueError('embedding_dimensions_mismatch')
    numbers = [float(x) for x in values]
    if not all(math.isfinite(x) for x in numbers):
        raise ValueError('embedding_nonfinite')
    norm = math.sqrt(sum(x*x for x in numbers))
    if norm <= 0:
        raise ValueError('embedding_zero_vector')
    return [x/norm for x in numbers]


class VectorMemory:
    def __init__(self, engine, provider, config, *, clock=time.time):
        self.engine, self.provider, self.config, self.clock = engine, provider, config, clock
        self.dim = int(provider.get_dim())
        if not 1 <= self.dim <= 8192:
            raise ValueError('embedding_dimensions_required')
        pc = getattr(provider, 'provider_config', {})
        spec = {k: pc.get(k) for k in ('id', 'type', 'embedding_model', 'embedding_api_base',
                                      'embedding_dimensions', 'model', 'api_base')}
        self.model = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
        self.path = engine._safe_path(engine.root / 'index/embedding.sqlite3')
        if not self.path.exists():
            fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            os.close(fd)
        os.chmod(self.path,0o600)
        for suffix in ('-wal','-shm'):
            journal=engine._safe_path(self.path.with_name(self.path.name+suffix))
            if journal.exists():os.chmod(journal,0o600)
        self.db = sqlite3.connect(self.path, timeout=.1)
        self.db.executescript('''PRAGMA journal_mode=WAL; PRAGMA secure_delete=ON;
            CREATE TABLE IF NOT EXISTS vectors(agent TEXT, ns TEXT, digest TEXT, model TEXT,
              dim INTEGER, vector TEXT NOT NULL, PRIMARY KEY(agent,ns,digest,model));
            CREATE TABLE IF NOT EXISTS usage(day TEXT PRIMARY KEY,calls INTEGER,utf8_bytes INTEGER);
            CREATE TABLE IF NOT EXISTS stats(key TEXT PRIMARY KEY,value INTEGER);
        ''')
        os.chmod(self.path, 0o600)
        self.cache = OrderedDict()
        self.inflight = None
        self.closed = False
        self.cooldown_until = 0.
        self.wake = asyncio.Event()
        self.worker = None

    def metric(self, key):
        with self.db:
            self.db.execute('INSERT INTO stats VALUES(?,1) ON CONFLICT(key) DO UPDATE SET value=value+1', (key,))

    def reserve(self, texts):
        size = sum(len(t.encode('utf-8')) for t in texts)
        day = time.strftime('%Y-%m-%d', time.gmtime(self.clock()+8*3600))
        with self.db:
            row = self.db.execute('SELECT calls,utf8_bytes FROM usage WHERE day=?', (day,)).fetchone() or (0,0)
            if row[0]+1 > int(self.config.get('embedding_daily_calls', 500)) or row[1]+size > int(self.config.get('embedding_daily_utf8_bytes', 200000)):
                self.metric('budget_rejections')
                return False
            self.db.execute('INSERT INTO usage VALUES(?,1,?) ON CONFLICT(day) DO UPDATE SET calls=calls+1,utf8_bytes=utf8_bytes+excluded.utf8_bytes', (day,size))
        return True

    def busy(self):
        return self.inflight is not None and not self.inflight.done()

    async def _request(self, texts, on_success):
        try:
            result = await self.provider.get_embeddings(texts)
            if len(result) != len(texts):
                raise ValueError('embedding_count_mismatch')
            vectors = [unit_vector(v, self.dim) for v in result]
            if not self.closed:
                on_success(vectors)
                self.metric('successful_calls')
            return vectors
        except asyncio.CancelledError:
            raise
        except Exception:
            # Provider errors can include credentials or private text: never serialize them.
            if not self.closed:
                self.metric('failed_calls')
                self.cooldown_until = self.clock()+300
            return None

    async def request(self, texts, callback, timeout):
        if self.closed or self.busy() or self.clock() < self.cooldown_until or not self.reserve(texts):
            return None
        self.inflight = asyncio.create_task(self._request(texts, callback))
        try:
            # A timed-out SDK thread may still run. Keep its task until completion;
            # no overlapping requests, automatic retry or model fallback.
            return await asyncio.wait_for(asyncio.shield(self.inflight), timeout)
        except asyncio.TimeoutError:
            self.metric('wait_timeouts')
            return None

    def candidates(self, principal):
        # ACL is applied by the engine before text/digest/vector ranking is accessed.
        return [r for r in self.engine.vector_documents(principal) if not PRIVATE.search(r['text'])]

    async def related(self, principal, query):
        query = safe_text(query[:512], 1024)
        if PRIVATE.search(query):return []
        docs = self.candidates(principal)
        if not docs or not query:
            return []
        visible = []
        for row in docs:
            stored = self.db.execute('SELECT vector FROM vectors WHERE agent=? AND ns=? AND digest=? AND model=? AND dim=?',
                                     (row['agent'], row['ns'], row['digest'], self.model, self.dim)).fetchone()
            if stored:
                visible.append((row, json.loads(stored[0])))
        if not visible:
            return []  # No API spending when this principal has no indexed memories.
        key = self.engine._mac(json.dumps([self.model,principal.agent,principal.actor,
                                principal.readable,query],ensure_ascii=False))
        cached = self.cache.get(key)
        if cached and cached[0] > self.clock():
            qvec = cached[1]
            self.metric('query_cache_hits')
        else:
            def save(vectors):
                self.cache[key] = (self.clock()+3600,vectors[0])
                self.cache.move_to_end(key)
                while len(self.cache)>128:self.cache.popitem(last=False)
            result = await self.request([query], save, float(self.config.get('embedding_query_timeout_seconds', .6)))
            if result is None:
                return []
            qvec = result[0]
        scored = []
        for row, vec in visible:
            similarity = sum(x*y for x,y in zip(qvec,vec))
            if similarity >= float(self.config.get('embedding_min_similarity', .78)):
                scored.append({'id':row['id'],'digest':row['digest'],'similarity':similarity})
        return sorted(scored,key=lambda r:(-r['similarity'],r['id']))[:3]

    async def index_once(self):
        docs = [r for r in self.engine.vector_documents() if not PRIVATE.search(r['text'])]
        current = {(r['agent'],r['ns'],r['digest']) for r in docs}
        with self.db:
            for agent,ns,digest,model in self.db.execute('SELECT agent,ns,digest,model FROM vectors').fetchall():
                if model != self.model or (agent,ns,digest) not in current:
                    self.db.execute('DELETE FROM vectors WHERE agent=? AND ns=? AND digest=? AND model=?',(agent,ns,digest,model))
        pending, seen = [], set()
        for row in docs:
            key = (row['agent'],row['ns'],row['digest'])
            if key in seen:continue
            seen.add(key)
            if not self.db.execute('SELECT 1 FROM vectors WHERE agent=? AND ns=? AND digest=? AND model=? AND dim=?',(*key,self.model,self.dim)).fetchone():
                pending.append(row)
            if len(pending)>=16:break
        if not pending:return
        def save(vectors):
            # Re-check identity, digest, expiration and document before committing late results.
            valid = {(r['agent'],r['ns'],r['digest']) for r in self.engine.vector_documents()}
            with self.db:
                for row,vector in zip(pending,vectors):
                    key = (row['agent'],row['ns'],row['digest'])
                    if key in valid:
                        self.db.execute('INSERT OR REPLACE INTO vectors VALUES(?,?,?,?,?,?)',(*key,self.model,self.dim,json.dumps(vector,separators=(',',':'))))
        await self.request([r['text'] for r in pending], save, 20.)

    async def run(self):
        try:
            await asyncio.sleep(5)
            while not self.closed:
                self.wake.clear()
                try:await self.index_once()
                except Exception:self.metric('index_failures')
                try:await asyncio.wait_for(self.wake.wait(), max(60,int(self.config.get('embedding_index_interval_seconds',1800))))
                except asyncio.TimeoutError:pass
        except asyncio.CancelledError:pass

    def start(self):
        self.worker = asyncio.create_task(self.run())

    async def close(self):
        self.closed = True
        if self.worker:
            self.worker.cancel()
            await asyncio.gather(self.worker,return_exceptions=True)
        if self.busy():
            self.inflight.cancel()
            await asyncio.gather(self.inflight,return_exceptions=True)
        self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        self.db.close()
