"""Fragmented tool calls, actual host clock, real HTTP follow-up and persisted cards."""
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.chat import DeepSeekChat
from app.chat_config import LocalChatConfig,MODELS
from app.memory import ConversationMemory
from app.streaming import ChatStream,StreamError
from app.tool_registry import builtin_tools,ToolRegistry,ToolPlugin
from chat_test_server import ChatTestServer,TEST_KEY,sse
from tool_test_data import tool_parts,multiple_tools

app=QCoreApplication([])
out=ROOT/'.local/evidence/tools'
out.mkdir(parents=True,exist_ok=True)
previous=os.environ.pop('DEEPSEEK_API_KEY',None)
checks=[]

def wait_until(condition,timeout=6000):
    end=time.monotonic()+timeout/1000
    while time.monotonic()<end:
        app.processEvents()
        if condition():return
        QTest.qWait(5)
    raise AssertionError('tool verification timed out')

try:
    parser=ChatStream()
    raw=b''.join(tool_parts(arguments='{"错误":"参数🐟"}'))
    for byte in raw:parser.feed(bytes([byte]))
    assert parser.complete and parser.tool_calls[0]['function']['name']=='get_current_time'
    assert json.loads(parser.tool_calls[0]['function']['arguments'])=={'错误':'参数🐟'}
    interleaved=ChatStream()
    for part in [sse({'tool_calls':[{'index':1,'id':'second','function':{'name':'get_current_time','arguments':'{'}}]}),
                 sse({'tool_calls':[{'index':0,'id':'first','function':{'name':'get_current_time','arguments':'{}'}},
                     {'index':1,'function':{'arguments':'}'}}]}),sse(finish='tool_calls'),b'data: [DONE]\n\n']:
        interleaved.feed(part)
    assert interleaved.complete and [c['id'] for c in interleaved.tool_calls]==['first','second']
    checks.append('byte-split Unicode arguments and interleaved tool indices assemble without executing partial calls')
    registry=builtin_tools()
    before=time.time()
    result=registry.execute('get_current_time','{}')
    after=time.time()
    actual=datetime.fromisoformat(result['local_time'])
    assert result['ok'] and before-1<=result['unix_timestamp']<=after+1
    assert actual.utcoffset()==datetime.now().astimezone().utcoffset()
    assert not registry.execute('get_current_time','{"timezone":"ignored"}')['ok']
    assert not registry.execute('get_current_time','[]')['ok']
    assert not registry.execute('get_current_time','{broken')['ok']
    assert not registry.execute('unregistered','{}')['ok']
    extra=ToolRegistry([ToolPlugin('test_echo','测试插件','Echo fixture',
        {'type':'object','properties':{'text':{'type':'string'}},'required':['text'],'additionalProperties':False},
        lambda args:{'ok':True,'display':args['text']},lambda args:isinstance(args,dict) and set(args)=={'text'})])
    assert extra.execute('test_echo','{"text":"插件接口可扩展"}')['display']=='插件接口可扩展'
    broken=ToolRegistry([ToolPlugin('test_broken','测试异常','Exception fixture',{},
        lambda _args:(_ for _ in ()).throw(RuntimeError(TEST_KEY)))])
    failure=broken.execute('test_broken','{}')
    assert not failure['ok'] and TEST_KEY not in json.dumps(failure)
    assert not extra.execute('test_echo','{"text":""}')['ok']
    checks.append('registered host-clock plugin returns the real local offset; argument validation and plugin registration work')
    with tempfile.TemporaryDirectory(prefix='user-',dir=out) as directory:
        user=Path(directory)
        config=LocalChatConfig(user/'deepseek.json')
        config.save(TEST_KEY,MODELS[0])
        memory=ConversationMemory(user/'memory.json')
        api=ChatTestServer()
        client=DeepSeekChat(config,endpoint=api.endpoint,memory=memory,timeout_ms=3000)
        results,failures,updates,completed,busy=[],[],[],[],[]
        client.toolFinished.connect(lambda *args:results.append(args))
        client.requestFailed.connect(failures.append)
        client.replyUpdated.connect(updates.append)
        client.messageAdded.connect(lambda role,text:completed.append(text) if role=='assistant' else None)
        client.busyChanged.connect(busy.append)
        try:
            fragments=tool_parts(prefix='我看一下。')
            api.enqueue(parts=[*fragments[:-2],(.2,fragments[-2]),fragments[-1]])
            api.enqueue(parts=[sse({'content':'时间查好啦，'}),(.2,sse({'content':'结果就在上面。'})),sse(finish='stop'),b'data: [DONE]\n\n'])
            assert client.send('现在几点？')
            wait_until(lambda:bool(updates))
            assert client.busy and not results and not completed
            wait_until(lambda:bool(results))
            assert client.busy and not completed and memory.load()==[]
            wait_until(lambda:not client.busy)
            assert busy==[True,False] and len(completed)==1
            assert completed[0]=='我看一下。\n\n时间查好啦，结果就在上面。'
            assert updates[-1]==completed[0] and memory.load()==client.history
            wire=api.requests[-1]['payload']
            assert wire['stream'] and wire['messages'][-2]['tool_calls'][0]['id']=='call_clock_1'
            tool_message=wire['messages'][-1]
            payload=json.loads(tool_message['content'])
            assert tool_message['role']=='tool' and tool_message['tool_call_id']=='call_clock_1'
            assert abs(payload['unix_timestamp']-time.time())<5 and payload['display']==results[-1][2]
            assert client.history[-1]['tool_results'][0]['content']==payload['display']
            checks.append('only a complete tool stream runs; follow-up carries its actual result; busy spans both hops and only the final reply commits')
            recovered=DeepSeekChat(config,endpoint=api.endpoint,memory=ConversationMemory(memory.path))
            assert recovered.history[-1]['tool_results']==client.history[-1]['tool_results']
            assert recovered.send('你好')
            wait_until(lambda:not recovered.busy)
            prior=api.requests[-1]['payload']['messages']
            assert all(m['role']!='tool' and 'tool_results' not in m and 'tool_calls' not in m for m in prior)
            checks.append('completed tool cards restore from disk while prior protocol/tool metadata never leaks into a new request')
            for name,args in [('unregistered','{}'),('get_current_time','{broken'),('get_current_time','{"path":"private"}')]:
                start=len(results)
                api.enqueue(parts=tool_parts(name,args,'call_error_'+str(start)))
                api.enqueue()
                assert client.send('失败工具')
                wait_until(lambda:not client.busy)
                assert len(results)==start+1 and not results[-1][3]
                assert not json.loads(api.requests[-1]['payload']['messages'][-1]['content'])['ok']
            checks.append('unknown tools and invalid arguments produce safe visible failures and return feedback to the model')
            baseline=memory.path.read_bytes()
            for parts in [tool_parts()[:-1], tool_parts()[:-2]+[sse(finish='stop'),b'data: [DONE]\n\n'],
                          [sse({'tool_calls':[{'index':i,'id':'duplicate','function':{'name':'get_current_time','arguments':'{}'}}
                              for i in range(2)]}),sse(finish='tool_calls'),b'data: [DONE]\n\n']]:
                start=len(results)
                api.enqueue(parts=parts)
                assert client.send('损坏的工具协议')
                wait_until(lambda:not client.busy)
                assert len(results)==start and memory.path.read_bytes()==baseline
            for delta in ({'tool_calls':[{'index':4,'id':'x'}]}, {'tool_calls':[{'index':0,'function':{'arguments':'x'*4097}}]}):
                try:ChatStream().feed(sse(delta))
                except StreamError:pass
                else:raise AssertionError('unbounded tool data accepted')
            checks.append('incomplete or inconsistent calls never execute; call count and argument size remain bounded')
            start=len(results)
            requests=len(api.requests)
            api.enqueue(parts=tool_parts())
            cancel_before_run=lambda *_args:client.cancel()
            client.toolStarted.connect(cancel_before_run)
            assert client.send('执行前取消')
            wait_until(lambda:not client.busy)
            client.toolStarted.disconnect(cancel_before_run)
            QTest.qWait(50)
            assert len(results)==start and len(api.requests)==requests+1 and memory.path.read_bytes()==baseline
            checks.append('cancelling between the HTTP response and tool execution prevents the plugin and follow-up request')
            for action in ('cancel','clear'):
                start=len(results)
                api.enqueue(parts=tool_parts(identifier='call_after_'+action))
                api.enqueue(parts=[sse({'content':'半截答案'}),(.25,sse({'content':'不能复活'})),sse(finish='stop'),b'data: [DONE]\n\n'])
                updates.clear()
                assert client.send('第二阶段取消')
                wait_until(lambda:len(results)>start and bool(updates))
                getattr(client,action)()
                QTest.qWait(300)
                assert not client.busy
                if action=='cancel':assert memory.path.read_bytes()==baseline
                else:assert memory.load()==[] and client.history==[]
            checks.append('cancel/clear during the final stream discard the entire incomplete turn, including tool records and late data')
            timed=DeepSeekChat(config,endpoint=api.endpoint,memory=ConversationMemory(user/'timed.json'),timeout_ms=170)
            timed_results,notices=[],[]
            timed.toolFinished.connect(lambda *args:timed_results.append(args))
            timed.requestFailed.connect(notices.append)
            api.enqueue(parts=tool_parts(),delay=.06)
            api.enqueue(parts=[sse({'content':'太慢'}),(.25,sse(finish='stop')),b'data: [DONE]\n\n'])
            assert timed.send('总时限')
            wait_until(lambda:not timed.busy)
            QTest.qWait(300)
            assert timed_results and any('超时' in n for n in notices) and not timed.history
            checks.append('one total timeout covers both network hops instead of resetting after a tool result')
            start=len(results)
            for round_number in range(3):api.enqueue(parts=tool_parts(identifier=f'loop_{round_number}'))
            assert client.send('重复工具循环')
            wait_until(lambda:not client.busy)
            assert len(results)==start+2 and api.requests[-1]['payload']['tool_choice']=='none' and not client.history
            assert '上限' in failures[-1]
            checks.append('repeated tool loops stop after two rounds and force the last request to answer without another tool')
            api.enqueue(parts=tool_parts(identifier='call_server_error'))
            api.enqueue(status=401,body={'error':{'message':TEST_KEY}})
            assert client.send('工具后的服务错误')
            wait_until(lambda:not client.busy)
            assert TEST_KEY not in failures[-1] and not client.history and not memory.load()
            checks.append('a follow-up API error stays sanitized and never commits a half-finished tool turn')
        finally:
            client.cancel()
            api.close()
    result={'passed':checks,'errors':[],'fixture':'real host clock, Qt networking and filesystem; local SSE server; no live credentials'}
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
finally:
    if previous is not None:os.environ['DEEPSEEK_API_KEY']=previous
