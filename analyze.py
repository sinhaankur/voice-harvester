"""
analyze — the AI layer for Voice Harvester.

Makes a mixed recording usable for cloning by breaking it into per-speaker,
per-utterance segments you can pick from:

  1. Demucs-isolate the voice (reuses engine.py).
  2. Whisper transcribe with timestamps (local, faster-whisper if available).
  3. Split into segments at natural pauses + transcript boundaries, and tag each
     with a rough "voice signature" (pitch + energy) so different speakers cluster
     into groups (Speaker A / B / C). You confirm which group is the one you want.

So from a clip of mom + dad + you, you get labeled segments and can export just
one person's — exactly what voice cloning needs.

Outputs are JSON so any UI (the cross-platform GUI, CLI, automation) can drive it.
Local + private; nothing leaves the machine.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass, asdict
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine  # noqa: E402


@dataclass
class Segment:
    index: int
    start: float
    end: float
    text: str
    pitch_hz: float           # mean fundamental-ish pitch
    energy: float             # RMS loudness 0..1
    speaker: str = "?"        # assigned group label, e.g. "A"
    @property
    def duration(self) -> float:
        return round(self.end - self.start, 2)


# ---------- pitch (autocorrelation, stdlib only) ----------
def _mean_pitch(samples: list[float], sr: int) -> float:
    """Rough mean pitch (Hz) of a voiced chunk via autocorrelation. 0 if unvoiced."""
    n = len(samples)
    if n < sr // 20:
        return 0.0
    # work in 40ms frames, take the median of voiced frames
    frame = int(sr * 0.04)
    hop = frame // 2
    pitches: list[float] = []
    lo = int(sr / 350)   # 350 Hz max
    hi = int(sr / 70)    # 70 Hz min
    i = 0
    while i + frame <= n:
        f = samples[i:i + frame]
        # remove DC
        m = sum(f) / len(f)
        f = [x - m for x in f]
        e = sum(x * x for x in f)
        if e > 1e-3:
            best_lag, best = 0, 0.0
            for lag in range(lo, min(hi, frame - 1)):
                s = 0.0
                for k in range(0, frame - lag, 2):  # stride 2 for speed
                    s += f[k] * f[k + lag]
                if s > best:
                    best, best_lag = s, lag
            if best_lag:
                pitches.append(sr / best_lag)
        i += hop
    if not pitches:
        return 0.0
    pitches.sort()
    return round(pitches[len(pitches) // 2], 1)


def _read_wav_mono(path: str) -> tuple[list[float], int]:
    w = wave.open(path, "rb")
    sr = w.getframerate()
    n = w.getnframes()
    raw = w.readframes(n)
    w.close()
    import array
    a = array.array("h")
    a.frombytes(raw)
    ch = w.getnchannels()
    data = list(a)
    if ch == 2:
        data = [(data[i] + data[i + 1]) / 2 for i in range(0, len(data) - 1, 2)]
    return [x / 32768.0 for x in data], sr


# ---------- transcription ----------
def _transcribe(path: str) -> list[dict[str, Any]]:
    """Return [{start,end,text}] via faster-whisper if available, else a single
    block (so segmentation still works on pitch/pauses alone)."""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="auto", compute_type="int8")
        segs, _ = model.transcribe(path, beam_size=1, vad_filter=True)
        return [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()} for s in segs]
    except Exception:
        return []


# ---------- main analysis ----------
def analyze(src: str, *, use_demucs: Optional[bool] = None,
            log=lambda m: None) -> dict[str, Any]:
    if not engine.have_ffmpeg():
        return {"ok": False, "error": "ffmpeg not found"}
    use_demucs = engine.have_demucs() if use_demucs is None else use_demucs

    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "raw.wav")
        log("Extracting audio…")
        engine._extract_audio(src, raw)
        voice = raw
        if use_demucs:
            try:
                log("Isolating voice (Demucs)…")
                voice = engine._isolate_with_demucs(raw, tmp)
            except engine.ProcessingError:
                voice = raw
        # normalize to mono 16k for analysis
        clean = os.path.join(tmp, "clean.wav")
        engine._run(["ffmpeg", "-y", "-i", voice, "-ar", "16000", "-ac", "1",
                     "-c:a", "pcm_s16le", clean])

        log("Transcribing…")
        words = _transcribe(clean)
        data, sr = _read_wav_mono(clean)

        # build segments: from whisper if we have it, else fixed 3s windows
        spans = ([(w["start"], w["end"], w["text"]) for w in words] if words
                 else [(t, min(t + 3, len(data) / sr), "")
                       for t in _frange(0, len(data) / sr, 3)])

        segs: list[Segment] = []
        for i, (st, en, text) in enumerate(spans):
            a, b = int(st * sr), int(en * sr)
            chunk = data[a:b]
            if not chunk:
                continue
            rms = math.sqrt(sum(x * x for x in chunk) / len(chunk))
            segs.append(Segment(i, round(st, 2), round(en, 2), text,
                                _mean_pitch(chunk, sr), round(rms, 4)))

        log("Clustering speakers by voice…")
        _assign_speakers(segs)
        return {"ok": True, "source": src, "duration": round(len(data) / sr, 1),
                "transcribed": bool(words),
                "segments": [_seg_json(s) for s in segs],
                "speakers": _speaker_summary(segs)}


def _frange(a: float, b: float, step: float):
    x = a
    while x < b:
        yield x
        x += step


def _assign_speakers(segs: list[Segment]) -> None:
    """Cluster segments into speaker groups by pitch (simple, transparent: split
    voiced segments around pitch gaps into up to 3 bands → A/B/C)."""
    voiced = [s for s in segs if s.pitch_hz > 0]
    if not voiced:
        return
    pitches = sorted(s.pitch_hz for s in voiced)
    # crude k≈ up to 3 bands using the overall pitch range
    lo, hi = pitches[0], pitches[-1]
    if hi - lo < 25:                       # everyone sounds similar → one speaker
        for s in segs:
            if s.pitch_hz > 0:
                s.speaker = "A"
        return
    t1 = lo + (hi - lo) / 3
    t2 = lo + 2 * (hi - lo) / 3
    for s in segs:
        if s.pitch_hz <= 0:
            continue
        s.speaker = "A" if s.pitch_hz < t1 else ("B" if s.pitch_hz < t2 else "C")


def _speaker_summary(segs: list[Segment]) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for s in segs:
        if s.speaker == "?":
            continue
        d = out.setdefault(s.speaker, {"speaker": s.speaker, "segments": 0,
                                       "seconds": 0.0, "pitches": []})
        d["segments"] += 1
        d["seconds"] = round(d["seconds"] + s.duration, 1)
        d["pitches"].append(s.pitch_hz)
    for d in out.values():
        ps = sorted(d.pop("pitches"))
        d["avg_pitch"] = round(sum(ps) / len(ps), 0) if ps else 0
        # a friendly hint based on typical ranges
        d["likely"] = ("lower / male-range" if d["avg_pitch"] < 145
                       else "higher / female-range" if d["avg_pitch"] > 175
                       else "mid-range")
    return sorted(out.values(), key=lambda d: -d["seconds"])


def _seg_json(s: Segment) -> dict[str, Any]:
    j = asdict(s)
    j["duration"] = s.duration
    return j


def export_speaker(src: str, speaker: str, out_path: str, *,
                   use_demucs: Optional[bool] = None,
                   pick_indices: Optional[list[int]] = None,
                   log=lambda m: None) -> dict[str, Any]:
    """Re-extract + concatenate just the chosen speaker's (or chosen segments')
    audio into one clean wav, ready for cloning."""
    res = analyze(src, use_demucs=use_demucs, log=log)
    if not res.get("ok"):
        return res
    segs = res["segments"]
    chosen = [s for s in segs
              if (pick_indices is not None and s["index"] in pick_indices)
              or (pick_indices is None and s["speaker"] == speaker)]
    if not chosen:
        return {"ok": False, "error": "no segments matched"}

    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "raw.wav")
        engine._extract_audio(src, raw)
        voice = raw
        if (engine.have_demucs() if use_demucs is None else use_demucs):
            try:
                voice = engine._isolate_with_demucs(raw, tmp)
            except engine.ProcessingError:
                voice = raw
        parts = []
        for i, s in enumerate(chosen):
            part = os.path.join(tmp, f"p{i}.wav")
            engine._run(["ffmpeg", "-y", "-i", voice, "-ss", str(s["start"]),
                         "-to", str(s["end"]), "-ar", "22050", "-ac", "1",
                         "-c:a", "pcm_s16le", part])
            parts.append(part)
        engine.merge_wavs(parts, out_path)
        # final clean-up pass (silence strip + normalize)
        tmp_out = out_path + ".tmp.wav"
        engine._clean_normalize(out_path, tmp_out)
        os.replace(tmp_out, out_path)
    dur = engine.probe_duration(out_path)
    return {"ok": True, "out": out_path, "segments": len(chosen),
            "duration": round(dur, 1)}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--export-speaker")
    ap.add_argument("--out", default="speaker.wav")
    a = ap.parse_args()
    if a.export_speaker:
        print(json.dumps(export_speaker(a.src, a.export_speaker, a.out, log=lambda m: print(m, file=sys.stderr)), indent=2))
    else:
        print(json.dumps(analyze(a.src, log=lambda m: print(m, file=sys.stderr)), indent=2))
