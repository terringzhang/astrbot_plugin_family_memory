import unittest,tempfile,asyncio,json
from pathlib import Path
from astrbot_plugin_family_memory.engine import MemoryEngine
from astrbot_plugin_family_memory.lifecycle import ConversationArchive
from astrbot_plugin_family_memory.embedding import VectorMemory
from astrbot_plugin_family_memory.archive_semantic import ArchiveSemantic
from astrbot_plugin_family_memory.tests.test_engine import fixture_config

class Provider:
 provider_config={'id':'synthetic'}
 def __init__(self):self.calls=0
 def get_dim(self):return 2
 async def get_embeddings(self,texts):
  self.calls+=1
  return [[1.,0.] if ('房' in x or '住所' in x) else [0.,1.] for x in texts]

class ArchiveTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();r=Path(self.tmp.name)
  self.e=MemoryEngine(r/'mem',fixture_config());self.a=ConversationArchive(r/'arc',self.e.key)
  self.p=self.e.policy.resolve('default','fixture-bot','owner-fixture');self.peer=self.e.policy.resolve('default','fixture-bot','peer-fixture')
  self.provider=Provider();self.v=VectorMemory(self.e,self.provider,{})
  self.s=ArchiveSemantic(self.a,self.v)
 def add(self,p,text,role='user'):
  self.a.snapshot(p,text,[{'role':role,'content':text}])
 async def asyncTearDown(self):
  await self.v.close();self.a.close();self.e.close();self.tmp.cleanup()
 async def test_meaning_without_common_keyword_and_cache(self):
  self.add(self.p,'打算买一台电脑当作我们的房子')
  await self.s.index_once();r=await self.s.search(self.p,'未来住所');self.assertEqual(len(r),1)
  self.assertIn('房子',r[0]['text']);calls=self.provider.calls
  await self.s.search(self.p,'未来住所');self.assertEqual(calls,self.provider.calls)
 async def test_identity_isolation_before_api(self):
  self.add(self.p,'打算购买房子');await self.s.index_once();calls=self.provider.calls
  self.assertEqual(await self.s.search(self.peer,'未来住所'),[]);self.assertEqual(calls,self.provider.calls)
 async def test_cross_agent_isolation(self):
  self.add(self.p,'打算购买房子');await self.s.index_once()
  bot2=self.e.policy.resolve('official','','owner-openid-fixture')
  self.assertEqual(await self.s.search(bot2,'未来住所'),[])
 async def test_incremental_dedup_and_persistence(self):
  self.add(self.p,'房子计划是买一台电脑');self.add(self.p,'房子计划是买一台电脑')
  await self.s.index_once();calls=self.provider.calls;await self.s.index_once()
  self.assertEqual(calls,self.provider.calls);self.assertEqual(self.v.db.execute('select count(*) from archive_vectors').fetchone()[0],1)
  other=ArchiveSemantic(self.a,self.v);self.assertTrue(await other.search(self.p,'未来住所'))
 async def test_low_similarity_and_sensitive_and_tool_excluded(self):
  self.add(self.p,'房子计划');self.add(self.p,'工具中的房子信息','tool');self.add(self.p,'/fmem remember private 房子命令')
  self.assertEqual(len(self.s.documents()),1);await self.s.index_once()
  self.assertEqual(await self.s.search(self.p,'天气'),[])
 async def test_archive_budget_and_global_budget(self):
  self.add(self.p,'房子计划')
  day=__import__('time').strftime('%Y-%m-%d',__import__('time').gmtime(self.v.clock()+28800))
  with self.v.db:self.v.db.execute('insert into archive_usage values(?,100000,0)',(day,))
  await self.s.index_once();self.assertEqual(self.provider.calls,0)
 async def test_global_budget_and_busy_preserved(self):
  self.add(self.p,'房子计划');self.v.config['embedding_daily_calls']=0
  await self.s.index_once();self.assertEqual(self.provider.calls,0)
 async def test_query_timeout_falls_back(self):
  self.add(self.p,'房子计划');await self.s.index_once()
  async def unavailable(*args,**kwargs):return None
  self.v.request=unavailable
  self.assertTrue(await self.s.search(self.p,'房子'));self.assertEqual(await self.s.search(self.p,'未来住所'),[])
