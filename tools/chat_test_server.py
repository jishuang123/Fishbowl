"""Loopback HTTP fixture; never contacts DeepSeek or handles real credentials."""
import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TEST_KEY = 'local-fixture-not-a-real-api-key'


def sse(delta=None, finish=None):
    return ('data: '+json.dumps({'choices':[{'index':0,'delta':delta or {},
        'finish_reason':finish}]},ensure_ascii=False)+'\n\n').encode('utf-8')


def response_parts(text):
    return [sse({'role':'assistant'}), *[sse({'content':text[i:i+5]}) for i in range(0,len(text),5)],
            sse(finish='stop'), b'data: [DONE]\n\n']

class ChatTestServer:
    def __init__(self):
        self.responses = queue.Queue()
        self.requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.requests.append({'path':self.path, 'payload':payload,
                    'authorized':self.headers.get('Authorization') == 'Bearer '+TEST_KEY})
                try:
                    plan = owner.responses.get_nowait()
                except queue.Empty:
                    plan = {}
                time.sleep(plan.get('delay',0))
                body = plan.get('body', {'choices':[{'message':{'role':'assistant',
                    'content':'你好呀，我在鱼缸里陪你。🐟'}, 'finish_reason':'stop'}]})
                data = body if isinstance(body,bytes) else json.dumps(body,ensure_ascii=False).encode('utf-8')
                parts = plan.get('parts')
                if parts is None and payload.get('stream') and plan.get('status',200)==200:
                    try:
                        parts = response_parts(body['choices'][0]['message']['content'])
                    except (KeyError,IndexError,TypeError):
                        pass
                if parts is not None:
                    data = b''.join(part[1] if isinstance(part,tuple) else part for part in parts)
                self.send_response(plan.get('status',200))
                self.send_header('Content-Type','text/event-stream' if parts is not None else 'application/json')
                self.send_header('Content-Length',str(len(data)))
                if 'location' in plan:
                    self.send_header('Location',plan['location'])
                self.end_headers()
                try:
                    for part in (parts if parts is not None else [data]):
                        if isinstance(part,tuple):
                            time.sleep(part[0])
                            part = part[1]
                        self.wfile.write(part)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

        self.httpd = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever,daemon=True)
        self.thread.start()
        self.endpoint = f'http://127.0.0.1:{self.httpd.server_port}/chat/completions'

    def enqueue(self, **plan):
        self.responses.put(plan)

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
