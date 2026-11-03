import logging
from logging.handlers import RotatingFileHandler
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = time.perf_counter()


def create_window(user_dir, *, chat_client=None):
    from .pet_window import PetWindow
    from .server import RendererServer
    from .characters import CharacterRegistry
    characters = CharacterRegistry(user_dir,renderer_root=ROOT/'frontend/dist')
    server = RendererServer(ROOT/'frontend/dist',characters)
    try:
        window = PetWindow(server.url,settings_path=user_dir/'settings.json',
                           chat_client=chat_client,characters=characters)
    except Exception:
        server.close()
        raise
    return server,window


def main():
    parser = argparse.ArgumentParser(description='Fishbowl desktop companion')
    parser.add_argument('--data-dir',type=Path,help='Use a separate writable data directory')
    parser.add_argument('--benchmark-report',type=Path,help='Write a startup/performance report and exit')
    parser.add_argument('--verify-package',type=Path,help='Run isolated packaged-app acceptance checks')
    parser.add_argument('--verification-model',type=Path,help='Model entry to import during package verification')
    parser.add_argument('--verify-live',action='store_true',help='Explicitly allow a live API check during verification')
    args = parser.parse_args()
    from PySide6.QtCore import QStandardPaths,QCoreApplication,Qt
    from PySide6.QtWidgets import QApplication,QMessageBox
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([sys.argv[0]])
    app.setApplicationName('Fishbowl')
    app.setOrganizationName('Fishbowl')
    if args.verify_package:
        from .package_check import verify_package
        return verify_package(app,args.verify_package,args.verification_model,args.verify_live)
    log_dir = (args.data_dir.resolve() if args.data_dir else
               Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)))
    if getattr(sys,'frozen',False) and log_dir.is_relative_to(Path(sys.executable).parent):
        QMessageBox.critical(None,'Fishbowl 启动失败','用户数据目录须放在程序文件夹之外。')
        return 1
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(handlers=[RotatingFileHandler(log_dir/'fishbowl.log',maxBytes=2*1024*1024,backupCount=2,encoding='utf-8')],
                        level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        server,window = create_window(log_dir)
    except (OSError, FileNotFoundError) as error:
        QMessageBox.critical(None, 'Fishbowl 启动失败', str(error))
        return 1
    if args.benchmark_report:
        from .performance import attach_probe
        attach_probe(window,args.benchmark_report,float(os.environ.get('FISHBOWL_MEASURE_ORIGIN',START)))
    window.show()
    try:
        return app.exec()
    finally:
        window.tray.hide()
        window.close()
        server.close()


if __name__ == '__main__':
    sys.exit(main())
