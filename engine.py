"""
VoiceHarvester - core processing engine.

Extracts and isolates spoken voice from video/audio files and produces
clean WAV files suitable as input for AI voice-cloning tools
(ElevenLabs, Play.ht, RVC, XTTS, etc.).

Pipeline per file:
  1. Extract audio track with ffmpeg.
  2. Isolate voice:
       - If Demucs is installed -> deep-learning vocal separation (best quality).
       - Otherwise -> ffmpeg denoise + band-pass fallback (always works).
  3. Clean & normalize (high-pass, FFT denoise, loudness normalize) to a
     mono 44.1 kHz 16-bit WAV, the format cloning tools prefer.

Can also merge all cleaned clips into a single combined training sample.

No GUI dependencies here so the engine can be tested / scripted on its own.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from typing import Callable, List, Optional

# File types we accept as input.
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".flv", ".wmv", ".mpg", ".mpeg"}
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma", ".aiff", ".aif"}
SUPPORTED_EXTS = VIDEO_EXTS | AUDIO_EXTS

# Target output spec — widely accepted by voice-cloning services.
TARGET_SR = 44100
TARGET_CH = 1  # mono


class ProcessingError(Exception):
    pass


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def have_ffmpeg() -> bool:
    return _which("ffmpeg") is not None and _which("ffprobe") is not None


def have_demucs() -> bool:
    """Demucs gives true voice/music separation if the user installed it."""
    if _which("demucs") is not None:
        return True
    try:
        import demucs  # noqa: F401
        return True
    except Exception:
        return False


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def probe_duration(path: str) -> float:
    cp = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ])
    try:
        return float(cp.stdout.strip())
    except ValueError:
        return 0.0


def has_audio_stream(path: str) -> bool:
    cp = _run([
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ])
    return "audio" in cp.stdout


def _extract_audio(src: str, dst_wav: str) -> None:
    """Pull the raw audio track out to a high-quality WAV."""
    cp = _run([
        "ffmpeg", "-y", "-i", src, "-vn",
        "-ar", str(TARGET_SR), "-ac", "2",
        "-c:a", "pcm_s16le", dst_wav,
    ])
    if cp.returncode != 0 or not os.path.exists(dst_wav):
        raise ProcessingError(f"Audio extraction failed:\n{cp.stderr[-500:]}")


def _isolate_with_demucs(in_wav: str, work_dir: str) -> str:
    """Run Demucs and return the path to the separated vocals stem."""
    cp = _run([
        "demucs", "--two-stems", "vocals", "-o", work_dir, in_wav,
    ])
    if cp.returncode != 0:
        raise ProcessingError(f"Demucs failed:\n{cp.stderr[-500:]}")
    # Demucs writes <work_dir>/<model>/<trackname>/vocals.wav
    stem = os.path.splitext(os.path.basename(in_wav))[0]
    for root, _dirs, files in os.walk(work_dir):
        for f in files:
            if f == "vocals.wav" and stem in root:
                return os.path.join(root, f)
    # Fallback: any vocals.wav produced
    for root, _dirs, files in os.walk(work_dir):
        if "vocals.wav" in files:
            return os.path.join(root, "vocals.wav")
    raise ProcessingError("Demucs ran but no vocals stem was found.")


# ffmpeg cleanup chain. Used both as the no-Demucs fallback and as the
# final normalization pass after Demucs separation.
_CLEAN_FILTER = (
    "highpass=f=80,"          # cut low rumble / handling noise
    "lowpass=f=12000,"        # trim hiss above the vocal range
    "afftdn=nf=-25,"          # FFT denoise
    "loudnorm=I=-16:TP=-1.5:LRA=11,"  # broadcast-standard loudness
    "dynaudnorm=f=150:g=15"   # gentle dynamic leveling
)


def _clean_normalize(in_wav: str, out_wav: str) -> None:
    cp = _run([
        "ffmpeg", "-y", "-i", in_wav,
        "-af", _CLEAN_FILTER,
        "-ar", str(TARGET_SR), "-ac", str(TARGET_CH),
        "-c:a", "pcm_s16le", out_wav,
    ])
    if cp.returncode != 0 or not os.path.exists(out_wav):
        raise ProcessingError(f"Cleanup failed:\n{cp.stderr[-500:]}")


@dataclass
class FileResult:
    src: str
    out: Optional[str]
    ok: bool
    message: str
    duration: float = 0.0


def process_file(
    src: str,
    out_dir: str,
    use_demucs: Optional[bool] = None,
    log: Callable[[str], None] = print,
) -> FileResult:
    """Process one file end-to-end. Returns a FileResult."""
    name = os.path.splitext(os.path.basename(src))[0]
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip() or "clip"
    out_wav = os.path.join(out_dir, f"{safe}_voice.wav")

    if not os.path.exists(src):
        return FileResult(src, None, False, "File not found.")
    if os.path.splitext(src)[1].lower() not in SUPPORTED_EXTS:
        return FileResult(src, None, False, "Unsupported file type.")
    if not has_audio_stream(src):
        return FileResult(src, None, False, "No audio track in this file.")

    if use_demucs is None:
        use_demucs = have_demucs()

    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "raw.wav")
        log(f"  Extracting audio from {os.path.basename(src)} ...")
        _extract_audio(src, raw)

        voice = raw
        if use_demucs:
            try:
                log("  Isolating voice with Demucs (this can take a bit) ...")
                voice = _isolate_with_demucs(raw, tmp)
            except ProcessingError as e:
                log(f"  Demucs unavailable/failed, using ffmpeg cleanup. ({e})")
                voice = raw

        log("  Cleaning & normalizing ...")
        _clean_normalize(voice, out_wav)

    dur = probe_duration(out_wav)
    return FileResult(src, out_wav, True, "OK", dur)


def merge_wavs(wavs: List[str], out_path: str, gap_seconds: float = 0.6) -> str:
    """Concatenate cleaned WAVs into one combined sample with short gaps."""
    wavs = [w for w in wavs if w and os.path.exists(w)]
    if not wavs:
        raise ProcessingError("Nothing to merge.")

    # Build a silence clip matching the target spec, then concat.
    with tempfile.TemporaryDirectory() as tmp:
        silence = os.path.join(tmp, "gap.wav")
        _run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"anullsrc=r={TARGET_SR}:cl=mono",
            "-t", str(gap_seconds), "-c:a", "pcm_s16le", silence,
        ])
        list_file = os.path.join(tmp, "list.txt")
        with open(list_file, "w") as fh:
            for i, w in enumerate(wavs):
                fh.write(f"file '{os.path.abspath(w)}'\n")
                if i != len(wavs) - 1:
                    fh.write(f"file '{os.path.abspath(silence)}'\n")
        cp = _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file, "-ar", str(TARGET_SR), "-ac", str(TARGET_CH),
            "-c:a", "pcm_s16le", out_path,
        ])
        if cp.returncode != 0 or not os.path.exists(out_path):
            raise ProcessingError(f"Merge failed:\n{cp.stderr[-500:]}")
    return out_path


def process_batch(
    sources: List[str],
    out_dir: str,
    use_demucs: Optional[bool] = None,
    merge: bool = False,
    progress: Optional[Callable[[int, int, str], None]] = None,
    log: Callable[[str], None] = print,
) -> List[FileResult]:
    """Process many files. Optionally merge the clean outputs into one sample."""
    os.makedirs(out_dir, exist_ok=True)
    results: List[FileResult] = []
    total = len(sources)
    for i, src in enumerate(sources, 1):
        if progress:
            progress(i, total, os.path.basename(src))
        log(f"[{i}/{total}] {os.path.basename(src)}")
        try:
            results.append(process_file(src, out_dir, use_demucs, log))
        except ProcessingError as e:
            results.append(FileResult(src, None, False, str(e)))
            log(f"  ERROR: {e}")

    if merge:
        good = [r.out for r in results if r.ok and r.out]
        if good:
            log("Merging clean clips into one combined sample ...")
            merged = os.path.join(out_dir, "combined_voice_sample.wav")
            try:
                merge_wavs(good, merged)
                results.append(FileResult("(merged)", merged, True, "Combined sample",
                                          probe_duration(merged)))
            except ProcessingError as e:
                log(f"  Merge error: {e}")
    return results
