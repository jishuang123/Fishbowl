"""Actual model picker, native character menu, SSE isolation, TTS and mute."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QTimer
from PySide6.QtWidgets import QApplication,QFileDialog,QWidget,QLabel,QLineEdit,QDialogButtonBox
from PySide6.QtTest import QTest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.characters import CharacterRegistry,Character
from app.config import UserSettings
from app.chat import DeepSeekChat
from app.chat_config import LocalChatConfig,MODELS
from app.memory import ConversationMemory
from app.pet_window import PetWindow
from app.server import RendererServer
from chat_test_server import ChatTestServer,TEST_KEY,sse

QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
app=QApplication([])
out=ROOT/'.local/evidence/characters/ui'
out.mkdir(parents=True,exist_ok=True)
previous=os.environ.pop('DEEPSEEK_API_KEY',None)
checks=[]

def wait_until(condition,timeout=60000):
    end=time.monotonic()+timeout/1000
    while time.monotonic()<end:
        app.processEvents()
        if condition():return
        QTest.qWait(15)
    raise AssertionError('character UI timed out')

def js(script):
    result=[]
    pet.page().runJavaScript(script,0,result.append)
    wait_until(lambda:bool(result))
    return result[0]

def ready(identifier):
    return (pet.character_id==identifier and not pet._switch_timer.isActive() and
            js('Boolean(window.fishbowl?.snapshot().ready)'))

def choose(identifier):
    pet.character_menu.popup(pet.mapToGlobal(QPoint(50,80)))
    QTest.qWait(150)
    action=next(a for a in pet.character_menu.actions() if a.data()==identifier)
    QTest.mouseClick(pet.character_menu,Qt.MouseButton.LeftButton,
                    pos=pet.character_menu.actionGeometry(action).center())
    wait_until(lambda:ready(identifier))

def reply(text):
    api.enqueue(parts=[sse({'content':text}),sse(finish='stop'),b'data: [DONE]\n\n'])
    panel.input.setPlainText('请记住：'+text)
    QTest.mouseClick(panel.send_button,Qt.MouseButton.LeftButton)
    wait_until(lambda:not client.busy)
    assert client.history[-1]['content']==text

with tempfile.TemporaryDirectory(prefix='user-',dir=out) as directory:
    user=Path(directory)
    registry=CharacterRegistry(user)
    api=ChatTestServer()
    server=RendererServer(ROOT/'frontend/dist',registry)
    config=LocalChatConfig(user/'deepseek.json')
    config.save(TEST_KEY,MODELS[0])
    client=DeepSeekChat(config,endpoint=api.endpoint)
    settings=user/'settings.json'
    settings.write_text('{}',encoding='utf-8')
    pet=PetWindow(server.url,settings_path=settings,chat_client=client,characters=registry)
    pet.audio.outputs['voices'].setVolume(0)
    back=QWidget()
    back.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
    back.setStyleSheet('background:#e9f2f9;')
    back.setGeometry(80,50,1080,780)
    back.show()
    pet.move(620,100)
    pet.show()
    panel=pet.chat_window
    try:
        wait_until(lambda:ready('deepseek'))
        pet.show_chat()
        reply('只属于大肥鱼的蓝色记忆。')
        wait_until(lambda:pet.audio.speaking)
        # A real asynchronous model import must keep the window and frame loop alive.
        frames=js('window.fishbowl.snapshot().frames')
        source=ROOT/'.local/sdk/CubismSdkForWeb-5-r.5/Samples/Resources/Haru/Haru.model3.json'
        def pick_model():
            dialog=next(w for w in QApplication.topLevelWidgets() if isinstance(w,QFileDialog))
            dialog.setDirectory(str(source.parent))
            dialog.selectFile(source.name)
            def accept_file():
                dialog.findChild(QLineEdit,'fileNameEdit').setText(str(source))
                buttons=dialog.findChild(QDialogButtonBox)
                QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Open),Qt.MouseButton.LeftButton)
            QTimer.singleShot(700,accept_file)
            QTimer.singleShot(3000,dialog.reject)  # Fail promptly if selection was not accepted.
        QTimer.singleShot(300,pick_model)
        pet.choose_model()
        assert pet._importing,'model picker did not accept its selected file'
        wait_until(lambda:not pet._importing and pet.character_id!='deepseek')
        identifier=pet.character_id
        wait_until(lambda:ready(identifier))
        assert not pet.speech.busy and not pet.audio.speaking and not client.history
        assert 'Haru' in panel.windowTitle() and config.credentials()[0]==TEST_KEY
        assert js('window.fishbowl.snapshot().frames')>0 and frames>0
        pet.grab().save(str(out/'haru.png'))
        panel.grab().save(str(out/'haru-new-chat.png'))
        checks.append('native model picker imports and renders Haru; switch stops real TTS and opens a separate empty conversation')
        pet.audio.setMuted(True)
        reply('只属于 Haru 的金色记忆。')
        assert not pet.speech.busy and not pet.audio.speaking
        assert 'Haru' in api.requests[-1]['payload']['messages'][0]['content']
        assert '蓝色记忆' not in json.dumps(api.requests[-1]['payload'],ensure_ascii=False)
        panel.input.setPlainText('Haru 的未发送草稿')
        choose('deepseek')
        assert pet.audio.muted and pet.mute_action.isChecked()
        assert len(client.history)==2 and '蓝色记忆' in client.history[-1]['content']
        assert 'Haru' not in json.dumps(client.history,ensure_ascii=False)
        panel.grab().save(str(out/'deepseek-memory.png'))
        pet.grab().save(str(out/'deepseek.png'))
        checks.append('role menu restores only DeepSeek memory and retains the global mute setting')
        reply('大肥鱼的第二条。')
        payload=api.requests[-1]['payload']['messages']
        assert '大肥鱼' in payload[0]['content'] and 'Haru' not in json.dumps(payload,ensure_ascii=False)
        choose(identifier)
        assert len(client.history)==2 and '金色记忆' in client.history[-1]['content']
        assert panel.input.toPlainText()=='Haru 的未发送草稿'
        assert '正在载入' not in panel.status.text()
        panel.grab().save(str(out/'haru-memory.png'))
        checks.append('each request uses its own persona/context and each role restores its unsent draft')
        api.enqueue(parts=[sse({'content':'Haru 的半截回复'}),(1.2,sse({'content':'不应串到大肥鱼。'})),sse(finish='stop'),b'data: [DONE]\n\n'])
        panel.input.setPlainText('这条会在切换时取消。')
        QTest.mouseClick(panel.send_button,Qt.MouseButton.LeftButton)
        wait_until(lambda:any(w.text()=='Haru 的半截回复' for w in panel.content.findChildren(QLabel)))
        choose('deepseek')
        QTest.qWait(1400)
        assert len(client.history)==4 and 'Haru' not in json.dumps(client.history,ensure_ascii=False)
        assert len(ConversationMemory(registry.memory_path(identifier)).load())==2
        assert not any('半截回复' in w.text() for w in panel.content.findChildren(QLabel))
        checks.append('switch cancels an active SSE reply; late chunks never enter another role or saved memory')
        # A bad imported model fails back to the previous working role.
        role=registry.get(identifier)
        data=json.loads(json.dumps(role.data))
        data['runtime']['model_url']=f'/character-assets/{identifier}/missing.model3.json'
        registry.characters={**registry.characters,identifier:Character(role.path,data)}
        assert pet.switch_character(identifier)
        wait_until(lambda:ready('deepseek'))
        assert len(client.history)==4 and pet.audio.muted
        registry.characters={**registry.characters,identifier:role}
        checks.append('model load failure rolls back to the previous role without altering memory or mute')
        # Original interaction behavior still runs after multiple page replacements.
        before=pet.pos()
        QTest.mousePress(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,320))
        QTest.qWait(80)
        QTest.mouseMove(pet.focusProxy(),QPoint(235,340))
        QTest.qWait(150)
        QTest.mouseRelease(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,320))
        assert pet.pos()==before+QPoint(35,20)
        assert not json.loads(js('JSON.stringify(window.fishbowl.snapshot())'))['errors']
        pet.character_menu.popup(pet.mapToGlobal(QPoint(50,80)))
        QTest.qWait(200)
        pet.character_menu.grab().save(str(out/'character-menu.png'))
        pet.character_menu.hide()
        assert UserSettings(settings).muted and UserSettings(settings).data['character_id']=='deepseek'
        pet.audio.setMuted(False)
        assert UserSettings(settings).data['character_id']=='deepseek'
        choose(identifier)
        client.clear()
        assert not ConversationMemory(registry.memory_path(identifier)).load()
        assert len(ConversationMemory(registry.memory_path('deepseek')).load())==4
        assert not UserSettings(settings).muted and UserSettings(settings).data['character_id']==identifier
        checks.append('drag survives repeated switches; role/mute persist together and clearing Haru keeps DeepSeek memory')
        pet.close()
        pet=PetWindow(server.url,settings_path=settings,characters=CharacterRegistry(user))
        pet.audio.outputs['voices'].setVolume(0)
        pet.move(620,100)
        pet.show()
        wait_until(lambda:ready(identifier))
        assert pet.chat_client.character_name=='Haru' and not pet.audio.muted and not pet.chat_client.history
        choose('deepseek')
        assert len(pet.chat_client.history)==4
        checks.append('a new desktop window starts as the saved imported role and can restore DeepSeek memory afterwards')
        result={'passed':checks,'errors':[], 'liveDeepSeekVerified':False,'audibleSpeakerQualityVerified':False,
                'fixture':'native Qt/WebEngine, SDK Haru, real Windows TTS at output volume zero, local SSE, temporary settings'}
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,indent=2))
    finally:
        pet.close()
        back.close()
        server.close()
        api.close()
        if previous is not None:os.environ['DEEPSEEK_API_KEY']=previous
