"""Real file imports, private asset boundary, migration, and two rendered models."""
import json
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
from playwright.sync_api import sync_playwright
from PySide6.QtWidgets import QApplication

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.characters import CharacterRegistry
from app.memory import ConversationMemory
from app.server import RendererServer

app=QApplication([])
out=ROOT/'.local/evidence/characters'
out.mkdir(parents=True,exist_ok=True)
checks=[]
haru=ROOT/'.local/sdk/CubismSdkForWeb-5-r.5/Samples/Resources/Haru/Haru.model3.json'

with tempfile.TemporaryDirectory(prefix='user-',dir=out) as directory:
    user=Path(directory)
    registry=CharacterRegistry(user)
    legacy=user/'chat-memory.json'
    old=[{'role':'user','content':'大肥鱼记住我喜欢蓝色。'}, {'role':'assistant','content':'记住啦。'}]
    assert ConversationMemory(legacy).save(old)
    role=registry.import_model(haru)
    assert ConversationMemory(registry.memory_path(role.id)).load()==[] and legacy.exists()
    migrated=registry.memory_path('deepseek')
    assert ConversationMemory(migrated).load()==old and not legacy.exists()
    assert ConversationMemory(migrated).save([])
    assert ConversationMemory(registry.memory_path('deepseek')).load()==[]
    checks.append('old memory migrates only to DeepSeek; clearing it cannot resurrect the legacy file')
    second=[{'role':'user','content':'Haru 喜欢金色。'}, {'role':'assistant','content':'好的。'}]
    assert ConversationMemory(registry.memory_path(role.id)).save(second)
    reloaded=CharacterRegistry(user)
    assert role.id in reloaded.characters and reloaded.get(role.id).persona.read_text(encoding='utf-8')
    assert ConversationMemory(reloaded.memory_path(role.id)).load()==second
    assert ConversationMemory(reloaded.memory_path('deepseek')).load()==[]
    copied=json.loads((registry.asset_root(role.id)/haru.name).read_text(encoding='utf-8'))
    assert all('Sound' not in m for group in copied['FileReferences']['Motions'].values() for m in group)
    assert 'Sound' in haru.read_text(encoding='utf-8')
    checks.append('import survives registry restart, keeps memories separate, and leaves source audio references unchanged')
    broken=user/'broken'
    broken.mkdir()
    entry=broken/'bad.model3.json'
    for refs in ({'Moc':'missing.moc3','Textures':['missing.png']},
                 {'Moc':'../outside.moc3','Textures':['x.png']},
                 {'Moc':'C:/outside.moc3','Textures':['x.png']},
                 {'Moc':'model.moc3','Textures':['x.png']}):
        entry.write_text(json.dumps({'Version':3,'FileReferences':refs}),encoding='utf-8')
        (broken/'model.moc3').write_bytes(b'not a valid moc')
        (broken/'x.png').write_bytes(b'png')
        try:registry.import_model(entry)
        except ValueError:pass
        else:raise AssertionError('invalid or escaping model accepted')
    assert len(registry.characters)==2 and not list((user/'characters').glob('.import-*'))
    checks.append('missing assets, escaping/absolute references and invalid MOC are rejected without partial roles')
    server=RendererServer(ROOT/'frontend/dist',registry)
    try:
        public=json.load(urlopen(server.url+f'character-profile.json?id={role.id}'))
        assert public['id']==role.id and not any(k in public for k in ('persona','prepare','api_key','memory'))
        for path in (f'character-assets/{role.id}/../persona.txt',
                     f'character-assets/{role.id}/%2e%2e/persona.txt',
                     f'character-assets/{role.id}/%2e%2e/%2e%2e/%2e%2e/memories/{role.id}.json'):
            try:urlopen(server.url+path)
            except HTTPError as error:assert error.code==404
            else:raise AssertionError('private role file exposed')
        checks.append('web profile excludes persona/memory; asset paths cannot escape the imported model directory')
        errors=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page(viewport={'width':400,'height':640})
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('console',lambda m:errors.append(m.text) if m.type=='error' or '[CSM][E]' in m.text else None)
            for identifier,name in [('deepseek','deepseek-before'),(role.id,'haru-imported'),('deepseek','deepseek-returned')]:
                page.goto(server.url+'?character='+identifier)
                page.wait_for_function('window.fishbowl?.snapshot().ready',timeout=60000)
                page.mouse.move(300,150)
                page.wait_for_timeout(500)
                snap=page.evaluate('window.fishbowl.snapshot()')
                assert snap['character']==identifier and snap['cornerPixel'][3]==0 and not snap['errors']
                assert snap['textures']>0 and snap['parameters']>0 and snap['glError']==0
                page.mouse.click(200,180)
                page.mouse.move(200,320)
                page.mouse.down()
                page.mouse.move(235,340,steps=4)
                page.mouse.up()
                page.screenshot(path=str(out/f'{name}.png'),omit_background=True)
            assert not errors,errors
            browser.close()
        checks.append('real Chrome renders DeepSeek, imported Haru and DeepSeek again with transparent backgrounds and no console errors')
    finally:server.close()

result={'passed':checks,'errors':[],'fixture':'official SDK Haru; temporary local character copies; no personal settings or API calls'}
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
