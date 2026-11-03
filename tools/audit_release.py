"""Inspect actual bundle bytes and data files without ever printing any credential."""
import argparse
import base64
import hashlib
import json
import sys
import pefile
from pathlib import Path
from PySide6.QtCore import QCoreApplication,QStandardPaths
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.chat_config import LocalChatConfig

parser=argparse.ArgumentParser()
parser.add_argument('--folder',type=Path,default=ROOT/'dist/Fishbowl')
parser.add_argument('--report',type=Path,default=ROOT/'.local/evidence/package/audit.json')
args=parser.parse_args()
app=QCoreApplication([])
app.setApplicationName('Fishbowl')
app.setOrganizationName('Fishbowl')
folder=args.folder.resolve()
assert folder.is_dir()
profile=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
config=LocalChatConfig(profile/'deepseek.json')
keys={key for key in (config.credentials()[0],config.read().get('api_key','')) if isinstance(key,str) and key}
needles=[value for key in keys for value in (key.encode('utf-8'),key.encode('utf-16-le'),base64.b64encode(key.encode('utf-8')))]
forbidden={'deepseek.json','deepseek.local.json','chat-memory.json','settings.json','.env','fishbowl.log','startup-error.log'}
personal_dirs={'memories','interactions','interaction-audio','user-data','.venv','node_modules'}
errors=[]
records={}
for path in sorted(folder.rglob('*')):
    if not path.is_file():continue
    relative=path.relative_to(folder).as_posix()
    if not path.resolve().is_relative_to(folder):errors.append('bundle contains an external link')
    if path.name.lower() in forbidden or personal_dirs & {p.lower() for p in path.relative_to(folder).parts}:
        errors.append('forbidden personal data file: '+relative)
    digest=hashlib.sha256()
    tail=b''
    with path.open('rb') as stream:
        while chunk:=stream.read(4*1024*1024):
            digest.update(chunk)
            data=tail+chunk
            if any(needle in data for needle in needles):errors.append('credential bytes found in a bundle file')
            tail=data[-256:]
    records[relative]={'bytes':path.stat().st_size,'sha256':digest.hexdigest()}
    if path.suffix=='.json':
        value=json.loads(path.read_text(encoding='utf-8'))
        if isinstance(value,dict) and ('api_key' in value or ('messages' in value and value.get('version')==1)):
            errors.append('credential or conversation JSON found: '+relative)
manifest=json.loads((folder/'_internal/asset-manifest.json').read_text(encoding='utf-8'))
for name,record in manifest['files'].items():
    actual=records.get('_internal/'+name)
    if actual is None or actual['sha256']!=record['sha256']:errors.append('resource manifest mismatch: '+name)
archive=CArchiveReader(str(folder/'Fishbowl.exe'))
console=pefile.PE(str(folder/'Fishbowl.exe'),fast_load=True).OPTIONAL_HEADER.Subsystem!=2
if console:errors.append('EXE unexpectedly uses a console subsystem')
if any(path.name.lower()=='icuuc.dll' for path in folder.rglob('*.dll')):
    errors.append('foreign ICU DLL would shadow Windows native ICU')
pyz_name=next(n for n in archive.toc if n.endswith('.pyz'))
modules=archive.open_embedded_archive(pyz_name).toc
assert 'app.main' in modules and 'app.plugins.current_time' in modules
assert not any(name.startswith(('tools.','tests.')) for name in modules)
result={'passed':not errors,'errors':errors,'file_count':len(records),'total_bytes':sum(r['bytes'] for r in records.values()),
        'credential_scan_performed':bool(needles),'private_data_files':False if not errors else None,
        'entry_console':console,'resource_manifest_verified':not errors,'files':records}
args.report.parent.mkdir(parents=True,exist_ok=True)
args.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='files'},indent=2))
assert not errors
