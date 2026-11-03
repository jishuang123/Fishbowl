"""Actual result cards + two-hop SSE + Windows TTS/mouth + cancel/role isolation."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication,QWidget,QLabel,QFrame
from PySide6.QtTest import QTest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.chat import DeepSeekChat
from app.chat_config import LocalChatConfig,MODELS
from app.chat_window import ChatWindow
from app.characters import CharacterRegistry
from app.memory import ConversationMemory
from app.pet_window import PetWindow
from app.server import RendererServer
from chat_test_server import ChatTestServer,TEST_KEY,sse
from tool_test_data import tool_parts

app=QApplication([])
out=ROOT/'.local/evidence/tools/ui'
out.mkdir(parents=True,exist_ok=True)
previous=os.environ.pop('DEEPSEEK_API_KEY',None)
original_cursor=QCursor.pos()
checks=[]

def wait_until(condition,timeout=60000):
    end=time.monotonic()+timeout/1000
    while time.monotonic()<end:
        app.processEvents()
        if condition():return
        QTest.qWait(10)
    raise AssertionError('tool UI timed out')

def js(script):
    values=[]
    pet.page().runJavaScript(script,0,values.append)
    wait_until(lambda:bool(values))
    return values[0]

def snap():return json.loads(js('JSON.stringify(window.fishbowl.snapshot())'))

def ready():return not pet._switch_timer.isActive() and js('Boolean(window.fishbowl?.snapshot().ready)')

def labels():return [w.text() for w in panel.content.findChildren(QLabel)]

def send(text):
    panel.input.setPlainText(text)
    QTest.mouseClick(panel.send_button,Qt.MouseButton.LeftButton)
    assert client.busy

with tempfile.TemporaryDirectory(prefix='user-',dir=out) as directory:
    user=Path(directory)
    registry=CharacterRegistry(user)
    haru=registry.import_model(ROOT/'.local/sdk/CubismSdkForWeb-5-r.5/Samples/Resources/Haru/Haru.model3.json')
    api=ChatTestServer()
    renderer=RendererServer(ROOT/'frontend/dist',registry)
    config=LocalChatConfig(user/'deepseek.json')
    config.save(TEST_KEY,MODELS[0])
    client=DeepSeekChat(config,endpoint=api.endpoint)
    pet=PetWindow(renderer.url,settings_path=user/'settings.json',chat_client=client,characters=registry)
    pet.audio.outputs['voices'].setVolume(0)
    waves,results=[],[]
    pet.speech.synthesized.connect(waves.append)
    client.toolFinished.connect(lambda *args:results.append(args))
    back=QWidget()
    back.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
    back.setStyleSheet('background:#e9f2f9;')
    back.setGeometry(80,50,1080,780)
    back.show()
    pet.move(620,100)
    pet.show()
    panel=pet.chat_window
    try:
        wait_until(ready)
        pet.show_chat()
        QCursor.setPos(pet.mapToGlobal(QPoint(200,147)))
        api.enqueue(parts=tool_parts(prefix='我查一下本机时间。'))
        api.enqueue(parts=[sse({'content':'时间查好了，'}),(1.2,sse({'content':'本机时间和时区显示在上面的卡片里啦。'})),sse(finish='stop'),b'data: [DONE]\n\n'])
        send('现在几点？请查询本机时间。')
        wait_until(lambda:bool(results) and any('时间查好了，' in t for t in labels()))
        assert client.busy and not waves and pet.speech.job is None
        assert results[-1][2] in labels() and any('查询当前时间 · 已完成'==t for t in labels())
        assert not ConversationMemory(registry.memory_path('deepseek')).load()
        panel.grab().save(str(out/'tool-result-streaming.png'))
        frames=snap()['frames']
        before=pet.pos()
        QTest.mousePress(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,320))
        QTest.qWait(80)
        QTest.mouseMove(pet.focusProxy(),QPoint(235,340))
        QTest.qWait(150)
        QTest.mouseRelease(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,320))
        assert pet.pos()==before+QPoint(35,20) and snap()['frames']>frames
        checks.append('actual local time card appears while final text still streams; neither tool nor preamble starts TTS and the pet still drags')
        wait_until(lambda:pet.audio.speaking)
        wait_until(lambda:snap()['speech']['parameters']['ParamMouthOpenY']['value']>.15)
        assert len(waves)==1 and len(client.history)==2 and not client.busy
        assert client.history[-1]['tool_results'][0]['content']==results[0][2]
        panel.grab().save(str(out/'tool-final.png'))
        pet.grab().save(str(out/'tool-mouth.png'))
        checks.append('only the complete final reply triggers real Windows speech and mouth/jaw movement; tool cards persist with the turn')
        pet.audio.setMuted(True)
        wait_until(lambda:snap()['speech']['parameters']['ParamMouthOpenY']['value']<.01)
        assert not pet.audio.speaking and results[0][2] in labels()
        count=len(waves)
        pet.audio.setMuted(False)
        QTest.qWait(250)
        assert len(waves)==count and not pet.speech.busy
        checks.append('global mute stops speech and mouth without changing results; unmute never replays a tool or reply')
        panel.hide()
        recovered=DeepSeekChat(config,endpoint=api.endpoint,memory=ConversationMemory(registry.memory_path('deepseek')))
        restored=ChatWindow(recovered,pet)
        restored.move(panel.pos())
        restored.show()
        QTest.qWait(150)
        assert len(recovered.history)==2 and restored.messages.count()==3
        assert results[0][2] in [w.text() for w in restored.content.findChildren(QLabel)]
        assert len(waves)==count
        restored.grab().save(str(out/'tool-memory-restored.png'))
        restored.close()
        panel.show()
        checks.append('a new native chat panel restores the completed tool card and answer without replaying speech')
        pet.audio.setMuted(True)
        api.enqueue(parts=tool_parts('not_installed',identifier='call_missing'))
        api.enqueue(parts=[sse({'content':'<b>这个工具暂时不可用。</b>'}),sse(finish='stop'),b'data: [DONE]\n\n'])
        send('未知工具测试。')
        wait_until(lambda:not client.busy)
        assert not results[-1][3] and any('未支持的工具 · 未成功'==t for t in labels())
        assert '<b>这个工具暂时不可用。</b>' in labels()
        for card in panel.content.findChildren(QFrame,'toolBubble'):
            assert all(label.textFormat()==Qt.TextFormat.PlainText for label in card.findChildren(QLabel))
        panel.grab().save(str(out/'tool-unavailable.png'))
        checks.append('unknown tools show a readable failure card and all result/reply text stays plain text')
        pet.audio.setMuted(False)
        baseline=ConversationMemory(registry.memory_path('deepseek')).load()
        count=len(waves)
        api.enqueue(parts=tool_parts(identifier='call_cancelled'))
        api.enqueue(parts=[sse({'content':'这一轮会取消，'}),(.8,sse({'content':'不要保存或朗读。'})),sse(finish='stop'),b'data: [DONE]\n\n'])
        send('取消这一轮时间查询。')
        wait_until(lambda:'这一轮会取消，' in labels())
        QTest.mouseClick(panel.cancel_button,Qt.MouseButton.LeftButton)
        QTest.qWait(900)
        assert not client.busy and len(waves)==count and ConversationMemory(registry.memory_path('deepseek')).load()==baseline
        assert any('查询当前时间 · 本轮未完成' in t for t in labels())
        panel.grab().save(str(out/'tool-cancelled.png'))
        checks.append('cancelling after a result but before final completion marks the card uncommitted, never saves or reads partial text')
        api.enqueue(parts=tool_parts(identifier='call_switch'))
        api.enqueue(parts=[sse({'content':'切换时的半截，'}),(1,sse({'content':'不能串到新角色。'})),sse(finish='stop'),b'data: [DONE]\n\n'])
        send('切换前再查一次。')
        wait_until(lambda:'切换时的半截，' in labels())
        assert pet.switch_character(haru.id)
        wait_until(ready)
        QTest.qWait(1100)
        assert not client.history and not client.busy and not any('半截' in t for t in labels())
        assert ConversationMemory(registry.memory_path('deepseek')).load()==baseline
        assert pet.switch_character('deepseek')
        wait_until(ready)
        assert client.history==baseline and results[0][2] in labels()
        QTest.mouseClick(panel.clear_button,Qt.MouseButton.LeftButton)
        assert not client.history and not panel.messages.count() and not ConversationMemory(registry.memory_path('deepseek')).load()
        checks.append('role switching cancels the tool turn and isolates cards/memory; clearing removes completed cards and dialogue together')
        assert not snap()['errors']
        result={'passed':checks,'errors':[],'liveDeepSeekVerified':False,'audibleSpeakerQualityVerified':False,
                'fixture':'actual clock, native Qt/WebEngine, real TTS at zero output volume, local SSE, temporary user data'}
        (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    finally:
        pet.close()
        back.close()
        renderer.close()
        api.close()
        QCursor.setPos(original_cursor)
        if previous is not None:os.environ['DEEPSEEK_API_KEY']=previous
