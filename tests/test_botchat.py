import asyncio
import tempfile
import unittest
from pathlib import Path
from astrbot_plugin_family_memory.botchat import BotChatGuard


class BotChatTests(unittest.TestCase):
    def test_farewell_words(self):
        for text in ['晚安', '好啦，下次再说吧。', '以后再见吧', '那就下次再聊', '拜拜～']:
            self.assertTrue(BotChatGuard.is_closing(text), text)
        for text in ['你好', '不要说晚安', '例如晚安', '她说“晚安”是什么意思', '今天聊什么']:
            self.assertFalse(BotChatGuard.is_closing(text), text)

    def test_pair_latch_persists_and_does_not_affect_owner(self):
        with tempfile.TemporaryDirectory() as d:
            g = BotChatGuard(d, ['a', 'b'])
            self.assertFalse(g.admit('a', '你好'))
            self.assertTrue(g.admit('owner', '晚安'))
            g.set_paused(False, 'owner_resume')
            self.assertTrue(g.admit('a', '你好'))
            self.assertFalse(g.admit('b', '下次再说吧'))
            self.assertFalse(g.admit('a', '嗯'))
            self.assertFalse(g.admit('b', '你怎么不说话'))
            restored = BotChatGuard(d, ['a', 'b'])
            self.assertTrue(restored.paused)
            restored.set_paused(False, 'owner_resume')
            self.assertTrue(restored.admit('a', '你好'))

    def test_invalid_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'botchat_state.json').write_text('{broken')
            self.assertTrue(BotChatGuard(d, ['a']).paused)


class BotChatHookTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_disabled_keeps_guard_without_opening_memory(self):
        import importlib
        from unittest.mock import patch
        adapter = importlib.import_module('test_adapter')
        module = importlib.import_module('astrbot_plugin_family_memory.main')
        with tempfile.TemporaryDirectory() as d:
            p = adapter.FamilyMemoryPlugin(None, {'enabled': False, 'botchat_guard_enabled': True, 'botchat_peer_umos': ['peer']})
            with patch.object(module.StarTools, 'get_data_dir', return_value=Path(d)), patch.object(module, 'MemoryEngine') as engine:
                await p.initialize()
                engine.assert_not_called()
            self.assertIsNone(p.engine)
            self.assertTrue(p.botchat.paused)
            self.assertFalse((Path(d)/'agent_memory/index').exists())

    async def test_incoming_silent_and_outgoing_closing_allowed_once(self):
        import importlib
        adapter = importlib.import_module('test_adapter')
        FamilyMemoryPlugin, Event, response = adapter.FamilyMemoryPlugin, adapter.Event, adapter.response
        FamilyMemoryPlugin.botchat_receive.__globals__['logger'].info = lambda *a, **kw: None
        with tempfile.TemporaryDirectory() as d:
            p = FamilyMemoryPlugin(None, {})
            p.botchat = BotChatGuard(d, ['peer-a', 'peer-b'])
            p._stop_pair_runs = lambda e: None
            def evt(umo, text):
                e = Event(text)
                e.unified_msg_origin = umo
                e.stopped = False
                e.result = 'synthetic reply'
                e.stop_event = lambda: setattr(e, 'stopped', True)
                e.set_result = lambda r: setattr(e, 'result', r)
                return e
            p.botchat.set_paused(False, 'test')
            e = evt('peer-a', '你好')
            await p.botchat_receive(e)
            old = evt('peer-b', '你好')
            await p.botchat_receive(old)
            r = response('晚安，早点休息。')
            await p.botchat_response(e, r)
            await p.botchat_before_send(e)
            self.assertFalse(e.stopped)
            stale = response('嗯')
            await p.botchat_response(old, stale)
            await p.botchat_before_send(old)
            self.assertEqual(stale.completion_text, '')
            self.assertTrue(old.stopped)
            self.assertIsNone(old.result)
            incoming = evt('peer-b', '晚安')
            await p.botchat_receive(incoming)
            self.assertTrue(incoming.stopped)
            self.assertIsNone(incoming.result)
            owner = evt('owner', '晚安')
            await p.botchat_receive(owner)
            self.assertFalse(owner.stopped)
            p.botchat.set_paused(False, 'test_resume')
            await p.botchat_before_send(e)
            self.assertTrue(e.stopped, 'old farewell must not revive after resume')
