"""Verify the built transparent page in real Chrome without a desktop bridge."""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.server import RendererServer

app = QApplication([])
server = RendererServer(ROOT / 'frontend/dist')
out = ROOT / '.local/evidence'
out.mkdir(parents=True, exist_ok=True)
errors = []
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width':400, 'height':640})
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' or '[CSM][E]' in msg.text else None)
        page.on('response', lambda r: errors.append(f'{r.status}: {r.url}') if r.status >= 400 else None)
        page.goto(server.url)
        page.wait_for_function('window.fishbowl?.snapshot().ready', timeout=60000)
        page.mouse.move(200,320)
        page.mouse.down()
        page.mouse.move(245,350,steps=5)
        page.mouse.up()
        page.mouse.click(200,320,button='right')
        page.wait_for_function("""() => Object.values(window.fishbowl.snapshot().ranges).every(r => r[1]-r[0]>0.5)""", timeout=30000)
        result = page.evaluate('window.fishbowl.snapshot()')
        page.screenshot(path=str(out / 'transparent-web.png'), omit_background=True)
        result['browserErrors'] = errors
        img = QImage(str(out / 'transparent-web.png'))
        result['screenshotCornerAlpha'] = img.pixelColor(0,0).alpha()
        (out / 'transparent-web.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
        assert not errors and not result['errors'] and result['screenshotCornerAlpha'] == 0
        browser.close()
finally:
    server.close()
