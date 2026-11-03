"""Real Chrome exercises saved per-role mappings against the actual Cubism model."""
import json
import sys
import tempfile
from pathlib import Path
from PySide6.QtWidgets import QApplication
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.characters import CharacterRegistry
from app.interaction_config import InteractionConfig
from app.server import RendererServer

app=QApplication([])
out=ROOT/'.local/evidence/mappings/web'
out.mkdir(parents=True,exist_ok=True)
checks=[]
with tempfile.TemporaryDirectory(prefix='user-',dir=out) as directory:
    registry=CharacterRegistry(Path(directory))
    config=InteractionConfig(registry,'deepseek')
    catalog=config.catalog()
    action=next(k for k,v in catalog['actions'].items() if v['label']=='狗尾草切换出来')
    rows=config.defaults()
    rows['head']={'mode':'custom','action':'','expression':'Hearts','voice':''}
    rows['body']={'mode':'custom','action':action,'expression':'','voice':''}
    rows['idle']={'mode':'custom','action':'gesture','expression':'Blush','voice':''}
    config.save(rows)
    server=RendererServer(ROOT/'frontend/dist',registry)
    errors=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page(viewport={'width':400,'height':640})
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('console',lambda m:errors.append(m.text) if m.type=='error' or '[CSM][E]' in m.text else None)
            page.on('response',lambda r:errors.append(f'{r.status}: {r.url}') if r.status>=400 else None)
            page.clock.install()
            page.goto(server.url)
            page.wait_for_function('window.fishbowl?.snapshot().ready',timeout=60000)
            snap=lambda:page.evaluate('window.fishbowl.snapshot().interaction')
            def advance(milliseconds):
                while milliseconds>0:
                    step=min(milliseconds,1000)
                    page.clock.fast_forward(step)
                    milliseconds-=step
            def capture(name):page.screenshot(path=str(out/f'{name}.png'),omit_background=True)
            page.mouse.click(200,125)
            page.wait_for_function("window.fishbowl.snapshot().interaction.expression==='Hearts'")
            page.wait_for_function('window.fishbowl.snapshot().interaction.values.key4>.8')
            capture('mapped-head-hearts')
            advance(3500)
            page.wait_for_function('window.fishbowl.snapshot().interaction.values.key4<.05')
            checks.append('saved head expression is visibly rendered and restores without stacking')
            page.mouse.click(200,300)
            page.wait_for_function("window.fishbowl.snapshot().interaction.phase==='custom'")
            page.wait_for_function('window.fishbowl.snapshot().interaction.values.Movement1>.8')
            capture('mapped-body-action')
            advance(5000)
            assert snap()['phase']=='idle'
            assert snap()['values']['Movement1']<.05
            capture('mapped-body-restored')
            checks.append('original looping body motion runs once and returns instead of staying active')
            advance(40000)
            assert snap()['idle']['count']==0
            for _ in range(65):
                advance(1000)
                if snap()['idle']['count']:break
            assert snap()['idle']['count']==1 and snap()['idle']['active']
            page.wait_for_function('window.fishbowl.snapshot().interaction.values.key7>.8')
            capture('mapped-idle')
            page.mouse.click(200,125)
            page.wait_for_function("window.fishbowl.snapshot().interaction.expression==='Hearts'")
            assert not snap()['idle']['active'] and snap()['phase']=='idle'
            capture('manual-preempts-mapped-idle')
            count=snap()['idle']['count']
            page.mouse.move(200,320)
            page.mouse.down()
            advance(110000)
            page.mouse.move(235,340,steps=4)
            page.mouse.up()
            assert snap()['idle']['count']==count
            checks.append('custom idle keeps the low frequency; manual click and held drag preempt it without queued actions')
            rows['head']={'mode':'off','action':'','expression':'','voice':''}
            rows['idle']={'mode':'off','action':'','expression':'','voice':''}
            config.save(rows)
            page.reload()
            page.wait_for_function('window.fishbowl?.snapshot().ready',timeout=60000)
            page.mouse.click(200,125)
            advance(115000)
            assert not snap()['history'] and snap()['idle']['count']==0
            capture('disabled-triggers')
            checks.append('disabled head and idle stay off after a real reload')
            assert not errors and not page.evaluate('window.fishbowl.snapshot().errors'),errors
            browser.close()
    finally:server.close()
result={'passed':checks,'errors':errors}
(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
