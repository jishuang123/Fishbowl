"""Prepare local licensed SDK/sample/model inputs without changing the source ZIP."""
import argparse
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK_NAME = 'CubismSdkForWeb-5-r.5'
PROFILE = json.loads((ROOT/'characters/deepseek/character.json').read_text(encoding='utf-8'))
PLAN = PROFILE['prepare']


def prepare(archive: Path, sdk_zip: Path):
    cache = ROOT / '.local'
    sdk = cache / 'sdk' / SDK_NAME
    # Unpack into a fixed local directory; reject paths outside that directory.
    with zipfile.ZipFile(sdk_zip) as z:
        required = ('LICENSE.md', 'Core/live2dcubismcore.js',
                    'Framework/src/live2dcubismframework.ts', 'Samples/TypeScript/Demo/src/lappdelegate.ts')
        if any(f'{SDK_NAME}/{name}' not in z.namelist() for name in required):
            raise ValueError(f'Use the complete official {SDK_NAME}.zip')
        base = (cache / 'sdk').resolve()
        for name in z.namelist():
            if not (base / name).resolve().is_relative_to(base):
                raise ValueError(f'Unsafe SDK path: {name}')
        z.extractall(base)

    frontend = ROOT / 'frontend'
    vendor = frontend / 'vendor'
    shutil.copytree(sdk / 'Samples/TypeScript/Demo/src', vendor, dirs_exist_ok=True)
    public = frontend / 'public'
    shutil.copytree(sdk / 'Core', public / 'Core', dirs_exist_ok=True)
    shutil.copytree(sdk / 'Framework/Shaders', public / 'Framework/Shaders', dirs_exist_ok=True)
    model_dir = public / 'Resources' / PLAN['output_directory']
    model_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            name = info.filename
            if not info.flag_bits & 0x800:
                name = name.encode('cp437').decode('gbk')
            parts = name.split('/')
            if len(parts) < 3 or parts[1] != PLAN['source_directory'] or info.is_dir():
                continue
            target = model_dir.joinpath(*parts[2:]).resolve()
            if not target.is_relative_to(model_dir.resolve()):
                raise ValueError(f'Unsafe model path: {name}')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(info))
    entries = [model_dir/PLAN['source_entry']]
    if len(entries) != 1:
        raise ValueError('Expected exactly one original model entry')
    model = json.loads(entries[0].read_text(encoding='utf-8-sig'))
    adapted = model_dir / 'Fishbowl'
    adapted.mkdir(exist_ok=True)
    # Original gesture exports loop forever; local copies play once.
    motions = PLAN['motions']
    for index, name in enumerate(motions):
        motion = json.loads((model_dir / f'Animation/{name}.motion3.json').read_text(encoding='utf-8-sig'))
        if any(c['Id'] in ['ParamEyeLOpen', 'ParamEyeROpen'] for c in motion['Curves']):
            raise ValueError('Click gestures must not own eyelid parameters')
        motion['Meta']['Loop'] = False
        motion['FadeInTime'] = 0.15
        motion['FadeOutTime'] = 0.15
        (adapted / f'gesture-{index}.motion3.json').write_text(json.dumps(motion), encoding='utf-8')
    model['FileReferences']['Motions'] = {PROFILE['runtime']['gesture']['group']: [
        {'File': f'Fishbowl/gesture-{i}.motion3.json', 'FadeInTime': 0.15, 'FadeOutTime': 0.15}
        for i in range(2)]}
    # Additional model motions are explicit settings choices, never automatic defaults.
    model['FileReferences']['Motions']['Custom'] = [
        {'File':path.relative_to(model_dir).as_posix()} for path in sorted((model_dir/'Animation').glob('*.motion3.json'))]
    # Complete mutually exclusive expression values so a new expression cannot
    # retain the previous eye shape. Originals remain available and unmodified.
    keys = PLAN['expression_keys']
    expressions = list(PLAN['expressions'].items())
    model['FileReferences']['Expressions'] = []
    for identifier, name in expressions:
        values = dict.fromkeys(keys, 0)
        if name:
            original = json.loads((model_dir / f'Exp3/{name}.exp3.json').read_text(encoding='utf-8-sig'))
            values.update({p['Id']: p['Value'] for p in original['Parameters']})
        expr = {'Type': 'Live2D Expression', 'FadeInTime': 0.2, 'FadeOutTime': 0.2,
                'Parameters': [{'Id': k, 'Value': v, 'Blend': 'Overwrite'} for k, v in values.items()]}
        (adapted / f'{identifier}.exp3.json').write_text(json.dumps(expr), encoding='utf-8')
        model['FileReferences']['Expressions'].append({'Name': identifier, 'File': f'Fishbowl/{identifier}.exp3.json'})
    for path in sorted((model_dir/'Exp3').glob('*.exp3.json')):
        model['FileReferences']['Expressions'].append({
            'Name':'Custom:'+path.name.removesuffix('.exp3.json'), 'File':path.relative_to(model_dir).as_posix()})
    (model_dir / PLAN['output_entry']).write_text(
        json.dumps(model, ensure_ascii=False, indent=2), encoding='utf-8')

    def patch(name, change):
        path = vendor / name
        path.write_text(change(path.read_text(encoding='utf-8-sig')), encoding='utf-8')

    patch('lappdefine.ts', lambda s: re.sub(
        r'export const ModelDir: string\[\] = \[.*?\];',
        "export const ModelDir: string[] = ['Character'];", s, flags=re.S)
        .replace("'../../Resources/'", "'/Resources/'")
        .replace("'../../Framework/Shaders/WebGL/'", "'/Framework/Shaders/WebGL/'")
        .replace('export const DebugLogEnable = true;', 'export const DebugLogEnable = false;'))
    patch('lappdefine.ts', lambda s: "import { currentCharacter } from '../src/character';\n"+s+
          '\nexport const CharacterProfile = currentCharacter;\n')
    patch('lapplive2dmanager.ts', lambda s: s.replace(
        "const modelPath: string = LAppDefine.ResourcesPath + model + '/';",
        "const modelPath: string = new URL(LAppDefine.CharacterProfile.model_url, location.href).href.replace(/[^/]*$/, '');")
        .replace('let modelJsonName: string = LAppDefine.ModelDir[index];',
                 "let modelJsonName: string = LAppDefine.CharacterProfile.model_url.split('/').pop();")
        .replace("modelJsonName += '.model3.json';",''))
    patch('lappsubdelegate.ts', lambda s: s.replace(
        'gl.clearColor(0.0, 0.0, 0.0, 1.0);', 'gl.clearColor(0.0, 0.0, 0.0, 0.0);')
        .replace('export class LAppSubdelegate {',
                 'export class LAppSubdelegate {\n  public onFrameRendered?: (now: number) => void;')
        .replace('this._view.render();', 'this._view.render();\n    this.onFrameRendered?.(performance.now());'))
    patch('lappmodel.ts', lambda s: s.replace(
        'export class LAppModel extends CubismUserModel {',
        '''export class LAppModel extends CubismUserModel {
  // DeepSeek has 49 active masks; one default buffer supports only 36.
  public createRenderer(width: number, height: number, maskBufferCount = LAppDefine.CharacterProfile.mask_buffers): void {
    super.createRenderer(width, height, maskBufferCount);
  }
  public mouthLevel = 0;
  public mouthActive = false;
'''))
    # This model's physics consumes AngleX/Y/Z and outputs ParamAngleX/Y/Z.
    # Only the curated hand motions are registered; neither owns the eyelids.
    patch('lappmodel.ts', lambda s: s.replace('() => this._motionUpdated,',
          '() => this._motionUpdated && !LAppDefine.CharacterProfile.blink_while_motion,')
          .replace('CubismDefaultParameterId.ParamAngleX', 'LAppDefine.CharacterProfile.tracking.x')
          .replace('CubismDefaultParameterId.ParamAngleY', 'LAppDefine.CharacterProfile.tracking.y')
          .replace('CubismDefaultParameterId.ParamAngleZ', 'LAppDefine.CharacterProfile.tracking.z'))
    patch('lappmodel.ts', lambda s: "import { NativeMouthUpdater } from '../src/mouth_updater';\n"+s.replace(
        'this._updateScheduler = new CubismUpdateScheduler();',
        'this._updateScheduler = new CubismUpdateScheduler();\n    this._updateScheduler.addUpdatableList(new NativeMouthUpdater(this));'))
    patch('lappdelegate.ts', lambda s: s.replace('this.initializeEventListener();',
          '// Fishbowl owns pointer input to distinguish click from drag.'))
    patch('lappdelegate.ts', lambda s: "import { FrameClock } from '../src/frame_clock';\n"+s.replace(
        '// メインループ\n    const loop', '// メインループ\n    const clock = new FrameClock();\n    const loop').replace(
        '      // 時間更新\n      LAppPal.updateTime();',
        '      if (!clock.due(performance.now(), document.hidden)) { requestAnimationFrame(loop); return; }\n      // 時間更新\n      LAppPal.updateTime();'))
    patch('lapptexturemanager.ts', lambda s: re.sub(
        r'        // 2回目以降.*?this\._textures\[i\]\.img\.src = fileName;',
        '        callback(this._textures[i]);',s,flags=re.S).replace(
        'textureInfo.img = img;', 'textureInfo.img = null; // The GPU texture owns its pixels; do not retain decoded PNGs.').replace(
        '        // テクスチャオブジェクトの作成',
        "        const limit = this._glManager.getGl().getParameter(this._glManager.getGl().MAX_TEXTURE_SIZE);\n        if (img.width > limit || img.height > limit) throw new Error('模型贴图超过显卡支持的尺寸');\n        // テクスチャオブジェクトの作成"))
    # Keep the official model/render/update pipeline; remove the demo scenery and gear.
    patch('lappview.ts', lambda s: re.sub(
        r'  public initializeSprite\(\): void \{.*?\n  \}',
        '''  public initializeSprite(): void {
    if (this._programId == null) this._programId = this._subdelegate.createShader();
  }''', s, flags=re.S)
        .replace('this._gear.release();', 'this._gear?.release();')
        .replace('this._back.release();', 'this._back?.release();')
        .replace('this._gear.isHit(posX, posY)', 'this._gear?.isHit(posX, posY)'))

    # Prepare a separate official demo for reproducing the initial compatibility
    # check: original scenery and interactions, only model and mask count differ.
    demo = sdk / 'Samples/TypeScript/Demo'
    shutil.copytree(model_dir, sdk / 'Samples/Resources' / PLAN['output_directory'], dirs_exist_ok=True)
    # Keep the official compatibility demo on the original entry without added gestures.
    (sdk / 'Samples/Resources' / PLAN['output_directory'] / PLAN['output_entry']).write_bytes(entries[0].read_bytes())
    path = demo / 'src/lappdefine.ts'
    path.write_text(re.sub(r'export const ModelDir: string\[\] = \[.*?\];',
                          "export const ModelDir: string[] = ['DeepSeek'];",
                          path.read_text(encoding='utf-8-sig'), flags=re.S), encoding='utf-8')
    path = demo / 'src/lappmodel.ts'
    path.write_text(path.read_text(encoding='utf-8-sig').replace(
        'export class LAppModel extends CubismUserModel {',
        '''export class LAppModel extends CubismUserModel {
  public createRenderer(width: number, height: number, maskBufferCount = 2): void {
    super.createRenderer(width, height, maskBufferCount);
  }
'''), encoding='utf-8')
    path = demo / 'index.html'
    path.write_text(path.read_text(encoding='utf-8-sig').replace(
        '<head>', '<head><link rel="icon" href="data:,">'), encoding='utf-8')
    print('Prepared official R5 sample, Core, shaders, and local model in frontend/.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-zip', type=Path)
    parser.add_argument('--sdk-zip', type=Path, default=ROOT / '.local' / f'{SDK_NAME}.zip',
                        help='Official Cubism Web 5 R5 ZIP obtained from Live2D')
    args = parser.parse_args()
    if args.model_zip is None:
        candidates = list(ROOT.glob(PLAN['archive_glob']))
        if len(candidates) != 1:
            parser.error('Pass --model-zip with the original DeepSeek model ZIP.')
        args.model_zip = candidates[0]
    if not args.model_zip.is_file():
        parser.error('Model ZIP does not exist. Check --model-zip.')
    if not args.sdk_zip.is_file():
        parser.error(f'Pass --sdk-zip with {SDK_NAME}.zip obtained from Live2D.')
    try:
        prepare(args.model_zip, args.sdk_zip)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.error(str(error))
