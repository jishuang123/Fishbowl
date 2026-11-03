"""Real Qt networking against a local contract fixture, not live API validation."""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app.chat_config import LocalChatConfig, MODELS
from app.chat import DeepSeekChat
from app.memory import ConversationMemory
from chat_test_server import ChatTestServer, TEST_KEY

app = QApplication([])
server = ChatTestServer()
out = ROOT / '.local/evidence/chat'
out.mkdir(parents=True,exist_ok=True)
previous = os.environ.pop('DEEPSEEK_API_KEY',None)
checks, failures = [], []
config = LocalChatConfig(out / 'deepseek.json')
config.save('',MODELS[0])
ConversationMemory(config.path.with_name('chat-memory.json')).save([])
client = DeepSeekChat(config,endpoint=server.endpoint,timeout_ms=3000)
client.requestFailed.connect(failures.append)


def wait_until(condition, timeout=5000):
    end = time.monotonic()+timeout/1000
    while time.monotonic()<end:
        app.processEvents()
        if condition(): return
        QTest.qWait(10)
    raise AssertionError('Chat verification timed out')


try:
    assert not client.send('你好') and not server.requests
    checks.append('missing key prevents any network request')
    config.save(TEST_KEY,MODELS[0])
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda:ticks.append(1))
    timer.start(10)
    server.enqueue(delay=.2)
    assert client.send('你好') and not client.send('重复提交')
    wait_until(lambda:not client.busy)
    assert len(server.requests)==1 and len(ticks)>3 and len(client.history)==2
    request = server.requests[-1]
    assert request['authorized'] and request['path']=='/chat/completions'
    assert request['payload']['model']==MODELS[0] and request['payload']['thinking']=={'type':'disabled'}
    assert request['payload']['stream'] is True
    checks.append('real HTTP contract, single-flight request and responsive event loop')
    assert client.send('再聊一句')
    wait_until(lambda:not client.busy)
    assert [m['role'] for m in server.requests[-1]['payload']['messages']]==['system','user','assistant','user']
    checks.append('successful turns supply conversation context')
    count = len(client.history)
    for status in [401,402,429,503]:
        server.enqueue(status=status,body={'error':{'message':TEST_KEY}})
        assert client.send('错误测试')
        wait_until(lambda:not client.busy)
        assert len(client.history)==count and TEST_KEY not in failures[-1]
    checks.append('HTTP errors are sanitized and failed turns never enter context')
    for body in [b'not json', {}, {'choices':[{'message':{'content':''}}]}]:
        server.enqueue(body=body)
        assert client.send('格式测试')
        wait_until(lambda:not client.busy)
        assert len(client.history)==count
    checks.append('malformed and empty replies fail without damaging context')
    server.enqueue(delay=.25)
    assert client.send('取消测试')
    wait_until(lambda:len(server.requests)==10)
    client.cancel()
    wait_until(lambda:not client.busy)
    QTest.qWait(300)
    assert len(client.history)==count
    checks.append('cancellation ignores late completion')
    fast_memory = ConversationMemory(out / 'timeout-memory.json')
    fast_memory.save([])
    fast = DeepSeekChat(config,endpoint=server.endpoint,timeout_ms=80,memory=fast_memory)
    fast_errors=[]
    fast.requestFailed.connect(fast_errors.append)
    server.enqueue(delay=.25)
    assert fast.send('超时测试')
    wait_until(lambda:not fast.busy)
    assert fast_errors and not fast.history
    QTest.qWait(300)
    checks.append('absolute timeout releases the request')
    server.enqueue(status=302,location=server.endpoint,body={})
    before = len(server.requests)
    assert client.send('重定向测试')
    wait_until(lambda:not client.busy)
    assert len(server.requests)==before+1 and len(client.history)==count
    checks.append('redirects are not followed with credentials')
    for _ in range(12):
        assert client.send('上下文边界测试')
        wait_until(lambda:not client.busy)
    assert len(client.history)==20 and len(server.requests[-1]['payload']['messages'])<=22
    before = len(server.requests)
    assert not client.send('x'*2001) and not client.send('  ')
    assert len(server.requests)==before
    checks.append('input and session context stay bounded')
    server.enqueue(delay=.25)
    assert client.send('清空测试')
    wait_until(lambda:len(server.requests)==before+1)
    client.clear()
    QTest.qWait(300)
    assert not client.busy and client.history==[]
    checks.append('clearing cancels pending work and forgets the session')
    assert all(TEST_KEY not in text for text in failures)
    result = {'passed':checks,'transport':'real QNetworkAccessManager + local HTTP contract fixture',
              'liveDeepSeekVerified':False,'secretEchoInErrors':False}
    (out / 'service-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
finally:
    client.cancel()
    server.close()
    if previous is not None: os.environ['DEEPSEEK_API_KEY']=previous
