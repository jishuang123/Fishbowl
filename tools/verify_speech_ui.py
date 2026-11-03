"""Actual SSE -> native TTS -> decoder -> QWebChannel -> rendered model parameters."""
import json
import os
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication,QWidget,QLabel
from PySide6.QtTest import QTest
from app.chat import DeepSeekChat
from app.chat_config import LocalChatConfig,MODELS
from app.memory import ConversationMemory
from app.pet_window import PetWindow
from app.server import RendererServer
from chat_test_server import ChatTestServer,TEST_KEY,sse

app=QApplication([])
api=ChatTestServer()
renderer=RendererServer(ROOT / 'frontend/dist')
out=ROOT / '.local/evidence/tts/ui'
out.mkdir(parents=True,exist_ok=True)
previous=os.environ.pop('DEEPSEEK_API_KEY',None)
config=LocalChatConfig(out / 'deepseek.json')
config.save(TEST_KEY,MODELS[0])
ConversationMemory(config.path.with_name('chat-memory.json')).save([])
client=DeepSeekChat(config,endpoint=api.endpoint)
settings=out / 'settings.json'
settings.write_text('{}',encoding='utf-8')
pet=PetWindow(renderer.url,settings_path=settings,chat_client=client)
pet.audio.outputs['voices'].setVolume(0)
back=QWidget()
back.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
back.setStyleSheet('background:#e9f2f9;')
back.setGeometry(80,50,1080,780)
back.show()
pet.move(620,100)
pet.show()
original_cursor=QCursor.pos()
QCursor.setPos(pet.mapToGlobal(QPoint(200,147)))
checks,waves=[],[]
pet.speech.synthesized.connect(waves.append)


def wait_until(condition,timeout=30000):
    until=time.monotonic()+timeout/1000
    while time.monotonic()<until:
        app.processEvents()
        if condition():return
        QTest.qWait(10)
    raise AssertionError('Speech UI verification timed out')


def js(script):
    result=[]
    pet.page().runJavaScript(script,0,result.append)
    wait_until(lambda:bool(result))
    return result[0]


def snapshot():return json.loads(js('JSON.stringify(window.fishbowl.snapshot())'))


try:
    wait_until(lambda:js('Boolean(window.fishbowl?.snapshot().ready)'))
    pet.show_chat()
    panel=pet.chat_window
    api.enqueue(parts=[sse({'content':'先让我说一句，'}),
        (1.1,sse({'content':'你好，我是大肥鱼。我在这儿，慢慢聊，不着急。'})),sse(finish='stop'),b'data: [DONE]\n\n'])
    panel.input.setPlainText('和我说句话。')
    QTest.keyClick(panel.input,Qt.Key.Key_Return)
    wait_until(lambda:any(label.text()=='先让我说一句，' for label in panel.content.findChildren(QLabel)))
    assert client.busy and pet.speech.job is None and not waves
    panel.grab().save(str(out / 'stream-first.png'))
    before=snapshot()['frames']
    position=[pet.x(),pet.y()]
    QTest.mousePress(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,320))
    QTest.qWait(100)
    QTest.mouseMove(pet.focusProxy(),QPoint(235,340))
    QTest.qWait(150)
    assert [pet.x(),pet.y()]==[position[0]+35,position[1]+20]
    QTest.mouseRelease(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,320))
    assert snapshot()['frames']>before
    checks.append('streamed text arrives and the pet drags before any TTS starts')
    wait_until(lambda:pet.audio.speaking)
    wait_until(lambda:snapshot()['speech']['parameters']['ParamMouthOpenY']['value']>.15)
    opened=snapshot()['speech']
    assert opened['parameters']['JawOpen']['value']>.02
    pet.grab().save(str(out / 'mouth-open.png'))
    panel.grab().save(str(out / 'reading.png'))
    assert not client.busy and panel.stop_speech_button.isEnabled() and waves
    checks.append('complete reply triggers actual Windows TTS and visibly opens mouth/jaw through WebChannel')
    pet.audio.setMuted(True)
    wait_until(lambda:snapshot()['speech']['parameters']['ParamMouthOpenY']['value']<.01)
    closed=snapshot()['speech']
    assert not pet.audio.speaking and closed['parameters']['JawOpen']['value']<.01
    pet.grab().save(str(out / 'mouth-muted.png'))
    panel.grab().save(str(out / 'muted.png'))
    checks.append('mute stops real playback and restores mouth/jaw without changing streamed text')
    count=len(waves)
    pet.audio.setMuted(False)
    QTest.qWait(300)
    assert not pet.speech.busy and len(waves)==count
    checks.append('unmute has no queued or delayed speech')
    api.enqueue()
    panel.input.setPlainText('再说一句。')
    QTest.mouseClick(panel.send_button,Qt.MouseButton.LeftButton)
    wait_until(lambda:pet.audio.speaking)
    QTest.mouseClick(panel.stop_speech_button,Qt.MouseButton.LeftButton)
    wait_until(lambda:snapshot()['speech']['parameters']['ParamMouthOpenY']['value']<.01)
    assert not pet.speech.busy and not pet.audio.speaking
    assert len(client.history)==4
    checks.append('stop-reading button resets mouth while preserving the completed conversation')
    api.enqueue(parts=[sse({'content':'这句会被取消，'}),(.6,sse({'content':'不该被朗读。'})),
                       sse(finish='stop'),b'data: [DONE]\n\n'])
    count=len(waves)
    panel.input.setPlainText('取消半截。')
    QTest.mouseClick(panel.send_button,Qt.MouseButton.LeftButton)
    wait_until(lambda:any(label.text()=='这句会被取消，' for label in panel.content.findChildren(QLabel)))
    QTest.mouseClick(panel.cancel_button,Qt.MouseButton.LeftButton)
    QTest.qWait(800)
    assert len(waves)==count and pet.speech.job is None and len(client.history)==4
    checks.append('cancelled partial replies never trigger synthesis or speech')
    assert not snapshot()['errors']
    result={'passed':checks,'open':opened,'closed':closed,'voice':pet.speech.voice_name,
            'liveDeepSeekVerified':False,'audibleSpeakerQualityVerified':False,
            'fixture':'local SSE reply; actual installed TTS, decoder, model and WebChannel; output volume zero'}
    (out / 'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
finally:
    pet.close()
    back.close()
    QCursor.setPos(original_cursor)
    renderer.close()
    api.close()
    if previous is not None:os.environ['DEEPSEEK_API_KEY']=previous
