import tempfile
import unittest
from pathlib import Path
from astrbot_plugin_family_memory.engine import MemoryEngine
from astrbot_plugin_family_memory.security import Rejected
from astrbot_plugin_family_memory.tests.test_engine import fixture_config


class PeerIdentityTests(unittest.TestCase):
    def test_explicit_mutual_read_retains_write_and_visitor_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=fixture_config(bot2_private_mutual_read=True,bot2_peer_binding={'approved':True,'openid':'peer-fixture','evidence_ref':'synthetic-verification'})
            e=MemoryEngine(Path(d),cfg)
            owner=e.policy.resolve('official','official-self','owner-openid-fixture')
            peer=e.policy.resolve('official','official-self','peer-fixture')
            visitor=e.policy.resolve('official','official-self','visitor-fixture')
            ids=[]
            for p,text in [(owner,'主人喜欢银色陶罐'),(peer,'bot1喜欢蓝色风筝')]:
                sid=e.capture(p,'synthetic-'+p.role,text)
                ids.append(e.remember(p,text,[{'id':sid,'quote':text}]))
            self.assertTrue(owner.can_read(peer.agent,peer.private_ns))
            self.assertTrue(peer.can_read(owner.agent,owner.private_ns))
            self.assertTrue(peer.can_read(owner.agent,'private-'+owner.actor))
            self.assertFalse(owner.can_write(peer.private_ns))
            self.assertFalse(peer.can_write(owner.private_ns))
            self.assertTrue(e.search(owner,'蓝色风筝'))
            self.assertTrue(e.search(peer,'银色陶罐'))
            self.assertFalse(e.search(visitor,'银色陶罐 蓝色风筝'))
            for p,mid in [(owner,ids[1]),(peer,ids[0])]:
                with self.assertRaises(Rejected):e.forget(p,mid)
            self.assertFalse(peer.can_read(peer.agent,'visitor-'+peer.actor))
            cfg['bot2_private_mutual_read']=False
            isolated=e.policy.resolve('official','official-self','peer-fixture')
            self.assertFalse(e.search(isolated,'银色陶罐'))
            e.close();cfg['bot2_private_mutual_read']=True;e=MemoryEngine(Path(d),cfg)
            restored=e.policy.resolve('official','official-self','peer-fixture')
            self.assertTrue(e.search(restored,'银色陶罐'))
            cfg['bot2_peer_binding']['approved']=False
            revoked=e.policy.resolve('official','official-self','peer-fixture')
            self.assertFalse(e.search(revoked,'银色陶罐 蓝色风筝'))
            e.close()

    def test_namespaces_permissions_revoke_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=fixture_config(bot2_peer_binding={'approved':False,'openid':'peer-fixture','evidence_ref':''})
            e=MemoryEngine(Path(d),cfg)
            visitor=e.policy.resolve('official','official-self','peer-fixture')
            sid=e.capture(visitor,'synthetic-before-approval','访客旧记录琥珀灯')
            before=tuple(e.db.execute('select * from sources where id=?',(sid,)).fetchone())
            cfg['bot2_peer_binding']={'approved':True,'openid':'peer-fixture','evidence_ref':'synthetic-trusted-transport'}
            e.policy.config=cfg
            owner=e.policy.resolve('official','official-self','owner-openid-fixture')
            peer=e.policy.resolve('official','official-self','peer-fixture')
            outsider=e.policy.resolve('official','official-self','other-fixture')
            self.assertTrue(owner.private_ns.startswith('private-owner-'))
            self.assertTrue(peer.private_ns.startswith('private-peer-'))
            self.assertTrue(outsider.private_ns.startswith('visitor-'))
            self.assertFalse(peer.can_read(visitor.agent,visitor.private_ns))
            self.assertFalse(owner.can_read(peer.agent,peer.private_ns))
            self.assertFalse(peer.can_read(owner.agent,owner.private_ns))
            self.assertFalse(outsider.can_read(owner.agent,owner.private_ns))
            self.assertTrue(owner.can_read(owner.agent,'private-'+owner.actor))
            new=e.capture(peer,'synthetic-after-approval','bot1私有记录蓝色陶罐')
            row=e.db.execute('select ns from sources where id=?',(new,)).fetchone()
            self.assertEqual(row[0],peer.private_ns)
            mid=e.remember(peer,'bot1私有记录蓝色陶罐',[{'id':new,'quote':'bot1私有记录蓝色陶罐'}])
            self.assertTrue(e.search(peer,'蓝色陶罐'))
            self.assertFalse(e.search(owner,'蓝色陶罐'))
            self.assertFalse(e.search(outsider,'蓝色陶罐'))
            with self.assertRaises(Rejected):e.get(owner,mid)
            self.assertEqual(tuple(e.db.execute('select * from sources where id=?',(sid,)).fetchone()),before)
            ns=peer.private_ns;e.close();e=MemoryEngine(Path(d),cfg)
            self.assertEqual(e.policy.resolve('official','official-self','peer-fixture').private_ns,ns)
            self.assertTrue(e.search(e.policy.resolve('official','official-self','peer-fixture'),'蓝色陶罐'))
            cfg['bot2_peer_binding']['approved']=False
            revoked=e.policy.resolve('official','official-self','peer-fixture')
            self.assertEqual(revoked.role,'visitor')
            self.assertFalse(e.search(revoked,'蓝色陶罐'))
            e.close()
