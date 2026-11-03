"""Read-only audio inventory of the supplied model archive."""
import argparse
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--model-zip', type=Path)
args = parser.parse_args()
archive = args.model_zip or next(ROOT.glob('DeepSeek*.zip'))
extensions = {'.wav','.mp3','.ogg','.oga','.opus','.flac','.m4a','.aac','.wma','.aif','.aiff','.weba','.mp4','.webm'}
result = {'archive':archive.name, 'fileCount':0, 'audioFiles':[], 'mediaHeaders':[],
          'motionSoundReferences':[], 'hotkeySoundConfigs':0, 'activeSoundConfigs':0,
          'soundSlotCount':0, 'soundTriggerCount':0}
with zipfile.ZipFile(archive) as z:
    for info in z.infolist():
        if info.is_dir():
            continue
        result['fileCount'] += 1
        name = info.filename if info.flag_bits & 0x800 else info.filename.encode('cp437').decode('gbk')
        if Path(name).suffix.lower() in extensions:
            result['audioFiles'].append(name)
        with z.open(info) as source:
            header = source.read(16)
        if (header.startswith((b'ID3',b'OggS',b'fLaC')) or
            (header.startswith(b'RIFF') and header[8:12] == b'WAVE') or header[4:8] == b'ftyp'):
            result['mediaHeaders'].append(name)
        if name.endswith('.model3.json'):
            model = json.loads(z.read(info))
            for motions in model.get('FileReferences',{}).get('Motions',{}).values():
                result['motionSoundReferences'].extend(m['Sound'] for m in motions if m.get('Sound'))
        if name.endswith('.vtube.json'):
            config = json.loads(z.read(info))
            for hotkey in config.get('Hotkeys',[]):
                sound = hotkey.get('SoundConfig')
                if isinstance(sound,dict):
                    result['hotkeySoundConfigs'] += 1
                    result['activeSoundConfigs'] += int(bool(sound.get('SoundActive')))
                    result['soundSlotCount'] += len(sound.get('SoundSlots',[]))
            result['soundTriggerCount'] += len(config.get('ParameterCustomization',{}).get('SoundTriggers',[]))
out = ROOT / '.local/evidence/audio'
out.mkdir(parents=True, exist_ok=True)
(out / 'resource-inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
