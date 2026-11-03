"""Real installed Windows voice -> in-memory WAV -> real Qt decoder, at zero output volume."""
import io
import json
import os
import sys
import time
import wave
from array import array
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.audio import PetAudio
from app.config import UserSettings
from app.chat import DeepSeekChat
from app.chat_config import LocalChatConfig
from app.speech import SpeechController

app=QApplication([])
out=ROOT / '.local/evidence/tts'
out.mkdir(parents=True,exist_ok=True)
settings_path=out / 'settings.json'
settings_path.write_text('{}',encoding='utf-8')
audio=PetAudio(ROOT / 'assets/audio',UserSettings(settings_path))
audio.outputs['voices'].setVolume(0)
chat=DeepSeekChat(LocalChatConfig(out / 'deepseek.json'))
speech=SpeechController(audio,chat)
waves,levels,ticks,statuses=[],[],[],[]
speech.synthesized.connect(waves.append)
audio.mouthChanged.connect(levels.append)
speech.statusChanged.connect(statuses.append)
timer=QTimer()
timer.timeout.connect(lambda:ticks.append(1))
timer.start(10)
checks=[]


def wait_until(condition,timeout=20000):
    end=time.monotonic()+timeout/1000
    while time.monotonic()<end:
        app.processEvents()
        if condition():return
        QTest.qWait(10)
    raise AssertionError('Speech verification timed out; last status='+str(statuses[-1:]))


try:
    speech.speak('你好，我是大肥鱼。我在这儿，慢慢说。')
    wait_until(lambda:bool(waves))
    wait_until(lambda:audio.speaking and any(level>.05 for level in levels))
    with wave.open(io.BytesIO(waves[0]),'rb') as wav:
        assert wav.getnchannels()==1 and wav.getsampwidth()==2 and wav.getframerate()==24000
        pcm=array('h',wav.readframes(wav.getnframes()))
        assert max(abs(sample) for sample in pcm)>100
        duration=wav.getnframes()/wav.getframerate()
    (out / 'sample-speech.wav').write_bytes(waves[0])
    assert len(ticks)>10
    checks.append('installed Chinese voice synthesizes real non-silent PCM without blocking the event loop')
    checks.append('real playback buffers produce a changing mouth envelope')
    audio.setMuted(True)
    assert not speech.busy and not audio.speaking and levels[-1]==0
    assert audio.players['voices'].sourceDevice() is None
    count=len(waves)
    speech.speak('静音时不该合成这一句。')
    QTest.qWait(200)
    assert speech.job is None and len(waves)==count
    checks.append('mute stops playback, resets the mouth, and suppresses new synthesis')
    audio.setMuted(False)
    QTest.qWait(200)
    assert not speech.busy and not audio.speaking and len(waves)==count
    checks.append('unmuting never replays the discarded reply')
    speech.speak('这句还没有准备完就要静音。')
    assert speech.job is not None
    audio.setMuted(True)
    QTest.qWait(1200)
    assert speech.job is None and not speech.busy and len(waves)==count
    checks.append('muting during synthesis kills the job and rejects late output')
    audio.setMuted(False)
    speech.speak('这句会被手动停止。')
    speech.stop()
    QTest.qWait(600)
    assert speech.job is None and len(waves)==count
    checks.append('explicit stop cancels synthesis without delayed playback')
    speech.speak('停止所有音频也要取消这句。')
    audio.stopAll()
    QTest.qWait(600)
    assert speech.job is None and len(waves)==count
    checks.append('the existing stopAll API also cancels pending TTS')
    speech.speak('新的问题优先。')
    chat.messageAdded.emit('user','下一条消息')
    QTest.qWait(600)
    assert speech.job is None and len(waves)==count
    checks.append('a new user message preempts old speech')
    speech.speak('```python\nprint(1)\n```')
    assert speech.job is None and not speech.busy
    checks.append('code-only responses are not spoken')
    speech.speak('这一句会正常读完。')
    wait_until(lambda:len(waves)>count)
    wait_until(lambda:not speech.busy,timeout=20000)
    assert not audio.speaking and levels[-1]==0 and audio.players['voices'].sourceDevice() is None
    checks.append('natural completion closes the mouth and releases generated audio')
    result={'passed':checks,'voice':speech.voice_name,'sampleDurationSeconds':duration,
            'peakMouthLevel':max(levels),'audibleSpeakerQualityVerified':False,
            'fixture':'actual Windows TTS and Qt playback; output volume set to zero'}
    (out / 'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
finally:
    speech.stop()
