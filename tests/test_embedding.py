"""Synthetic vectors; no paid APIs or actual QQ events."""
import asyncio
import json
import math
import os
import tempfile
import unittest
from pathlib import Path

from astrbot_plugin_family_memory.engine import MemoryEngine
from astrbot_plugin_family_memory.embedding import VectorMemory, unit_vector
from astrbot_plugin_family_memory.tests.test_engine import fixture_config


class Provider:
    provider_config = {'id':'synthetic-embedding','embedding_model':'fixture','embedding_dimensions':3}
    def __init__(self):self.calls=0;self.delay=0;self.error=False
    def get_dim(self):return 3
    async def get_embeddings(self,texts):
        self.calls+=1
        await asyncio.sleep(self.delay)
        if self.error:raise RuntimeError('synthetic credential must not be logged')
        return [[1.,0.,0.] if 'unrelated' not in t else [0.,1.,0.] for t in texts]


class VectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='family-vectors-')
        self.config=fixture_config(embedding_query_timeout_seconds=.2)
        self.engine=MemoryEngine(Path(self.tmp.name),self.config)
        self.owner=self.engine.policy.resolve('default','fixture-bot','owner-fixture')
        self.visitor=self.engine.policy.resolve('default','fixture-bot','visitor-A')
        self.bot2=self.engine.policy.resolve('official','official-self','owner-openid-fixture')
        self.provider=Provider()
        self.vec=VectorMemory(self.engine,self.provider,self.config)
        self.seq=0

    async def asyncTearDown(self):
        await self.vec.close();self.engine.close();self.tmp.cleanup()

    def write(self,p,text):
        self.seq+=1
        source=self.engine.capture(p,'vector-event-'+str(self.seq),text)
        return self.engine.remember(p,text,[{'id':source,'quote':text}])

    async def test_incremental_reuses_unchanged_vectors(self):
        self.write(self.owner,'我喜欢金色茶盏')
        await self.vec.index_once();await self.vec.index_once()
        self.assertEqual(self.provider.calls,1)

    async def test_semantic_recall_without_keyword_overlap(self):
        mid=self.write(self.owner,'我喜欢金色茶盏')
        await self.vec.index_once()
        hits=await self.vec.related(self.owner,'杯子偏好')
        self.assertEqual(hits[0]['id'],mid)
        self.assertEqual(self.engine.search(self.owner,'杯子偏好',semantic=hits)[0]['id'],mid)

    async def test_cross_agent_and_visitor_acl_before_query_call(self):
        self.write(self.owner,'我喜欢金色茶盏');await self.vec.index_once()
        self.assertEqual(await self.vec.related(self.visitor,'杯子偏好'),[])
        self.assertEqual(await self.vec.related(self.bot2,'杯子偏好'),[])
        self.assertEqual(self.provider.calls,1)

    async def test_peer_owner_peer_mutual_read_keeps_write_isolation(self):
        self.config.update(bot2_private_mutual_read=True,
            bot2_peer_binding={'approved':True,'evidence_ref':'synthetic-confirmed','openid':'peer-fixture'})
        owner=self.engine.policy.resolve('official','official-self','owner-openid-fixture')
        peer=self.engine.policy.resolve('official','official-self','peer-fixture')
        mid=self.write(peer,'我喜欢金色茶盏');await self.vec.index_once()
        self.assertEqual((await self.vec.related(owner,'杯子偏好'))[0]['id'],mid)
        from astrbot_plugin_family_memory.security import Rejected
        with self.assertRaises(Rejected):self.engine.forget(owner,mid)

    async def test_forged_semantic_hit_cannot_bypass_acl(self):
        mid=self.write(self.owner,'我喜欢金色茶盏')
        row=self.engine.get(self.owner,mid)
        hit=[{'id':mid,'digest':row['digest'],'similarity':1.}]
        self.assertEqual(self.engine.search(self.visitor,'杯子偏好',semantic=hit),[])

    async def test_irrelevant_vector_not_injected(self):
        self.write(self.owner,'我喜欢金色茶盏');await self.vec.index_once()
        self.assertEqual(await self.vec.related(self.owner,'unrelated weather'),[])

    async def test_query_vector_cache_reuses_call(self):
        self.write(self.owner,'我喜欢金色茶盏');await self.vec.index_once()
        await self.vec.related(self.owner,'杯子偏好');await self.vec.related(self.owner,'杯子偏好')
        self.assertEqual(self.provider.calls,2)

    async def test_forget_blocks_cached_query_and_purges_vector(self):
        mid=self.write(self.owner,'我喜欢金色茶盏');await self.vec.index_once()
        await self.vec.related(self.owner,'杯子偏好')
        self.engine.forget(self.owner,mid)
        self.assertEqual(await self.vec.related(self.owner,'杯子偏好'),[])
        await self.vec.index_once()
        self.assertEqual(self.vec.db.execute('select count(*) from vectors').fetchone()[0],0)

    async def test_edit_invalidates_old_vector(self):
        mid=self.write(self.owner,'我喜欢金色茶盏');await self.vec.index_once()
        source=self.engine.capture(self.owner,'correction','我喜欢绿色风筝')
        self.engine.correct(self.owner,mid,'我喜欢绿色风筝',[{'id':source,'quote':'我喜欢绿色风筝'}])
        self.assertEqual(await self.vec.related(self.owner,'杯子偏好'),[])
        await self.vec.index_once();self.assertEqual(self.provider.calls,2)

    async def test_sources_are_never_indexed(self):
        self.engine.capture(self.owner,'cache-only','我喜欢青色纸鹤')
        await self.vec.index_once();self.assertEqual(self.provider.calls,0)

    async def test_private_marked_memory_and_query_not_uploaded(self):
        self.write(self.owner,'保密，我喜欢青色纸鹤')
        await self.vec.index_once();self.assertEqual(self.provider.calls,0)
        self.write(self.owner,'我喜欢金色茶盏');await self.vec.index_once()
        self.assertEqual(await self.vec.related(self.owner,'保密住址'),[])
        self.assertEqual(self.provider.calls,1)

    async def test_budget_persists_across_reopen(self):
        self.config['embedding_daily_calls']=1
        self.write(self.owner,'我喜欢金色茶盏');await self.vec.index_once()
        await self.vec.close();self.vec=VectorMemory(self.engine,self.provider,self.config)
        self.assertEqual(await self.vec.related(self.owner,'杯子偏好'),[])
        self.assertEqual(self.provider.calls,1)

    async def test_timeout_does_not_create_parallel_requests(self):
        self.config['embedding_query_timeout_seconds']=.02
        self.write(self.owner,'我喜欢金色茶盏');await self.vec.index_once()
        self.provider.delay=.1
        self.assertEqual(await self.vec.related(self.owner,'杯子偏好'),[])
        self.assertEqual(await self.vec.related(self.owner,'另一个问题'),[])
        self.assertEqual(self.provider.calls,2)
        await asyncio.sleep(.12)
        self.assertTrue(await self.vec.related(self.owner,'杯子偏好'))
        self.assertEqual(self.provider.calls,2)

    async def test_provider_error_cools_down_without_retry(self):
        self.write(self.owner,'我喜欢金色茶盏');self.provider.error=True
        await self.vec.index_once();await self.vec.index_once()
        self.assertEqual(self.provider.calls,1)
        self.assertEqual(self.vec.db.execute("select value from stats where key='failed_calls'").fetchone()[0],1)

    async def test_sidecar_survives_reopen(self):
        self.write(self.owner,'我喜欢金色茶盏');await self.vec.index_once()
        await self.vec.close();self.vec=VectorMemory(self.engine,self.provider,self.config)
        await self.vec.index_once();self.assertEqual(self.provider.calls,1)
        self.assertEqual(self.vec.db.execute('pragma integrity_check').fetchone()[0],'ok')

    async def test_model_change_reindexes(self):
        self.write(self.owner,'我喜欢金色茶盏');await self.vec.index_once()
        await self.vec.close()
        self.provider.provider_config={**self.provider.provider_config,'embedding_model':'new-fixture'}
        self.vec=VectorMemory(self.engine,self.provider,self.config)
        await self.vec.index_once();self.assertEqual(self.provider.calls,2)

    async def test_invalid_vectors_rejected(self):
        for value in ([0,0,0],[math.nan,0,1],[1,2]):
            with self.assertRaises(ValueError):unit_vector(value,3)

    async def test_linux_database_and_journals_private_from_creation(self):
        if os.name=='nt':return  # Windows privacy uses ACLs rather than POSIX mode.
        for suffix in ('','-wal','-shm'):
            path=Path(str(self.vec.path)+suffix)
            if path.exists():self.assertEqual(path.stat().st_mode & 0o777,0o600)

    async def test_byte_budget_rejects_before_api(self):
        self.config['embedding_daily_utf8_bytes']=1
        self.write(self.owner,'我喜欢金色茶盏');await self.vec.index_once()
        self.assertEqual(self.provider.calls,0)

    async def test_lexical_retrieval_before_index_ready(self):
        mid=self.write(self.owner,'我喜欢金色茶盏')
        hits=await self.vec.related(self.owner,'金色茶盏')
        self.assertEqual(self.engine.search(self.owner,'金色茶盏',semantic=hits)[0]['id'],mid)

    async def test_late_response_after_forget_does_not_restore_vector(self):
        mid=self.write(self.owner,'我喜欢金色茶盏');self.provider.delay=.05
        task=asyncio.create_task(self.vec.index_once())
        await asyncio.sleep(.01);self.engine.forget(self.owner,mid)
        await task
        self.assertEqual(self.vec.db.execute('select count(*) from vectors').fetchone()[0],0)
