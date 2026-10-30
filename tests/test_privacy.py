import json,sqlite3,tempfile,unittest,types
from pathlib import Path
from astrbot_plugin_family_memory.security import Principal,Rejected
from astrbot_plugin_family_memory.privacy import PrivacyPolicy,level,filtered_payload
from astrbot_plugin_family_memory.tests.test_archive_semantic import ArchiveTests

class PrivacyTests(ArchiveTests):
 async def test_redacted_tool_arguments_remain_valid_json(self):
  raw={'function':{'name':'fixture_tool','arguments':json.dumps({'token':'fixture-not-real'})}}
  result=filtered_payload(raw);self.assertEqual(json.loads(result['function']['arguments']),{})
 async def test_credential_image_link_becomes_safe_text_but_normal_image_retained(self):
  bad={'type':'image_url','image_url':{'url':'https://example.test/image?access_token=fixture-not-real'}}
  self.assertEqual(filtered_payload(bad)['type'],'text')
  normal={'type':'image_url','image_url':{'url':'https://example.test/normal.png'}}
  self.assertEqual(filtered_payload(normal),normal)
 async def test_explicit_chinese_credentials_and_personal_health_address(self):
  self.assertEqual(level('验证码是000000'),3)
  self.assertEqual(level('我被诊断为合成测试病症'),2)
  self.assertEqual(level('我住在合成测试路0号'),2)
  self.assertEqual(level('研究如何用模型做医学诊断'),1)
 async def test_policy_evaluated_per_record_not_per_fts_join_pair(self):
  for i in range(12):self.add(self.p,'普通房子计划'+str(i))
  before=self.a.privacy.allowed;calls=[]
  def counted(*args,**kwargs):calls.append(1);return before(*args,**kwargs)
  self.a.privacy.allowed=counted
  self.a.search(self.p,'房子')
  self.assertLessEqual(len(calls),18)
 async def test_late_privacy_guard_blocks_provider_before_send(self):
  result=await self.v.request(['synthetic safe question'],lambda values:None,1.,guard=lambda:False)
  self.assertIsNone(result);self.assertEqual(self.provider.calls,0)
 async def asyncSetUp(self):
  await super().asyncSetUp();self.a.privacy=self.e.privacy
  self.reader=Principal(self.p.agent,'f'*24,'peer',self.p.private_ns,(self.p.private_ns,))
 async def test_private_owner_only_across_paths(self):
  self.add(self.p,'仅你知道：房子在青松路')
  self.assertTrue(self.a.search(self.p,'保密 房子'))
  self.assertEqual(self.a.search(self.reader,'房子'),[]);self.assertEqual(self.a.earliest(self.reader),[])
  self.assertEqual(self.a.search_report(self.reader,[],'relevance')['coverage']['searchable_messages'],0)
  row=self.a.db.execute('select id from messages').fetchone()[0];self.assertEqual(self.a.describe_times(self.reader,[{'id':row}]),[])
  self.assertEqual(self.s.documents(),[]);await self.s.index_once();self.assertEqual(self.provider.calls,0)
 async def test_consent_revoke_persists_and_does_not_allow_embedding(self):
  text='仅你知道：房子在青松路';self.add(self.p,text);mid=self.a.db.execute('select id from messages').fetchone()[0];record=self.a.privacy_record(self.p,mid)
  self.e.privacy.consent(self.p,record,self.reader.actor,True);self.assertTrue(self.a.search(self.reader,'房子'))
  other=PrivacyPolicy(self.e.root,self.e.key);self.assertTrue(other.allowed(self.reader,**record))
  self.assertEqual(self.s.documents(),[])
  self.e.privacy.consent(self.p,record,self.reader.actor,False);self.assertFalse(self.a.search(self.reader,'房子'));self.assertFalse(other.allowed(self.reader,**record))
 async def test_credential_never_returned_even_after_consent(self):
  text='password: fixture-not-a-real-credential'
  # Simulate pre-existing raw history without mutating it during policy checks.
  with self.a.db:
   self.a.db.execute('insert into messages(agent,ns,actor,cid,digest,occurrence,role,payload,created) values(?,?,?,?,?,1,?,?,1)',(self.p.agent,self.p.private_ns,self.p.actor,'secret','fixture','user',json.dumps({'role':'user','content':text})))
   mid=self.a.db.execute('select id from messages').fetchone()[0];self.a.db.execute('insert into chat_fts values(?,?)',(str(mid),text))
  self.assertEqual(self.a.search(self.p,'fixture'),[]);self.assertEqual(self.a.earliest(self.p),[]);self.assertEqual(self.a.describe_times(self.p,[{'id':mid}]),[])
  with self.assertRaises(Rejected):self.e.privacy.consent(self.p,dict(agent=self.p.agent,ns=self.p.private_ns,subject=self.p.actor,text=text),self.reader.actor,True)
 async def test_science_not_sensitive_and_query_stays_local(self):
  self.assertEqual(level('讨论医学诊断算法与住址标准化研究'),1)
  self.add(self.p,'讨论医学诊断算法与住址标准化研究');self.assertTrue(self.a.search(self.reader,'诊断'))
  self.add(self.p,'仅你知道：房子');calls=self.provider.calls;self.assertTrue(await self.s.search(self.p,'保密 房子'));self.assertEqual(calls,self.provider.calls)
 async def test_explicit_restrict_clears_grants_and_embedding(self):
  self.add(self.p,'房子在青松路');mid=self.a.db.execute('select id from messages').fetchone()[0];record=self.a.privacy_record(self.p,mid)
  self.assertTrue(self.a.search(self.reader,'房子'));self.e.privacy.restrict(self.p,record)
  self.assertEqual(self.a.search(self.reader,'房子'),[]);self.assertTrue(self.a.search(self.p,'房子'));self.assertEqual(self.s.documents(),[])
 async def test_only_subject_can_grant_and_base_acl_not_expanded(self):
  record=dict(agent=self.p.agent,ns=self.p.private_ns,subject=self.p.actor,text='保密 房子')
  with self.assertRaises(Rejected):self.e.privacy.consent(self.reader,record,self.reader.actor,True)
  alien=Principal('bot2',self.reader.actor,'owner','unrelated',('unrelated',))
  self.e.privacy.consent(self.p,record,alien.actor,True);self.assertFalse(self.e.privacy.allowed(alien,**record))
 async def test_payload_redaction_and_raw_old_rows_retained(self):
  text='password: fixture-fake-value';self.add(self.p,text)
  payload=self.a.db.execute('select payload from messages').fetchone()[0];self.assertNotIn('fixture-fake-value',payload)
  self.assertEqual(filtered_payload({'parts':[{'token':'fixture-fake-value'}]})['parts'][0]['token'],'[敏感凭据已屏蔽]')
 async def test_formal_cache_rechecked_after_revoke(self):
  text='仅你知道：我喜欢青色松塔';sid=self.e.capture(self.p,'private-source',text);mid=self.e.remember(self.p,text,[{'id':sid,'quote':text}]);record=self.e.privacy_record(self.e.get(self.p,mid))
  self.assertTrue(self.e.search(self.p,'青色松塔'));self.assertEqual(self.e.search(self.reader,'青色松塔'),[])
  self.e.privacy.consent(self.p,record,self.reader.actor,True);self.assertTrue(self.e.search(self.reader,'青色松塔'))
  self.e.privacy.consent(self.p,record,self.reader.actor,False);self.assertEqual(self.e.search(self.reader,'青色松塔'),[])
  self.assertEqual(self.e.vector_documents(),[])
 async def test_sensitive_image_owner_grant_revoke(self):
  folder=self.a.root/'images'/self.p.agent/self.p.actor;folder.mkdir(parents=True);path=folder/'image.png';path.write_bytes(b'fixture')
  mid='a'*32
  with self.a.db:self.a.db.execute('insert into images values(?,?,?,?,?,1)',(mid,self.p.agent,self.p.private_ns,'fixture',str(path.relative_to(self.a.root))))
  self.assertEqual(self.a.image(self.p,mid),path)
  with self.assertRaises(Rejected):self.a.image(self.reader,mid)
  record=self.a.image_privacy_record(self.p,mid);self.e.privacy.consent(self.p,record,self.reader.actor,True);self.assertEqual(self.a.image(self.reader,mid),path)
  self.e.privacy.consent(self.p,record,self.reader.actor,False)
  with self.assertRaises(Rejected):self.a.image(self.reader,mid)
 async def test_shared_fact_subject_comes_from_evidence_not_namespace_first_writer(self):
  text='公开的青松房子计划';sid=self.e.capture(self.p,'family-source',text,share=True);mid=self.e.remember(self.p,text,[{'id':sid,'quote':text}],shared=True)
  record=self.e.privacy_record(self.e.get(self.p,mid));self.assertEqual(record['subject'],self.p.actor)
  self.e.privacy.restrict(self.p,record)
  other=Principal(self.p.agent,'e'*24,'peer','unused',('family',))
  self.assertFalse(self.e.search(other,'青松房子'));self.assertTrue(self.e.search(self.p,'青松房子'))
 async def test_known_sensitive_query_does_not_call_provider(self):
  self.add(self.p,'仅你知道：我把青色松塔放在抽屉');self.add(self.p,'普通房子计划')
  await self.s.index_once();before=self.provider.calls
  self.assertTrue(await self.s.search(self.p,'青色松塔'));self.assertEqual(self.provider.calls,before)
  self.v.archive_index=self.s;await self.v.related(self.p,'青色松塔');self.assertEqual(self.provider.calls,before)
 async def test_real_adapter_consent_command_and_wrong_actor_denied(self):
  from astrbot_plugin_family_memory.tests.test_adapter import FamilyMemoryPlugin
  from astrbot_plugin_family_memory.security import IdentityPolicy
  import asyncio
  cfg=dict(self.e.config,bot2_peer_binding={'approved':True,'evidence_ref':'synthetic','openid':'peer-openid-fixture'},bot2_private_mutual_read=True)
  self.e.policy=IdentityPolicy(self.e.key,cfg)
  owner=self.e.policy.resolve('official','','owner-openid-fixture');peer=self.e.policy.resolve('official','','peer-openid-fixture')
  self.add(owner,'仅你知道：青松房子');mid=self.a.db.execute('select id from messages order by id desc limit 1').fetchone()[0]
  plugin=object.__new__(FamilyMemoryPlugin);plugin.engine=self.e;plugin.archive=self.a;plugin.vectors=None;plugin.config=cfg;plugin.closed=False;plugin.gate=asyncio.Semaphore(1);plugin._principal=lambda event:owner
  event=types.SimpleNamespace(plain_result=lambda text:text)
  outputs=[x async for x in plugin.privacy_command(event,'grant','archive:'+str(mid),'peer')]
  self.assertIn('已授权',outputs[0]);self.assertTrue(self.a.search(peer,'青松房子'))
  plugin._principal=lambda event:peer
  denied=[x async for x in plugin.privacy_command(event,'revoke','archive:'+str(mid),'owner')];self.assertIn('未变更',denied[0])
  plugin._principal=lambda event:owner
  outputs=[x async for x in plugin.privacy_command(event,'revoke','archive:'+str(mid),'peer')];self.assertIn('撤回授权',outputs[0]);self.assertEqual(self.a.search(peer,'青松房子'),[])
