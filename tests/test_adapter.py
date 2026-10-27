"""Hook contract tests with local AstrBot API doubles, never a QQ client."""
import asyncio
import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from astrbot_plugin_family_memory.engine import MemoryEngine
from astrbot_plugin_family_memory.tests.test_engine import fixture_config


class Filter:
    EventMessageType=types.SimpleNamespace(ALL='all')
    def event_message_type(self,*a,**kw):return lambda f:f
    def on_decorating_result(self,**kw):return lambda f:f
    def command(self,*a,**kw):return lambda f:f
    def on_llm_request(self,**kw):return lambda f:f
    def on_llm_response(self,**kw):return lambda f:f
    def on_agent_done(self,**kw):return lambda f:f
    def after_message_sent(self,**kw):return lambda f:f
    def llm_tool(self,**kw):return lambda f:f
    def command_group(self,_):
        def decorate(f):
            f.command=lambda *_a,**_k:lambda method:method
            return f
        return decorate


class Star:
    def __init__(self,context):self.context=context


class TextPart:
    def __init__(self,text):self.text=text;self._no_save=False
    def mark_as_temp(self):self._no_save=True;return self


def install_api_doubles():
    for name in ['astrbot.core.star','astrbot.core.star.filter','astrbot.core.star.filter.command']:
        sys.modules[name]=types.ModuleType(name)
    sys.modules['astrbot.core.star.filter.command'].GreedyStr=type('GreedyStr',(str,),{})
    for name in ['astrbot','astrbot.api','astrbot.api.event','astrbot.api.platform','astrbot.api.star','astrbot.core','astrbot.core.agent','astrbot.core.agent.message']:
        sys.modules[name]=types.ModuleType(name)
    sys.modules['astrbot.api'].logger=types.SimpleNamespace(warning=lambda *_a,**_k:None,info=lambda *_a,**_k:None)
    sys.modules['astrbot.api.event'].AstrMessageEvent=object
    sys.modules['astrbot.api.event'].filter=Filter()
    sys.modules['astrbot.api.platform'].MessageType=types.SimpleNamespace(FRIEND_MESSAGE='friend',GROUP_MESSAGE='group')
    sys.modules['astrbot.api.star'].Star=Star
    sys.modules['astrbot.api.star'].Context=object
    sys.modules['astrbot.api.star'].StarTools=types.SimpleNamespace(get_data_dir=lambda _n:Path('/unused-offline-fixture'))
    sys.modules['astrbot.core.agent.message'].TextPart=TextPart


install_api_doubles()
FamilyMemoryPlugin=importlib.import_module('astrbot_plugin_family_memory.main').FamilyMemoryPlugin


class Event:
    def __init__(self,text='我喜欢琉璃风铃',mid='fixture-msg',sender='owner-fixture',platform='default',self_id='fixture-bot'):
        self.text=text;self.sender=sender;self.platform=platform;self.self_id=self_id;self.extras={}
        self.message_obj=types.SimpleNamespace(message_id=mid,timestamp=1792810000)
        self.role='member'
    def get_platform_id(self):return self.platform
    def get_self_id(self):return self.self_id
    def get_sender_id(self):return self.sender
    def get_message_type(self):return 'friend'
    def get_message_str(self):return self.text
    def get_extra(self,k,default=None):return self.extras.get(k,default)
    def set_extra(self,k,v):self.extras[k]=v
    def plain_result(self,text):return text


def request():
    return types.SimpleNamespace(prompt='unchanged original prompt',system_prompt='unchanged persona',
        contexts=[{'role':'user','content':'original history'}],model='original-model',extra_user_content_parts=[])


def response(text='收到',**kw):
    return types.SimpleNamespace(completion_text=text,role='assistant',is_chunk=False,tools_call_name=[],**kw)


