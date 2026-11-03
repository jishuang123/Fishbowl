"""Exercise visible interaction behavior in real Chrome, with screenshot evidence."""
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
out = ROOT / '.local/evidence/interactions'
out.mkdir(parents=True, exist_ok=True)
errors, checks = [], []
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width':400, 'height':640})
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: errors.append(m.text) if m.type=='error' or '[CSM][E]' in m.text else None)
        page.on('response', lambda r: errors.append(f'{r.status}: {r.url}') if r.status >= 400 else None)
        page.goto(server.url)
        page.wait_for_function('window.fishbowl?.snapshot().ready', timeout=60000)
        snap = lambda: page.evaluate('window.fishbowl.snapshot().interaction')
        def capture(name):
            page.screenshot(path=str(out / f'{name}.png'), omit_background=True)
            (out / f'{name}.json').write_text(json.dumps(snap(), indent=2), encoding='utf-8')
        for name,x,y,condition in [
            ('look-right',380,125,'v.ParamEyeBallX > .4 && v.ParamAngleX > 5'),
            ('look-left',20,125,'v.ParamEyeBallX < -.4 && v.ParamAngleX < -5'),
            ('look-up',200,5,'v.ParamEyeBallY > .2 && v.ParamAngleY > 5'),
            ('look-down',200,620,'v.ParamEyeBallY < -.4 && v.ParamAngleY < -5'),
        ]:
            page.mouse.move(x,y)
            page.wait_for_function('() => {const v=window.fishbowl.snapshot().interaction.values;return '+condition+'}', timeout=12000)
            page.wait_for_timeout(500)
            capture(name)
        checks.append('head and eyes follow all four directions')
        before = snap()['history']
        page.mouse.click(5,5)
        page.wait_for_timeout(400)
        assert snap()['history'] == before, 'Blank background triggered a reaction'
        capture('background-ignored')
        checks.append('transparent background ignores clicks')
        for name,key in [('Blush','key7'),('Hearts','key4'),('Happy','key5')]:
            page.mouse.click(200,125)
            page.wait_for_function(f'window.fishbowl.snapshot().interaction.values.{key} > .8')
            page.wait_for_timeout(350)
            assert snap()['expression'] == name
            capture('expression-'+name)
        checks.append('three head expressions show')
        page.wait_for_function("window.fishbowl.snapshot().interaction.expression === 'Neutral'")
        page.wait_for_timeout(500)
        assert all(abs(snap()['values'][key]) < .1 for key in ['key4','key5','key7'])
        capture('expression-reset')
        checks.append('expressions restore without stacking')
        page.mouse.click(200,300)
        page.wait_for_function('window.fishbowl.snapshot().interaction.values.Movement2 > .85')
        page.wait_for_function("window.fishbowl.snapshot().interaction.phase === 'hold'")
        page.wait_for_timeout(200)
        capture('hand-to-chest')
        count = len(snap()['history'])
        page.mouse.click(200,300)
        page.wait_for_timeout(350)
        assert len(snap()['history']) == count, 'Busy gesture was queued or restarted'
        page.wait_for_function("window.fishbowl.snapshot().interaction.phase === 'idle'", timeout=10000)
        page.wait_for_timeout(400)
        assert abs(snap()['values']['Movement2']) < .05, snap()
        capture('gesture-reset')
        checks.append('gesture plays once, ignores repeats, and restores')
        page.mouse.move(200,147)
        page.wait_for_function("""() => {const v=window.fishbowl.snapshot().interaction.values;
            return Math.abs(v.ParamEyeBallX)<.03 && Math.abs(v.ParamEyeBallY)<.03;}""", timeout=10000)
        capture('gaze-reset-after-gesture')
        checks.append('gesture completion does not bake gaze into the base pose')
        history = snap()['history']
        page.mouse.move(200,300)
        page.mouse.down()
        page.mouse.move(250,340,steps=5)
        page.mouse.up()
        page.wait_for_timeout(400)
        assert snap()['history'] == history, 'Drag triggered a click reaction'
        capture('drag-no-reaction')
        checks.append('drag does not trigger a reaction')
        assert not errors and not page.evaluate('window.fishbowl.snapshot().errors')
        result = {'passed':checks, 'errors':errors, 'final':snap()}
        (out / 'result.json').write_text(json.dumps(result,indent=2), encoding='utf-8')
        print(json.dumps(result,indent=2))
        browser.close()
finally:
    server.close()
