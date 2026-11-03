"""Bounded, asynchronous DeepSeek text chat. No secret or content logging."""
import json
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from .chat_config import LocalChatConfig
from .memory import ConversationMemory
from .persona import load_persona
from .streaming import ChatStream, StreamError
from .tool_registry import builtin_tools

ENDPOINT = 'https://api.deepseek.com/chat/completions'
MAX_TOOL_ROUNDS = 2
MAX_TOOL_CALLS = 4


class DeepSeekChat(QObject):
    messageAdded = Signal(str, str)
    busyChanged = Signal(bool)
    requestFailed = Signal(str)
    statusChanged = Signal(str)
    cleared = Signal()
    replyUpdated = Signal(str)
    characterChanged = Signal()
    toolStarted = Signal(str,str)
    toolFinished = Signal(str,str,str,bool)

    def __init__(self, config: LocalChatConfig, parent=None, *, endpoint=ENDPOINT, timeout_ms=45000,
                 memory: ConversationMemory | None = None, tools=None):
        super().__init__(parent)
        url = QUrl(endpoint)
        if endpoint != ENDPOINT and not (url.scheme() == 'http' and url.host() in ('127.0.0.1', 'localhost')):
            raise ValueError('Only the official endpoint or a local test server is allowed')
        self.config = config
        self.character_name = '大肥鱼'
        self.greeting = '我在这儿，慢慢聊。今天想说点什么？'
        self.persona_path = None
        self.endpoint = endpoint
        self.timeout_ms = timeout_ms
        self.manager = QNetworkAccessManager(self)
        self.manager.setRedirectPolicy(QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self._abort('请求超时，请稍后重试。'))
        self.reply = None
        self._active = False
        self._turn = 0
        self.tools = tools if tools is not None else builtin_tools()
        self.memory = memory if memory is not None else ConversationMemory(config.path.with_name('chat-memory.json'))
        self.history = self.memory.load()
        self._pending = ''
        self._stream = ChatStream()
        self._stream_started = False
        self._abort_reason = ''
        self._messages = []
        self._tool_results = []
        self._seen_call_ids = set()
        self._tool_rounds = 0
        self._prefix = ''
        self._key = self._model = ''

    @property
    def busy(self):
        return self._active

    def set_character(self, character, memory_path):
        self.cancel()
        self.character_name = character.name
        self.greeting = character.data.get('welcome',f'你好，我是{character.name}。')
        self.persona_path = character.persona
        self.memory = ConversationMemory(memory_path)
        self.history = self.memory.load()
        self.characterChanged.emit()

    def send(self, text: str) -> bool:
        text = text.strip()
        if self.busy:
            return False
        if not text or len(text) > 2000:
            self.statusChanged.emit('请输入 1–2000 个字符。')
            return False
        key, model = self.config.credentials()
        if not key or any(c.isspace() for c in key):
            self.statusChanged.emit('请先打开「API 设置」填写有效的 API Key。')
            return False
        self._turn += 1
        self._active = True
        self._pending, self._abort_reason = text, ''
        self._key, self._model = key, model
        self._tool_rounds = 0
        self._tool_results = []
        self._seen_call_ids = set()
        self._prefix = ''
        # Only plain dialogue from previous turns goes back to the API. Tool
        # protocol messages belong exclusively to the current tool round.
        self._messages = [{'role':'system','content':load_persona(self.persona_path)},
            *[{'role':m['role'],'content':m['content']} for m in self.history[-20:]],
            {'role':'user','content':text}]
        self.timer.start(self.timeout_ms)  # One total deadline, across every hop.
        self._post()
        self.messageAdded.emit('user', text)
        self.busyChanged.emit(True)
        self.statusChanged.emit(f'{self.character_name}正在想…')
        return True

    def _post(self):
        request = QNetworkRequest(QUrl(self.endpoint))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, 'application/json')
        request.setRawHeader(b'Authorization', b'Bearer '+self._key.encode('utf-8'))
        request.setTransferTimeout(self.timeout_ms)
        payload = {'model':self._model, 'messages':self._messages,
                   'stream':True, 'thinking':{'type':'disabled'}, 'max_tokens':512}
        schemas = self.tools.schemas()
        if schemas:
            payload['tools'] = schemas
            payload['tool_choice'] = 'auto' if self._tool_rounds<MAX_TOOL_ROUNDS else 'none'
        request.setRawHeader(b'Accept',b'text/event-stream')
        self._stream, self._stream_started = ChatStream(), False
        reply = self.manager.post(request, json.dumps(payload,ensure_ascii=False).encode('utf-8'))
        self.reply = reply
        reply.setReadBufferSize(1024*1024)
        reply.readyRead.connect(lambda: self._read(reply))
        reply.finished.connect(lambda: self._finished(reply))

    def _read(self, reply):
        if reply is not self.reply:
            return
        data = bytes(reply.readAll())
        if self._abort_reason or reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)!=200:
            return
        try:
            updates = self._stream.feed(data)
        except StreamError as error:
            self._abort_reason = str(error)
            if reply.isRunning():
                reply.abort()
            return
        if updates:
            if len(self._prefix)+len(updates[-1])>16000:
                self._abort('回复过长，请缩短问题后重试。')
                return
            if not self._stream_started:
                self._stream_started = True
                self.statusChanged.emit(f'{self.character_name}正在说…')
            if reply is self.reply and self.busy:self.replyUpdated.emit(self._prefix+updates[-1])

    def _abort(self, reason):
        if not self.busy:return
        self._abort_reason = reason
        if self.reply is not None:
            self.reply.abort()
        else:
            self._end_error(reason)

    def cancel(self):
        self._abort('本次请求已取消。')

    def clear(self):
        self.cancel()
        if not self.memory.save([]):
            self.statusChanged.emit('无法清空本机记忆，请检查用户目录权限后重试。')
            return
        self.history.clear()
        self.cleared.emit()
        self.statusChanged.emit('已清空本机记忆，可以重新聊了。')

    def _finished(self, reply):
        if reply is not self.reply:
            reply.deleteLater()
            return
        self._read(reply)
        if reply is not self.reply:return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0
        error = self._abort_reason
        if not error and reply.error() == QNetworkReply.NetworkError.TimeoutError:
            error = '请求超时，请稍后重试。'
        stream = self._stream
        if not error and status != 200:
            error = {401:'API Key 无效或已失效，请检查 API 设置。',
                     402:'DeepSeek 账户余额不足。', 429:'请求过于频繁，请稍后重试。',
                     500:'DeepSeek 服务暂时异常，请稍后重试。',
                     503:'DeepSeek 服务繁忙，请稍后重试。'}.get(status,
                     '网络或服务请求失败，请检查网络与 API 设置。')
        if not error and reply.error() != QNetworkReply.NetworkError.NoError:
            error = '网络连接中断，请稍后重试。'
        if not error:
            if not self._stream.complete:
                error = '回复未完整接收，请重试；未完成内容不会保存到记忆。'
        self.reply = None
        reply.deleteLater()
        if error:
            self._end_error(error)
            return
        calls = stream.tool_calls
        if calls:
            identifiers = {call['id'] for call in calls}
            if (self._tool_rounds>=MAX_TOOL_ROUNDS or len(self._seen_call_ids)+len(calls)>MAX_TOOL_CALLS or
                    identifiers & self._seen_call_ids):
                self._end_error('本次工具调用已达到上限，请重新提问。')
                return
            self._seen_call_ids.update(identifiers)
            self._tool_rounds += 1
            if stream.text:self._prefix += stream.text+'\n\n'
            self._messages.append({'role':'assistant','content':stream.text or None,'tool_calls':calls})
            turn = self._turn
            QTimer.singleShot(0,lambda:self._execute_tools(turn,calls))
            return
        content = self._prefix+stream.text
        if len(content)>16000:
            self._end_error('回复过长，请缩短问题后重试。')
            return
        assistant = {'role':'assistant','content':content}
        if self._tool_results:assistant['tool_results'] = self._tool_results[:]
        self.history.extend([{'role':'user','content':self._pending},assistant])
        self.history = self.history[-20:]
        saved = self.memory.save(self.history)
        truncated = stream.finish_reason=='length'
        self._reset_turn()
        self.messageAdded.emit('assistant', content)
        self.statusChanged.emit('回复已显示，但无法保存本机记忆；当前只在本次运行中保留。' if not saved else
            '回复达到长度上限，可继续追问。' if truncated else '已记住最近的聊天，可以继续聊。')
        self.busyChanged.emit(False)

    def _execute_tools(self, turn, calls):
        for call in calls:
            if not self.busy or turn!=self._turn:return
            name = call['function']['name']
            title = self.tools.title(name)
            self.statusChanged.emit('正在'+title+'…')
            if not self.busy or turn!=self._turn:return
            self.toolStarted.emit(call['id'],title)
            if not self.busy or turn!=self._turn:return
            result = self.tools.execute(name,call['function']['arguments'])
            if not self.busy or turn!=self._turn:return
            self._messages.append({'role':'tool','tool_call_id':call['id'],
                                   'content':json.dumps(result,ensure_ascii=False)})
            self._tool_results.append({'name':name if name in self.tools.plugins else 'unknown',
                'title':title,'content':result['display'],'ok':result['ok']})
            self.toolFinished.emit(call['id'],title,result['display'],result['ok'])
        if not self.busy or turn!=self._turn:return
        self.statusChanged.emit(f'工具结果已返回，{self.character_name}继续说…')
        if self.busy and turn==self._turn:self._post()

    def _reset_turn(self):
        self.timer.stop()
        self._active = False
        self._turn += 1
        self._pending = self._abort_reason = self._prefix = ''
        self._key = self._model = ''
        self._messages = []
        self._tool_results = []
        self._seen_call_ids = set()

    def _end_error(self, message):
        self._reset_turn()
        # No raw API error bodies, tool arguments, exceptions, or secrets in UI/logs.
        self.requestFailed.emit(message)
        self.statusChanged.emit(message)
        self.busyChanged.emit(False)
