"""Fragmented SSE and persistence acceptance via real local HTTP and filesystem."""
import json
import os
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app.chat import DeepSeekChat
from app.chat_config import LocalChatConfig, MODELS
from app.memory import ConversationMemory
from app.persona import load_persona
from app.streaming import ChatStream, StreamError
from chat_test_server import ChatTestServer, TEST_KEY, sse

app=QApplication([])
api=ChatTestServer()
out=ROOT / '.local/evidence/stream-memory'
out.mkdir(parents=True,exist_ok=True)
previous=os.environ.pop('DEEPSEEK_API_KEY',None)
config=LocalChatConfig(out / 'deepseek.json')
config.save(TEST_KEY,MODELS[0])
memory=ConversationMemory(out / 'chat-memory.json')
memory.save([])
client=DeepSeekChat(config,endpoint=api.endpoint,memory=memory,timeout_ms=3000)
updates, failures, statuses=[],[],[]
client.replyUpdated.connect(updates.append)
client.requestFailed.connect(failures.append)
client.statusChanged.connect(statuses.append)
checks=[]


def wait_until(condition,timeout=5000):
    until=time.monotonic()+timeout/1000
    while time.monotonic()<until:
        app.processEvents()
        if condition():return
        QTest.qWait(10)
    raise AssertionError('Stream/memory verification timed out')


def parts(delay=.25):
    return [b': keepalive\r\n\r\n',sse({'role':'assistant'}),sse({'content':'先说一句，'}),
            (delay,sse({'content':'再慢慢接着说。🐟'})),sse(finish='stop'),b'data: [DONE]\n\n']


try:
    parser=ChatStream()
    raw=(b': ping\r\n\r\n'+sse({'role':'assistant'})+sse({'reasoning_content':'not-for-display'})+
        sse({'content':'你好，🐟！'}).replace(b'\n',b'\r\n')+
        b'data: {"choices":\r\ndata: [{"delta":{},"finish_reason":"stop"}]}\r\n\r\n'+
        b'data: {"choices":[],"usage":{}}\n\ndata: [DONE]\n\n')
    for byte in raw:parser.feed(bytes([byte]))
    assert parser.complete and parser.text=='你好，🐟！'
    checks.append('single-byte UTF-8/CRLF, keepalives, usage and reasoning are parsed safely')
    try:
        ChatStream().feed(b'x'*(1024*1024+1))
        raise AssertionError('Oversized response accepted')
    except StreamError:pass
    checks.append('oversized stream is rejected before memory grows without bound')

    api.enqueue(parts=parts())
    assert client.send('我喜欢在晚上画画。')
    wait_until(lambda:bool(updates))
    assert client.busy and memory.load()==[] and updates[-1]=='先说一句，'
    wait_until(lambda:not client.busy)
    assert memory.load()==client.history and updates[-1]=='先说一句，再慢慢接着说。🐟'
    assert config.credentials()[0]==TEST_KEY
    checks.append('partial text arrives before completion; only finished turns are saved')
    recovered=DeepSeekChat(config,endpoint=api.endpoint,memory=ConversationMemory(memory.path))
    assert recovered.history==client.history
    assert recovered.send('还记得我喜欢什么吗？')
    wait_until(lambda:not recovered.busy)
    messages=api.requests[-1]['payload']['messages']
    assert messages[0]['content']==load_persona()
    assert messages[1]['content']=='我喜欢在晚上画画。'
    assert all(term in messages[0]['content'] for term in ['温和','不编造','用户的节奏'])
    checks.append('a new client restores memory and sends the designed persona with prior context')
    baseline=memory.path.read_bytes()
    # client still owns its earlier session, but failed work must never alter the file.
    updates.clear()
    api.enqueue(parts=parts(.3))
    assert client.send('取消半截回复。')
    wait_until(lambda:bool(updates))
    client.cancel()
    QTest.qWait(350)
    assert memory.path.read_bytes()==baseline and len(client.history)==2
    checks.append('cancelling after partial output never saves it or resurrects a late reply')
    for stream in [
        [sse({'content':'半截'}),sse(finish='stop')],
        [sse({'content':'半截'}),b'data: {broken}\n\n'],
        [sse({'reasoning_content':'not-for-display'}),sse(finish='stop'),b'data: [DONE]\n\n'],
        [sse({'content':'半截'}),sse(finish='aborted'),b'data: [DONE]\n\n'],
    ]:
        before=len(failures)
        api.enqueue(parts=stream)
        assert client.send('不完整协议测试。')
        wait_until(lambda:not client.busy)
        assert len(failures)==before+1 and memory.path.read_bytes()==baseline
    checks.append('missing DONE, malformed events, reasoning-only and aborted output are not remembered')
    timed_memory=ConversationMemory(out / 'timeout-memory.json')
    timed_memory.save([])
    timed=DeepSeekChat(config,endpoint=api.endpoint,memory=timed_memory,timeout_ms=80)
    timed_updates=[]
    timed.replyUpdated.connect(timed_updates.append)
    api.enqueue(parts=parts(.3))
    assert timed.send('流式超时。')
    wait_until(lambda:not timed.busy)
    QTest.qWait(350)
    assert timed_updates and timed_memory.load()==[]
    checks.append('timeout after a partial response does not commit memory')

    updates.clear()
    api.enqueue(parts=parts(.3))
    assert client.send('清空时取消。')
    wait_until(lambda:bool(updates))
    client.clear()
    QTest.qWait(350)
    assert client.history==[] and ConversationMemory(memory.path).load()==[]
    assert config.credentials()[0]==TEST_KEY
    checks.append('clear cancels a stream and persists empty memory without touching the Key')
    for _ in range(12):
        assert client.send('十轮容量验证。')
        wait_until(lambda:not client.busy)
    assert len(ConversationMemory(memory.path).load())==20
    assert len(api.requests[-1]['payload']['messages'])<=22
    checks.append('disk and request context retain at most ten complete pairs')

    broken=out / 'broken-memory.json'
    for content in ['not json',json.dumps({'version':1,'messages':[{'role':'system','content':'x'}]})]:
        broken.write_text(content,encoding='utf-8')
        store=ConversationMemory(broken)
        assert store.load()==[] and store.read_failed
    checks.append('corrupt or unexpected memory safely starts a new session')
    blocked=out / 'not-a-file'
    blocked.mkdir(exist_ok=True)
    failing=DeepSeekChat(config,endpoint=api.endpoint,memory=ConversationMemory(blocked))
    notices=[]
    failing.statusChanged.connect(notices.append)
    assert failing.send('磁盘错误不影响聊天。')
    wait_until(lambda:not failing.busy)
    assert len(failing.history)==2 and '无法保存' in notices[-1]
    failing.clear()
    assert len(failing.history)==2 and '无法清空' in notices[-1]
    checks.append('write failures preserve the response and never falsely claim memory was cleared')
    result={'passed':checks,'liveDeepSeekVerified':False,
            'personaQualityVerifiedWithLiveModel':False,
            'fixture':'real Qt networking and filesystem; local SSE test server'}
    (out / 'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
finally:
    client.cancel()
    api.close()
    if previous is not None:os.environ['DEEPSEEK_API_KEY']=previous
