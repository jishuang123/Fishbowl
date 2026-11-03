"""Actual native editor, audio picker, streamed chat, real decoder/TTS and mouth."""
import json
import math
import os
import sys
import tempfile
import time
import wave
from array import array
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication,QWidget,QFileDialog,QLineEdit,QDialogButtonBox,QLabel
from PySide6.QtTest import QTest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.characters import CharacterRegistry
from app.interaction_config import InteractionConfig
from app.interaction_window import InteractionDialog
from app.chat import DeepSeekChat
from app.chat_config import LocalChatConfig,MODELS
from app.server import RendererServer
from app.pet_window import PetWindow
from chat_test_server import ChatTestServer,TEST_KEY,sse

QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
app=QApplication([])
out=ROOT/'.local/evidence/mappings/ui'
out.mkdir(parents=True,exist_ok=True)
previous=os.environ.pop('DEEPSEEK_API_KEY',None)
original_cursor=QCursor.pos()
checks=[]

def wait_until(condition,timeout=60000):
    end=time.monotonic()+timeout/1000
    while time.monotonic()<end:
        app.processEvents()
        if condition():return
        QTest.qWait(15)
    raise AssertionError('mapping UI timed out')

def js(script):
    values=[]
    pet.page().runJavaScript(script,0,values.append)
    wait_until(lambda:bool(values))
    return values[0]

def snap():return json.loads(js('JSON.stringify(window.fishbowl.snapshot())'))

def ready():return not pet._switch_timer.isActive() and js('Boolean(window.fishbowl?.snapshot().ready)')

def select(combo,value):
    index=combo.findData(value)
    assert index>=0,value
    combo.setFocus()
    QTest.keyClick(combo,Qt.Key.Key_Home)
    for _ in range(index):QTest.keyClick(combo,Qt.Key.Key_Down)
    assert combo.currentData()==value

def editor(edit):
    failures=[]
    def use_dialog():
        try:
            dialog=QApplication.activeModalWidget()
            assert isinstance(dialog,InteractionDialog)
            edit(dialog)
        except Exception as error:
            failures.append(error)
            if dialog is not None:dialog.reject()
    pet.menu.popup(pet.mapToGlobal(QPoint(100,80)))
    QTest.qWait(100)
    QTimer.singleShot(100,use_dialog)
    QTest.mouseClick(pet.menu,Qt.MouseButton.LeftButton,pos=pet.menu.actionGeometry(pet.interaction_action).center())
    if failures:raise failures[0]
    QTest.qWait(150)

