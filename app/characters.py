"""Character packages and validated local model imports; no credentials in profiles."""
import json
import math
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from .memory import ConversationMemory

ROOT = Path(__file__).resolve().parents[1]
BUILTIN = ROOT / 'characters/deepseek/character.json'
ID_PATTERN = re.compile(r'[a-z0-9][a-z0-9_-]{0,63}')
PUBLIC_FIELDS = ('model_url','mask_buffers','blink_while_motion','tracking','mouth','expressions','gesture')


def valid_runtime(value):
    """Reject broken hand-edited packages before they can become the saved role."""
    try:
        if type(value['mask_buffers']) is not int or not 1<=value['mask_buffers']<=8:return False
        if type(value['blink_while_motion']) is not bool:return False
        if not all(isinstance(value['tracking'][axis],str) and value['tracking'][axis] for axis in ('x','y','z')):return False
        mouth=value['mouth']
        if not all(isinstance(mouth[k],str) for k in ('open','jaw')):return False
        scale=mouth['jaw_scale']
        if not isinstance(scale,(int,float)) or not math.isfinite(scale) or not 0<=scale<=1:return False
        expressions=value['expressions']
        if not isinstance(expressions['neutral'],str):return False
        for kind in ('manual','idle'):
            if not isinstance(expressions[kind],list) or not all(isinstance(s,str) and s for s in expressions[kind]):return False
        if (expressions['manual'] or expressions['idle']) and not expressions['neutral']:return False
        gesture=value['gesture']
        if gesture is not None:
            if not all(isinstance(gesture[k],str) and gesture[k] for k in ('group','name')):return False
            if not all(type(gesture[k]) is int and gesture[k]>=0 for k in ('enter','exit','hold_ms')):return False
            if not isinstance(gesture['parameters'],list) or not all(isinstance(s,str) and s for s in gesture['parameters']):return False
        return True
    except (KeyError,TypeError,ValueError):return False


@dataclass(frozen=True)
class Character:
    path: Path
    data: dict

    @property
    def id(self): return self.data['id']
    @property
    def name(self): return self.data['name']
    @property
    def persona(self):
        path=(self.path.parent/self.data['persona']).resolve()
        if not path.is_relative_to(self.path.parent.resolve()):
            raise ValueError('角色人格路径无效。')
        return path

    def public(self):
        return {**{k:self.data['runtime'][k] for k in PUBLIC_FIELDS},'id':self.id,'name':self.name}


