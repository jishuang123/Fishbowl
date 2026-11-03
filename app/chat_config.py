"""Secrets stay in the native process and in the user's local data directory."""
import json
import os
from pathlib import Path
from PySide6.QtCore import QIODevice, QSaveFile

MODELS = ('deepseek-flash', 'deepseek-v4-pro')


class LocalChatConfig:
    def __init__(self, path: Path):
        self.path = path

    def read(self):
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def credentials(self):
        data = self.read()
        key = os.environ.get('DEEPSEEK_API_KEY', '').strip() or data.get('api_key', '')
        key = key.strip() if isinstance(key, str) else ''
        model = data.get('model', MODELS[0])
        return key, model if model in MODELS else MODELS[0]

    def save(self, key: str, model: str):
        if model not in MODELS or any(c.isspace() for c in key):
            raise ValueError('请检查 Key 和模型设置。')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            target = QSaveFile(str(self.path))
            payload = json.dumps({'api_key':key, 'model':model}, ensure_ascii=False, indent=2).encode('utf-8')
            if not target.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError()
            if target.write(payload) != len(payload):
                target.cancelWriting()
                raise OSError()
            if not target.commit():
                raise OSError()
        except OSError:
            raise ValueError('无法保存本机设置，请检查用户目录是否可写。') from None
