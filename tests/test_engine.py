"""Synthetic identities and messages only. Never reads production data."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from astrbot_plugin_family_memory.engine import MemoryEngine, TokenBudget
from astrbot_plugin_family_memory.security import Rejected


def fixture_config(**overrides):
    return {"bot1_platform":"default","bot1_self_id":"fixture-bot",
            "bot2_platform":"official","bot1_owner_ids":["owner-fixture"],
            "bot2_owner_openids":["owner-openid-fixture"],
            "bot1_peer_binding":{"qq_id":"peer-fixture","approved":True,"evidence_ref":"synthetic-verified-route"},
            "retrieval_timeout_ms":200,"max_summary_calls_per_day":2,"min_summary_interval_seconds":0,**overrides}


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='family-memory-test-')
        self.root=Path(self.tmp.name);self.now=[1792810000.]
        self.engine=MemoryEngine(self.root,fixture_config(),clock=lambda:self.now[0])
        self.owner=self.engine.policy.resolve('default','fixture-bot','owner-fixture')
        self.peer=self.engine.policy.resolve('default','fixture-bot','peer-fixture')
        self.visitor=self.engine.policy.resolve('default','fixture-bot','visitor-A')
        self.other=self.engine.policy.resolve('default','fixture-bot','visitor-B')
        self.bot2=self.engine.policy.resolve('official','official-self','owner-openid-fixture')
        self.seq=0

    def tearDown(self):
        try:self.engine.close()
        except sqlite3.ProgrammingError:pass
        assert self.root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
        self.tmp.cleanup()

    def write(self,p,text,shared=False,**kw):
        self.seq+=1
        sid=self.engine.capture(p,'synthetic-'+str(self.seq),text,share=shared,event_time=self.now[0])
        return self.engine.remember(p,text,[{'id':sid,'quote':text}],shared=shared,**kw)

    def ids(self,p,q):return {r['id'] for r in self.engine.search(p,q)}

    def test_same_owner_new_conversation_recalls(self):
        mid=self.write(self.owner,'我喜欢紫色风筝')
        new=self.engine.policy.resolve('default','fixture-bot','owner-fixture')
        self.assertIn(mid,self.ids(new,'紫色风筝'))

    def test_peer_to_owner_explicit_family_recall(self):
        mid=self.write(self.peer,'我们一起修理了纸灯笼',True)
        self.assertIn(mid,self.ids(self.owner,'纸灯笼'))

    def test_owner_to_peer_explicit_family_recall(self):
        mid=self.write(self.owner,'家庭一起欣赏蓝色流星',True)
        self.assertIn(mid,self.ids(self.peer,'蓝色流星'))

    def test_private_owner_overlay_not_shared(self):
        mid=self.write(self.owner,'我私下喜欢绿色茶杯')
        self.assertNotIn(mid,self.ids(self.peer,'绿色茶杯'))

    def test_visitor_cannot_read_family_even_via_graph(self):
        mid=self.write(self.owner,'家庭收藏琥珀海螺',True,tags=['海螺'])
        self.assertNotIn(mid,self.ids(self.visitor,'海螺 bot2 bot1'))

    def test_visitors_are_mutually_isolated(self):
        mid=self.write(self.visitor,'我喜欢银色纸鹤')
        self.assertIn(mid,self.ids(self.visitor,'银色纸鹤'))
        self.assertNotIn(mid,self.ids(self.other,'银色纸鹤'))
        with self.assertRaises(Rejected):self.engine.get(self.other,mid)

    def test_agent_isolation(self):
        a=self.write(self.bot2,'bot2珍藏红色贝壳')
        b=self.write(self.owner,'bot1珍藏金色风铃',True)
        self.assertNotIn(a,self.ids(self.owner,'红色贝壳'))
        self.assertNotIn(b,self.ids(self.bot2,'金色风铃'))

    def test_same_name_does_not_merge_people(self):
        self.write(self.owner,'两位同名朋友一起赏月',entities=[{'key':'person:first','type':'Person','name':'张三'},
                  {'key':'person:second','type':'Person','name':'张三'}],edges=[{'src':'person:first','dst':'person:second','relation':'KNOWS'}])
        self.assertEqual(self.engine.db.execute("SELECT count(*) FROM entities WHERE name='张三'").fetchone()[0],2)

    def test_missing_stable_id_skips_capture(self):
        with self.assertRaises(Rejected):self.engine.capture(self.owner,'','hello')

    def test_duplicate_delivery_is_idempotent(self):
        a=self.engine.capture(self.owner,'stable-id','我喜欢橙色帆船')
        b=self.engine.capture(self.owner,'stable-id','我喜欢橙色帆船')
        self.assertEqual(a,b)
        first=self.engine.remember(self.owner,'我喜欢橙色帆船',[{'id':a,'quote':'我喜欢橙色帆船'}])
        second=self.engine.remember(self.owner,'我喜欢橙色帆船',[{'id':a,'quote':'我喜欢橙色帆船'}])
        self.assertEqual(first,second)
        self.assertEqual(self.engine.stats()['memory_count'],1)

    def test_cache_and_graph_do_not_resurrect_deleted_memory(self):
        mid=self.write(self.owner,'家庭记录翡翠山谷',True,tags=['山谷'])
        self.assertIn(mid,self.ids(self.peer,'翡翠山谷'))
        self.assertIn(mid,self.ids(self.peer,'翡翠山谷'))
        self.engine.forget(self.owner,mid)
        self.assertNotIn(mid,self.ids(self.peer,'翡翠山谷'))
        self.assertEqual(self.engine.db.execute('SELECT count(*) FROM edges WHERE source_memory=?',(mid,)).fetchone()[0],0)
        self.assertEqual(self.engine.db.execute('SELECT count(*) FROM aliases WHERE source_memory=?',(mid,)).fetchone()[0],0)
        self.engine.sync_markdown()
        self.assertNotIn(mid,self.ids(self.owner,'翡翠山谷'))

    def test_correction_changes_index_and_keeps_audit(self):
        mid=self.write(self.owner,'我喜欢山楂')
        sid=self.engine.capture(self.owner,'correction-fixture','我现在喜欢柠檬')
        self.engine.correct(self.owner,mid,'我现在喜欢柠檬',[{'id':sid,'quote':'我现在喜欢柠檬'}])
        self.assertIn(mid,self.ids(self.owner,'柠檬'))
        self.assertNotIn(mid,self.ids(self.owner,'山楂'))
        self.assertEqual(self.engine.get(self.owner,mid)['version'],2)
        self.assertEqual(self.engine.db.execute('SELECT count(*) FROM audit WHERE memory_id=?',(mid,)).fetchone()[0],2)

    def test_factual_conflict_is_quarantined(self):
        self.write(self.owner,'我住在杭州',fact_key='owner.city',fact_value='杭州')
        mid=self.write(self.owner,'我住在北京',fact_key='owner.city',fact_value='北京')
        self.assertEqual(self.engine.get(self.owner,mid)['status'],'conflict')
        self.assertNotIn(mid,self.ids(self.owner,'北京'))

    def test_uncertainty_is_not_recalled_as_fact(self):
        mid=self.write(self.owner,'开玩笑，我住在月球')
        self.assertEqual(self.engine.get(self.owner,mid)['status'],'pending')
        self.assertNotIn(mid,self.ids(self.owner,'月球'))

    def test_model_cannot_strip_joke_prefix_to_create_a_fact(self):
        sid=self.engine.capture(self.owner,'joke-fixture','开玩笑，我住在火星')
        mid=self.engine.remember(self.owner,'我住在火星',[{'id':sid,'quote':'我住在火星'}],automatic=True)
        self.assertEqual(self.engine.get(self.owner,mid)['status'],'pending')
        self.assertNotIn(mid,self.ids(self.owner,'火星'))

    def test_simple_residence_conflict_is_detected_without_llm_slot(self):
        self.write(self.owner,'我住在杭州')
        mid=self.write(self.owner,'我住在北京')
        self.assertEqual(self.engine.get(self.owner,mid)['status'],'conflict')

    def test_revoked_family_binding_cannot_use_existing_cache(self):
        mid=self.write(self.owner,'家庭收藏白色纸扇',True)
        self.assertIn(mid,self.ids(self.peer,'白色纸扇'))
        cfg=fixture_config(bot1_peer_binding={'qq_id':'peer-fixture','approved':False})
        revoked=type(self.engine.policy)(self.engine.key,cfg).resolve('default','fixture-bot','peer-fixture')
        self.assertNotIn(mid,self.ids(revoked,'白色纸扇'))

    def test_plain_token_and_otp_credentials_are_blocked(self):
        for s in ['token=synthetic-token-value','OTP: 123456','令牌：synthetic-value']:
            with self.assertRaises(Rejected):self.engine.capture(self.owner,'secret'+s[:3],s)

    def test_sensitive_source_never_lands(self):
        with self.assertRaises(Rejected):self.engine.capture(self.owner,'secret-fixture','password=SynthSecret999')
        self.assertEqual(self.engine.db.execute('SELECT count(*) FROM sources').fetchone()[0],0)

    def test_model_cannot_hide_credentials_in_metadata(self):
        with self.assertRaises(Rejected):self.write(self.owner,'一条正常的合成事实',fact_value='token=synthetic-hidden-value')
        self.assertEqual(self.engine.stats()['memory_count'],0)

    def test_long_transport_message_id_is_not_mistaken_for_a_bank_card(self):
        sid=self.engine.capture(self.owner,'transport:1234567890123456789','记录青色山川')
        mid=self.engine.remember(self.owner,'记录青色山川',[{'id':sid,'quote':'记录青色山川'}])
        self.assertIn(mid,self.ids(self.owner,'青色山川'))

    def test_private_marker_overrides_family_permission(self):
        sid=self.engine.capture(self.owner,'private-fixture','保密，我喜欢蓝色陶罐',share=True)
        with self.assertRaises(Rejected):
            self.engine.remember(self.owner,'我喜欢蓝色陶罐',[{'id':sid,'quote':'我喜欢蓝色陶罐'}],shared=True)

    def test_family_requires_per_source_sharing_consent(self):
        sid=self.engine.capture(self.owner,'nonshared-fixture','我喜欢黄色枫叶')
        with self.assertRaises(Rejected):
            self.engine.remember(self.owner,'我喜欢黄色枫叶',[{'id':sid,'quote':'我喜欢黄色枫叶'}],shared=True)

    def test_source_references_are_verifiable(self):
        sid=self.engine.capture(self.owner,'quote-fixture','我喜欢蓝色树屋')
        with self.assertRaises(Rejected):
            self.engine.remember(self.owner,'喜欢火星',[{'id':sid,'quote':'喜欢火星'}])
        with self.assertRaises(Rejected):
            self.engine.remember(self.other,'蓝色树屋',[{'id':sid,'quote':'蓝色树屋'}])

    def test_model_cannot_invent_paraphrased_fact(self):
        sid=self.engine.capture(self.owner,'grounding-fixture','我看过红色山峰')
        with self.assertRaises(Rejected):
            self.engine.remember(self.owner,'我拥有红色山峰',[{'id':sid,'quote':'我看过红色山峰'}],automatic=True)

    def test_expiry_also_invalidates_cached_results(self):
        mid=self.write(self.owner,'明天准备风筝节',kind='temporary',ttl_days=1)
        self.assertIn(mid,self.ids(self.owner,'风筝节'))
        self.now[0]+=2*86400
        self.assertNotIn(mid,self.ids(self.owner,'风筝节'))
        self.engine.maintenance()
        self.assertEqual(self.engine.get(self.owner,mid)['status'],'expired')

    def test_no_relevant_memory_means_no_injection(self):
        self.write(self.owner,'我喜欢桃花糕',tags=['糕点'])
        self.assertEqual(self.engine.injection(self.owner,'火星岩石的化学成分'), '')

    def test_relative_plan_is_not_kept_forever_as_a_fact(self):
        mid=self.write(self.owner,'明天去看纸鹤展',kind='fact')
        row=self.engine.get(self.owner,mid)
        self.assertEqual(row['kind'],'temporary');self.assertIsNotNone(row['expires'])
        self.assertIn('@2026-',self.engine.injection(self.owner,'纸鹤展'))

    def test_callers_cannot_mutate_cached_results(self):
        mid=self.write(self.owner,'记录琥珀色树叶')
        rows=self.engine.search(self.owner,'琥珀色树叶');rows[0]['text']='unexpected mutation'
        self.assertEqual(self.engine.search(self.owner,'琥珀色树叶')[0]['text'],'记录琥珀色树叶')

    def test_graph_does_not_expand_through_generic_agent_hub(self):
        wanted=self.write(self.owner,'我喜欢苹果派',True,tags=['苹果'])
        unrelated=self.write(self.owner,'家庭参观故宫',True,tags=['故宫'])
        result=self.ids(self.owner,'苹果')
        self.assertIn(wanted,result);self.assertNotIn(unrelated,result)

    def test_bounded_one_hop_association(self):
        mid=self.write(self.owner,'去年参观了玉石展厅',True,entities=[{'key':'place:jade','type':'Place','name':'翠玉馆','aliases':['玉馆']},
                {'key':'topic:exhibit','type':'Topic','name':'石雕展'}],edges=[{'src':'place:jade','dst':'topic:exhibit','relation':'RELATED_TO'}])
        self.assertIn(mid,self.ids(self.peer,'玉馆'))

    def test_expired_alias_is_not_used_as_a_graph_seed(self):
        self.write(self.owner,'旧展厅使用过的名称',entities=[{'key':'place:hall','type':'Place','name':'旧称玉馆'}],ttl_days=1)
        active=self.write(self.owner,'新展厅保留了一本图册',entities=[{'key':'place:hall','type':'Place','name':'新称青馆'}])
        self.now[0]+=2*86400
        self.assertNotIn(active,self.ids(self.owner,'旧称玉馆'))

    def test_restart_preserves_memory(self):
        mid=self.write(self.owner,'我喜欢棕色木马',True)
        self.engine.close()
        self.engine=MemoryEngine(self.root,fixture_config(),clock=lambda:self.now[0])
        p=self.engine.policy.resolve('default','fixture-bot','peer-fixture')
        self.assertIn(mid,self.ids(p,'棕色木马'))

    def test_separate_process_reopens_persistent_memory(self):
        import subprocess,os
        mid=self.write(self.owner,'家庭记录合成松塔',True)
        self.engine.close()
        code="import json,sys; from astrbot_plugin_family_memory.engine import MemoryEngine; e=MemoryEngine(sys.argv[1],json.loads(sys.argv[2])); p=e.policy.resolve('default','fixture-bot','peer-fixture'); print(json.dumps([r['id'] for r in e.search(p,'合成松塔')])); e.close()"
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[2])}
        output=subprocess.check_output([sys.executable,'-B','-c',code,str(self.root),json.dumps(fixture_config())],env=env,text=True)
        self.assertIn(mid,json.loads(output))
        self.engine=MemoryEngine(self.root,fixture_config(),clock=lambda:self.now[0])

    def test_sqlite_can_be_rebuilt_without_old_chat_import(self):
        mid=self.write(self.owner,'我喜欢青色航船',True)
        removed=self.write(self.owner,'家庭遗忘石榴',True)
        self.engine.forget(self.owner,removed)
        self.engine.close();(self.root/'index/memory.sqlite3').unlink()
        self.engine=MemoryEngine(self.root,fixture_config(),clock=lambda:self.now[0])
        self.assertIn(mid,self.ids(self.owner,'青色航船'))
        self.assertNotIn(removed,self.ids(self.owner,'石榴'))

    def test_external_file_deletion_does_not_leak_from_cache(self):
        mid=self.write(self.owner,'我喜欢玻璃蝴蝶')
        self.ids(self.owner,'玻璃蝴蝶')
        (self.root/self.engine.get(self.owner,mid)['path']).unlink()
        self.assertNotIn(mid,self.ids(self.owner,'玻璃蝴蝶'))

    def test_markdown_metadata_edit_reindexes(self):
        mid=self.write(self.owner,'一条关于纸灯的记录')
        path=self.root/self.engine.get(self.owner,mid)['path']
        doc=self.engine._parse(path);doc['tags']=['星际图书馆'];self.engine._atomic_doc(doc)
        self.engine.sync_markdown()
        self.assertIn(mid,self.ids(self.owner,'星际图书馆'))

    def test_external_body_edit_requires_review(self):
        mid=self.write(self.owner,'我喜欢春日')
        path=self.root/self.engine.get(self.owner,mid)['path']
        doc=self.engine._parse(path);doc['text']='我喜欢秋日';self.engine._atomic_doc(doc)
        self.assertNotIn(mid,self.ids(self.owner,'春日'))
        self.engine.sync_markdown()
        self.assertEqual(self.engine.get(self.owner,mid)['text'],'我喜欢秋日')
        self.assertEqual(self.engine.get(self.owner,mid)['status'],'pending')

    def test_acl_header_tampering_fails_closed(self):
        mid=self.write(self.visitor,'私有的琉璃杯')
        path=self.root/self.engine.get(self.visitor,mid)['path']
        doc=self.engine._parse(path);doc['ns']='family'
        target=self.engine._path(doc['agent'],doc['ns'],mid);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text('---\n'+json.dumps({k:v for k,v in doc.items() if k!='text'})+'\n---\n'+doc['text'])
        self.engine.sync_markdown()
        self.assertNotIn(mid,self.ids(self.owner,'琉璃杯'))

    def test_nickname_or_unapproved_binding_does_not_grant_access(self):
        policy=type(self.engine.policy)(self.engine.key,fixture_config(bot1_peer_binding={'qq_id':'peer-fixture','approved':False}))
        p=policy.resolve('default','fixture-bot','peer-fixture')
        self.assertEqual(p.role,'visitor');self.assertNotIn('family',p.readable)
        with self.assertRaises(Rejected):policy.resolve('unrelated','fixture-bot','owner-fixture')
        with self.assertRaises(Rejected):policy.resolve('default','wrong-bot','owner-fixture')

    def test_paths_use_hashed_identity(self):
        mid=self.write(self.visitor,'访客记录蓝色邮票')
        self.assertNotIn('visitor-A',self.engine.get(self.visitor,mid)['path'])

    def test_tombstone_blocks_accidental_relearning(self):
        mid=self.write(self.owner,'我不再保存雪山故事')
        self.engine.forget(self.owner,mid)
        with self.assertRaises(Rejected):self.write(self.owner,'我不再保存雪山故事')

    def test_merge_archives_old_entries_and_preserves_sources(self):
        a=self.write(self.owner,'我喜欢蓝色帆船');b=self.write(self.owner,'我喜欢木制书架')
        merged=self.engine.merge(self.owner,[a,b])
        self.assertEqual(self.engine.get(self.owner,a)['status'],'superseded')
        self.assertIn(merged,self.ids(self.owner,'木制书架'))
        self.assertNotIn(a,self.ids(self.owner,'蓝色帆船'))
        with self.assertRaises(Rejected):self.engine.merge(self.peer,[a,b])

    def test_memory_has_unknown_time_when_source_time_missing(self):
        sid=self.engine.capture(self.owner,'unknown-time','记录淡紫色云朵')
        mid=self.engine.remember(self.owner,'记录淡紫色云朵',[{'id':sid,'quote':'记录淡紫色云朵'}])
        doc=self.engine._parse(self.root/self.engine.get(self.owner,mid)['path'])
        self.assertIsNone(doc['event_time']);self.assertEqual(doc['time_precision'],'unknown')

    def test_budget_is_labelled_and_respected(self):
        self.write(self.owner,'记忆'+('木制风车'*120))
        injected=self.engine.injection(self.owner,'木制风车')
        self.assertTrue(injected)
        self.assertLessEqual(len(injected.encode()),600)
        self.assertEqual(self.engine.stats()['token_counter'],'utf8_bytes_estimate')
        exact=TokenBudget(64,counter=lambda t:len(t),label='fixture_counter')
        self.assertEqual(len(exact.trim('a'*200)),64)

    def test_budget_is_shared_across_three_relevant_memories(self):
        mids=[self.write(self.owner,'第'+str(i)+'项合成事实：'+('青色纸风车'*40),tags=['合成话题']) for i in range(3)]
        text=self.engine.injection(self.owner,'合成话题')
        self.assertLessEqual(len(text.encode()),600)
        for mid in mids:self.assertIn(mid[:8],text)

    def test_accumulation_and_summary_budget(self):
        for i in range(20):
            self.engine.capture(self.owner,'batch'+str(i),'我喜欢测试纸鹤'+str(i))
            self.engine.capture(self.owner,'batch'+str(i),'已收到',role='assistant')
            if i<19:self.assertIsNone(self.engine.prepare_batch(self.owner))
        batch=self.engine.prepare_batch(self.owner);self.assertIsNotNone(batch)
        src=batch['sources'][0]
        mids=self.engine.finish_batch(self.owner,batch,[{'text':src['text'],'sources':[{'id':src['id'],'quote':src['text']}]}])
        self.assertEqual(len(mids),1)
        self.assertIsNone(self.engine.prepare_batch(self.owner))
        self.assertTrue(self.engine.reserve_summary_call());self.assertTrue(self.engine.reserve_summary_call())
        self.assertFalse(self.engine.reserve_summary_call())

    def test_markdown_write_then_index_failure_recovers(self):
        old=self.engine._index
        def fail(_):raise sqlite3.OperationalError('synthetic')
        self.engine._index=fail
        with self.assertRaises(sqlite3.OperationalError):self.write(self.owner,'记录橘色晚霞')
        self.engine._index=old;self.engine.close()
        self.engine=MemoryEngine(self.root,fixture_config(),clock=lambda:self.now[0])
        self.assertTrue(self.ids(self.owner,'橘色晚霞'))

    def test_malformed_model_batch_is_preflighted_before_any_write(self):
        self.engine.config['summary_rounds']=2
        for i in range(2):
            self.engine.capture(self.owner,'preflight'+str(i),'记录合成纸船'+str(i))
            self.engine.capture(self.owner,'preflight'+str(i),'收到',role='assistant')
        batch=self.engine.prepare_batch(self.owner);src=batch['sources'][0]
        valid={'text':src['text'],'sources':[{'id':src['id'],'quote':src['text']}]}
        bad={**valid,'shared':'false'}
        with self.assertRaises(Rejected):self.engine.finish_batch(self.owner,batch,[valid,bad])
        self.assertEqual(self.engine.stats()['memory_count'],0)

    def test_long_rounds_do_not_turn_into_per_message_summary_backlog(self):
        for i in range(20):
            self.engine.capture(self.owner,'long'+str(i),'合成'+('文字'*1900)+str(i))
            self.engine.capture(self.owner,'long'+str(i),'收到',role='assistant')
        batch=self.engine.prepare_batch(self.owner)
        self.assertEqual(len(batch['sources']),20)
        self.assertLessEqual(sum(len(s['text']) for s in batch['sources']),6000)
        self.engine.finish_batch(self.owner,batch,[])
        self.assertIsNone(self.engine.prepare_batch(self.owner))

    def test_summary_cooldown_limits_calls_after_backlog_or_failure(self):
        self.engine.config['min_summary_interval_seconds']=600
        self.assertTrue(self.engine.reserve_summary_call())
        self.assertFalse(self.engine.reserve_summary_call())
        self.now[0]+=601
        self.assertTrue(self.engine.reserve_summary_call())

    def test_limits_stop_new_memory_without_deleting_existing(self):
        self.engine.config['max_memories']=1
        mid=self.write(self.owner,'第一条松林记忆')
        with self.assertRaises(Rejected):self.write(self.owner,'第二条湖泊记忆')
        self.assertIn(mid,self.ids(self.owner,'松林记忆'))

    def test_pending_source_buffer_is_bounded(self):
        self.engine.config['pending_source_limit']=4
        for i in range(10):self.engine.capture(self.owner,'buf'+str(i),'无记忆缓存'+str(i))
        self.assertEqual(self.engine.db.execute('SELECT count(*) FROM sources').fetchone()[0],4)


if __name__=='__main__':unittest.main()
