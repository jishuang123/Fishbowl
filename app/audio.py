"""Asynchronous local sound/voice playback, independent of pet rendering/input."""
import json
import logging
import math
from array import array
from pathlib import Path
from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot, QBuffer, QByteArray, QIODevice
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QAudioBufferOutput, QAudioFormat, QAudioBuffer
from .config import UserSettings


class PetAudio(QObject):
    mutedChanged = Signal(bool)
    playbackFailed = Signal(str, str)
    mouthChanged = Signal(float)
    speakingChanged = Signal(bool)
    allStopped = Signal()

    def __init__(self, root: Path, settings: UserSettings, parent=None):
        super().__init__(parent)
        self.root = root.resolve()
        self.settings = settings
        self._muted = settings.muted
        self.cues = {'sounds': {}, 'voices': {}}
        self.players = {}
        self.outputs = {}
        self._speaking = False
        self._voice_buffer = None
        self.interaction_source = None
        try:
            manifest = json.loads((self.root / 'cues.json').read_text(encoding='utf-8'))
            if not isinstance(manifest, dict):
                raise ValueError('Expected an audio cue object')
            for group in self.cues:
                values = manifest.get(group, {})
                if isinstance(values, dict):
                    self.cues[group] = {k:v for k,v in values.items() if isinstance(v, str)}
        except FileNotFoundError:
            pass
        except (ValueError, OSError) as error:
            logging.warning('Audio manifest unavailable: %s', error)
        for group in self.cues:
            output = QAudioOutput(self)
            output.setMuted(self._muted)
            output.setVolume(0.5 if group == 'sounds' else 0.7)
            player = QMediaPlayer(self)
            player.setAudioOutput(output)
            player.errorOccurred.connect(lambda error, message, name=group: self._failed(name, message))
            self.players[group] = player
            self.outputs[group] = output
        pcm = QAudioFormat()
        pcm.setSampleRate(24000)
        pcm.setChannelCount(1)
        pcm.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self.buffer_output = QAudioBufferOutput(pcm,self)
        self.players['voices'].setAudioBufferOutput(self.buffer_output)
        self.buffer_output.audioBufferReceived.connect(self._mouth_buffer)
        self.players['voices'].playbackStateChanged.connect(self._voice_state)
        self.players['voices'].mediaStatusChanged.connect(lambda status:
            self.stopVoice() if status==QMediaPlayer.MediaStatus.EndOfMedia else None)

    @Property(bool,notify=speakingChanged)
    def speaking(self):
        return self._speaking

    def _voice_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState and not self._muted
        if playing != self._speaking:
            self._speaking = playing
            self.speakingChanged.emit(playing)
        if not playing:
            self.mouthChanged.emit(0.0)

    @Slot(QAudioBuffer)
    def _mouth_buffer(self, buffer):
        if self._muted or not self._speaking or not buffer.isValid():
            self.mouthChanged.emit(0.0)
            return
        if buffer.format().sampleFormat()!=QAudioFormat.SampleFormat.Int16:
            self.mouthChanged.emit(0.0)
            return
        samples = array('h',bytes(buffer.constData()))
        rms = math.sqrt(sum(sample*sample for sample in samples)/max(1,len(samples)))/32768
        self.mouthChanged.emit(min(.85,max(0.0,(rms-.008)*8)))

    def playGeneratedVoice(self, data: bytes) -> bool:
        if self._muted:
            return False
        self.stopVoice()
        self._voice_buffer = QBuffer(self)
        self._voice_buffer.setData(QByteArray(data))
        self._voice_buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.players['voices'].setSourceDevice(self._voice_buffer,QUrl('speech.wav'))
        self.players['voices'].play()
        return True

    @Slot()
    def stopVoice(self):
        self.interaction_source = None
        self.players['voices'].stop()
        self.players['voices'].setSource(QUrl())
        self._voice_state(QMediaPlayer.PlaybackState.StoppedState)
        if self._voice_buffer is not None:
            self._voice_buffer.close()
            self._voice_buffer.deleteLater()
            self._voice_buffer = None

    @Property(bool, notify=mutedChanged)
    def muted(self):
        return self._muted

    @Slot(bool)
    def setMuted(self, muted: bool):
        if self._muted == muted:
            return
        self._muted = muted
        for output in self.outputs.values():
            output.setMuted(muted)
        if muted:
            self.stopAll()
        self.settings.save_muted(muted)
        self.mutedChanged.emit(muted)

    def _failed(self, group, message):
        logging.warning('Audio playback failed (%s): %s', group, message)
        self.playbackFailed.emit(group, message)

    def playInteractionVoice(self, path:Path, source:str):
        if self._muted or not path.is_file():return False
        self.stopVoice()
        self.interaction_source = source
        self.players['voices'].setSource(QUrl.fromLocalFile(str(path)))
        self.players['voices'].play()
        return True

    def stopIdleVoice(self):
        if self.interaction_source=='idle':self.stopVoice()

    def _play(self, group: str, cue: str) -> bool:
        # Missing cues are normal until the user supplies licensed audio.
        if self._muted:
            return False
        relative = self.cues[group].get(cue)
        if not relative:
            return False
        try:
            path = (self.root / relative).resolve()
            available = path.is_relative_to(self.root) and path.is_file()
        except (OSError, ValueError):
            available = False
        if not available:
            self._failed(group, f'Unavailable local audio cue: {cue}')
            return False
        player = self.players[group]
        if group=='voices':
            self.stopVoice()
        # Replace within each channel; never build an unbounded playback queue.
        player.stop()
        player.setSource(QUrl.fromLocalFile(str(path)))
        player.play()
        return True

    @Slot(str, result=bool)
    def playSound(self, cue: str) -> bool:
        return self._play('sounds', cue)

    @Slot(str, result=bool)
    def playVoice(self, cue: str) -> bool:
        return self._play('voices', cue)

    @Slot()
    def stopAll(self):
        self.stopVoice()
        self.players['sounds'].stop()
        self.players['sounds'].setSource(QUrl())
        self.allStopped.emit()
