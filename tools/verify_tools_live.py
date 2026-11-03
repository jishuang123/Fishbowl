"""Opt-in live API smoke test. Reads the local key; never prints or copies it."""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from PySide6.QtCore import QStandardPaths,Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.chat import DeepSeekChat
from app.chat_config import LocalChatConfig
from app.characters import CharacterRegistry
from app.memory import ConversationMemory
from app.pet_window import PetWindow
from app.server import RendererServer

parser=argparse.ArgumentParser()
parser.add_argument('--live',action='store_true',help='Explicitly allow a real API request using the local key')
args=parser.parse_args()
if not args.live:parser.error('Use --live to enable the real API test.')
app=QApplication([])
app.setApplicationName('Fishbowl')
app.setOrganizationName('Fishbowl')
root=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
config=LocalChatConfig(root/'deepseek.json')
if not config.credentials()[0]:raise SystemExit('No local key configured.')
out=ROOT/'.local/evidence/tools/live'
out.mkdir(parents=True,exist_ok=True)

def wait_until(condition,timeout=60000):
    end=time.monotonic()+timeout/1000
    while time.monotonic()<end:
        app.processEvents()
        if condition():return
        QTest.qWait(10)
    raise AssertionError('live tool verification timed out')

with tempfile.TemporaryDirectory(prefix='user-',dir=out) as directory:
    user=Path(directory)
    registry=CharacterRegistry(user)
    renderer=RendererServer(ROOT/'frontend/dist',registry)
    client=DeepSeekChat(config,memory=ConversationMemory(registry.memory_path('deepseek')))
    pet=PetWindow(renderer.url,settings_path=user/'settings.json',chat_client=client,characters=registry)
    pet.audio.outputs['voices'].setVolume(0)
    pet.audio.setMuted(True)
    pet.show()
    results,failures,updates=[],[],[]
    client.toolFinished.connect(lambda *args:results.append(args))
    client.requestFailed.connect(failures.append)
    client.replyUpdated.connect(updates.append)
    try:
        wait_until(lambda:not pet._switch_timer.isActive())
        pet.show_chat()
        pet.chat_window.input.setPlainText('现在几点？请查询本机当前时间，用一句话告诉我日期、时间和时区。')
        QTest.mouseClick(pet.chat_window.send_button,Qt.MouseButton.LeftButton)
        wait_until(lambda:not client.busy)
        success=not failures and len(client.history)==2 and any(r[3] for r in results)
        if success:
            QTest.qWait(150)
            pet.chat_window.grab().save(str(out/'live-time-chat.png'))
        result={'liveDeepSeekVerified':success,'streamingVerified':bool(updates),'model':config.credentials()[1],
                'toolCallCount':len(results),'toolsSuccessful':all(r[3] for r in results) if results else False,
                'isolatedMemory':True,'personalSettingsUnchanged':True,'muted':pet.audio.muted,
                'errors':failures,'audibleSpeakerQualityVerified':False}
        (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
        assert success,'Live tool call did not complete; see sanitized metadata.'
    finally:
        pet.close()
        renderer.close()
