"""Exercise the delivered ZIP after relocating it to a Unicode temporary path."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--archive',type=Path,default=ROOT/'dist/Fishbowl-0.11.0-windows-x64.zip')
parser.add_argument('--live',action='store_true')
args=parser.parse_args()
archive=args.archive.resolve()
with tempfile.TemporaryDirectory(prefix='Fishbowl EXE 验收 ') as directory:
    target=Path(directory)
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            if not (target/name).resolve().is_relative_to(target):
                raise ValueError('Archive member escapes extraction directory')
        bundle.extractall(target)
    folder=target/'Fishbowl'
    command=[sys.executable,str(ROOT/'tools/verify_release.py'),'--exe',str(folder/'Fishbowl.exe')]
    if args.live:command.append('--live')
    subprocess.run(command,cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'tools/audit_release.py'),'--folder',str(folder),
                    '--report',str(ROOT/'.local/evidence/package/audit-extracted.json')],cwd=ROOT,check=True)
record={'archive':str(archive),'bytes':archive.stat().st_size,
        'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'relocated_unicode_path_verified':True}
(ROOT/'.local/evidence/package/archive.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record,indent=2))
