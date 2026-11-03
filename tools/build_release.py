"""Build a Windows onedir EXE using an explicit, private-data-free resource list."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from importlib.metadata import distribution
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QImage,QImageReader,QImageWriter,QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


def stage_resources(full_textures=False):
    stage=ROOT/'.local/release'/('stage-'+uuid.uuid4().hex[:10])
    stage.mkdir(parents=True)
    files={}
    def copy(source,relative):
        source=Path(source).resolve()
        target=stage/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        files[relative]={'bytes':target.stat().st_size}
        return target
    frontend=ROOT/'frontend/dist'
    copy(frontend/'index.html','frontend/dist/index.html')
    for path in (frontend/'assets').iterdir():
        if path.suffix in ('.js','.css','.woff','.woff2'):
            copy(path,'frontend/dist/assets/'+path.name)
    copy(frontend/'Core/live2dcubismcore.js','frontend/dist/Core/live2dcubismcore.js')
    for path in (frontend/'Framework/Shaders/WebGL').rglob('*'):
        if path.is_file() and path.suffix in ('.vert','.frag'):
            copy(path,'frontend/dist/'+path.relative_to(frontend).as_posix())
    profile=json.loads((ROOT/'characters/deepseek/character.json').read_text(encoding='utf-8'))
    entry=frontend/profile['runtime']['model_url'].lstrip('/')
    model=json.loads(entry.read_text(encoding='utf-8'))
    refs=model['FileReferences']
    referenced=[refs['Moc'],*refs['Textures']]
    for key in ('Physics','Pose','DisplayInfo','UserData'):
        if refs.get(key):referenced.append(refs[key])
    referenced += [v['File'] for v in refs.get('Expressions',[])]
    referenced += [v['File'] for group in refs.get('Motions',{}).values() for v in group]
    copy(entry,'frontend/dist/'+entry.relative_to(frontend).as_posix())
    texture_before=texture_after=0
    for relative in sorted(set(referenced)):
        source=(entry.parent/relative).resolve()
        if not source.is_relative_to(entry.parent.resolve()):raise ValueError('Model reference escapes resource directory')
        relative_target='frontend/dist/'+source.relative_to(frontend).as_posix()
        target=copy(source,relative_target)
        if relative not in refs['Textures']:continue
        reader=QImageReader(str(source))
        size=reader.size()
        texture_before+=size.width()*size.height()*4
        output_size=size if full_textures else QSize(max(1,size.width()//2),max(1,size.height()//2))
        if not full_textures:
            reader.setScaledSize(output_size)
            image=reader.read()
            if image.isNull():raise ValueError('Cannot decode model atlas')
            if image.size()!=output_size:image=image.scaled(output_size,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
            writer=QImageWriter(str(target),b'png')
            writer.setCompression(75)
            if not writer.write(image):raise ValueError('Cannot encode model atlas')
        texture_after+=output_size.width()*output_size.height()*4
        files[relative_target].update(bytes=target.stat().st_size,dimensions=[output_size.width(),output_size.height()])
    for relative in ('characters/deepseek/character.json','characters/deepseek/persona.txt','characters/generic.json',
                     'assets/icons/fish.svg','assets/audio/cues.json','app/synthesize.ps1'):
        copy(ROOT/relative,relative)
    # Project defaults, never the machine's audio mappings or imported characters.
    cues=json.loads((stage/'assets/audio/cues.json').read_text(encoding='utf-8'))
    if cues!={'sounds':{},'voices':{}}:raise ValueError('Release must use empty default audio cues, not personal audio mappings')
    sdk=ROOT/'.local/sdk/CubismSdkForWeb-5-r.5'
    for source,relative in ((sdk/'LICENSE.md','licenses/Live2D-SDK.md'),(sdk/'Core/LICENSE.md','licenses/Live2D-Core.md'),
                            (sdk/'Framework/LICENSE.md','licenses/Live2D-Framework.md')):
        copy(source,relative)
    copy(Path(sys.base_prefix)/'LICENSE.txt','licenses/Python.txt')
    for name in ('PySide6','PySide6_Essentials','PySide6_Addons','PySide6_WebEngine',
                 'PySide6_Pdf','shiboken6','psutil','PyInstaller'):
        package=distribution(name)
        for path in package.files or []:
            if '.dist-info/' in str(path).replace('\\','/') and ('license' in str(path).lower() or str(path).endswith('COPYING.txt')):
                copy(package.locate_file(path),'licenses/'+name+'/'+Path(path).name)
    copy(ROOT/'docs/windows-release.md','使用说明.md')
    icon=QImage(256,256,QImage.Format.Format_ARGB32_Premultiplied)
    icon.fill(Qt.GlobalColor.transparent)
    painter=QPainter(icon)
    QSvgRenderer(str(ROOT/'assets/icons/fish.svg')).render(painter)
    painter.end()
    if not icon.save(str(stage/'fish.ico')):raise ValueError('Cannot create EXE icon')
    files['fish.ico']={'bytes':(stage/'fish.ico').stat().st_size}
    for name,record in files.items():record['sha256']=hashlib.sha256((stage/name).read_bytes()).hexdigest()
    manifest={'version':'0.11.0','quality':'original' if full_textures else 'desktop',
              'texture_rgba_bytes_before':texture_before,'texture_rgba_bytes_after':texture_after,'files':files}
    (stage/'asset-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return stage


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage-only',action='store_true')
    parser.add_argument('--full-textures',action='store_true')
    args=parser.parse_args()
    app=QApplication([])
    stage=stage_resources(args.full_textures)
    state=ROOT/'.local/release/latest-stage.json'
    state.write_text(json.dumps({'stage':str(stage)},ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'stage':str(stage),'files':len(json.loads((stage/'asset-manifest.json').read_text(encoding='utf-8'))['files'])}))
    if not args.stage_only:
        output=(ROOT/'dist/Fishbowl').resolve()
        work=(ROOT/'.local/pyinstaller').resolve()
        if not output.is_relative_to(ROOT) or not work.is_relative_to(ROOT):raise ValueError('Build paths outside workspace')
        environment=os.environ.copy()
        environment['FISHBOWL_RELEASE_STAGE']=str(stage)
        environment.pop('FISHBOWL_REUSE_ANALYSIS',None)
        subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm',
            '--distpath',str(ROOT/'dist'),'--workpath',str(work),str(ROOT/'Fishbowl.spec')],cwd=ROOT,env=environment,check=True)
        shutil.copyfile(stage/'使用说明.md',output/'使用说明.md')
        subprocess.run([sys.executable,str(ROOT/'tools/audit_release.py')],cwd=ROOT,check=True)
        archive=ROOT/'dist/Fishbowl-0.11.0-windows-x64.zip'
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
            for path in sorted(output.rglob('*')):
                if path.is_file():bundle.write(path,path.relative_to(output.parent))
        with zipfile.ZipFile(archive) as bundle:
            if bundle.testzip() is not None:raise ValueError('Release archive checksum failed')
        archive_record={'archive':str(archive),'bytes':archive.stat().st_size,
                        'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
        (ROOT/'.local/evidence/package/archive.json').write_text(json.dumps(archive_record,indent=2),encoding='utf-8')
        print(json.dumps(archive_record))
