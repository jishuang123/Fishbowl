"""Small, atomic user settings store outside the installation directory."""
import json
import logging
from pathlib import Path
from PySide6.QtCore import QIODevice, QSaveFile, QStandardPaths


class UserSettings:
    def __init__(self, path: Path | None = None):
        self.path = path if path is not None else Path(QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppLocalDataLocation)) / 'settings.json'
        self.data = {}
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(value, dict):
                self.data = value
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            logging.warning('Cannot read settings: %s', self.path)

    @property
    def muted(self) -> bool:
        audio = self.data.get('audio', {})
        return isinstance(audio, dict) and audio.get('muted') is True

    def save_muted(self, muted: bool):
        audio = self.data.get('audio')
        if not isinstance(audio, dict):
            audio = self.data['audio'] = {}
        audio['muted'] = muted
        self._save()

    def save_character(self, identifier):
        self.data['character_id'] = identifier
        self._save()

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            target = QSaveFile(str(self.path))
            body = json.dumps(self.data, ensure_ascii=False, indent=2).encode('utf-8')
            if not target.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(target.errorString())
            if target.write(body) != len(body):
                target.cancelWriting()
                raise OSError('Incomplete settings write')
            if not target.commit():
                raise OSError(target.errorString())
        except OSError as error:
            logging.warning('Cannot save user settings: %s', error)