class CharacterRegistry:
    def __init__(self, user_data: Path | None = None, *, renderer_root: Path | None = None):
        self.user_data = user_data.resolve() if user_data is not None else None
        self.renderer_root = renderer_root if renderer_root is not None else ROOT/'frontend/dist'
        self.characters = {}
        self.refresh()

    def refresh(self):
        paths=[BUILTIN]
        if self.user_data is not None:
            paths += list((self.user_data/'characters').glob('*/character.json'))
        found={}
        for path in paths:
            try:
                data=json.loads(path.read_text(encoding='utf-8'))
                if (not ID_PATTERN.fullmatch(data['id']) or not isinstance(data['name'],str) or
                    not data['name'].strip() or len(data['name'])>60 or not isinstance(data['runtime'],dict)):
                    continue
                if data['id'] in found: continue
                if path!=BUILTIN and path.parent.name!=data['id']:continue
                if path!=BUILTIN and not path.resolve().is_relative_to(self.user_data/'characters'):continue
                runtime=data['runtime']
                if not valid_runtime(runtime):continue
                url=runtime.get('model_url','')
                prefix='/Resources/' if path==BUILTIN else f"/character-assets/{data['id']}/"
                if not isinstance(url,str) or not url.startswith(prefix):continue
                if not isinstance(data.get('welcome',''),str):continue
                role=Character(path,data)
                role.persona  # Validate private relative path before accepting.
                found[role.id]=role
            except (OSError,ValueError,KeyError,TypeError):
                continue
        self.characters=found

    def get(self, identifier):
        return self.characters[identifier]

    def public_profile(self, identifier):
        from .interaction_config import InteractionConfig
        return {**self.get(identifier).public(), 'bindings':InteractionConfig(self,identifier).public()}

    def memory_path(self, identifier):
        if self.user_data is None or not ID_PATTERN.fullmatch(identifier):
            raise ValueError('缺少本机角色数据目录。')
        target=self.user_data/'memories'/f'{identifier}.json'
        legacy=self.user_data/'chat-memory.json'
        if identifier=='deepseek' and not target.exists() and legacy.is_file():
            store=ConversationMemory(legacy)
            store.load()
            if store.read_failed:return legacy
            if not store.read_failed:
                if not (legacy.resolve().is_relative_to(self.user_data) and target.resolve().is_relative_to(self.user_data)):
                    raise ValueError('记忆迁移路径无效。')
                try:
                    target.parent.mkdir(parents=True,exist_ok=True)
                    legacy.replace(target)
                except OSError:
                    return legacy  # Keep the existing memory usable if the move fails.
        return target

    def asset_root(self, identifier):
        role=self.get(identifier)
        if role.path==BUILTIN: return None
        root=(role.path.parent/'model').resolve()
        if not root.is_relative_to(role.path.parent.resolve()):raise ValueError('角色资源路径无效。')
        return root

    def import_model(self, entry: Path, cancelled=None):
        if self.user_data is None:
            raise ValueError('无法写入角色目录。')
        entry=entry.resolve()
        if not entry.name.endswith('.model3.json'):
            raise ValueError('请选择 .model3.json 模型入口。')
        base=entry.parent
        try:
            if entry.stat().st_size>512*1024*1024:raise ValueError()
            model=json.loads(entry.read_text(encoding='utf-8-sig'))
            refs=model['FileReferences']
            if model.get('Version')!=3 or not isinstance(refs,dict):raise ValueError()
            required=[(refs['Moc'],'.moc3')]
            textures=refs['Textures']
            if not isinstance(textures,list) or not textures:raise ValueError()
            required += [(p,'.png') for p in textures]
            for field,suffix in [('Physics','.physics3.json'),('Pose','.pose3.json'),
                                 ('DisplayInfo','.cdi3.json'),('UserData','.userdata3.json')]:
                if refs.get(field):required.append((refs[field],suffix))
            for expression in refs.get('Expressions',[]):required.append((expression['File'],'.exp3.json'))
            for motions in refs.get('Motions',{}).values():
                for motion in motions:
                    required.append((motion['File'],'.motion3.json'))
                    if motion.get('Sound'):required.append((motion['Sound'],('.wav','.mp3','.ogg')))
            files={entry}
            for relative,suffix in required:
                if not isinstance(relative,str) or not relative.endswith(suffix) or ':' in relative or Path(relative).is_absolute():
                    raise ValueError()
                path=(base/relative).resolve()
                if not path.is_relative_to(base) or not path.is_file():raise ValueError()
                files.add(path)
            total=0
            for path in files:
                total+=path.stat().st_size
                if total>512*1024*1024:raise ValueError()
                if path.suffix=='.json':json.loads(path.read_text(encoding='utf-8-sig'))
                if path.suffix=='.moc3':
                    with path.open('rb') as source:
                        if source.read(4)!=b'MOC3':raise ValueError()
        except (OSError,ValueError,KeyError,TypeError,AttributeError):
            raise ValueError('模型资源缺失、引用越界、格式无效或超过 512 MiB；请检查完整模型目录。') from None
        root=(self.user_data/'characters').resolve()
        if not root.is_relative_to(self.user_data):raise ValueError('角色目录路径无效。')
        root.mkdir(parents=True,exist_ok=True)
        staging=Path(tempfile.mkdtemp(prefix='.import-',dir=root)).resolve()
        if not staging.is_relative_to(root):raise ValueError('导入路径无效。')
        identifier='model-'+uuid.uuid4().hex[:12]
        target=(root/identifier).resolve()
        if not target.is_relative_to(root):raise ValueError('导入路径无效。')
        try:
            for source in files:
                destination=staging/'model'/source.relative_to(base)
                destination.parent.mkdir(parents=True,exist_ok=True)
                with source.open('rb') as src,destination.open('wb') as dst:
                    while chunk:=src.read(1024*1024):
                        if cancelled is not None and cancelled.is_set():raise ValueError('导入已取消。')
                        dst.write(chunk)
            name=entry.name.removesuffix('.model3.json').strip()[:60] or '新伙伴'
            runtime=json.loads((ROOT/'characters/generic.json').read_text(encoding='utf-8'))
            runtime['model_url']=f'/character-assets/{identifier}/'+quote(entry.name)
            data={'id':identifier,'name':name,'persona':'persona.txt',
                  'welcome':f'你好，我是{name}。想聊什么？','runtime':runtime}
            (staging/'persona.txt').write_text(
                f'你是 Fishbowl 的 AI 桌面伙伴“{name}”。自然、友好、简洁地用中文交流。'
                '只根据当前和历史对话延续话题，不编造记忆，不声称读取或操作用户桌面。',encoding='utf-8')
            # Browser motion audio must never bypass the native global mute/TTS path.
            for motions in refs.get('Motions',{}).values():
                for motion in motions:motion.pop('Sound',None)
            (staging/'model'/entry.name).write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
            (staging/'character.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            if cancelled is not None and cancelled.is_set():raise ValueError('导入已取消。')
            staging.rename(target)
        finally:
            if staging.exists() and staging.resolve().is_relative_to(root):
                shutil.rmtree(staging)
        # Publishing is a single dictionary assignment, after the complete package exists.
        role=Character(target/'character.json',data)
        self.characters={**self.characters,identifier:role}
        return role
