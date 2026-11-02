import sqlite3
from pathlib import Path
from astrbot_plugin_family_memory.tests.test_archive_semantic import ArchiveTests

class TimeTests(ArchiveTests):
 async def test_old_session_is_not_dated_by_archive_time(self):
  self.add(self.p,'旧日房子计划')
  cid='旧日房子计划';path=Path(self.tmp.name)/'native.sqlite3'
  d=sqlite3.connect(path);d.execute('create table conversations(conversation_id text,created_at text,updated_at text)');d.execute('insert into conversations values(?,?,?)',(cid,'2026-10-23 12:00:00','2026-10-24 18:00:00'));d.commit();d.close();self.a.native_history_path=path
  await self.s.index_once()
  for rows in (self.a.search(self.p,'房子'),await self.s.search(self.p,'未来住所')):
   self.assertTrue(rows);r=rows[0];self.assertNotIn('archived_at',r);self.assertIsNone(r['message_time']);self.assertEqual(r['conversation_time_bounds']['created_at'],'2026-10-23 12:00:00')
 async def test_unknown_time_does_not_invent_date_and_cross_scope_drops(self):
  self.add(self.p,'旧日房子计划');r=self.a.search(self.p,'房子')[0]
  self.assertIsNone(r['message_time']);self.assertNotIn('conversation_time_bounds',r)
  self.assertEqual(self.a.describe_times(self.peer,[r]),[])
 async def test_missing_native_table_still_returns_unknown_time(self):
  self.add(self.p,'旧日房子计划');path=Path(self.tmp.name)/'empty.sqlite3';sqlite3.connect(path).close();self.a.native_history_path=path
  r=self.a.search(self.p,'房子')[0];self.assertIsNone(r['message_time']);self.assertNotIn('archived_at',r)
