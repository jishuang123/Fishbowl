"""SSE framing over arbitrary byte chunks, including split UTF-8 and CRLF."""
import json
import re


class StreamError(ValueError):
    pass


class ChatStream:
    def __init__(self):
        self.buffer = bytearray()
        self.data_lines = []
        self.text = ''
        self.done = False
        self.finish_reason = None
        self.bytes_seen = 0
        self.calls = {}

    def feed(self, data: bytes):
        self.bytes_seen += len(data)
        if self.bytes_seen>1024*1024:
            raise StreamError('回复过大，请缩短问题后重试。')
        self.buffer.extend(data)
        updates = []
        while b'\n' in self.buffer:
            line, _, rest = self.buffer.partition(b'\n')
            self.buffer = bytearray(rest)
            line = bytes(line).removesuffix(b'\r')
            if line == b'':
                if self.data_lines:
                    text = self._event(b'\n'.join(self.data_lines))
                    self.data_lines.clear()
                    if text is not None:
                        updates.append(text)
            elif line.startswith(b'data:'):
                value = line[5:]
                self.data_lines.append(value[1:] if value.startswith(b' ') else value)
            # Ignore SSE comments/keep-alives, event names, ids, retry fields.
        return updates

    def _event(self, data):
        if self.done:
            return None
        if data.strip()==b'[DONE]':
            self.done = True
            return None
        try:
            value = json.loads(data.decode('utf-8'))
            if not isinstance(value,dict) or 'error' in value:
                raise ValueError()
            choices = value.get('choices')
            if not isinstance(choices,list):
                raise ValueError()
            if not choices:  # Optional usage-only event.
                return None
            choice = choices[0]
            if choice.get('index',0)!=0:
                return None
            delta = choice['delta']
            if not isinstance(delta,dict):
                raise ValueError()
            fragment = delta.get('content')
            if fragment is not None and not isinstance(fragment,str):
                raise ValueError()
            tool_deltas = delta.get('tool_calls')
            if tool_deltas is not None:
                if not isinstance(tool_deltas,list):raise ValueError()
                for call in tool_deltas:
                    index = call['index']
                    if type(index) is not int or not 0<=index<4:raise ValueError()
                    if call.get('type') not in (None,'function'):raise ValueError()
                    target = self.calls.setdefault(index,{'id':'','type':'function','function':{'name':'','arguments':''}})
                    for field,limit in (('id',256),):
                        value = call.get(field)
                        if value is not None:
                            if not isinstance(value,str):raise ValueError()
                            target[field] += value
                            if len(target[field])>limit:raise ValueError()
                    function = call.get('function')
                    if function is not None:
                        if not isinstance(function,dict):raise ValueError()
                        for field,limit in (('name',64),('arguments',4096)):
                            value = function.get(field)
                            if value is not None:
                                if not isinstance(value,str):raise ValueError()
                                target['function'][field] += value
                                if len(target['function'][field])>limit:raise ValueError()
            if choice.get('finish_reason') is not None:
                self.finish_reason = choice['finish_reason']
            if fragment:
                self.text += fragment
                if len(self.text)>16000:
                    raise StreamError('回复过长，请缩短问题后重试。')
                return self.text
            return None
        except StreamError:
            raise
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise StreamError('流式回复格式异常，请重试。') from None

    @property
    def complete(self):
        if self.calls:
            return (self.done and self.finish_reason=='tool_calls' and
                    len({call['id'] for call in self.calls.values()})==len(self.calls) and
                    all(re.fullmatch(r'[A-Za-z0-9_-]{1,256}',call['id']) and
                        re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,63}',call['function']['name'])
                        for call in self.calls.values()))
        return self.done and self.finish_reason in ('stop','length') and bool(self.text.strip())

    @property
    def tool_calls(self):
        return [self.calls[index] for index in sorted(self.calls)]
