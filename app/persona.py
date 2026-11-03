from pathlib import Path

PERSONA_PATH = Path(__file__).resolve().parents[1] / 'characters/deepseek/persona.txt'


def load_persona(path: Path | None = None):
    try:
        text = (path or PERSONA_PATH).read_text(encoding='utf-8').strip()
        if text and len(text)<=8000:
            return text
    except (OSError, ValueError):
        pass
    return ('你是 Fishbowl 的 AI 桌面伙伴，温和、简洁，偶尔幽默。认真回应用户，'
            '不编造记忆，不声称看见或操作了用户桌面。')
