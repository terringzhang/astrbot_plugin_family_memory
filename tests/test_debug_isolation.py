from astrbot_plugin_family_memory.tests.test_archive_semantic import ArchiveTests
from astrbot_plugin_family_memory.lifecycle import dumps

class DebugTests(ArchiveTests):
 async def test_empty_tool_call_bodies_do_not_share_labels(self):
  debug={'role':'assistant','content':None,'tool_calls':[{'id':'debug-call','function':{'name':'astrbot_execute_python','arguments':'{}'}}]}
  social={'role':'assistant','content':None,'tool_calls':[{'id':'social-call','function':{'name':'search_memes','arguments':'{}'}}]}
  sig=self.a.mac(dumps(debug))
  with self.a.db:self.a.db.execute('insert into label_signatures values(?,?,?,?,?,?,?)',(self.p.agent,self.p.private_ns,'scope',sig,'debug','synthetic',1))
  self.a.snapshot(self.p,'scope',[debug,social])
  rows=self.a.db.execute('select m.payload from archive_labels q join messages m on m.id=q.message_id').fetchall()
  self.assertEqual(len(rows),1);self.assertIn('debug-call',rows[0][0]);self.assertNotIn('social-call',rows[0][0])
 async def test_marked_text_excluded_from_all_search_paths_but_raw_preserved(self):
  self.add(self.p,'旧房子调试错误结论');self.add(self.p,'正常的住所计划')
  row=self.a.db.execute('select * from messages order by id limit 1').fetchone()
  signature=self.a.mac(row['role']+'|旧房子调试错误结论')
  with self.a.db:
   self.a.db.execute('insert into archive_labels values(?,?,?,?,?)',(row['id'],'error_example','synthetic',signature,1))
   self.a.db.execute('insert into label_signatures values(?,?,?,?,?,?,?)',(row['agent'],row['ns'],row['cid'],signature,'error_example','synthetic',1))
  self.assertEqual(self.a.search(self.p,'错误结论'),[])
  self.assertEqual(self.a.describe_times(self.p,[{'id':row['id']}]),[])
  self.assertFalse(any(x['id']==row['id'] for x in self.s.documents(self.p)))
  self.assertFalse(any(x['id']==row['id'] for x in self.a.earliest(self.p)))
  self.assertIsNotNone(self.a.db.execute('select payload from messages where id=?',(row['id'],)).fetchone())
  self.assertEqual(self.a.search_report(self.p,[],'relevance')['coverage']['searchable_messages'],1)
 async def test_same_scope_new_snapshot_variant_inherits_label_and_rollback(self):
  text='房子调试用例';self.add(self.p,text);row=self.a.db.execute('select * from messages').fetchone();sig=self.a.mac(dumps({'role':'user','content':text}))
  with self.a.db:self.a.db.execute('insert into label_signatures values(?,?,?,?,?,?,?)',(row['agent'],row['ns'],row['cid'],sig,'debug','synthetic',1))
  self.a.snapshot(self.p,text,[{'role':'user','content':text},{'role':'user','content':text}])
  self.assertEqual(self.a.db.execute('select count(*) from archive_labels').fetchone()[0],2)
  with self.a.db:self.a.db.execute('delete from archive_labels');self.a.db.execute('delete from label_signatures')
  self.assertTrue(self.a.search(self.p,'调试用例'))
