"""Exercise real Qt playback with generated silent PCM; never changes user settings."""
import json
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtMultimedia import QMediaPlayer
from app.audio import PetAudio
from app.config import UserSettings

app = QApplication([])
out = ROOT / '.local/evidence/audio'
out.mkdir(parents=True, exist_ok=True)
with wave.open(str(out / 'silent.wav'), 'wb') as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(24000)
    wav.writeframes(b'\0\0' * 72000)
(out / 'broken.wav').write_text('This is not an audio file.', encoding='utf-8')
(out / 'cues.json').write_text(json.dumps({
    'sounds': {'test':'silent.wav', 'missing':'missing.wav', 'escape':'../outside.wav', 'broken':'broken.wav'},
    'voices': {'test':'silent.wav'},
}), encoding='utf-8')
settings_path = out / 'settings.json'
settings_path.write_text(json.dumps({'otherSetting':42, 'audio':{'muted':False}}), encoding='utf-8')
settings = UserSettings(settings_path)
audio = PetAudio(out, settings)
errors, checks = [], []
audio.playbackFailed.connect(lambda group, message: errors.append((group,message)))


def wait_until(condition, timeout=6000):
    deadline = time.monotonic()+timeout/1000
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        QTest.qWait(25)
    raise AssertionError('Audio state did not reach the expected condition')


assert not audio.playSound('unmapped') and not audio.playVoice('unmapped')
checks.append('unmapped sound/voice cues are silent no-ops')
assert audio.playSound('test') and audio.playVoice('test')
wait_until(lambda: all(p.position()>100 and p.duration()==3000 for p in audio.players.values()))
checks.append('both real Qt channels decode PCM and advance playback')
audio.setMuted(True)
assert all(p.playbackState()==QMediaPlayer.PlaybackState.StoppedState and p.source().isEmpty() for p in audio.players.values())
assert all(o.isMuted() for o in audio.outputs.values())
assert not audio.playSound('test') and not audio.playVoice('test')
checks.append('mute immediately stops both channels and rejects new playback')
audio.setMuted(False)
QTest.qWait(250)
assert all(p.playbackState()==QMediaPlayer.PlaybackState.StoppedState for p in audio.players.values())
checks.append('unmuting does not resume discarded playback')
audio.setMuted(True)
restored = PetAudio(out, UserSettings(settings_path))
assert restored.muted
assert json.loads(settings_path.read_text(encoding='utf-8'))['otherSetting']==42
checks.append('mute preference survives a new service instance without losing other settings')
audio.setMuted(False)
assert not audio.playSound('missing') and not audio.playSound('escape')
checks.append('missing and out-of-directory files fail without throwing')
assert audio.playSound('broken')
wait_until(lambda: len(errors)>=3)
assert audio.playSound('test')
wait_until(lambda: audio.players['sounds'].position()>100)
audio.stopAll()
assert all(p.source().isEmpty() for p in audio.players.values())
checks.append('decoder errors are reported, and subsequent valid playback still works')
result = {'passed':checks, 'reportedFailures':[group for group,_ in errors],
          'fixture':'generated 3-second silent PCM WAV; no bundled character audio',
          'audibleOutputVerified':False}
(out / 'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
