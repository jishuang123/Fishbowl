# Only generated release resources enter the data archive. No workspace glob.
import os
from pathlib import Path
from types import SimpleNamespace
from ast import literal_eval
from PyInstaller.config import CONF

root=Path(SPECPATH)
stage=Path(os.environ['FISHBOWL_RELEASE_STAGE']).resolve()
assert stage.is_relative_to((root/'.local/release').resolve())
datas=[(str(path),path.relative_to(stage).parent.as_posix()) for path in stage.rglob('*') if path.is_file()]
if os.environ.get('FISHBOWL_REUSE_ANALYSIS')=='1':
    # Developer iteration only, for code changes with unchanged imports/data.
    # Normal release builds always perform dependency analysis below.
    cached=literal_eval((Path(CONF['workpath'])/'Analysis-00.toc').read_text(encoding='utf-8'))
    a=SimpleNamespace(**{name:cached[i] for i,(name,_) in enumerate(Analysis._GUTS)})
else:
    a=Analysis([str(root/'app/entry.py')],pathex=[str(root)],binaries=[],datas=datas,
               hiddenimports=[],hookspath=[],runtime_hooks=[],excludes=['tkinter','__main__'],noarchive=False)
# Qt 6.12 uses Windows' inbox ICU (unversioned exports). A foreign icuuc.dll
# on the build host's PATH can shadow it during dependency discovery. Never
# ship that incompatible DLL; the supported Windows version supplies ICU.
a.binaries=[item for item in a.binaries if Path(item[0]).name.lower() not in ('icuuc.dll','icuin.dll','icudt.dll','icudt78.dll')]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='Fishbowl',debug=False,
        bootloader_ignore_signals=False,strip=False,upx=False,console=False,
        icon=str(stage/'fish.ico'),contents_directory='_internal',
        version=str(root/'packaging/version.txt'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='Fishbowl')
