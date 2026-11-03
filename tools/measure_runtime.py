"""Compare actual Qt/WebEngine startup and process-tree memory in isolated user data."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

START=time.perf_counter()
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--report',type=Path,required=True)
parser.add_argument('--child',action='store_true')
parser.add_argument('--seconds',type=int,default=8)
parser.add_argument('--renderer',type=Path,default=ROOT/'frontend/dist')
args=parser.parse_args()
args.report.parent.mkdir(parents=True,exist_ok=True)
if not args.child:
    environment=os.environ.copy()
    environment['FISHBOWL_MEASURE_ORIGIN']=str(time.perf_counter())
    raise SystemExit(subprocess.call([sys.executable,str(Path(__file__).resolve()),'--child','--report',str(args.report.resolve()),
        '--seconds',str(args.seconds),'--renderer',str(args.renderer.resolve())],env=environment))
sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from app.pet_window import PetWindow
from app.server import RendererServer
from app.characters import CharacterRegistry
import psutil

origin=float(os.environ['FISHBOWL_MEASURE_ORIGIN'])
app=QApplication([])
app.setApplicationName('FishbowlMeasure')
process=psutil.Process()

def tree():
    memory=cpu=0
    for p in [process,*process.children(recursive=True)]:
        try:
            memory+=p.memory_info().private
            t=p.cpu_times()
            cpu+=t.user+t.system
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    return {'private_bytes':memory,'cpu_seconds':cpu}

with tempfile.TemporaryDirectory(prefix='fishbowl-measure-') as directory:
    user=Path(directory)
    registry=CharacterRegistry(user,renderer_root=args.renderer)
    renderer=RendererServer(args.renderer,registry)
    pet=PetWindow(renderer.url,settings_path=user/'settings.json',characters=registry)
    result={'import_seconds':time.perf_counter()-origin}
    ready_at=None
    def reported(raw):
        global ready_at
        value=json.loads(raw)
        if value.get('error'):
            result['error']='renderer error'
            app.quit()
        if not value.get('ready') or ready_at is not None:return
        ready_at=time.perf_counter()
        result['startup_seconds']=ready_at-origin
        result['before']=tree()
        pet.page().runJavaScript('window.fishbowl.snapshot().frames',0,lambda n:result.update(start_frames=n))
        QTimer.singleShot(args.seconds*1000,finish)
    def finish():
        pet.grab().save(str(args.report.with_suffix('.png')))
        result['after']=tree()
        result['sample_seconds']=time.perf_counter()-ready_at
        result['cpu_percent_one_core']=(result['after']['cpu_seconds']-result['before']['cpu_seconds'])/result['sample_seconds']*100
        pet.page().runJavaScript('JSON.stringify(window.fishbowl.snapshot())',0,got_snapshot)
    def got_snapshot(raw):
        result['renderer']=json.loads(raw)
        result['observed_fps']=(result['renderer']['frames']-result.get('start_frames',0))/(time.perf_counter()-ready_at)
        app.quit()
    pet.bridge.rendererReported.connect(reported)
    pet.show()
    QTimer.singleShot(60000,app.quit)
    app.exec()
    pet.close()
    renderer.close()
args.report.parent.mkdir(parents=True,exist_ok=True)
args.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='renderer'},indent=2))
assert ready_at is not None and 'error' not in result
