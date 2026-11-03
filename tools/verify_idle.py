"""Run real rendered idle interactions with Playwright's accelerated clock."""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.server import RendererServer

app = QApplication([])
server = RendererServer(ROOT / 'frontend/dist')
out = ROOT / '.local/evidence/idle'
out.mkdir(parents=True, exist_ok=True)
errors, checks = [], []
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width':400,'height':640})
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: errors.append(m.text) if m.type=='error' or '[CSM][E]' in m.text else None)
        page.on('response', lambda r: errors.append(f'{r.status}: {r.url}') if r.status >= 400 else None)
        page.clock.install()
        page.goto(server.url)
        page.wait_for_function('window.fishbowl?.snapshot().ready', timeout=60000)
        snap = lambda: page.evaluate('window.fishbowl.snapshot().interaction')
        def advance(milliseconds):
            # Short frame gaps represent quiet time, rather than system sleep.
            while milliseconds > 0:
                step = min(milliseconds, 1000)
                page.clock.fast_forward(step)
                milliseconds -= step
        def capture(name):
            page.screenshot(path=str(out / f'{name}.png'), omit_background=True)
            (out / f'{name}.json').write_text(json.dumps(snap(),indent=2),encoding='utf-8')
        def next_idle(random_value):
            count = snap()['idle']['count']
            page.evaluate('(value) => Math.random = () => value', random_value)
            for _ in range(110):
                advance(1000)
                if snap()['idle']['count'] > count:
                    return
            raise AssertionError('No idle interaction within the configured window')

        advance(40000)
        assert snap()['idle']['count'] == 0, 'Idle interaction started too soon'
        capture('quiet-start')
        checks.append('no automatic interaction in the first 40 seconds')

        next_idle(0)
        page.wait_for_function('window.fishbowl.snapshot().interaction.values.key7 > .8')
        assert snap()['idle']['active'] and snap()['history'] == []
        capture('idle-blush')
        checks.append('idle expression visibly renders without consuming the manual expression cycle')
        first_time = snap()['idle']['history'][-1]['at']
        advance(3500)
        page.wait_for_function('window.fishbowl.snapshot().interaction.values.key7 < .1')
        assert snap()['expression'] == 'Neutral'
        capture('idle-expression-restored')
        checks.append('idle expression expires and restores')

        next_idle(.99)
        page.wait_for_function("window.fishbowl.snapshot().interaction.phase === 'hold'")
        assert snap()['idle']['history'][-1]['at'] - first_time >= 45000
        page.wait_for_function('window.fishbowl.snapshot().interaction.values.Movement2 > .8')
        capture('idle-gesture')
        checks.append('idle gesture visibly renders at a low frequency')
        page.mouse.click(200,125)
        page.wait_for_function('window.fishbowl.snapshot().interaction.values.key7 > .8')
        assert not snap()['idle']['active'] and snap()['phase'] == 'idle'
        assert snap()['history'] == ['Blush']
        page.wait_for_function('window.fishbowl.snapshot().interaction.values.Movement2 < .05')
        capture('manual-click-preempts-idle')
        checks.append('manual click cancels the idle gesture and applies immediately')

        advance(40000)
        assert snap()['idle']['count'] == 2, 'Idle interaction was not postponed after clicking'
        page.mouse.move(200,300)
        page.mouse.down()
        count = snap()['idle']['count']
        advance(110000)
        assert snap()['idle']['count'] == count
        capture('held-press-pauses-idle')
        page.mouse.move(250,340,steps=5)
        advance(110000)
        assert snap()['idle']['count'] == count
        page.mouse.up()
        capture('drag-pauses-idle')
        checks.append('holding and dragging block idle, and do not queue a click')
        assert snap()['history'] == ['Blush']

        next_idle(.99)  # Previous automatic gesture forces a different kind.
        assert snap()['idle']['history'][-1]['kind'] != 'HandToChest'
        page.mouse.click(200,300)
        page.wait_for_function("window.fishbowl.snapshot().interaction.phase === 'hold'")
        assert snap()['history'] == ['Blush','HandToChest'] and not snap()['idle']['active']
        capture('manual-gesture-preempts-idle')
        page.wait_for_function("window.fishbowl.snapshot().interaction.phase === 'idle'",timeout=10000)
        capture('manual-gesture-restored')
        checks.append('manual gesture preempts an idle expression and returns normally')

        page.clock.fast_forward(150000)  # Suspended frame loop: no catch-up event.
        assert snap()['idle']['count'] == 3
        capture('resume-no-burst')
        checks.append('a long frame gap reschedules instead of catching up')
        next_idle(0)
        assert snap()['idle']['count'] == 4
        assert not errors and not page.evaluate('window.fishbowl.snapshot().errors')
        capture('idle-resumes')
        checks.append('automatic interaction resumes after a fresh delay')
        result = {'passed':checks,'errors':errors,'final':snap()}
        (out / 'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
        browser.close()
finally:
    server.close()
