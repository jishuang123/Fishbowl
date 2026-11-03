"""Only complete user/assistant pairs are retained; no credentials or request logs."""
import json
from pathlib import Path
from PySide6.QtCore import QIODevice, QSaveFile


class ConversationMemory:
    def __init__(self, path: Path):
        self.path = path
        self.read_failed = False

    @staticmethod
    def valid(messages):
        return (isinstance(messages,list) and len(messages)<=20 and len(messages)%2==0 and
                all(isinstance(m,dict) and m.get('role')==('user' if i%2==0 else 'assistant') and
                    isinstance(m.get('content'),str) and m['content'].strip() and
                    len(m['content'])<=(2000 if i%2==0 else 16000) and
                    ('tool_results' not in m or (i%2==1 and ConversationMemory.valid_tools(m['tool_results'])))
                    for i,m in enumerate(messages)))

    @staticmethod
    def valid_tools(results):
        return (isinstance(results,list) and len(results)<=4 and all(
            isinstance(r,dict) and type(r.get('ok')) is bool and
            all(isinstance(r.get(k),str) and 0<len(r[k])<=limit for k,limit in
                (('name',64),('title',80),('content',4000))) for r in results))

    @staticmethod
    def project(message):
        value = {'role':message['role'],'content':message['content']}
        if message.get('tool_results'):
            value['tool_results'] = [{k:r[k] for k in ('name','title','content','ok')} for r in message['tool_results']]
        return value

    def load(self):
        try:
            if self.path.stat().st_size>1024*1024:
                raise ValueError()
            data = json.loads(self.path.read_text(encoding='utf-8'))
            messages = data['messages']
            if data.get('version')!=1 or not self.valid(messages):
                raise ValueError()
            return [self.project(m) for m in messages]
        except FileNotFoundError:
            return []
        except (OSError, ValueError, KeyError, TypeError):
            self.read_failed = True
            return []

    def save(self, messages):
        if not self.valid(messages):
            return False
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            target = QSaveFile(str(self.path))
            body = json.dumps({'version':1,'messages':[self.project(m) for m in messages]},
                ensure_ascii=False,indent=2).encode('utf-8')
            if not target.open(QIODevice.OpenModeFlag.WriteOnly):
                return False
            if target.write(body)!=len(body):
                target.cancelWriting()
                return False
            return target.commit()
        except OSError:
            return False
