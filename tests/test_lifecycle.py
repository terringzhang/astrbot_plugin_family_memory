import base64,json,sys,tempfile,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from astrbot_plugin_family_memory.lifecycle import ConversationArchive,SOCIAL_TOOLS,estimate,visible,SUMMARY_MARK
from astrbot_plugin_family_memory.engine import MemoryEngine
from astrbot_plugin_family_memory.security import Rejected
from astrbot_plugin_family_memory.tests.test_engine import fixture_config
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1XcAAAAASUVORK5CYII=')
def msg(role,text):return {'role':role,'content':[{'type':'text','text':text}]}
def turns(n):return [m for i in range(n) for m in [msg('user','交流'+str(i)),msg('assistant','回应'+str(i))]]
class LifecycleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.now=[1792810000.]
  self.engine=MemoryEngine(Path(self.tmp.name)/'memory',fixture_config(activation_enabled=True),clock=lambda:self.now[0])
  self.owner=self.engine.policy.resolve('default','fixture-bot','owner-fixture');self.peer=self.engine.policy.resolve('default','fixture-bot','peer-fixture')
  self.archive=ConversationArchive(Path(self.tmp.name)/'archive',self.engine.key,clock=lambda:self.now[0])
 def tearDown(self):self.archive.close();self.engine.close();self.tmp.cleanup()
 def image_turns(self,after):
  m=turns(after+1);m[0]['content'].append({'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(PNG).decode()}});return m
 def test_image_9_rounds_retained(self):
  result,s=self.archive.transform(self.owner,'cid',self.image_turns(9));self.assertEqual(s.get('images_retired',0),0);self.assertEqual(result[0]['content'][1]['type'],'image_url')
 def test_image_10_rounds_retired_but_original_and_bytes_saved(self):
  original=self.image_turns(10);result,s=self.archive.transform(self.owner,'cid',original)
  self.assertEqual(s['images_retired'],1);self.assertEqual(original[0]['content'][1]['type'],'image_url')
  row=self.archive.db.execute('select * from images').fetchone();self.assertEqual(self.archive.image(self.owner,row['id']).read_bytes(),PNG)
  self.assertIn('data:image/png;base64',self.archive.db.execute('select payload from messages where id=1').fetchone()[0])
 def test_image_other_identity_denied(self):
  self.archive.transform(self.owner,'cid',self.image_turns(10));mid=self.archive.db.execute('select id from images').fetchone()[0]
  with self.assertRaises(Rejected):self.archive.image(self.peer,mid)
 def test_unarchivable_image_not_removed(self):
  m=self.image_turns(12);m[0]['content'][1]['image_url']['url']='http://127.0.0.1/private';r,s=self.archive.transform(self.owner,'cid',m)
  self.assertEqual(s['image_archive_failures'],1);self.assertEqual(r[0]['content'][1]['type'],'image_url')
 def test_compaction_never_removes_young_image_early(self):
  m=self.image_turns(4)
  for a in m:a['content'].append(dict(type='text',text='很长的交流'*2000))
  r,s=self.archive.transform(self.owner,'a',m)
  self.assertTrue(any(x.get('type')=='image_url' for a in r for x in a['content'] if isinstance(a['content'],list)))
 def test_duplicate_turns_not_lost_and_repeat_snapshot_dedup(self):
  m=[msg('user','同一句'),msg('assistant','一样'),msg('user','同一句')]
  self.archive.snapshot(self.owner,'cid',m);self.archive.snapshot(self.owner,'cid',m)
  self.assertEqual(self.archive.db.execute('select count(*) from messages').fetchone()[0],3)
  self.assertEqual(self.archive.db.execute('select count(*) from snapshots').fetchone()[0],1)
 def test_scoped_archive_search(self):
  self.archive.snapshot(self.owner,'a',[msg('user','蓝色风铃是我的珍藏')]);self.assertTrue(self.archive.search(self.owner,'蓝色风铃'));self.assertFalse(self.archive.search(self.peer,'蓝色风铃'))
 def test_cross_agent_denied(self):
  bot2=self.engine.policy.resolve('official','','owner-openid-fixture');self.archive.snapshot(self.owner,'a',[msg('user','蓝色风铃')]);self.assertFalse(self.archive.search(bot2,'蓝色风铃'))
 def test_tools_removed_as_pairs_social_kept(self):
  m=[msg('user','检查后给我发图'),{'role':'assistant','content':None,'tool_calls':[{'id':'a','function':{'name':'astrbot_execute_shell','arguments':'SECRET'}},{'id':'b','function':{'name':'send_message_to_user','arguments':'{}'}}]},dict(role='tool',tool_call_id='a',content='long code'),dict(role='tool',tool_call_id='b',content='sent'),msg('assistant','好了')]
  r,s=self.archive.transform(self.owner,'a',m);self.assertEqual(s['technical_calls_removed'],1);self.assertEqual(s['technical_returns_removed'],1)
  self.assertEqual(r[1]['tool_calls'][0]['id'],'b');self.assertEqual(r[2]['tool_call_id'],'b')
  self.assertEqual(self.archive.db.execute('select count(*) from messages').fetchone()[0],5)
 def test_inflight_call_not_removed(self):
  m=[msg('user','x'),dict(role='assistant',content=None,tool_calls=[{'id':'a','function':{'name':'astrbot_execute_shell','arguments':'{}'}}])]
  r,s=self.archive.transform(self.owner,'a',m);self.assertEqual(r[1]['tool_calls'][0]['id'],'a')
 def test_historical_social_shell_preserved_without_execution_permission(self):
  m=[msg('user','发空间'),dict(role='assistant',content=None,tool_calls=[dict(id='a',function=dict(name='astrbot_execute_shell',arguments='python qzone_publish.py'))]),dict(role='tool',tool_call_id='a',content='发布成功')]
  r,s=self.archive.transform(self.owner,'a',m);self.assertEqual(len(r),3);self.assertNotIn('astrbot_execute_shell',SOCIAL_TOOLS)
 def test_archive_write_failure_does_not_mutate_source(self):
  original=self.image_turns(12);before=copy.deepcopy(original)
  self.archive.db.execute('pragma query_only=1')
  with self.assertRaises(Exception):self.archive.transform(self.owner,'a',original)
  self.assertEqual(original,before);self.archive.db.execute('pragma query_only=0')
 def test_image_dedup_reuses_saved_file(self):
  self.archive.transform(self.owner,'a',self.image_turns(9));self.archive.transform(self.owner,'a',self.image_turns(10))
  self.assertEqual(self.archive.db.execute('select count(*) from images').fetchone()[0],1)
 def test_hidden_thinking_removed_but_archived(self):
  m=[msg('user','你好'),dict(role='assistant',content=[dict(type='think',think='internal',encrypted='signature'),dict(type='text',text='你好呀')])]
  r,s=self.archive.transform(self.owner,'a',m);self.assertEqual(r[1]['content'],[dict(type='text',text='你好呀')]);self.assertEqual(s['historical_thinking_removed'],1)
 def test_tool_payload_not_searchable(self):
  m=[dict(role='tool',tool_call_id='a',content='技术红色气球'),dict(role='assistant',content='',tool_calls=[dict(id='a',function=dict(name='astrbot_execute_shell',arguments='技术红色气球'))])]
  self.archive.snapshot(self.owner,'a',m);self.assertFalse(self.archive.search(self.owner,'红色气球'))
 def test_long_history_compacts_and_raw_survives(self):
  m=turns(40)
  for a in m:a['content'][0]['text']+='交流原文'*300
  r,s=self.archive.transform(self.owner,'a',m);self.assertTrue(visible(r[0]).startswith(SUMMARY_MARK));self.assertLess(estimate(r),estimate(m));self.assertEqual(self.archive.db.execute('select count(*) from messages').fetchone()[0],80)
 def test_handoff_is_scoped_by_conversation_and_identity(self):
  m=turns(40)
  for a in m:a['content'][0]['text']+='交流原文'*300
  self.archive.transform(self.owner,'a',m)
  self.assertEqual(self.archive.db.execute('select count(*) from handoffs where cid=?',('b',)).fetchone()[0],0)
 def test_tool_whitelist_denies_maintenance(self):
  for name in ['astrbot_execute_python','astrbot_execute_shell','astrbot_file_read_tool','astrbot_file_write_tool','astrbot_execute_browser','handoff_admin']:self.assertNotIn(name,SOCIAL_TOOLS)
  for name in ['send_message_to_user','search_memes','llm_publish_feed','companion_archive_search','companion_memory_save']:self.assertIn(name,SOCIAL_TOOLS)
 def write(self,text='我喜欢紫色风筝',kind='preference'):
  sid=self.engine.capture(self.owner,'one',text);return self.engine.remember(self.owner,text,[{'id':sid,'quote':text}],kind=kind)
 def test_unused_activation_decays_without_deletion(self):
  mid=self.write();r=self.engine.search(self.owner,'紫色风筝')[0];self.now[0]+=60*86400;self.engine.cache.clear();s=self.engine.search(self.owner,'紫色风筝')
  if s:self.assertLess(s[0]['score'],r['score'])
  self.assertEqual(self.engine.db.execute('select status from memories where id=?',(mid,)).fetchone()[0],'active')
 def test_reading_and_injection_do_not_reinforce(self):
  mid=self.write();self.now[0]+=10*86400
  for _ in range(5):self.engine.injection(self.owner,'紫色风筝')
  self.assertEqual(self.engine.db.execute('select count(*) from activation').fetchone()[0],0)
 def test_explicit_remention_reinforces_once_per_day(self):
  mid=self.write();self.now[0]+=10*86400
  for _ in range(5):self.engine.cache.clear();self.engine.search(self.owner,'还记得紫色风筝')
  row=self.engine.db.execute('select * from activation where memory_id=?',(mid,)).fetchone();self.assertEqual(row['reinforcements'],1)
 def test_reactivation_does_not_change_digest(self):
  mid=self.write();before=self.engine.db.execute('select digest from memories where id=?',(mid,)).fetchone()[0];self.now[0]+=10*86400;self.engine.search(self.owner,'以前的紫色风筝');after=self.engine.db.execute('select digest from memories where id=?',(mid,)).fetchone()[0];self.assertEqual(before,after)
 def test_forgotten_never_reactivated(self):
  mid=self.write();self.engine.forget(self.owner,mid);self.assertFalse(self.engine.search(self.owner,'以前的紫色风筝'))
 def test_archive_survives_restart(self):
  self.archive.snapshot(self.owner,'a',[msg('user','蓝色风铃')]);self.archive.close();self.archive=ConversationArchive(Path(self.tmp.name)/'archive',self.engine.key);self.assertTrue(self.archive.search(self.owner,'蓝色风铃'))
 def test_integrity(self):
  self.archive.transform(self.owner,'a',turns(4));self.assertEqual(self.archive.db.execute('pragma integrity_check').fetchone()[0],'ok');self.assertEqual(self.engine.db.execute('pragma integrity_check').fetchone()[0],'ok')
if __name__=='__main__':unittest.main()
