import logging
import json
import threading
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QActionGroup
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QFileDialog
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from .bridge import PetBridge
from .audio import PetAudio
from .config import UserSettings
from .chat_config import LocalChatConfig
from .chat import DeepSeekChat
from .chat_window import ChatWindow
from .speech import SpeechController
from .characters import CharacterRegistry
from .memory import ConversationMemory
from .interaction_config import InteractionConfig,TRIGGERS
from .interaction_window import InteractionDialog


class PetPage(QWebEnginePage):
    def __init__(self, origin, parent):
        super().__init__(parent)
        self.origin = QUrl(origin)

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        return (url.scheme(), url.host(), url.port()) == (
            self.origin.scheme(), self.origin.host(), self.origin.port())

    def javaScriptConsoleMessage(self, level, message, line, source):
        logging.info('JS %s %s:%s %s', level.name, source, line, message)


class PetWindow(QWebEngineView):
    imported = Signal(str)
    importFailed = Signal(str)

    def __init__(self, url: str, *, settings_path: Path | None = None, audio_root: Path | None = None,
                 chat_client: DeepSeekChat | None = None, characters: CharacterRegistry | None = None):
        super().__init__()
        self.setWindowTitle('Fishbowl · 大肥鱼入缸')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet('background: transparent;')
        self.resize(400, 640)
        available = QApplication.primaryScreen().availableGeometry()
        self.move(available.right() - self.width() - 24, available.bottom() - self.height() - 16)
        page = PetPage(url, self)
        page.setBackgroundColor(QColor(Qt.GlobalColor.transparent))
        page.setAudioMuted(True)
        page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, False)
        page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        self.setPage(page)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.channel = QWebChannel(page)
        settings = UserSettings(settings_path)
        self.settings = settings
        self.characters = characters if characters is not None else CharacterRegistry(settings.path.parent)
        selected=settings.data.get('character_id','deepseek')
        self.character_id=selected if isinstance(selected,str) and selected in self.characters.characters else 'deepseek'
        self._previous_character = None
        self._drafts = {}
        self._base_url = url
        self._closing = threading.Event()
        self._importing = False
        self._switch_timer = QTimer(self)
        self._switch_timer.setSingleShot(True)
        self._switch_timer.timeout.connect(lambda:self._role_failed('角色加载超时。'))
        self.chat_client = chat_client if chat_client is not None else DeepSeekChat(
            LocalChatConfig(settings.path.parent / 'deepseek.json'), self,
            memory=ConversationMemory(self.characters.memory_path(self.character_id)))
        if chat_client is None or characters is not None:
            role=self.characters.get(self.character_id)
            self.chat_client.set_character(role,self.characters.memory_path(self.character_id))
        self.chat_window = ChatWindow(self.chat_client, self)
        self.audio = PetAudio(audio_root if audio_root is not None else
                              Path(__file__).resolve().parents[1] / 'assets/audio',
                              settings, self)
        self.channel.registerObject('audio', self.audio)
        self.speech = SpeechController(self.audio,self.chat_client,self)
        self.chat_window.attach_speech(self.speech)
        self.bridge = PetBridge(self)
        self.bridge.rendererReported.connect(self._renderer_report)
        self.channel.registerObject('pet', self.bridge)
        page.setWebChannel(self.channel)
        self.menu = QMenu(self)
        # The pet view's transparent background must not make its menu transparent.
        self.menu.setStyleSheet('''
            QMenu { background: #f7fbff; color: #173552; border: 1px solid #b6c9da; padding: 5px; }
            QMenu::item { padding: 7px 18px 7px 24px; }
            QMenu::item:selected { background: #d8ecff; }
        ''')
        self.show_action = self.menu.addAction('显示角色', self.showNormal)
        self.chat_action = self.menu.addAction('和大肥鱼聊天…', self.show_chat)
        self.character_menu = self.menu.addMenu('切换角色')
        self._character_actions = None
        self._refresh_characters()
        self.interaction_action = self.menu.addAction('角色互动设置…',self.show_interaction_settings)
        self.mute_action = QAction('静音', self)
        self.mute_action.setCheckable(True)
        self.mute_action.setChecked(self.audio.muted)
        self.mute_action.toggled.connect(self.audio.setMuted)
        self.audio.mutedChanged.connect(self.mute_action.setChecked)
        self.menu.addAction(self.mute_action)
        self.menu.addSeparator()
        self.exit_action = QAction('退出 Fishbowl', self)
        self.exit_action.triggered.connect(QApplication.instance().quit)
        self.menu.addAction(self.exit_action)
        icon = QIcon(str(Path(__file__).resolve().parents[1] / 'assets/icons/fish.svg'))
        self.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip('Fishbowl · 大肥鱼（右键退出）')
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(lambda reason: self.showNormal() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.renderProcessTerminated.connect(self._render_process_stopped)
        QApplication.instance().aboutToQuit.connect(self.audio.stopAll)
        QApplication.instance().aboutToQuit.connect(self.chat_client.cancel)
        QApplication.instance().aboutToQuit.connect(self.speech.stop)
        self.imported.connect(self._imported)
        self.importFailed.connect(self._import_failed)
        self._update_character_labels()
        self.chat_window.set_character_loading(True)
        if self.character_id != 'deepseek':
            self._previous_character = 'deepseek'
        self._switch_timer.start(45000)
        self._refresh_characters()
        self.load(self._character_url(self.character_id))

    def _character_url(self, identifier):
        url=QUrl(self._base_url)
        url.setQuery('character='+identifier)
        return url

    def _update_character_labels(self):
        name=self.characters.get(self.character_id).name
        self.setWindowTitle(f'Fishbowl · {name}')
        self.chat_action.setText(f'和{name}聊天…')
        if hasattr(self,'tray'):self.tray.setToolTip(f'Fishbowl · {name}（右键退出）')

    def _refresh_characters(self):
        if hasattr(self,'interaction_action'):
            self.interaction_action.setEnabled(not self._importing and not self._switch_timer.isActive())
        self.character_menu.clear()
        if self._character_actions is not None:self._character_actions.deleteLater()
        self._character_actions=QActionGroup(self)
        for role in self.characters.characters.values():
            action=self.character_menu.addAction(role.name)
            action.setCheckable(True)
            action.setChecked(role.id==self.character_id)
            action.setData(role.id)
            action.setEnabled(not self._importing and not self._switch_timer.isActive())
            action.triggered.connect(lambda _checked=False,identifier=role.id:self.switch_character(identifier))
            self._character_actions.addAction(action)
        self.character_menu.addSeparator()
        self.import_action=self.character_menu.addAction('导入 Live2D 模型…',self.choose_model)
        self.import_action.setEnabled(not self._importing and not self._switch_timer.isActive())

    def switch_character(self, identifier):
        if identifier==self.character_id or self._switch_timer.isActive() or self._importing:
            self._refresh_characters()
            return False
        if identifier not in self.characters.characters:return False
        self._previous_character=self.character_id
        self._switch_timer.start(45000)
        self._activate_character(identifier)
        return True

    def _activate_character(self, identifier):
        draft=self.chat_window.input.toPlainText()
        if not draft and self.chat_client.busy:draft=self.chat_window._last_text
        self._drafts[self.character_id]=draft
        self.chat_window.set_character_loading(True)
        self.speech.stop()
        self.audio.stopAll()
        self.bridge.cancelDrag()
        self.character_id=identifier
        self.chat_client.set_character(self.characters.get(identifier),self.characters.memory_path(identifier))
        self.chat_window.input.setPlainText(self._drafts.get(identifier,''))
        self.chat_window.status.setText('正在载入角色…')
        self._update_character_labels()
        self._refresh_characters()
        self.load(self._character_url(identifier))

    def _renderer_report(self, message):
        value=json.loads(message)
        if not isinstance(value,dict) or value.get('character',self.character_id)!=self.character_id:return
        if value.get('ready'):
            self._switch_timer.stop()
            self._previous_character=None
            self.chat_window.set_character_loading(False)
            self._refresh_characters()
            if self.chat_window.status.text()=='正在载入角色…':
                self.chat_window.status.setText('本机记忆无法读取，暂时从新对话开始。' if self.chat_client.memory.read_failed else
                    '已恢复这个角色最近的聊天。' if self.chat_client.history else '可以和新伙伴聊聊了。')
            self.settings.save_character(self.character_id)
        elif value.get('error'):
            self._role_failed('角色无法渲染。')

    def _render_process_stopped(self, status, code):
        logging.error('Renderer stopped: %s %s',status,code)
        if self._previous_character is not None:self._role_failed('角色渲染意外停止。')

    def _role_failed(self, message):
        self._switch_timer.stop()
        previous,self._previous_character=self._previous_character,None
        if previous is not None:
            self._switch_timer.start(45000)
            self._activate_character(previous)
            self.chat_window.status.setText(message+' 已返回之前的角色。')
            self.tray.showMessage('Fishbowl',message+' 已返回之前的角色。')
        else:
            self.chat_window.set_character_loading(False)
            self.chat_window.status.setText(message+' 请尝试切换其他角色。')
            self._refresh_characters()

    def choose_model(self):
        if self._importing or self._switch_timer.isActive():return
        path,_=QFileDialog.getOpenFileName(self,'导入 Live2D 模型','','Live2D 模型 (*.model3.json)')
        if path:self.import_model(Path(path))

    def import_model(self, entry):
        if self._importing or self._switch_timer.isActive():return False
        self._importing=True
        self._refresh_characters()
        def work():
            try:
                role=self.characters.import_model(entry,self._closing)
                if not self._closing.is_set():self.imported.emit(role.id)
            except (OSError,ValueError) as error:
                if not self._closing.is_set():self.importFailed.emit(str(error) if isinstance(error,ValueError) else '无法导入，请检查目录权限。')
        threading.Thread(target=work,daemon=True).start()
        return True

    def _imported(self, identifier):
        self._importing=False
        self._refresh_characters()
        self.switch_character(identifier)

    def _import_failed(self, message):
        self._importing=False
        self._refresh_characters()
        self.tray.showMessage('Fishbowl',message)

    def show_interaction_settings(self):
        if self._switch_timer.isActive() or self._importing:return
        dialog = InteractionDialog(InteractionConfig(self.characters,self.character_id),self)
        dialog.saved.connect(self.publish_interactions)
        dialog.exec()
        self.bridge.requestIdleState()

    def publish_interactions(self):
        if self.audio.interaction_source is not None:self.audio.stopVoice()
        value = {'character':self.character_id,'bindings':InteractionConfig(self.characters,self.character_id).public()}
        self.bridge.bindingsChanged.emit(json.dumps(value,ensure_ascii=False))

    def play_interaction_voice(self, character, trigger):
        if character!=self.character_id or trigger not in TRIGGERS or self._switch_timer.isActive():return
        if self.audio.muted or self.chat_client.busy or QApplication.activeModalWidget() is not None:return
        # Chat synthesis/playback takes priority; never replace a reply with a click cue.
        if self.audio.interaction_source is None and self.speech.busy:return
        if trigger=='idle' and (self.audio.speaking or not self.isVisible() or self.menu.isVisible()):return
        config = InteractionConfig(self.characters,character)
        if config.load()[trigger]['mode']!='custom':return
        path = config.voice_path(trigger)
        if path is not None:self.audio.playInteractionVoice(path,'idle' if trigger=='idle' else 'manual')

    def show_chat(self):
        if not self.chat_window.isVisible():
            screen = self.screen().availableGeometry()
            width, height = self.chat_window.width(), self.chat_window.height()
            x = self.x()-width-12
            if x < screen.left():
                x = self.x()+self.width()+12
            x = max(screen.left(),min(x,screen.right()-width+1))
            y = max(screen.top(),min(self.y(),screen.bottom()-height+1))
            self.chat_window.move(x,y)
        self.chat_window.show()
        self.chat_window.raise_()
        self.chat_window.activateWindow()
        self.chat_window.input.setFocus()

    def closeEvent(self, event):
        self._closing.set()
        self._switch_timer.stop()
        self.speech.stop()
        self.chat_client.cancel()
        self.chat_window.hide()
        self.audio.stopAll()
        self.tray.hide()
        event.accept()
        QApplication.instance().quit()
