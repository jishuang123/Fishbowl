"""Launch the actual frozen executable with no Python/source directories on PATH."""
import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--exe',type=Path,default=ROOT/'dist/Fishbowl/Fishbowl.exe')
parser.add_argument('--live',action='store_true')
parser.add_argument('--benchmark',action='store_true')
args=parser.parse_args()
executable=args.exe.resolve()
environment=os.environ.copy()
environment.pop('PYTHONPATH',None)
environment.pop('PYTHONHOME',None)
system_root=Path(os.environ.get('SystemRoot','C:/Windows'))
environment['PATH']=os.pathsep.join([str(system_root/'System32'),str(system_root)])
out=ROOT/'.local/evidence/package'
out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='fishbowl-launch-') as directory:
    if args.benchmark:
        for run in range(1,4):
            report=ROOT/f'.local/evidence/performance/exe-{run}.json'
            report.unlink(missing_ok=True)
            environment['FISHBOWL_MEASURE_ORIGIN']=str(time.perf_counter())
            command=[str(executable),'--data-dir',str(Path(directory)/('user-'+str(run))),'--benchmark-report',str(report)]
            result=subprocess.run(command,cwd=directory,env=environment,timeout=90)
            assert result.returncode==0 and report.is_file(),'EXE benchmark failed'
            data=json.loads(report.read_text(encoding='utf-8'))
            assert data['renderer']['ready'] and not data['renderer']['errors'],'EXE renderer failed during benchmark'
            assert 0<data['observed_fps']<35,'EXE rendering did not respect the frame limit'
            print(json.dumps({k:v for k,v in data.items() if k!='renderer'},indent=2),flush=True)
    else:
        (out/'result.json').unlink(missing_ok=True)
        command=[str(executable),'--verify-package',str(out),'--verification-model',
            str(ROOT/'.local/sdk/CubismSdkForWeb-5-r.5/Samples/Resources/Haru/Haru.model3.json')]
        if args.live:command.append('--verify-live')
        result=subprocess.run(command,cwd=directory,env=environment,timeout=180)
        assert (out/'result.json').is_file(),f'EXE exited before verification initialized (exit {result.returncode})'
        report=json.loads((out/'result.json').read_text(encoding='utf-8'))
        print(json.dumps(report,ensure_ascii=False,indent=2))
        assert result.returncode==0 and report['frozen'] and not report['errors']