class FakeProvider:
    def __init__(self):self.calls=0
    async def text_chat(self,**kw):
        self.calls+=1;src=json.loads(kw['prompt'])[0]
        return response(json.dumps([{'text':src['text'],'kind':'preference','sources':[{'id':src['id'],'quote':src['text']}]}]),
                        usage=types.SimpleNamespace(input_tokens=123,output_tokens=45,total_tokens=168))


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='family-memory-adapter-')
        self.root=Path(self.temp.name)
        self.provider=FakeProvider()
        self.context=types.SimpleNamespace(get_provider_by_id=lambda pid:self.provider if pid=='synthetic-provider' else None)
        self.config=fixture_config(enabled=True,summary_provider_id='synthetic-provider',allow_llm_extraction=False,hook_timeout_seconds=.3)
        self.plugin=FamilyMemoryPlugin(self.context,self.config)
        self.plugin.engine=MemoryEngine(self.root,self.config)
        self.owner=self.plugin.engine.policy.resolve('default','fixture-bot','owner-fixture')

    async def asyncTearDown(self):
        try:await self.plugin.terminate()
        except Exception:pass
        assert self.root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
        self.temp.cleanup()

    def remember(self,text='我喜欢琉璃风铃'):
        src=self.plugin.engine.capture(self.owner,'fixture-seed',text)
        return self.plugin.engine.remember(self.owner,text,[{'id':src,'quote':text}])

    async def test_temporary_append_preserves_persona_model_history(self):
        self.remember();event=Event();req=request()
        await self.plugin.recall(event,req)
        self.assertEqual(req.prompt,'unchanged original prompt')
        self.assertEqual(req.system_prompt,'unchanged persona')
        self.assertEqual(req.model,'original-model')
        self.assertEqual(req.contexts,[{'role':'user','content':'original history'}])
        self.assertEqual(len(req.extra_user_content_parts),1)
        self.assertTrue(req.extra_user_content_parts[0]._no_save)
        self.assertEqual(self.provider.calls,0)

    async def test_empty_remember_shows_usage_without_false_source_identity_error(self):
        replies=[r async for r in self.plugin.remember(Event(), 'private', '   ')]
        self.assertIn('/fmem remember private',replies[0])
        self.assertNotIn('missing_stable_source_identity',replies[0])
        self.assertEqual(self.plugin.engine.db.execute('select count(*) from sources').fetchone()[0],0)

    async def test_manual_command_has_independent_budget_from_chat_hook(self):
        import time
        original=self.plugin.engine.capture
        def slow_capture(*args,**kwargs):
            time.sleep(.12)
            return original(*args,**kwargs)
        self.plugin.engine.capture=slow_capture
        self.plugin.config['hook_timeout_seconds']=.02
        self.plugin.config['command_timeout_seconds']=.5
        replies=[r async for r in self.plugin.remember(Event(), 'private', '我喜欢琉璃风铃')]
        self.assertIn('记忆已保存',replies[0])
        self.assertEqual(self.plugin.engine.db.execute('select count(*) from memories').fetchone()[0],1)

    async def test_manual_timeout_does_not_claim_background_write_failed(self):
        import time
        original=self.plugin.engine.remember
        def slow_remember(*args,**kwargs):
            time.sleep(.3)
            return original(*args,**kwargs)
        self.plugin.engine.remember=slow_remember
        self.plugin.config['command_timeout_seconds']=.2
        replies=[r async for r in self.plugin.remember(Event(), 'private', '我喜欢琉璃风铃')]
        self.assertIn('后台操作可能仍在完成',replies[0])
        self.assertNotIn('未写入',replies[0])
        await asyncio.sleep(.2)
        self.assertEqual(self.plugin.engine.db.execute('select count(*) from memories').fetchone()[0],1)

    async def test_hook_repeat_neither_injects_nor_captures_twice(self):
        self.remember();event=Event();req=request()
        await self.plugin.recall(event,req);await self.plugin.recall(event,req)
        self.assertEqual(len(req.extra_user_content_parts),1)
        self.assertEqual(self.plugin.engine.db.execute('SELECT count(*) FROM sources').fetchone()[0],2)

    async def test_database_failure_does_not_modify_or_stop_chat(self):
        self.plugin.engine.close();event=Event();req=request()
        await self.plugin.recall(event,req)
        self.assertEqual(req.prompt,'unchanged original prompt');self.assertEqual(req.extra_user_content_parts,[])

    async def test_no_relevant_memory_adds_nothing(self):
        self.remember();req=request()
        await self.plugin.recall(Event('火星矿物成分'),req)
        self.assertEqual(req.extra_user_content_parts,[])

    async def test_sensitive_turn_skips_memory_but_not_original_chat(self):
        req=request();event=Event('password=SyntheticFixtureOnly999')
        await self.plugin.recall(event,req);await self.plugin.capture_response(event,response())
        self.assertEqual(req.prompt,'unchanged original prompt')
        self.assertEqual(self.plugin.engine.db.execute('SELECT count(*) FROM sources').fetchone()[0],0)

    async def test_unapproved_summary_makes_no_model_calls(self):
        event=Event();await self.plugin.recall(event,request());await self.plugin.capture_response(event,response())
        self.assertEqual(self.provider.calls,0)

    async def test_stream_chunks_and_tool_calls_are_not_completed_rounds(self):
        event=Event();await self.plugin.recall(event,request())
        chunk=response();chunk.is_chunk=True
        tool=response();tool.tools_call_name=['fixture-tool']
        await self.plugin.capture_response(event,chunk);await self.plugin.capture_response(event,tool)
        self.assertEqual(self.plugin.engine.db.execute("SELECT count(*) FROM sources WHERE role='assistant'").fetchone()[0],0)

    async def test_20_rounds_trigger_one_mock_summary_call(self):
        self.plugin.config['allow_llm_extraction']=True
        for i in range(20):
            event=Event('我喜欢纸鹤'+str(i),mid='batch-'+str(i))
            await self.plugin.recall(event,request());await self.plugin.capture_response(event,response())
            if self.plugin.jobs:await asyncio.gather(*list(self.plugin.jobs))
        self.assertEqual(self.provider.calls,1)
        self.assertEqual(self.plugin.engine.stats()['memory_count'],1)

    async def test_extraction_requires_independent_daily_cost_budget(self):
        self.plugin.config['allow_llm_extraction']=True
        self.plugin.engine.config['max_summary_calls_per_day']=0
        for i in range(20):
            event=Event('我喜欢纸灯'+str(i),mid='budget-'+str(i))
            await self.plugin.recall(event,request());await self.plugin.capture_response(event,response())
            if self.plugin.jobs:await asyncio.gather(*list(self.plugin.jobs))
        self.assertEqual(self.provider.calls,0)

    async def test_memory_timeout_fails_open_without_worker_pileup(self):
        import time
        original=self.plugin.engine.capture
        def slow(*a,**kw):time.sleep(.1);return original(*a,**kw)
        self.plugin.engine.capture=slow;self.plugin.config['hook_timeout_seconds']=.01
        req=request();await self.plugin.recall(Event(),req)
        self.assertEqual(req.extra_user_content_parts,[])
        self.assertTrue(self.plugin.gate.locked())
        await asyncio.sleep(.15)
        self.assertFalse(self.plugin.gate.locked())

    async def test_visitor_can_manage_own_memory_not_family(self):
        event=Event(mid='visitor-write',sender='visitor-A')
        result=[s async for s in self.plugin.remember(event,'private','我喜欢星空贴纸')]
        self.assertTrue(result[0].startswith('记忆已保存'))
        denied=[s async for s in self.plugin.remember(Event(mid='visitor-family',sender='visitor-A'),'family','家庭拥有月光帆船')]
        self.assertTrue(denied[0].startswith('未写入'))

    async def test_wrong_bot_instance_does_not_get_memory_access(self):
        self.remember();req=request()
        await self.plugin.recall(Event(self_id='different-bot'),req)
        self.assertEqual(req.extra_user_content_parts,[])

    async def test_original_transport_time_is_preferred_and_unknown_not_fabricated(self):
        event=Event();self.assertIsNone(self.plugin._source_time(event))
        event.message_obj.raw_message={'time':1792810000}
        self.assertEqual(self.plugin._source_time(event),1792810000)

    async def test_plugin_disabled_by_default(self):
        other=FamilyMemoryPlugin(self.context,{})
        await other.initialize()
        self.assertIsNone(other.engine)
        await other.terminate()

    async def test_context_policy_filters_tools_without_mutating_global_registry(self):
        from astrbot_plugin_family_memory.lifecycle import ConversationArchive
        module=types.ModuleType('astrbot.core.agent.tool');module.ToolSet=lambda x:list(x);sys.modules[module.__name__]=module
        self.plugin.config['context_policy_enabled']=True
        self.plugin.archive=ConversationArchive(self.root/'archive',self.plugin.engine.key)
        tools=[types.SimpleNamespace(name=n) for n in ['astrbot_execute_shell','astrbot_file_read_tool','send_message_to_user','companion_memory_search']]
        req=request();req.func_tool=tools;req.conversation=types.SimpleNamespace(cid='c',token_usage=999)
        await self.plugin.context_policy(Event(),req)
        self.assertEqual([t.name for t in req.func_tool],['send_message_to_user','companion_memory_search'])
        self.assertEqual(len(tools),4);self.assertEqual(req.conversation.token_usage,0)
        self.assertEqual(req.system_prompt,'unchanged persona');self.assertEqual(req.model,'original-model');self.assertEqual(self.provider.calls,0)

    async def test_policy_archive_unavailable_still_blocks_maintenance_tools(self):
        module=types.ModuleType('astrbot.core.agent.tool');module.ToolSet=lambda x:list(x);sys.modules[module.__name__]=module
        self.plugin.config['context_policy_enabled']=True
        req=request();req.func_tool=[types.SimpleNamespace(name='astrbot_execute_shell')]
        await self.plugin.context_policy(Event(),req)
        self.assertEqual(req.func_tool,[]);self.assertEqual(req.contexts,[{'role':'user','content':'original history'}])

    async def test_memory_tool_accepts_only_verbatim_current_user_fact(self):
        result=await self.plugin.companion_memory_save(Event('我喜欢紫色风铃'),'我喜欢紫色风铃')
        self.assertIn('已保存',result)
        rows=self.plugin.engine.db.execute('select ns,text from memories').fetchall();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['ns'],self.owner.private_ns)
        self.assertEqual(self.provider.calls,0)

    async def test_memory_tool_rejects_inference_uncertainty_privacy_and_optout(self):
        for text,quote in [('我喜欢风铃','主人是物理学家'),('也许我喜欢紫色风铃','也许我喜欢紫色风铃'),('我的手机号13800138000','我的手机号13800138000'),('不要记住我喜欢风铃','我喜欢风铃')]:
            result=await self.plugin.companion_memory_save(Event(text),quote);self.assertIn('未保存',result)
        self.assertEqual(self.plugin.engine.db.execute('select count(*) from memories').fetchone()[0],0)

    async def test_memory_tool_visitor_cannot_create_formal_entry(self):
        result=await self.plugin.companion_memory_save(Event('我喜欢紫色风铃',sender='visitor-fixture'),'我喜欢紫色风铃')
        self.assertIn('未保存',result)


if __name__=='__main__':unittest.main()
