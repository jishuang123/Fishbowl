import json
import logging
from PySide6.QtCore import QObject, QPoint, Slot, Signal, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication


class PetBridge(QObject):
    gazeChanged = Signal(float, float)
    idlePausedChanged = Signal(bool)
    rendererReported = Signal(str)
    bindingsChanged = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.anchor = None
        self.origin = QPoint()
        self.drag_count = 0
        self.menu_count = 0
        self._idle_paused = None
        self._last_gaze = None
        self.gaze_timer = QTimer(self)
        self.gaze_timer.timeout.connect(self.publish_gaze)
        self.gaze_timer.start(33)

    def publish_gaze(self):
        paused = (not self.window.isVisible() or self.window.isMinimized() or
                  QApplication.activeModalWidget() is not None or
                  (hasattr(self.window, 'menu') and self.window.menu.isVisible()))
        if paused != self._idle_paused:
            self._idle_paused = paused
            self.idlePausedChanged.emit(paused)
        if paused:
            return
        local = self.window.mapFromGlobal(QCursor.pos())
        width, height = self.window.width(), self.window.height()
        x = (local.x() - width * 0.5) / max(width * 0.7, 1)
        y = (height * 0.23 - local.y()) / max(height * 0.5, 1)
        gaze = (max(-1, min(1, x)),max(-1, min(1, y)))
        if gaze!=self._last_gaze:
            self._last_gaze = gaze
            self.gazeChanged.emit(*gaze)

    @Slot()
    def requestIdleState(self):
        self._idle_paused = None
        self._last_gaze = None
        self.publish_gaze()

    @Slot()
    def requestBindings(self):
        self.window.publish_interactions()

    @Slot(str,str)
    def triggerInteraction(self, character, trigger):
        self.window.play_interaction_voice(character,trigger)

    @Slot()
    def stopIdleVoice(self):
        self.window.audio.stopIdleVoice()

    @Slot(int, int)
    def beginDrag(self, x, y):
        self.anchor = QPoint(x, y)
        self.origin = self.window.pos()

    @Slot(int, int)
    def drag(self, x, y):
        if self.anchor is not None:
            self.window.move(self.origin + QPoint(x, y) - self.anchor)

    @Slot(int, int)
    def endDrag(self, x, y):
        if self.anchor is not None:
            self.drag(x, y)
            self.drag_count += 1
        self.anchor = None

    @Slot()
    def cancelDrag(self):
        self.anchor = None

    @Slot()
    def showMenu(self):
        self.anchor = None
        self.menu_count += 1
        self.window.menu.popup(QCursor.pos())

    @Slot(str)
    def report(self, message):
        logging.info('Renderer: %s', message)
        try:
            result = json.loads(message)
            self.rendererReported.emit(message)
            if result.get('error'):
                self.window.setToolTip(result['error'])
        except ValueError:
            logging.warning('Invalid renderer report')
