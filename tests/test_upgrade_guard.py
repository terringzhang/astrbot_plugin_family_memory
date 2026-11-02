import pathlib,tempfile,sqlite3,hashlib,unittest
from astrbot_plugin_family_memory.engine import MemoryEngine
from astrbot_plugin_family_memory.security import IdentityPolicy,Rejected
from astrbot_plugin_family_memory.lifecycle import ConversationArchive
class UpgradeGuardTests(unittest.TestCase):
    def test_unknown_route_database_rejected_without_changes(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t);(root/'index').mkdir();path=root/'index/memory.sqlite3'
            db=sqlite3.connect(path);db.execute('create table memories(agent text)');db.execute('insert into memories values(?)',('unsupported-old-route',));db.commit();db.close()
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(Rejected):MemoryEngine(root)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before);self.assertFalse((root/'.identity-key').exists())
    def test_unknown_route_directory_not_renamed(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t);folder=root/'agents/unsupported-old-route';folder.mkdir(parents=True)
            with self.assertRaises(Rejected):MemoryEngine(root)
            self.assertTrue(folder.exists());self.assertFalse((root/'.identity-key').exists())
    def test_old_archive_is_not_silently_relabelled(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t);path=root/'archive.sqlite3';db=sqlite3.connect(path);db.execute('create table messages(agent text)');db.execute('insert into messages values(?)',('unsupported-old-route',));db.commit();db.close()
            before=path.read_bytes()
            with self.assertRaises(Rejected):ConversationArchive(root,b'fixture-key')
            self.assertEqual(path.read_bytes(),before)
    def test_empty_bot_self_id_cannot_grant_a_route(self):
        with self.assertRaises(Rejected):IdentityPolicy(b'fixture',{'bot1_platform':'default','bot1_self_id':''}).resolve('default','','owner')

    def test_unknown_archive_vector_route_rejected_before_identity_key(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t);(root/'index').mkdir();path=root/'index/embedding.sqlite3'
            db=sqlite3.connect(path);db.execute('create table archive_vectors(agent text)');db.execute('insert into archive_vectors values(?)',('unsupported-old-route',));db.commit();db.close()
            before=path.read_bytes()
            with self.assertRaises(Rejected):MemoryEngine(root)
            self.assertEqual(before,path.read_bytes());self.assertFalse((root/'.identity-key').exists())
    def test_unknown_debug_label_route_rejected_before_archive_write(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t);path=root/'archive.sqlite3'
            db=sqlite3.connect(path);db.execute('create table label_signatures(agent text)');db.execute('insert into label_signatures values(?)',('unsupported-old-route',));db.commit();db.close()
            before=path.read_bytes()
            with self.assertRaises(Rejected):ConversationArchive(root,b'fixture-key')
            self.assertEqual(before,path.read_bytes())
