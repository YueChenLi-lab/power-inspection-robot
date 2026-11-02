"""Export an OPTIONAL Vosk grammar candidate. Does not import an ASR engine."""
import json
from pathlib import Path

from .safety import action_markers


def export_vosk_grammar(config_path):
    data = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("engine") != "vosk":
        raise ValueError("这里只导出Vosk语法候选；SenseVoice热词不受支持")
    phrases = data.get("phrases")
    if not isinstance(phrases, list) or not phrases or any(
        not isinstance(word, str) or not word.strip() or action_markers(word) for word in phrases
    ):
        raise ValueError("候选需非空，且不包含控制词")
    return {"grammar_json": json.dumps(list(dict.fromkeys([*phrases, "[unk]"])), ensure_ascii=False),
            "applied": False, "requires_model_verification": True,
            "note": "仅导出；模型词表与动态图兼容性、实际语音效果必须独立验证"}
