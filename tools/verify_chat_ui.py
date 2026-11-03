"""Native chat bubbles + real WebEngine + local HTTP fixture acceptance."""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QDialogButtonBox, QLineEdit
from PySide6.QtTest import QTest
from PySide6.QtGui import QInputMethodEvent
from app.chat import DeepSeekChat
from app.memory import ConversationMemory
from app.chat_config import LocalChatConfig, MODELS
from app.chat_window import ApiSettingsDialog, ChatWindow
from app.pet_window import PetWindow
from app.server import RendererServer
from chat_test_server import ChatTestServer, TEST_KEY, sse

app = QApplication([])
api = ChatTestServer()
renderer = RendererServer(ROOT / 'frontend/dist')
out = ROOT / '.local/evidence/chat/ui'
out.mkdir(parents=True,exist_ok=True)
previous = os.environ.pop('DEEPSEEK_API_KEY',None)
config = LocalChatConfig(out / 'deepseek.json')
config.save('',MODELS[0])
ConversationMemory(config.path.with_name('chat-memory.json')).save([])
client = DeepSeekChat(config,endpoint=api.endpoint,timeout_ms=3000)
back = QWidget()
back.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
back.setStyleSheet('background:#e9f2f9;')
back.setGeometry(80,50,1080,780)
back.show()
settings = out / 'settings.json'
settings.write_text('{}',encoding='utf-8')
pet = PetWindow(renderer.url,settings_path=settings,chat_client=client)
pet.audio.outputs['voices'].setVolume(0)
pet.move(620,100)
pet.show()
panel = pet.chat_window
checks=[]


def wait_until(condition,timeout=6000):
    end=time.monotonic()+timeout/1000
    while time.monotonic()<end:
        app.processEvents()
        if condition():return
        QTest.qWait(10)
    raise AssertionError('Chat UI verification timed out')


def js(script):
    values=[]
    pet.page().runJavaScript(script,0,values.append)
    wait_until(lambda:bool(values),60000)
    return values[0]


def capture(name):
    panel.grab().save(str(out / f'{name}.png'))


