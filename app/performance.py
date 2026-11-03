"""Opt-in diagnostics only; records renderer/process metrics, never chat or keys."""
import json
import time
from pathlib import Path


def attach_probe(window, report, origin, seconds=8):
    import psutil
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    report=Path(report)
    report.parent.mkdir(parents=True,exist_ok=True)
    process=psutil.Process()
    result={}
    def tree():
        private=cpu=0
        for p in [process,*process.children(recursive=True)]:
            try:
                private+=p.memory_info().private
                t=p.cpu_times()
                cpu+=t.user+t.system
            except (psutil.NoSuchProcess,psutil.AccessDenied):pass
        return {'private_bytes':private,'cpu_seconds':cpu}
    def reported(raw):
        value=json.loads(raw)
        if not value.get('ready') or result:return
        result.update(startup_seconds=time.perf_counter()-origin,before=tree(),started=time.perf_counter())
        window.page().runJavaScript('window.fishbowl.snapshot().frames',0,lambda n:result.update(start_frames=n))
        QTimer.singleShot(seconds*1000,finish)
    def finish():
        result['after']=tree()
        result['sample_seconds']=time.perf_counter()-result.pop('started')
        result['cpu_percent_one_core']=(result['after']['cpu_seconds']-result['before']['cpu_seconds'])/result['sample_seconds']*100
        window.grab().save(str(report.with_suffix('.png')))
        window.page().runJavaScript('JSON.stringify(window.fishbowl.snapshot())',0,got_snapshot)
    def got_snapshot(raw):
        result['renderer']=json.loads(raw)
        result['observed_fps']=(result['renderer']['frames']-result['start_frames'])/result['sample_seconds']
        report.write_text(json.dumps(result,indent=2),encoding='utf-8')
        QApplication.instance().quit()
    window.bridge.rendererReported.connect(reported)
    QTimer.singleShot(60000,lambda:QApplication.instance().quit() if not report.exists() else None)
