#!/usr/bin/env python3
"""Generate Voice Harvester's app icon — a clean waveform mark on a gradient —
at all macOS sizes, packaged into AppIcon.icns. Run: python3 make-icon.py"""
import math, os, subprocess, tempfile
from PIL import Image, ImageDraw


def render(size: int) -> Image.Image:
    S = size * 3
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # rounded-rect gradient background (blue -> purple), macOS-squircle-ish
    top = (52, 140, 255); bot = (115, 77, 242)
    for y in range(S):
        t = y / S
        c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (S, y)], fill=c + (255,))
    # mask to a rounded rect
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S, S], radius=int(S * 0.225), fill=255)
    img.putalpha(mask)

    # centered waveform bars (white)
    dd = ImageDraw.Draw(img)
    bars = 7
    cx, cy = S / 2, S / 2
    bw = S * 0.055
    gap = S * 0.038
    total = bars * bw + (bars - 1) * gap
    x = cx - total / 2
    heights = [0.30, 0.55, 0.85, 1.0, 0.85, 0.55, 0.30]
    for h in heights:
        bh = S * 0.5 * h
        dd.rounded_rectangle([x, cy - bh / 2, x + bw, cy + bh / 2],
                             radius=bw / 2, fill=(255, 255, 255, 235))
        x += bw + gap
    return img.resize((size, size), Image.LANCZOS)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "AppIcon.icns")
    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, "AppIcon.iconset"); os.makedirs(iconset)
        for s, name in [(16, "16x16"), (32, "16x16@2x"), (32, "32x32"), (64, "32x32@2x"),
                        (128, "128x128"), (256, "128x128@2x"), (256, "256x256"),
                        (512, "256x256@2x"), (512, "512x512"), (1024, "512x512@2x")]:
            render(s).save(os.path.join(iconset, f"icon_{name}.png"))
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", out], check=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
