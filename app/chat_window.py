"""Native companion bubbles, separate from the Live2D canvas and its input."""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QWidget, QDialog, QLabel, QLineEdit, QComboBox, QPushButton,
    QVBoxLayout, QHBoxLayout, QFormLayout, QDialogButtonBox, QScrollArea, QFrame,
    QPlainTextEdit, QSizePolicy)
from .chat_config import LocalChatConfig, MODELS


class ChatInput(QPlainTextEdit):
    sendRequested = Signal()

    def __init__(self):
        super().__init__()
        self._composing = False

    def inputMethodEvent(self, event):
        self._composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event):
        if (not self._composing and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.sendRequested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class ApiSettingsDialog(QDialog):
    def __init__(self, config: LocalChatConfig, parent):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle('DeepSeek API 设置')
        self.resize(400,200)
        layout = QVBoxLayout(self)
        note = QLabel('Key 仅保存在本机用户目录，不会进入桌宠网页。\n若设置了 DEEPSEEK_API_KEY 环境变量，会优先使用它。')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText('粘贴你的 DeepSeek API Key')
        stored_key = config.read().get('api_key','')
        self.key_input.setText(stored_key if isinstance(stored_key,str) else '')
        self.model_input = QComboBox()
        self.model_input.addItems(MODELS)
        self.model_input.setCurrentText(config.credentials()[1])
        form.addRow('API Key', self.key_input)
        form.addRow('模型', self.model_input)
        layout.addLayout(form)
        self.status = QLabel('留空并保存可删除本机保存的 Key。')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        try:
            self.config.save(self.key_input.text().strip(), self.model_input.currentText())
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.accept()


class ChatWindow(QWidget):
    closed = Signal()

    def __init__(self, client, parent):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.client = client
        self._role_loading = False
        self.setWindowTitle(f'Fishbowl · 和{client.character_name}聊天')
        self.resize(390,500)
        self.setMinimumSize(320,380)
        self.setStyleSheet('''
            QWidget { background: #f2f8fd; color: #173552; font-size: 14px; }
            QPushButton { background: #e0edfa; border: 1px solid #b6c9da; border-radius: 7px; padding: 7px 12px; }
            QPushButton:disabled { color: #8293a5; }
            QPlainTextEdit,QLineEdit,QComboBox { background: white; border: 1px solid #b6c9da; border-radius: 7px; padding: 6px; }
            QFrame#assistantBubble { background: white; border: 1px solid #dce8f2; border-radius: 12px; }
            QFrame#userBubble { background: #dbeeff; border: 1px solid #b9dcfa; border-radius: 12px; }
            QFrame#toolBubble { background: #eaf5ef; border: 1px solid #bfd9c9; border-radius: 10px; }
            QFrame QLabel { background: transparent; border: none; }
        ''')
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        title = QLabel(f'🐟 {client.character_name}')
        self.title_label = title
        title.setStyleSheet('font-size:18px; font-weight:600;')
        top.addWidget(title)
        top.addStretch()
        self.settings_button = QPushButton('API 设置')
        self.settings_button.clicked.connect(self.open_settings)
        self.clear_button = QPushButton('清空记忆')
        self.clear_button.clicked.connect(client.clear)
        top.addWidget(self.settings_button)
        top.addWidget(self.clear_button)
        layout.addLayout(top)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content = QWidget()
        self.messages = QVBoxLayout(self.content)
        self.messages.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.content)
        self.scroll.verticalScrollBar().rangeChanged.connect(
            lambda _minimum, maximum:self.scroll.verticalScrollBar().setValue(maximum))
        layout.addWidget(self.scroll,1)
        self.status = QLabel('本机记忆无法读取，暂时从新对话开始。' if client.memory.read_failed else
            '已恢复最近的聊天。' if client.history else '先打开「API 设置」填写 Key，再开始聊天。')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.input = ChatInput()
        self.input.setPlaceholderText(f'和{client.character_name}说点什么… Enter 发送，Shift+Enter 换行')
        self.input.setFixedHeight(76)
        self.input.sendRequested.connect(self.send)
        layout.addWidget(self.input)
        bottom = QHBoxLayout()
        note = QLabel('最近 10 轮保存在本机，可清空。')
        note.setStyleSheet('font-size:12px; color:#59738c;')
        bottom.addWidget(note)
        bottom.addStretch()
        self.cancel_button = QPushButton('取消')
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(client.cancel)
        self.send_button = QPushButton('发送')
        self.send_button.clicked.connect(self.send)
        bottom.addWidget(self.cancel_button)
        bottom.addWidget(self.send_button)
        layout.addLayout(bottom)
        self.speech_row = QWidget()
        speech_layout = QHBoxLayout(self.speech_row)
        speech_layout.setContentsMargins(0,0,0,0)
        self.speech_status = QLabel('回复完成后使用本机语音朗读。')
        self.speech_status.setWordWrap(True)
        self.speech_status.setStyleSheet('font-size:12px; color:#59738c;')
        self.stop_speech_button = QPushButton('停止朗读')
        self.stop_speech_button.setEnabled(False)
        speech_layout.addWidget(self.speech_status,1)
        speech_layout.addWidget(self.stop_speech_button)
        layout.addWidget(self.speech_row)
        self.speech_row.hide()
        self._last_text = ''
        self._stream_label = None
        self._stream_name = None
        self._stream_text = ''
        self._tool_cards = {}
        self._stream_timer = QTimer(self)
        self._stream_timer.setSingleShot(True)
        self._stream_timer.setInterval(32)
        self._stream_timer.timeout.connect(self.flush_reply)
        client.messageAdded.connect(self.complete_message)
        client.statusChanged.connect(self.status.setText)
        client.busyChanged.connect(self.set_busy)
        client.requestFailed.connect(self.failed)
        client.cleared.connect(self.clear_messages)
        client.replyUpdated.connect(self.update_reply)
        client.characterChanged.connect(self.restore_character)
        client.toolStarted.connect(self.start_tool)
        client.toolFinished.connect(self.finish_tool)
        if client.history:
            for message in client.history:
                self.restore_message(message)
        else:
            self.add_message('assistant',client.greeting)

    def restore_character(self):
        self.clear_messages()
        self._last_text = ''
        self.title_label.setText(f'🐟 {self.client.character_name}')
        self.setWindowTitle(f'Fishbowl · 和{self.client.character_name}聊天')
        self.input.setPlaceholderText(f'和{self.client.character_name}说点什么… Enter 发送，Shift+Enter 换行')
        for message in self.client.history:
            self.restore_message(message)
        if not self.client.history:self.add_message('assistant',self.client.greeting)
        self.status.setText('本机记忆无法读取，暂时从新对话开始。' if self.client.memory.read_failed else
            '已恢复这个角色最近的聊天。' if self.client.history else '可以和新伙伴聊聊了。')

    def attach_speech(self, speech):
        self.speech_row.show()
        self.stop_speech_button.clicked.connect(speech.stop)
        speech.busyChanged.connect(self.stop_speech_button.setEnabled)
        speech.statusChanged.connect(self.speech_status.setText)
        self.closed.connect(speech.stop)
        self.clear_button.clicked.connect(speech.stop)

    def send(self):
        if self._role_loading:return
        text = self.input.toPlainText()
        if self.client.send(text):
            self._last_text = text
            self.input.clear()

    def set_busy(self, busy):
        self.send_button.setEnabled(not busy and not self._role_loading)
        self.settings_button.setEnabled(not busy and not self._role_loading)
        self.cancel_button.setEnabled(busy)

    def set_character_loading(self, loading):
        self._role_loading = loading
        self.clear_button.setEnabled(not loading)
        self.set_busy(self.client.busy)

    def failed(self, _message):
        self.flush_reply()
        if self._stream_name is not None:
            self._stream_name.setText(f'{self.client.character_name} · 未完成，不计入记忆')
        self._stream_label = self._stream_name = None
        self._stream_text = ''
        for title,label in self._tool_cards.values():
            title.setText(title.text().split(' · ')[0]+' · 本轮未完成，不计入记忆')
        self._tool_cards.clear()
        if not self.input.toPlainText().strip():
            self.input.setPlainText(self._last_text)

    def add_message(self, role, text):
        if role=='user':self._tool_cards.clear()
        if role=='assistant':
            self._stream_timer.stop()
            self._stream_text = ''
        if role=='assistant' and self._stream_label is not None:
            self._stream_timer.stop()
            self._stream_label.setText(text)
            self._stream_name.setText(self.client.character_name)
            self._stream_label = self._stream_name = None
            self._stream_text = ''
            self.scroll_to_latest()
            return
        row = QWidget()
        outer = QHBoxLayout(row)
        outer.setContentsMargins(0,3,0,3)
        bubble = QFrame()
        bubble.setObjectName('userBubble' if role=='user' else 'assistantBubble')
        bubble.setMaximumWidth(320)
        inside = QVBoxLayout(bubble)
        name = QLabel('你' if role=='user' else self.client.character_name)
        name.setStyleSheet('font-size:12px; color:#59738c;')
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        inside.addWidget(name)
        inside.addWidget(label)
        if role=='user': outer.addStretch()
        outer.addWidget(bubble,1)
        if role!='user': outer.addStretch()
        self.messages.addWidget(row)
        while self.messages.count()>60:
            self.messages.takeAt(0).widget().deleteLater()
        self.scroll_to_latest()
        return label,name

    def complete_message(self, role, text):
        self.add_message(role,text)
        if role=='assistant':self._tool_cards.clear()

    def restore_message(self, message):
        for index,result in enumerate(message.get('tool_results',[])):
            identifier=f'history-{index}'
            self.start_tool(identifier,result['title'])
            self.finish_tool(identifier,result['title'],result['content'],result['ok'])
        self.add_message(message['role'],message['content'])
        self._tool_cards.clear()

    def start_tool(self, identifier, title):
        if identifier in self._tool_cards:return
        row = QWidget()
        outer = QHBoxLayout(row)
        outer.setContentsMargins(0,3,0,3)
        bubble = QFrame()
        bubble.setObjectName('toolBubble')
        bubble.setMaximumWidth(320)
        inside = QVBoxLayout(bubble)
        name = QLabel(title+' · 执行中')
        name.setTextFormat(Qt.TextFormat.PlainText)
        name.setWordWrap(True)
        name.setStyleSheet('font-size:12px; color:#32644c;')
        label = QLabel('正在查询本机工具…')
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        inside.addWidget(name)
        inside.addWidget(label)
        outer.addWidget(bubble,1)
        outer.addStretch()
        if self._stream_label is not None:
            stream_row=self._stream_label.parentWidget().parentWidget()
            self.messages.insertWidget(self.messages.indexOf(stream_row),row)
        else:self.messages.addWidget(row)
        self._tool_cards[identifier] = (name,label)
        while self.messages.count()>60:self.messages.takeAt(0).widget().deleteLater()
        self.scroll_to_latest()

    def finish_tool(self, identifier, title, content, ok):
        if identifier not in self._tool_cards:self.start_tool(identifier,title)
        name,label = self._tool_cards[identifier]
        name.setText(title+(' · 已完成' if ok else ' · 未成功'))
        label.setText(content)
        self.scroll_to_latest()

    def scroll_to_latest(self):
        QTimer.singleShot(0,lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def update_reply(self, text):
        self._stream_text = text
        if not self._stream_timer.isActive():
            self._stream_timer.start()

    def flush_reply(self):
        self._stream_timer.stop()
        if not self._stream_text:
            return
        if self._stream_label is None:
            self._stream_label,self._stream_name = self.add_message('assistant',self._stream_text)
            self._stream_name.setText(f'{self.client.character_name} · 正在说…')
        else:
            self._stream_label.setText(self._stream_text)
            self.scroll_to_latest()

    def clear_messages(self):
        self._stream_timer.stop()
        self._stream_label = self._stream_name = None
        self._stream_text = ''
        self._tool_cards.clear()
        while self.messages.count():
            self.messages.takeAt(0).widget().deleteLater()
        self.input.clear()

    def open_settings(self):
        draft = self.input.toPlainText()
        dialog = ApiSettingsDialog(self.client.config,self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.input.setPlainText(draft)
            self.status.setText('设置已保存，可以开始聊天。')

    def closeEvent(self, event):
        self.client.cancel()
        self.closed.emit()
        event.accept()
