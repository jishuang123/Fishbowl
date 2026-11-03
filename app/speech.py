"""Offline Windows speech generation; no text/files/credentials on the command line."""
import base64
import json
import io
import os
import re
import wave
from pathlib import Path
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal


def spoken_text(text):
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[`#*_~]', '', text)
    return text.strip()[:3000]


class SpeechController(QObject):
    statusChanged = Signal(str)
    busyChanged = Signal(bool)
    synthesized = Signal(bytes)

    def __init__(self, audio, chat, parent=None):
        super().__init__(parent)
        self.audio = audio
        self.job = None
        self._busy = False
        self.voice_name = ''
        self._loading = False
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._timed_out)
        chat.messageAdded.connect(self._message)
        chat.requestFailed.connect(lambda _message:self.stop())
        chat.cleared.connect(self.stop)
        audio.mutedChanged.connect(lambda muted:self.stop() if muted else None)
        audio.speakingChanged.connect(self._playing)
        audio.allStopped.connect(self.stop)
        audio.playbackFailed.connect(self._playback_failed)

    @property
    def busy(self):
        return self._busy

    def _set_busy(self, busy):
        if busy != self._busy:
            self._busy = busy
            self.busyChanged.emit(busy)

    def _message(self, role, text):
        if role == 'user':
            self.stop()
        elif role == 'assistant':
            self.speak(text)

    def speak(self, text):
        self.stop()
        if self.audio.muted:
            self.statusChanged.emit('已静音，本条回复不朗读。')
            return
        text = spoken_text(text)
        if not text:
            self.statusChanged.emit('这条回复没有需要朗读的文字。')
            return
        if os.name != 'nt':
            self.statusChanged.emit('本机语音仅支持 Windows，文字聊天可继续。')
            return
        try:
            script = Path(__file__).with_name('synthesize.ps1').read_text(encoding='utf-8')
        except OSError:
            self.statusChanged.emit('本机语音组件缺失，文字聊天可继续。')
            return
        process = QProcess(self)
        environment = QProcessEnvironment.systemEnvironment()
        environment.remove('DEEPSEEK_API_KEY')
        process.setProcessEnvironment(environment)
        process.setProgram(str(Path(os.environ.get('SystemRoot','C:/Windows')) /
                               'System32/WindowsPowerShell/v1.0/powershell.exe'))
        # Encode static program text only. Chat content is exclusively stdin JSON.
        process.setArguments(['-NoProfile','-NonInteractive','-WindowStyle','Hidden','-EncodedCommand',
                              base64.b64encode(script.encode('utf-16-le')).decode('ascii')])
        job = {'process':process,'output':bytearray()}
        self.job = job
        process.started.connect(lambda:self._write(job,text))
        process.readyReadStandardOutput.connect(lambda:self._read(job))
        process.readyReadStandardError.connect(lambda:process.readAllStandardError())
        process.finished.connect(lambda code,_status:self._finished(job,code))
        process.errorOccurred.connect(lambda _error:self._failed(job))
        self._set_busy(True)
        self.statusChanged.emit('正在准备本机语音…')
        self.timeout.start(30000)
        process.start()

    def _write(self, job, text):
        if job is not self.job:
            return
        process = job['process']
        process.write(json.dumps({'text':text},ensure_ascii=False).encode('utf-8'))
        process.closeWriteChannel()

    def _read(self, job):
        data = bytes(job['process'].readAllStandardOutput())
        if job is not self.job:
            return
        job['output'].extend(data)
        if len(job['output'])>48*1024*1024:
            self._failed(job)

    def _finished(self, job, code):
        self._read(job)
        if job is not self.job:
            job['process'].deleteLater()
            return
        self.timeout.stop()
        self.job = None
        try:
            value = json.loads(job['output'])
            if code != 0 or 'pcm' not in value:
                raise ValueError()
            pcm = base64.b64decode(value['pcm'],validate=True)
            if not pcm or len(pcm)>32*1024*1024 or len(pcm)%2:
                raise ValueError()
            output = io.BytesIO()
            with wave.open(output,'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(pcm)
            data = output.getvalue()
            self.voice_name = str(value.get('voice',''))
        except (ValueError,KeyError,TypeError):
            self._set_busy(False)
            self.statusChanged.emit('本机语音不可用，请检查是否安装中文系统声音；文字聊天可继续。')
        else:
            if self.audio.muted:
                self._set_busy(False)
            else:
                self._loading = True
                self.timeout.start(15000)
                if self.audio.playGeneratedVoice(data):
                    self.synthesized.emit(data)
                else:
                    self._loading = False
                    self.timeout.stop()
                    self._set_busy(False)
        finally:
            job['process'].deleteLater()

    def _failed(self, job):
        if job is self.job:
            self.stop()
            self.statusChanged.emit('本机语音生成失败，文字聊天可继续。')
        if job['process'].state()==QProcess.ProcessState.NotRunning:
            job['process'].deleteLater()

    def _timed_out(self):
        self.stop()
        self.statusChanged.emit('本机语音生成超时，文字聊天可继续。')

    def _playing(self, playing):
        if playing:
            self._loading = False
            self.timeout.stop()
            self._set_busy(True)
            self.statusChanged.emit('正在朗读 · 可随时停止或静音')
        elif self.job is None and not self._loading:
            self._set_busy(False)
            self.statusChanged.emit('朗读已结束。')

    def _playback_failed(self, group, _message):
        if group=='voices':
            self.stop()
            self.statusChanged.emit('语音播放失败，文字聊天可继续。')

    def stop(self):
        self.timeout.stop()
        self._loading = False
        job, self.job = self.job, None
        if job is not None:
            job['process'].kill()
        self.audio.stopVoice()
        self._set_busy(False)
        self.statusChanged.emit('朗读已停止。')
