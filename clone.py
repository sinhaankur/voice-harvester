"""
clone — the voice engine for Voice Harvester.

Turns a short harvested sample (~6–10s of clean speech is enough) into a voice you
can make say *anything*, in *any* of XTTS-v2's 17 languages — locally, on your own
machine. This completes the tool: harvest a voice → clone it → speak.

Powered by Coqui XTTS-v2 (zero-shot multilingual cloning). Auto-detects the
language of the text (Devanagari/Hinglish → Hindi, etc.), or you can force one.

Setup once:  pip install coqui-tts torch torchaudio torchcodec
(or use the helper a host app ships). Falls back gracefully (is_ready() = False)
when the engine isn't installed, so the rest of Voice Harvester still works.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

# XTTS-v2 supported languages.
LANGS = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "it": "Italian", "pt": "Portuguese", "pl": "Polish", "tr": "Turkish",
    "ru": "Russian", "nl": "Dutch", "cs": "Czech", "ar": "Arabic",
    "zh-cn": "Chinese", "ja": "Japanese", "hu": "Hungarian", "ko": "Korean",
    "hi": "Hindi",
}

_HINGLISH = {
    "beta", "beti", "hai", "nahi", "nahin", "kya", "kaise", "theek", "accha",
    "haan", "ji", "khana", "ghar", "maa", "papa", "pyaar", "namaste", "bhai",
    "mummy", "didi",
}


def _python() -> str:
    """The interpreter that has the TTS engine. Prefer a known venv, else self."""
    cand = os.environ.get("VH_TTS_PYTHON")
    if cand and os.path.exists(cand):
        return cand
    venv = os.path.expanduser("~/.cognitive-twin/tts-venv/bin/python")
    if os.path.exists(venv):
        return venv
    return sys.executable


_engine_cache = None  # None=unknown, ""=none, "xtts"=available


def detect_engine() -> str:
    global _engine_cache
    if _engine_cache is not None:
        return _engine_cache
    py = _python()
    try:
        r = subprocess.run([py, "-c", "import TTS"], capture_output=True, timeout=25)
        _engine_cache = "xtts" if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        _engine_cache = ""
    return _engine_cache


def is_ready() -> bool:
    return detect_engine() == "xtts"


def detect_language(text: str) -> str:
    if any('ऀ' <= c <= 'ॿ' for c in text):
        return "hi"
    words = [w.strip(".,!?").lower() for w in text.split()]
    if words and sum(1 for w in words if w in _HINGLISH) >= max(1, len(words) * 0.15):
        return "hi"
    return "en"


def speak(reference_wav: str, text: str, out_wav: str, *,
          language: str | None = None) -> dict:
    """Clone `reference_wav` and render `text` to `out_wav` in the given (or
    auto-detected) language. Returns {ok, out, language} or {ok:False, error}."""
    if not is_ready():
        return {"ok": False, "error": "voice engine not installed (pip install coqui-tts torch torchcodec)"}
    if not os.path.isfile(reference_wav):
        return {"ok": False, "error": f"reference not found: {reference_wav}"}
    lang = (language or detect_language(text)).lower()
    if lang not in LANGS:
        lang = "en"
    py = _python()
    code = (
        "import sys;from TTS.api import TTS;"
        "t=TTS('tts_models/multilingual/multi-dataset/xtts_v2');"
        "t.tts_to_file(text=sys.argv[1], speaker_wav=sys.argv[2], language=sys.argv[3], "
        "file_path=sys.argv[4], temperature=0.6, repetition_penalty=3.0, top_p=0.85)"
    )
    try:
        env = dict(os.environ, COQUI_TOS_AGREED="1")
        r = subprocess.run([py, "-c", code, text, reference_wav, lang, out_wav],
                           capture_output=True, timeout=240, env=env)
        if r.returncode == 0 and os.path.isfile(out_wav):
            return {"ok": True, "out": out_wav, "language": lang}
        return {"ok": False, "error": (r.stderr.decode("utf-8", "replace")[-300:] or "render failed")}
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": str(e)}


def status() -> str:
    return (f"voice engine: READY (XTTS-v2, {len(LANGS)} languages)"
            if is_ready() else
            "voice engine: not installed — pip install coqui-tts torch torchcodec")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref"); ap.add_argument("--text"); ap.add_argument("--out", default="cloned.wav")
    ap.add_argument("--lang")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status or not a.ref:
        print(json.dumps({"status": status(), "ready": is_ready(),
                          "languages": LANGS}, indent=2)); sys.exit(0)
    print(json.dumps(speak(a.ref, a.text or "Hello.", a.out, language=a.lang), indent=2))
