"""Check prospective public source files and staged blobs without printing secrets."""
import base64
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {'.gitignore', 'README.md', 'LICENSE', 'Fishbowl.spec', '启动鱼缸.cmd',
              'requirements.txt', 'requirements-dev.txt', 'requirements-build.txt'}
EXACT = {'assets/audio/cues.json', 'assets/icons/fish.svg',
         'characters/deepseek/character.json', 'characters/deepseek/persona.txt',
         'characters/generic.json', 'packaging/version.txt', 'frontend/index.html',
         'frontend/package.json', 'frontend/package-lock.json', 'frontend/tsconfig.json',
         'frontend/vite.config.ts', 'app/synthesize.ps1'}
SOURCE = {'app': '.py', 'tools': '.py', 'docs': '.md'}
PRIVATE_DIRS = {'.local', '.venv', 'memories', 'interactions', 'interaction-audio',
                'user-data', 'node_modules', '__pycache__', 'build', 'dist'}
TOKEN = re.compile(rb'(?<![\w-])sk-[A-Za-z0-9_-]{20,}')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def allowed(name):
    path = PurePosixPath(name)
    if any(part.lower() in PRIVATE_DIRS for part in path.parts):
        return False
    return (name in ROOT_FILES or name in EXACT
            or (len(path.parts) > 1 and path.suffix == SOURCE.get(path.parts[0]))
            or (path.parts[:2] == ('frontend', 'src') and path.suffix == '.ts'))


def credential_patterns():
    keys = [os.environ.get('DEEPSEEK_API_KEY', '')]
    local = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
    try:
        keys.append(json.loads((local / 'Fishbowl/Fishbowl/deepseek.json').read_text(
            encoding='utf-8')).get('api_key', ''))
    except FileNotFoundError:
        pass
    return {pattern for key in keys if isinstance(key, str) and key.strip()
            for pattern in (key.strip().encode(), key.strip().encode('utf-16-le'),
                            base64.b64encode(key.strip().encode()))}


def main():
    names = set(git('ls-files', '-z', '--cached', '--others', '--exclude-standard')
                .decode('utf-8').rstrip('\0').split('\0')) - {''}
    staged = {}
    for entry in git('ls-files', '-z', '--stage').decode('utf-8').split('\0'):
        if entry:
            metadata, name = entry.split('\t', 1)
            mode, blob, stage = metadata.split()
            staged.setdefault(name, []).append((mode, blob))
    patterns = credential_patterns()

    def has_key(data):
        return (any(pattern in data for pattern in patterns) or TOKEN.search(data)
                or (b'\0' in data and TOKEN.search(data.replace(b'\0', b''))))

    def inspect(name, data, location):
        if has_key(data):
            errors.append(f'{location}包含疑似凭据：{name}')
        if not name.endswith('.json'):
            return
        try:
            value = json.loads(data)
        except (ValueError, UnicodeError):
            errors.append(f'{location}包含无效 JSON：{name}')
            return
        if isinstance(value, dict) and (
                'api_key' in value or 'messages' in value or 'character_id' in value
                or isinstance(value.get('audio'), dict) and 'muted' in value['audio']):
            errors.append(f'{location}疑似包含个人数据：{name}')
        if name == 'assets/audio/cues.json' and value != {'sounds': {}, 'voices': {}}:
            errors.append(f'{location}音频清单须保持默认空值：{name}')

    errors = []
    for name in sorted(names):
        if has_key(name.encode()):
            errors.append('文件名包含疑似凭据（名称已隐藏）')
            continue
        if not allowed(name):
            errors.append(f'不在公开源码清单：{name}')
            continue
        path = ROOT / name
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            errors.append(f'不允许发布链接：{name}')
            continue
        if path.is_file():
            inspect(name, path.read_bytes(), '工作区')
        for mode, blob in staged.get(name, []):
            if mode not in ('100644', '100755'):
                errors.append(f'暂存区包含链接或子模块：{name}')
            else:
                inspect(name, git('cat-file', 'blob', blob), '暂存区')
    for error in errors:
        print(error)
    print(f'公开源码候选 {len(names)} 个，问题 {len(errors)} 项；'
          f'已对照本机凭据：{"是" if patterns else "无可用凭据"}。')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
