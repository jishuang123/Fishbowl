"""Windows acceptance check using real WebEngine and Qt mouse events.

Temporarily moves the pointer over test windows, then restores it.
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QTimer, Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QWidget
from app.pet_window import PetWindow
from app.server import RendererServer

parser = argparse.ArgumentParser()
parser.add_argument('--exit-via', choices=['menu', 'tray'], default='menu')
args = parser.parse_args()
out = ROOT / '.local/evidence'
out.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=out / f'desktop-{args.exit_via}.log', level=logging.INFO,
                    format='%(levelname)s %(message)s', encoding='utf-8', filemode='w')
app = QApplication([])
server = RendererServer(ROOT / 'frontend/dist')
back = QWidget()
back.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
back.setStyleSheet('background: #ee25be;')
back.setGeometry(80, 50, 740, 820)
back.show()
settings_path = out / f'desktop-{args.exit_via}-settings.json'
settings_path.write_text('{"audio":{"muted":false}}', encoding='utf-8')
window = PetWindow(server.url, settings_path=settings_path)
window.move(180, 100)
window.show()
original_cursor = QCursor.pos()
result = {'exitVia': args.exit_via}
started = time.monotonic()
ready_time = None
stage = 'load'
failure = None
expected_exit = False


def fail(error):
    global failure
    failure = str(error)
    result['failure'] = failure
    app.quit()


def poll():
    if time.monotonic() - started > 90:
        fail('Desktop verification timed out')
        return
    window.page().runJavaScript('JSON.stringify(window.fishbowl?.snapshot())', 0, receive)


def receive(raw):
    global ready_time, stage
    try:
        if not raw:
            return
        data = json.loads(raw)
        if data.get('errors'):
            raise AssertionError(data['errors'])
        if not data.get('ready'):
            return
        if ready_time is None:
            ready_time = time.monotonic()
        if stage == 'gaze-right':
            view = data['interaction']
            if view['gaze']['x'] > .9 and view['values']['ParamEyeBallX'] > .5 and view['values']['ParamAngleX'] > 5:
                result['outsideWindowRight'] = view
                stage = 'gaze-left'
                QCursor.setPos(window.mapToGlobal(QPoint(-100,150)))
            return
        if stage == 'gaze-left':
            view = data['interaction']
            if view['gaze']['x'] < -.9 and view['values']['ParamEyeBallX'] < -.5 and view['values']['ParamAngleX'] < -5:
                result['outsideWindowLeft'] = view
                result['startPosition'] = [window.x(), window.y()]
                stage = 'hidden'
                window.hide()
                QTimer.singleShot(300, lambda: window.page().runJavaScript(
                    'JSON.stringify(window.fishbowl.snapshot().interaction.idle)', 0, check_hidden))
            return
        if stage == 'load' and time.monotonic() - ready_time > 14:
            result['renderer'] = data
            assert data['textures'] == 5 and data['glError'] == 0 and not data['contextLost']
            assert data['cornerPixel'][3] == 0, data['cornerPixel']
            for key in ['ParamEyeLOpen', 'ParamEyeROpen', 'ParamBreath']:
                lo, hi = data['ranges'][key]
                assert hi - lo > 0.5, (key, lo, hi)
            rect = window.frameGeometry()
            back.raise_()
            window.raise_()
            QTest.qWait(200)
            shot = window.screen().grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())
            shot.save(str(out / f'desktop-{args.exit_via}.png'))
            image = shot.toImage()
            corner = image.pixelColor(2, 2)
            assert abs(corner.red()-238) < 4 and abs(corner.green()-37) < 4 and abs(corner.blue()-190) < 4, corner.name()
            # The visible character must contribute pixels over the contrasting backdrop.
            colors = [image.pixelColor(x, y).name() for x in range(80, 320, 40) for y in range(100, 580, 40)]
            assert len(set(colors)) > 10
            result['transparency'] = {'framebufferCornerAlpha': data['cornerPixel'][3], 'compositedCorner': corner.name()}
            stage = 'gaze-right'
            QCursor.setPos(window.mapToGlobal(QPoint(window.width()+100,150)))
    except Exception as error:
        fail(repr(error))


def check_hidden(raw):
    try:
        assert json.loads(raw)['paused'], 'Hidden window did not pause idle interactions'
        result['idlePausedWhenHidden'] = True
        window.show()
        QTimer.singleShot(400, lambda: window.page().runJavaScript(
            'JSON.stringify(window.fishbowl.snapshot().interaction.idle)', 0, check_shown))
    except Exception as error:
        fail(repr(error))


def check_shown(raw):
    global stage
    try:
        assert not json.loads(raw)['paused'], 'Idle did not resume when the window was shown'
        result['idleResumedWhenShown'] = True
        stage = 'drag'
        begin_drag()
    except Exception as error:
        fail(repr(error))


def begin_drag():
    QTest.mousePress(window.focusProxy(), Qt.MouseButton.LeftButton, pos=QPoint(200,320))
    QTimer.singleShot(300, move_drag)


def move_drag():
    if window.bridge.anchor is not None:
        fail('A stationary press incorrectly started dragging')
        return
    result['dragOrigin'] = [window.x(), window.y()]
    QTest.mouseMove(window.focusProxy(), QPoint(265,355))
    QTimer.singleShot(350, release_drag)


def release_drag():
    end = [window.x(), window.y()]
    result['endPosition'] = end
    expected = [result['dragOrigin'][0]+65, result['dragOrigin'][1]+35]
    if not all(abs(end[i]-expected[i]) <= 2 for i in range(2)):
        fail(f'Drag moved to {end}, expected {expected}')
        return
    QTest.mouseRelease(window.focusProxy(), Qt.MouseButton.LeftButton, pos=QPoint(200,320))
    QTimer.singleShot(500, check_drag)


def check_drag():
    try:
        assert window.bridge.drag_count > 0
        window.page().runJavaScript('JSON.stringify(window.fishbowl.snapshot().interaction)', 0, click_after_drag)
    except Exception as error:
        fail(repr(error))


def click_after_drag(raw):
    try:
        assert json.loads(raw)['history'] == [], 'Dragging triggered a reaction'
        QTest.mouseClick(window.focusProxy(), Qt.MouseButton.LeftButton, pos=QPoint(200,125))
        QTimer.singleShot(700, lambda: window.page().runJavaScript(
            'JSON.stringify(window.fishbowl.snapshot().interaction)', 0, check_click))
    except Exception as error:
        fail(repr(error))


def check_click(raw):
    try:
        view = json.loads(raw)
        assert view['history'] == ['Blush'] and view['values']['key7'] > .6, view
        result['desktopClick'] = view
        window.grab().save(str(out / f'desktop-{args.exit_via}-click.png'))
        QTest.mouseClick(window.focusProxy(), Qt.MouseButton.RightButton, pos=QPoint(200,320))
        QTimer.singleShot(700, check_menu)
    except Exception as error:
        fail(repr(error))


def check_menu():
    window.page().runJavaScript('JSON.stringify(window.fishbowl.snapshot().interaction.idle)', 0, check_menu_paused)


def check_menu_paused(raw):
    try:
        assert window.menu.isVisible() and window.bridge.menu_count > 0
        assert json.loads(raw)['paused'], 'Desktop menu did not pause idle interactions'
        result['idlePausedByMenu'] = True
        action_rect = window.menu.actionGeometry(window.mute_action)
        QTest.mouseClick(window.menu, Qt.MouseButton.LeftButton, pos=action_rect.center())
        QTimer.singleShot(250, check_mute)
    except Exception as error:
        fail(repr(error))


def check_mute():
    try:
        assert window.audio.muted and window.mute_action.isChecked()
        assert json.loads(settings_path.read_text(encoding='utf-8'))['audio']['muted'] is True
        result['muteMenuToggled'] = True
        window.tray.contextMenu().popup(window.mapToGlobal(QPoint(180,300)))
        QTimer.singleShot(250, check_shared_mute)
    except Exception as error:
        fail(repr(error))


def check_shared_mute():
    global expected_exit
    try:
        assert window.tray.contextMenu() is window.menu and window.mute_action.isChecked()
        capture_menu('muted')
        # Toggle back before continuing, then verify that dragging/clicking still work.
        QTest.mouseClick(window.menu, Qt.MouseButton.LeftButton,
                         pos=window.menu.actionGeometry(window.mute_action).center())
        assert not window.audio.muted
        result['sharedTrayMuteToggled'] = True
        result['afterMuteDragOrigin'] = [window.x(), window.y()]
        QTimer.singleShot(250, begin_after_mute_drag)
    except Exception as error:
        fail(repr(error))


def begin_after_mute_drag():
    QTest.mousePress(window.focusProxy(), Qt.MouseButton.LeftButton, pos=QPoint(200,320))
    QTest.mouseMove(window.focusProxy(), QPoint(225,335))
    QTimer.singleShot(250, finish_after_mute_drag)


def finish_after_mute_drag():
    try:
        assert [window.x(),window.y()] == [result['afterMuteDragOrigin'][0]+25, result['afterMuteDragOrigin'][1]+15]
        result['afterMuteDragEnd'] = [window.x(),window.y()]
        QTest.mouseRelease(window.focusProxy(), Qt.MouseButton.LeftButton, pos=QPoint(200,320))
        QTimer.singleShot(250, click_after_mute)
    except Exception as error:
        fail(repr(error))


def click_after_mute():
    QTest.mouseClick(window.focusProxy(), Qt.MouseButton.LeftButton, pos=QPoint(200,125))
    QTimer.singleShot(600, lambda: window.page().runJavaScript(
        'JSON.stringify(window.fishbowl.snapshot().interaction)', 0, finish_after_mute_click))


def finish_after_mute_click(raw):
    try:
        view = json.loads(raw)
        assert view['history'] == ['Blush','Hearts'] and view['values']['key4'] > .6, view
        result['clickAndDragAfterMute'] = True
        QTest.mouseClick(window.focusProxy(), Qt.MouseButton.RightButton, pos=QPoint(200,320))
        QTimer.singleShot(300, finish_menu)
    except Exception as error:
        fail(repr(error))


def finish_menu():
    window.page().runJavaScript("""(() => {
      const audio=window.fishbowl.audio;
      window.audioCheck={};
      audio.playSound('unmapped', value => window.audioCheck.sound=value);
      audio.playVoice('unmapped', value => window.audioCheck.voice=value);
      audio.setMuted(true);
    })()""")
    QTimer.singleShot(400, lambda: window.page().runJavaScript(
        'JSON.stringify(window.audioCheck)', 0, finish_audio_bridge))


def finish_audio_bridge(raw):
    global expected_exit
    try:
        assert json.loads(raw) == {'sound':False, 'voice':False}
        assert window.audio.muted and window.mute_action.isChecked()
        result['audioWebChannelVerified'] = True
        capture_menu('menu')
        result['contextMenu'] = True
        result['trayAvailable'] = window.tray.isSystemTrayAvailable()
        result['trayVisible'] = window.tray.isVisible()
        expected_exit = True
        if args.exit_via == 'tray':
            window.menu.hide()
            # Invoke the actual tray menu action; OS tray overflow placement is not automated.
            assert window.tray.contextMenu() is window.menu
            window.tray.contextMenu().actions()[-1].trigger()
        else:
            action_rect = window.menu.actionGeometry(window.exit_action)
            QTest.mouseClick(window.menu, Qt.MouseButton.LeftButton, pos=action_rect.center())
    except Exception as error:
        fail(repr(error))


def capture_menu(name):
    # Native Windows menus can produce empty QWidget.grab() results.
    rect = window.menu.frameGeometry()
    window.menu.screen().grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height()).save(
        str(out / f'desktop-{args.exit_via}-{name}.png'))


timer = QTimer()
timer.timeout.connect(poll)
timer.start(500)
try:
    app.exec()
    result['quitSignal'] = expected_exit and failure is None
finally:
    timer.stop()
    QCursor.setPos(original_cursor)
    window.tray.hide()
    window.close()
    back.close()
    server.close()
    logging.shutdown()
log = (out / f'desktop-{args.exit_via}.log').read_text(encoding='utf-8')
result['sdkErrors'] = [line for line in log.splitlines() if '[CSM][E]' in line]
(out / f'desktop-{args.exit_via}.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
sys.exit(0 if result['quitSignal'] and not result['sdkErrors'] else 1)
