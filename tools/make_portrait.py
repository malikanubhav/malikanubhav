#!/usr/bin/env python3
"""One-off: turn a photo into data/portrait.txt (ASCII, dark = dense).

    python tools/make_portrait.py path/to/photo.webp [cols]

Needs Pillow. Not run in CI; the daily job only reads the text file.
"""
import sys
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance

RAMP = " .`:-=+*sc#%@"
src, cols = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 96
img = Image.open(src).convert("RGBA")
bg = Image.new("RGBA", img.size, (255, 255, 255, 255))  # transparent -> white
img = Image.alpha_composite(bg, img).convert("L")
w, h = img.size
# Head and shoulders, above the placard in the portfolio photo.
img = img.crop((int(w * 0.17), int(h * 0.04), int(w * 0.83), int(h * 0.64)))
img = ImageOps.autocontrast(img, cutoff=1)
img = ImageEnhance.Contrast(img).enhance(1.5)
cw, ch = img.size
rows = round(cols * ch / cw * 0.55)  # monospace cells are ~0.55 as wide as tall
img = img.resize((cols, rows), Image.LANCZOS)
px = img.load()
lines = []
for y in range(rows):
    line = "".join(RAMP[min(len(RAMP) - 1, int((255 - px[x, y]) / 256 * len(RAMP)))] for x in range(cols))
    lines.append(line.rstrip())
out = Path(__file__).resolve().parent.parent / "data" / "portrait.txt"
out.write_text("\n".join(lines) + "\n")
print(f"{cols}x{rows} -> {out}")
