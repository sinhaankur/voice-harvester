"""
harvest_runner — a thin JSON-streaming wrapper around engine.py, for the native
macOS app (or any GUI/automation) to drive.

Usage:
  python harvest_runner.py --out DIR [--demucs 0|1] [--merge 0|1] FILE [FILE ...]
  python harvest_runner.py --check     # report ffmpeg/demucs availability as JSON

It prints one JSON object per line to stdout so a host UI can show live progress:
  {"event":"start","total":N}
  {"event":"file","i":1,"total":N,"name":"clip.mov"}
  {"event":"log","msg":"..."}
  {"event":"result","ok":true,"src":"...","out":"...","duration":12.3,"message":"OK"}
  {"event":"done","ok":3,"failed":0,"out":"DIR"}
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# import the existing engine (same folder)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine  # noqa: E402


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--out", default=os.path.expanduser("~/VoiceHarvester_output"))
    ap.add_argument("--demucs", default="auto")
    ap.add_argument("--merge", default="0")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if args.check:
        emit({"event": "check",
              "ffmpeg": engine.have_ffmpeg(),
              "demucs": engine.have_demucs()})
        return 0

    if not args.files:
        emit({"event": "done", "ok": 0, "failed": 0, "out": args.out})
        return 0
    if not engine.have_ffmpeg():
        emit({"event": "error", "msg": "ffmpeg not found on PATH"})
        return 2

    use_demucs = None if args.demucs == "auto" else args.demucs in ("1", "true", "yes")
    merge = args.merge in ("1", "true", "yes")
    os.makedirs(args.out, exist_ok=True)
    total = len(args.files)
    emit({"event": "start", "total": total})

    def progress(i, t, name):
        emit({"event": "file", "i": i, "total": t, "name": name})

    def log(msg):
        emit({"event": "log", "msg": str(msg)})

    results = engine.process_batch(
        args.files, args.out, use_demucs=use_demucs, merge=merge,
        progress=progress, log=log,
    )
    ok = 0
    for r in results:
        if r.ok:
            ok += 1
        emit({"event": "result", "ok": r.ok, "src": r.src, "out": r.out,
              "duration": round(r.duration, 2), "message": r.message})
    emit({"event": "done", "ok": ok, "failed": len(results) - ok, "out": args.out})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