try:
    wait_until(lambda:js('Boolean(window.fishbowl?.snapshot().ready)'),60000)
    pet.menu.popup(pet.mapToGlobal(QPoint(120,80)))
    QTest.qWait(200)
    QTest.mouseClick(pet.menu,Qt.MouseButton.LeftButton,pos=pet.menu.actionGeometry(pet.chat_action).center())
    wait_until(panel.isVisible)
    panel.input.setPlainText('你好，大肥鱼！')
    QTest.keyClick(panel.input,Qt.Key.Key_Return)
    assert not client.busy and not api.requests and panel.input.toPlainText()
    capture('missing-key')
    checks.append('menu opens chat; missing key is explained without losing input')

    def configure_dialog():
        dialog=QApplication.activeModalWidget()
        assert isinstance(dialog,ApiSettingsDialog)
        QTest.keyClicks(dialog.key_input,TEST_KEY)
        assert dialog.key_input.echoMode()==QLineEdit.EchoMode.Password
        dialog.grab().save(str(out / 'api-settings-masked.png'))
        buttons=dialog.findChild(QDialogButtonBox)
        QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
    QTimer.singleShot(100,configure_dialog)
    QTest.mouseClick(panel.settings_button,Qt.MouseButton.LeftButton)
    assert config.credentials()[0]==TEST_KEY
    assert panel.input.toPlainText()=='你好，大肥鱼！'
    assert not client.history
    assert TEST_KEY not in js('JSON.stringify(window.fishbowl.snapshot())')
    assert 'chat' not in pet.channel.registeredObjects()
    app.sendEvent(panel.input,QInputMethodEvent('ni',[]))
    QTest.keyClick(panel.input,Qt.Key.Key_Return)
    assert not client.busy and not api.requests
    app.sendEvent(panel.input,QInputMethodEvent('',[]))
    checks.append('masked native settings save locally; credentials stay outside WebChannel')

    panel.input.setPlainText('今天想和你聊聊天。')
    api.enqueue(parts=[sse({'role':'assistant'}),sse({'content':'我在这儿，'}),
        (1.2,sse({'content':'慢慢说，我陪你把今天理一理。🐟'})),sse(finish='stop'),b'data: [DONE]\n\n'])
    frames=js('window.fishbowl.snapshot().frames')
    QTest.keyClick(panel.input,Qt.Key.Key_Return)
    assert client.busy and not panel.send_button.isEnabled() and panel.cancel_button.isEnabled()
    wait_until(lambda:any(label.text()=='我在这儿，' for label in panel.content.findChildren(QLabel)))
    assert client.busy
    capture('streaming-partial')
    position=[pet.x(),pet.y()]
    QTest.mousePress(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,320))
    QTest.qWait(100)
    QTest.mouseMove(pet.focusProxy(),QPoint(250,340))
    QTest.qWait(200)
    assert [pet.x(),pet.y()]==[position[0]+50,position[1]+20]
    QTest.mouseRelease(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,320))
    assert js('window.fishbowl.snapshot().frames')>frames
    wait_until(lambda:not client.busy)
    assert len(client.history)==2 and panel.send_button.isEnabled()
    assert sum(label.text()=='我在这儿，慢慢说，我陪你把今天理一理。🐟'
               for label in panel.content.findChildren(QLabel))==1
    QTest.qWait(200)
    capture('chat-reply')
    checks.append('partial text appears before completion in one bubble; rendering and dragging continue')

    literal='<img src="https://invalid.example/x"> 这段按文字显示。'
    api.enqueue(body={'choices':[{'message':{'content':literal},'finish_reason':'stop'}]})
    panel.input.setPlainText('再聊一句。')
    QTest.mouseClick(panel.send_button,Qt.MouseButton.LeftButton)
    wait_until(lambda:not client.busy)
    labels=panel.content.findChildren(QLabel)
    assert any(label.text()==literal and label.textFormat()==Qt.TextFormat.PlainText for label in labels)
    assert len(api.requests[-1]['payload']['messages'])==4
    capture('plain-text-bubbles')
    checks.append('multi-turn context works; replies remain plain text, not executable markup')

    api.enqueue(status=401,body={'error':{'message':TEST_KEY}})
    panel.input.setPlainText('失败后保留这句话。')
    QTest.mouseClick(panel.send_button,Qt.MouseButton.LeftButton)
    wait_until(lambda:not client.busy)
    assert panel.input.toPlainText()=='失败后保留这句话。'
    assert TEST_KEY not in panel.status.text() and len(client.history)==4
    capture('request-error')
    checks.append('error is readable and sanitized; failed input can be retried')

    api.enqueue(parts=[sse({'content':'我先说到这里，'}),
        (.6,sse({'content':'这段不应继续显示。'})),sse(finish='stop'),b'data: [DONE]\n\n'])
    panel.input.setPlainText('取消这一条。')
    QTest.mouseClick(panel.send_button,Qt.MouseButton.LeftButton)
    wait_until(lambda:any(label.text()=='我先说到这里，' for label in panel.content.findChildren(QLabel)))
    QTest.mouseClick(panel.cancel_button,Qt.MouseButton.LeftButton)
    wait_until(lambda:not client.busy)
    QTest.qWait(650)
    assert len(client.history)==4 and panel.input.toPlainText()=='取消这一条。'
    assert any(label.text()=='大肥鱼 · 未完成，不计入记忆' for label in panel.content.findChildren(QLabel))
    wait_until(lambda:panel.scroll.verticalScrollBar().value()==panel.scroll.verticalScrollBar().maximum())
    capture('cancelled')
    checks.append('cancel returns control and drops the late response')

    panel.hide()
    recovered=DeepSeekChat(config,endpoint=api.endpoint)
    restored=ChatWindow(recovered,pet)
    restored.move(panel.pos())
    restored.show()
    assert len(recovered.history)==4 and restored.messages.count()==4
    restored.input.setPlainText('保留这份草稿。')
    memory_before=recovered.memory.path.read_bytes()
    def save_existing_settings():
        dialog=QApplication.activeModalWidget()
        buttons=dialog.findChild(QDialogButtonBox)
        QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
    QTimer.singleShot(100,save_existing_settings)
    QTest.mouseClick(restored.settings_button,Qt.MouseButton.LeftButton)
    assert recovered.memory.path.read_bytes()==memory_before and len(recovered.history)==4
    assert restored.input.toPlainText()=='保留这份草稿。'
    QTest.qWait(100)
    restored.grab().save(str(out / 'memory-restored.png'))
    restored.close()
    panel.show()
    checks.append('a new chat panel restores completed bubbles; API settings preserve memory and drafts')

    QTest.mouseClick(panel.clear_button,Qt.MouseButton.LeftButton)
    assert client.history==[] and panel.messages.count()==0
    assert ConversationMemory(client.memory.path).load()==[]
    panel.input.setPlainText('关闭面板取消请求。')
    api.enqueue(delay=.5)
    QTest.mouseClick(panel.send_button,Qt.MouseButton.LeftButton)
    QTest.qWait(100)
    panel.close()
    wait_until(lambda:not client.busy)
    assert pet.isVisible() and not panel.isVisible()
    QTest.qWait(550)
    assert client.history==[]
    pet.show_chat()
    capture('reopened')
    checks.append('clear forgets context; closing cancels chat without closing the pet')
    assert not js('window.fishbowl.snapshot().errors')
    result={'passed':checks,'liveDeepSeekVerified':False,'fixture':'local HTTP response, real Qt UI/WebEngine'}
    (out / 'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
finally:
    client.cancel()
    pet.close()
    back.close()
    renderer.close()
    api.close()
    if previous is not None:os.environ['DEEPSEEK_API_KEY']=previous
