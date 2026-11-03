"""Serve only the built renderer, on an ephemeral loopback port."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import json
import mimetypes
from urllib.parse import urlsplit,parse_qs,unquote
from .characters import CharacterRegistry


class RendererHandler(SimpleHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def do_GET(self):
        route=urlsplit(self.path)
        if route.path=='/character-profile.json':
            identifier=parse_qs(route.query).get('id',['deepseek'])[0]
            try:
                body=json.dumps(self.server.characters.public_profile(identifier),ensure_ascii=False).encode('utf-8')
            except KeyError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if route.path.startswith('/character-assets/'):
            parts=unquote(route.path).split('/',3)
            try:
                if len(parts)!=4:raise ValueError()
                root=self.server.characters.asset_root(parts[2])
                if root is None:raise ValueError()
                path=(root/parts[3]).resolve()
                if not path.is_relative_to(root) or not path.is_file():raise ValueError()
                self.send_response(200)
                self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
                self.send_header('Content-Length',str(path.stat().st_size))
                self.end_headers()
                with path.open('rb') as source:self.copyfile(source,self.wfile)
            except (OSError,KeyError,ValueError):
                self.send_error(404)
            return
        if self.path == '/qtwebchannel.js':
            body = self.server.channel_script
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, format, *args):
        if args and str(args[1] if len(args) > 1 else '').startswith(('4', '5')):
            super().log_message(format, *args)


class RendererHTTPServer(ThreadingHTTPServer):
    # Cubism loads many small expressions/motions at once. The default backlog
    # of five and HTTP/1.0 reconnects can introduce TCP retry delays at startup.
    request_queue_size = 64


class RendererServer:
    def __init__(self, directory: Path, characters: CharacterRegistry | None = None):
        if not (directory / 'index.html').exists():
            raise FileNotFoundError('缺少渲染页面，请先按 README 构建 frontend。')
        self.httpd = RendererHTTPServer(('127.0.0.1', 0), partial(RendererHandler, directory=str(directory)))
        self.httpd.characters = characters if characters is not None else CharacterRegistry()
        # Serve Qt's own bridge script from the same HTTP origin. An HTTP page
        # cannot load qrc:/// directly under Chromium's local resource policy.
        from PySide6.QtCore import QFile, QIODevice
        from PySide6.QtWebChannel import QWebChannel
        script = QFile(':/qtwebchannel/qwebchannel.js')
        if not script.open(QIODevice.OpenModeFlag.ReadOnly):
            self.httpd.server_close()
            raise FileNotFoundError('Qt WebChannel script is unavailable')
        self.httpd.channel_script = bytes(script.readAll())
        script.close()
        self.thread = Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.httpd.server_port}/'

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
