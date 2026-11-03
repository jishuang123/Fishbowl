"""Per-character interaction choices; model inventory and audio paths stay native."""
import json
import math
import shutil
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit
from PySide6.QtCore import QIODevice, QSaveFile

TRIGGERS = ('head', 'body', 'idle')
AUDIO_SUFFIXES = ('.wav', '.mp3', '.ogg')
LABELS = {'Blush':'脸红', 'Hearts':'爱心眼', 'Happy':'开心眼', 'Neutral':'恢复默认'}


class InteractionConfig:
    def __init__(self, registry, identifier):
        self.registry = registry
        self.identifier = identifier
        self.role = registry.get(identifier)
        self.path = (registry.user_data/'interactions'/f'{identifier}.json'
                     if registry.user_data is not None else None)
        self.audio_root = (registry.user_data/'interaction-audio'/identifier
                           if registry.user_data is not None else None)
        root = registry.asset_root(identifier)
        url = unquote(urlsplit(self.role.data['runtime']['model_url']).path)
        self.model_root = root if root is not None else registry.renderer_root/Path(url.lstrip('/')).parent
        self.model_entry = self.model_root/Path(url).name
        self.read_failed = False

    @staticmethod
    def defaults():
        return {key:{'mode':'default', 'action':'', 'expression':'', 'voice':''} for key in TRIGGERS}

    def _model_file(self, relative):
        path = (self.model_root/relative).resolve()
        if not path.is_relative_to(self.model_root.resolve()) or not path.is_file():
            raise ValueError('模型引用的资源不可用。')
        return path

    def catalog(self):
        actions, expressions, voices = {}, {}, {}
        gesture = self.role.data['runtime']['gesture']
        if gesture:
            actions['gesture'] = {'label':'抬手抚胸（完整动作）' if self.identifier=='deepseek' else gesture['name'], 'kind':'gesture'}
        try:
            model = json.loads(self.model_entry.read_text(encoding='utf-8-sig'))
            refs = model['FileReferences']
            for group, motions in refs.get('Motions',{}).items():
                if gesture and group==gesture['group']:continue
                for index, motion in enumerate(motions):
                    path = self._model_file(motion['File'])
                    data = json.loads(path.read_text(encoding='utf-8-sig'))
                    duration = float(data['Meta']['Duration'])
                    if not math.isfinite(duration) or duration<=0:continue
                    curves = data['Curves']
                    actions[f'motion:{group}:{index}'] = {
                        'label':path.name.removesuffix('.motion3.json'), 'kind':'motion',
                        'group':group, 'index':index, 'duration_ms':min(12000,int(duration*1000)+500),
                        'parameters':[c['Id'] for c in curves if c.get('Target')=='Parameter'],
                        'parts':[c['Id'] for c in curves if c.get('Target')=='PartOpacity']}
            for expression in refs.get('Expressions',[]):
                self._model_file(expression['File'])
                name = expression['Name']
                if name!=self.role.data['runtime']['expressions']['neutral']:
                    expressions[name] = {'label':LABELS.get(name,name.removeprefix('Custom:'))}
        except (OSError,ValueError,KeyError,TypeError):
            pass  # Missing prepared assets remain an explicit renderer error, not a settings crash.
        if self.model_root.is_dir():
            for path in sorted(self.model_root.rglob('*')):
                if path.suffix.lower() in AUDIO_SUFFIXES and path.is_file() and path.resolve().is_relative_to(self.model_root.resolve()):
                    voices['model/'+path.relative_to(self.model_root).as_posix()] = {'label':path.stem+'（模型音频）'}
        if self.audio_root is not None and self.audio_root.is_dir():
            for path in sorted(self.audio_root.iterdir()):
                if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES:
                    voices['user/'+path.name] = {'label':path.stem.rsplit('-',1)[0]+'（已导入）'}
        return {'actions':actions, 'expressions':expressions, 'voices':voices}

    def validate(self, rows):
        catalog = self.catalog()
        result = self.defaults()
        for key in TRIGGERS:
            row = rows[key]
            if row['mode'] not in ('default','custom','off'):raise ValueError('互动方式无效。')
            if row['mode']!='custom':
                result[key]['mode'] = row['mode']
                continue
            result[key]['mode'] = 'custom'
            for field, group in (('action','actions'),('expression','expressions'),('voice','voices')):
                choice = row[field]
                if not isinstance(choice,str) or (choice and choice not in catalog[group]):
                    raise ValueError('选择的资源已不可用，请重新选择后保存。')
                result[key][field] = choice
        return result

    def load(self):
        self.read_failed = False
        if self.path is None:return self.defaults()
        try:
            if self.path.stat().st_size>64*1024:raise ValueError()
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data['version']!=1:raise ValueError()
            return self.validate(data['triggers'])
        except FileNotFoundError:return self.defaults()
        except (OSError,ValueError,KeyError,TypeError):
            self.read_failed = True
            return self.defaults()

    def save(self, rows):
        if self.path is None:raise ValueError('无法保存本机角色设置。')
        rows = self.validate(rows)
        body = json.dumps({'version':1,'triggers':rows},ensure_ascii=False,indent=2).encode('utf-8')
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            target = QSaveFile(str(self.path))
            if not target.open(QIODevice.OpenModeFlag.WriteOnly):raise OSError()
            if target.write(body)!=len(body):
                target.cancelWriting()
                raise OSError()
            if not target.commit():raise OSError()
        except OSError:raise ValueError('无法保存互动设置，请检查用户目录权限。') from None

    def public(self):
        rows = self.load()
        catalog = self.catalog() if any(r['mode']=='custom' for r in rows.values()) else None
        return {key:{'mode':row['mode'], 'action':catalog['actions'].get(row['action']) if catalog else None,
                     'expression':row['expression'], 'voice':bool(row['voice'])} for key,row in rows.items()}

    def voice_path(self, trigger):
        key = self.load()[trigger]['voice']
        if not key:return None
        origin, relative = key.split('/',1)
        root = self.audio_root if origin=='user' else self.model_root
        path = (root/relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():return None
        return path

    def import_voice(self, source):
        source = Path(source).resolve()
        if self.audio_root is None or source.suffix.lower() not in AUDIO_SUFFIXES or not source.is_file():
            raise ValueError('请选择 WAV、MP3 或 OGG 音频。')
        if not 0<source.stat().st_size<=32*1024*1024:raise ValueError('音频须小于等于 32 MiB，且不能为空。')
        self.audio_root.mkdir(parents=True,exist_ok=True)
        if not self.audio_root.resolve().is_relative_to(self.registry.user_data):raise ValueError('音频目录无效。')
        target = self.audio_root/(source.stem[:40]+'-'+uuid.uuid4().hex[:8]+source.suffix.lower())
        # Only complete files become selectable. The original is never changed.
        temporary = target.with_suffix('.importing')
        try:
            shutil.copyfile(source,temporary)
            temporary.replace(target)
        finally:
            if temporary.exists():temporary.unlink()
        return 'user/'+target.name
