from pathlib import Path
import sqlite3
from astrbot_plugin_family_memory.tests.test_archive_semantic import ArchiveTests

class EarliestTests(ArchiveTests):
 async def test_earliest_beats_recent_keyword_echo(self):
  self.add(self.p,'你好，今天太阳不错。');self.add(self.p,'最早 第一次聊天 认识 最开始 最近的讨论')
  path=Path(self.tmp.name)/'native.sqlite3';d=sqlite3.connect(path);d.execute('create table conversations(conversation_id text,created_at text,updated_at text)')
  d.executemany('insert into conversations values(?,?,?)',[('你好，今天太阳不错。','2026-10-23','2026-10-24'),('最早 第一次聊天 认识 最开始 最近的讨论','2026-10-29','2026-10-30')]);d.commit();d.close();self.a.native_history_path=path
  self.assertTrue(self.a.earliest_query('第一次聊天 最早 开始 打招呼 认识'))
  rows=self.a.earliest(self.p);self.assertEqual(rows[0]['text'],'你好，今天太阳不错。')
  report=self.a.search_report(self.p,rows,'earliest_available_session');self.assertEqual(report['coverage']['earliest_available_conversation_created_at'],'2026-10-23');self.assertEqual(report['coverage']['accessible_sessions'],2)
  self.assertEqual(self.a.earliest(self.peer),[]);self.assertEqual(self.a.search_report(self.peer,[],'relevance')['coverage']['searchable_messages'],0)
 async def test_general_question_not_earliest_and_empty_result_not_empty_archive(self):
  self.assertFalse(self.a.earliest_query('第一次做饭失败了'));self.assertFalse(self.a.earliest_query('房子的计划'))
  self.add(self.p,'普通生活记录');r=self.a.search_report(self.p,[],'relevance');self.assertEqual(r['results'],[]);self.assertEqual(r['coverage']['searchable_messages'],1)
