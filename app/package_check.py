"""Explicit packaged-EXE acceptance mode; all generated data stays in a temp folder."""
import json
import math
import os
import queue
import sys
import tempfile
import threading
import time
import uuid
import wave
from array import array
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer


def verify_package(app, output, model_entry=None, live=False):
    from PySide6.QtCore import Qt,QPoint,QPointF,QEvent,QTimer,QStandardPaths
    from PySide6.QtGui import QCursor,QMouseEvent
    from PySide6.QtWidgets import QWidget,QLabel,QDialogButtonBox
    from PySide6.QtTest import QTest
    from .main import create_window
    from .chat import DeepSeekChat
    from .chat_config import LocalChatConfig,MODELS
    from .chat_window import ChatWindow
    from .memory import ConversationMemory
    from .characters import CharacterRegistry
    from .interaction_config import InteractionConfig
    from .interaction_window import InteractionDialog
    from .config import UserSettings
    output=Path(output).resolve()
    if getattr(sys,'frozen',False) and output.is_relative_to(Path(sys.executable).parent):
        raise ValueError('Verification output must be outside the release folder')
    output.mkdir(parents=True,exist_ok=True)
    original_cursor=QCursor.pos()
    environment_key=os.environ.pop('DEEPSEEK_API_KEY',None)
    checks=[]
    result={'frozen':bool(getattr(sys,'frozen',False)), 'checks':checks,'errors':[],
            'live_api_verified':False,'audible_speaker_quality_verified':False,'personal_data_used':False}

    def wait_until(condition,timeout=60000):
        until=time.monotonic()+timeout/1000
        while time.monotonic()<until:
            app.processEvents()
            if condition():return
            QTest.qWait(10)
        raise AssertionError('Package verification timed out')
    def sse(delta=None,finish=None):
        return ('data: '+json.dumps({'choices':[{'index':0,'delta':delta or {},'finish_reason':finish}]},ensure_ascii=False)+'\n\n').encode('utf-8')
    plans=queue.Queue()
    class Fixture(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*_args):pass
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            result['api_streaming']=payload.get('stream') is True
            parts=plans.get(timeout=5)
            body=b''.join(p[1] if isinstance(p,tuple) else p for p in parts)
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            try:
                for part in parts:
                    if isinstance(part,tuple):time.sleep(part[0]);part=part[1]
                    self.wfile.write(part);self.wfile.flush()
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    fixture=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
    thread=threading.Thread(target=fixture.serve_forever,daemon=True)
    thread.start()
    server=pet=back=None
    try:
        with tempfile.TemporaryDirectory(prefix='fishbowl-package-') as directory:
            user=Path(directory)
            config=LocalChatConfig(user/'deepseek.json')
            config.save(uuid.uuid4().hex,MODELS[0])
            chat=DeepSeekChat(config,endpoint=f'http://127.0.0.1:{fixture.server_port}/chat/completions')
            server,pet=create_window(user,chat_client=chat)
            pet.audio.outputs['voices'].setVolume(0)
            back=QWidget()
            back.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
            back.setStyleSheet('background:#e9f2f9;')
            back.setGeometry(80,50,1080,780)
            back.show()
            pet.move(620,100)
            pet.show()
            panel=pet.chat_window
            def js(script):
                values=[]
                pet.page().runJavaScript(script,0,values.append)
                wait_until(lambda:bool(values))
                return values[0]
            def snapshot():return json.loads(js('JSON.stringify(window.fishbowl.snapshot())'))
            def ready():return not pet._switch_timer.isActive() and js('Boolean(window.fishbowl?.snapshot().ready)')
            def capture(name):
                QTest.qWait(100)
                pet.grab().save(str(output/(name+'-pet.png')))
                if panel.isVisible():panel.grab().save(str(output/(name+'-chat.png')))
            def enqueue_time(identifier):
                plans.put([sse({'tool_calls':[{'index':0,'id':identifier,'type':'function',
                    'function':{'name':'get_current_time','arguments':'{}'}}]}),sse(finish='tool_calls'),b'data: [DONE]\n\n'])
                plans.put([sse({'content':'时间查好啦，'}),(.7,sse({'content':'本机时间和时区显示在卡片里。我在这儿，慢慢聊。'})),
                    sse(finish='stop'),b'data: [DONE]\n\n'])
            wait_until(ready)
            QTest.qWait(250)
            snap=snapshot()
            assert not snap['errors'] and snap['textures']==5 and snap['cornerPixel'][3]==0
            assert pet.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            capture('startup')
            checks.append('frozen resources load and render with a transparent window')
            QCursor.setPos(pet.mapToGlobal(QPoint(200,147)))
            QTest.qWait(250)
            QTest.mouseClick(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,125))
            wait_until(lambda:snapshot()['interaction']['expression']=='Blush')
            before=pet.pos()
            QCursor.setPos(pet.mapToGlobal(QPoint(200,320)))
            QTest.qWait(100)
            # Supply consistent local/global coordinates through Qt's actual
            # WebEngine input path, without mixing injected and OS cursor moves.
            target=pet.focusProxy()
            QTest.mousePress(target,Qt.MouseButton.LeftButton,pos=QPoint(200,320))
            QTest.qWait(80)
            move=QMouseEvent(QEvent.Type.MouseMove,QPointF(235,340),QPointF(before+QPoint(235,340)),
                             Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
            app.sendEvent(target,move)
            QTest.qWait(150)
            release=QMouseEvent(QEvent.Type.MouseButtonRelease,QPointF(200,320),QPointF(before+QPoint(235,340)),
                             Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier)
            app.sendEvent(target,release)
            QTest.qWait(100)
            assert pet.pos()==before+QPoint(35,20),f'drag: {before.x()},{before.y()} -> {pet.x()},{pet.y()}'
            frames=snapshot()['frames']
            pet.hide()
            QTest.qWait(500)
            hidden=snapshot()['frames']
            QTest.qWait(350)
            assert snapshot()['frames']-hidden<=1,f'hidden frames: {snapshot()["frames"]-hidden}'
            pet.show()
            wait_until(lambda:snapshot()['frames']>frames+4)
            checks.append('click, drag and gaze work; hidden rendering suspends and resumes')
            waves=[]
            pet.speech.synthesized.connect(waves.append)
            enqueue_time('package_clock')
            pet.show_chat()
            panel.input.setPlainText('现在几点？')
            QTest.keyClick(panel.input,Qt.Key.Key_Return)
            wait_until(lambda:any(w.objectName()=='toolBubble' for w in panel.content.findChildren(QWidget)))
            assert chat.busy and not waves
            capture('streaming-tool')
            wait_until(lambda:pet.audio.speaking or (not chat.busy and not pet.speech.busy))
            assert pet.audio.speaking,'speech did not start: '+panel.speech_status.text()
            wait_until(lambda:snapshot()['speech']['parameters']['ParamMouthOpenY']['value']>.1,timeout=10000)
            assert len(waves)==1 and len(chat.history)==2 and chat.history[-1].get('tool_results')
            capture('tts-mouth')
            pet.audio.setMuted(True)
            wait_until(lambda:snapshot()['speech']['parameters']['ParamMouthOpenY']['value']<.01)
            assert not pet.speech.busy
            enqueue_time('package_muted')
            panel.input.setPlainText('再查一次时间。')
            QTest.keyClick(panel.input,Qt.Key.Key_Return)
            wait_until(lambda:not chat.busy)
            assert len(waves)==1 and len(chat.history)==4 and pet.audio.muted
            checks.append('streaming tool results, packaged PowerShell TTS, mouth and global mute work together')
            settings=InteractionConfig(pet.characters,'deepseek')
            clip=user/'voice.wav'
            with wave.open(str(clip),'wb') as wav:
                wav.setparams((1,2,24000,0,'NONE','not compressed'))
                wav.writeframes(array('h',(int(6000*math.sin(2*math.pi*220*i/24000)) for i in range(72000))).tobytes())
            voice=settings.import_voice(clip)
            failures=[]
            def edit():
                dialog=app.activeModalWidget()
                try:
                    assert isinstance(dialog,InteractionDialog)
                    row=dialog.rows['head']
                    for field,value in (('mode','custom'),('expression','Happy'),('voice',voice)):
                        index=row[field].findData(value)
                        assert index>=0
                        row[field].setCurrentIndex(index)
                    dialog.grab().save(str(output/'interaction-settings.png'))
                    QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
                except Exception as error:
                    failures.append(type(error).__name__)
                    if dialog is not None:dialog.reject()
            QTimer.singleShot(100,edit)
            pet.show_interaction_settings()
            assert not failures and len(chat.history)==4
            pet.audio.setMuted(False)
            QTest.qWait(300)
            QTest.mouseClick(pet.focusProxy(),Qt.MouseButton.LeftButton,pos=QPoint(200,125))
            wait_until(lambda:pet.audio.speaking)
            wait_until(lambda:snapshot()['speech']['parameters']['ParamMouthOpenY']['value']>.1)
            assert snapshot()['interaction']['expression']=='Happy'
            pet.audio.setMuted(True)
            checks.append('interaction editor finds bundled motions/expressions and plays mapped voice with mouth synchronization')
            if model_entry is not None:
                assert pet.import_model(Path(model_entry))
                wait_until(lambda:not pet._importing and pet.character_id!='deepseek')
                imported=pet.character_id
                wait_until(ready)
                assert not chat.history and pet.audio.muted
                capture('imported-role')
                assert pet.switch_character('deepseek')
                wait_until(ready)
                assert len(chat.history)==4 and chat.history[-1].get('tool_results') and pet.audio.muted
                assert InteractionConfig(pet.characters,'deepseek').load()['head']['expression']=='Happy'
                checks.append('model import and role switching preserve isolated memory, mappings and global mute')
            assert UserSettings(user/'settings.json').muted
            assert len(ConversationMemory(pet.characters.memory_path('deepseek')).load())==4
            assert CharacterRegistry(user).get('deepseek').name=='大肥鱼'
            checks.append('settings and complete tool memory persist outside the executable folder')
            if live:
                # Read the already configured key directly. Never copy it to this
                # check's temp settings or put it in arguments, reports or screenshots.
                actual_root=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
                actual=LocalChatConfig(actual_root/'deepseek.json')
                if environment_key is not None:os.environ['DEEPSEEK_API_KEY']=environment_key
                real=DeepSeekChat(actual,memory=ConversationMemory(user/'live-memory.json'))
                live_panel=ChatWindow(real,pet)
                panel.hide()
                live_panel.move(panel.pos())
                live_panel.show()
                live_results=[]
                real.toolFinished.connect(lambda *values:live_results.append(values))
                live_panel.input.setPlainText('现在几点？请查询本机时间，用一句话告诉我时间和时区。')
                QTest.keyClick(live_panel.input,Qt.Key.Key_Return)
                wait_until(lambda:not real.busy)
                assert len(real.history)==2 and any(v[3] for v in live_results)
                QTest.qWait(150)
                live_panel.grab().save(str(output/'live-api-tool.png'))
                live_panel.close()
                panel.show()
                result['live_api_verified']=True
                checks.append('frozen Qt HTTPS client completes an actual DeepSeek streaming tool call with the external local key')
            assert not snapshot()['errors']
            exited=[]
            app.aboutToQuit.connect(lambda:exited.append(True))
            QTimer.singleShot(100,pet.exit_action.trigger)
            app.exec()
            assert exited
            checks.append('the real shared tray/menu exit action terminates the application')
        return_code=0
    except Exception as error:
        import traceback
        frame=traceback.extract_tb(error.__traceback__)[-1]
        result['failed_at']=Path(frame.filename).name+':'+str(frame.lineno)
        if pet is not None:
            result['speech_status']=pet.chat_window.speech_status.text()
            result['voice']=pet.speech.voice_name
            result['audio_error']=pet.audio.players['voices'].errorString()
            result['audio_state']=str(pet.audio.players['voices'].playbackState())
        result['errors'].append(type(error).__name__+': '+str(error)[:200])
        return_code=1
    finally:
        if pet is not None:pet.close()
        if back is not None:back.close()
        if server is not None:server.close()
        fixture.shutdown();fixture.server_close();thread.join(timeout=2)
        QCursor.setPos(original_cursor)
        if environment_key is not None:os.environ['DEEPSEEK_API_KEY']=environment_key
        (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return return_code