with tempfile.TemporaryDirectory(prefix='user-',dir=out) as directory:
    user=Path(directory)
    registry=CharacterRegistry(user)
    haru=registry.import_model(ROOT/'.local/sdk/CubismSdkForWeb-5-r.5/Samples/Resources/Haru/Haru.model3.json')
    config=InteractionConfig(registry,'deepseek')
    clip=user/'测试语音.wav'
    with wave.open(str(clip),'wb') as wav:
        wav.setparams((1,2,24000,0,'NONE','not compressed'))
        wav.writeframes(array('h',(int(6000*math.sin(2*math.pi*220*i/24000)) for i in range(24000*4))).tobytes())
    api=ChatTestServer()
    renderer=RendererServer(ROOT/'frontend/dist',registry)
    chat_config=LocalChatConfig(user/'deepseek.json')
    chat_config.save(TEST_KEY,MODELS[0])
    client=DeepSeekChat(chat_config,endpoint=api.endpoint)
    pet=PetWindow(renderer.url,settings_path=user/'settings.json',chat_client=client,characters=registry)
    pet.audio.outputs['voices'].setVolume(0)
    back=QWidget()
    back.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
    back.setStyleSheet('background:#e9f2f9;')
    back.setGeometry(80,50,1080,780)
    back.show()
    pet.move(620,100)
    pet.show()
    try:
        wait_until(ready)
        pet.audio.setMuted(True)
        pet.show_chat()
        api.enqueue(parts=[sse({'content':'先说一半，'}),(3,sse({'content':'设置保存后仍能继续。'})),sse(finish='stop'),b'data: [DONE]\n\n'])
        pet.chat_window.input.setPlainText('修改设置时继续聊。')
        QTest.keyClick(pet.chat_window.input,Qt.Key.Key_Return)
        wait_until(lambda:any(w.text()=='先说一半，' for w in pet.chat_window.content.findChildren(QLabel)))
        action=next(k for k,v in config.catalog()['actions'].items() if v['label']=='狗尾草切换出来')
        choices={}
        def configure(dialog):
            assert client.busy
            row=dialog.rows['head']
            select(row['mode'],'custom')
            select(row['expression'],'Custom:兔牙')
            def pick_audio():
                picker=QApplication.activeModalWidget()
                assert isinstance(picker,QFileDialog)
                picker.setDirectory(str(clip.parent))
                def accept_file():
                    picker.findChild(QLineEdit,'fileNameEdit').setText(str(clip))
                    QTest.mouseClick(picker.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Open),Qt.MouseButton.LeftButton)
                QTimer.singleShot(300,accept_file)
                QTimer.singleShot(3000,picker.reject)
            QTimer.singleShot(100,pick_audio)
            QTest.mouseClick(row['browse'],Qt.MouseButton.LeftButton)
            choices['voice']=row['voice'].currentData()
            assert choices['voice'].startswith('user/')
            dialog.grab().save(str(out/'head-settings.png'))
            dialog.tabs.setCurrentIndex(1)
            select(dialog.rows['body']['mode'],'custom')
            select(dialog.rows['body']['action'],action)
            select(dialog.rows['body']['expression'],'Happy')
            dialog.grab().save(str(out/'body-settings.png'))
            dialog.tabs.setCurrentIndex(2)
            select(dialog.rows['idle']['mode'],'custom')
            select(dialog.rows['idle']['action'],'gesture')
            select(dialog.rows['idle']['voice'],choices['voice'])
            dialog.grab().save(str(out/'idle-settings.png'))
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
        frames=snap()['frames']
        editor(configure)
        wait_until(lambda:not client.busy)
        assert len(client.history)==2 and '设置保存后仍能继续' in client.history[-1]['content']
        assert snap()['frames']>frames and pet.audio.muted
        assert chat_config.credentials()[0]==TEST_KEY
        assert config.load()['head']['voice']==choices['voice']
        assert InteractionConfig(CharacterRegistry(user),'deepseek').load()==config.load()
        assert all(r['mode']=='default' for r in InteractionConfig(registry,haru.id).load().values())
        checks.append('real editor and audio picker save only this role; streamed chat, key, mute and rendering survive; settings restore from disk')
        def cancel_change(dialog):
            select(dialog.rows['head']['mode'],'off')
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel),Qt.MouseButton.LeftButton)
        editor(cancel_change)
        assert config.load()['head']['mode']=='custom'
        checks.append('cancel discards changed mappings')
        pet.audio.setMuted(False)
        QCursor.setPos(pet.mapToGlobal(QPoint(200,147)))
        QTest.qWait(250)
        QTest.mouseClick(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,125))
        wait_until(lambda:pet.audio.speaking)
        wait_until(lambda:snap()['speech']['parameters']['ParamMouthOpenY']['value']>.15)
        assert pet.audio.interaction_source=='manual'
        pet.grab().save(str(out/'mapped-voice-mouth.png'))
        pet.audio.setMuted(True)
        wait_until(lambda:not pet.audio.speaking)
        QTest.mouseClick(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,125))
        QTest.qWait(300)
        assert not pet.audio.speaking and snap()['speech']['parameters']['ParamMouthOpenY']['value']<.01
        checks.append('mapped real audio drives the mouth; global mute stops it and blocks subsequent cues')
        pet.audio.setMuted(False)
        pet.bridge.triggerInteraction('deepseek','idle')
        wait_until(lambda:pet.audio.speaking)
        assert pet.audio.interaction_source=='idle'
        before=pet.pos()
        QTest.mousePress(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,320))
        QTest.qWait(80)
        QTest.mouseMove(pet.focusProxy(),QPoint(235,340))
        QTest.qWait(150)
        QTest.mouseRelease(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,320))
        assert pet.pos()==before+QPoint(35,20) and not pet.audio.speaking
        checks.append('a real drag stops an idle voice without generating a click cue')
        api.enqueue(parts=[sse({'content':'聊天朗读应该优先。'}),(.5,sse({'content':'点击时也不会被预录语音打断。'})),sse(finish='stop'),b'data: [DONE]\n\n'])
        pet.chat_window.input.setPlainText('测试朗读优先。')
        QTest.mouseClick(pet.chat_window.send_button,Qt.MouseButton.LeftButton)
        assert client.busy
        pet.bridge.triggerInteraction('deepseek','head')
        assert pet.audio.interaction_source is None
        wait_until(lambda:pet.speech.busy)
        pet.bridge.triggerInteraction('deepseek','head')
        assert pet.audio.interaction_source is None
        wait_until(lambda:pet.audio.speaking)
        QTest.mouseClick(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,125))
        wait_until(lambda:snap()['interaction']['expression']=='Custom:兔牙')
        wait_until(lambda:snap()['speech']['parameters']['ParamMouthOpenY']['value']>.15)
        assert pet.audio.interaction_source is None
        pet.grab().save(str(out/'chat-mouth-with-expression.png'))
        checks.append('streaming and real TTS take priority over mapped voices; mouth still moves with a custom mouth expression')
        def restore(dialog):
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults),Qt.MouseButton.LeftButton)
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
        assert pet.speech.busy and pet.audio.interaction_source is None
        editor(restore)
        assert pet.speech.busy and pet.audio.interaction_source is None
        assert all(r['mode']=='default' for r in config.load().values())
        assert len(client.history)==4 and not pet.audio.muted
        pet.speech.stop()
        assert pet.switch_character(haru.id)
        wait_until(ready)
        haru_config=InteractionConfig(registry,haru.id)
        haru_voice=haru_config.import_voice(clip)
        def haru_mouth(dialog):
            select(dialog.rows['head']['mode'],'custom')
            select(dialog.rows['head']['expression'],'F02')  # Owns ParamMouthOpenY=1.
            select(dialog.rows['head']['voice'],haru_voice)
            dialog.grab().save(str(out/'haru-settings.png'))
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
        editor(haru_mouth)
        QCursor.setPos(pet.mapToGlobal(QPoint(200,90)))
        QTest.qWait(250)
        QTest.mouseClick(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,90))
        wait_until(lambda:pet.audio.speaking)
        wait_until(lambda:.15<snap()['speech']['parameters']['ParamMouthOpenY']['value']<.92)
        mouth=snap()
        assert mouth['interaction']['expression']=='F02'
        assert abs(mouth['speech']['parameters']['ParamMouthOpenY']['value']-mouth['speech']['level'])<.15
        pet.grab().save(str(out/'haru-mouth-expression.png'))
        wait_until(lambda:snap()['interaction']['expression']=='Neutral')
        wait_until(lambda:not pet.audio.speaking)
        checks.append('imported Haru voice and an expression that forces the mouth open still follow native audio, then restore')
        def haru_off(dialog):
            select(dialog.rows['head']['mode'],'off')
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
        editor(haru_off)
        assert InteractionConfig(registry,haru.id).load()['head']['mode']=='off'
        assert config.load()['head']['mode']=='default'
        checks.append('restore defaults keeps chat/mute; editing the imported role never changes DeepSeek mappings')
        bad_config=InteractionConfig(registry,haru.id)
        blocked=user/'blocked-output'
        blocked.write_text('not a directory',encoding='utf-8')
        bad_config.path=blocked/'settings.json'
        dialog=InteractionDialog(bad_config,pet)
        dialog.show()
        select(dialog.rows['head']['mode'],'custom')
        QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
        assert dialog.isVisible() and '无法保存' in dialog.status.text()
        assert InteractionConfig(registry,haru.id).load()['head']['mode']=='off'
        dialog.grab().save(str(out/'save-error.png'))
        dialog.reject()
        checks.append('a real filesystem write failure keeps the editor open and preserves the saved mappings')
        assert not snap()['errors']
        result={'passed':checks,'errors':[],'liveDeepSeekVerified':False,'audibleSpeakerQualityVerified':False,
                'fixture':'actual Qt editor/WebEngine, generated PCM, real Windows TTS at zero output volume, local SSE, temporary user data'}
        (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    finally:
        pet.close()
        back.close()
        renderer.close()
        api.close()
        QCursor.setPos(original_cursor)
        if previous is not None:os.environ['DEEPSEEK_API_KEY']=previous
