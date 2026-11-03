"""Frozen entry point; all writable state remains outside the executable bundle."""
import sys
from app.main import main

if __name__=='__main__':
    try:
        code=main()
    except Exception as error:
        # Windowed executables have no stderr. Keep a useful stack outside the
        # bundle without serializing exception values (which could contain data).
        import traceback
        import os
        from pathlib import Path
        try:
            from PySide6.QtCore import QStandardPaths
            path=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        except ImportError:
            path=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'Fishbowl/Fishbowl'
        try:
            path.mkdir(parents=True,exist_ok=True)
            (path/'startup-error.log').write_text(type(error).__name__+'\n'+''.join(traceback.format_tb(error.__traceback__)),encoding='utf-8')
        except OSError:pass
        if not any(flag in sys.argv for flag in ('--verify-package','--benchmark-report')):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'Fishbowl 未能启动。请查看用户数据目录中的 startup-error.log。','Fishbowl 启动失败',0x10)
        code=1
    sys.exit(code)
