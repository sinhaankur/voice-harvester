"""
VoiceHarvester - command-line interface (for batch folders / no-GUI use).

Examples:
  python cli.py file1.mp4 file2.mov -o out/
  python cli.py /path/to/folder -o out/ --merge
  python cli.py *.mp4 -o out/ --no-demucs
"""

import argparse
import os
import sys

import engine


def collect(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for f in sorted(os.listdir(p)):
                full = os.path.join(p, f)
                if os.path.splitext(full)[1].lower() in engine.SUPPORTED_EXTS:
                    files.append(full)
        elif os.path.splitext(p)[1].lower() in engine.SUPPORTED_EXTS:
            files.append(p)
    return files


def main():
    ap = argparse.ArgumentParser(description="Extract clean voice for AI tools.")
    ap.add_argument("inputs", nargs="+", help="Files and/or folders.")
    ap.add_argument("-o", "--out", default="voiceharvester_output", help="Output folder.")
    ap.add_argument("--merge", action="store_true", help="Also merge into one sample.")
    ap.add_argument("--no-demucs", action="store_true", help="Force ffmpeg cleanup only.")
    args = ap.parse_args()

    if not engine.have_ffmpeg():
        sys.exit("ffmpeg/ffprobe not found. Install ffmpeg and retry.")

    files = collect(args.inputs)
    if not files:
        sys.exit("No supported media files found.")

    use_demucs = False if args.no_demucs else None
    results = engine.process_batch(files, args.out, use_demucs=use_demucs,
                                   merge=args.merge)
    ok = sum(1 for r in results if r.ok)
    print(f"\nDone. {ok}/{len(files)} processed. Output -> {args.out}")


if __name__ == "__main__":
    main()
