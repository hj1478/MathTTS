"""MathTTS app icon: a square-root sign whose radicand is a sound wave.
Usage: python make_icons.py OUT_DIR   (writes every size the app and Play need)"""
import math, sys
from pathlib import Path
from PIL import Image, ImageDraw

SS = 4                      # supersampling
N = 1024
BLUE_TOP, BLUE_BOTTOM = (43, 108, 240), (24, 64, 190)   # around the app's primary #1D4ED8
WHITE, YELLOW = (255, 255, 255, 255), (255, 229, 138, 255)  # hlBg #FFE58A: the phrase being read

# the glyph, drawn on a 1024 canvas and centred on (512, 512)
STROKE = 58
RADICAL = [(246, 548), (300, 522), (384, 706), (478, 318), (782, 318)]
SRC = (530, 566)            # where the sound comes from
ARCS = [84, 154, 224]       # radii
WAVE = 38                   # their stroke
SPAN = 42                   # degrees either side of straight right
DOT = 30


def background(size=N):
    im = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        im.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(BLUE_TOP, BLUE_BOTTOM)))
    return im.resize((size, size))


def glyph(scale=1.0, radical=WHITE, waves=YELLOW):
    """The mark on a transparent 1024 canvas, scaled about the centre."""
    n = N * SS
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    tx = lambda x: (512 + (x - 512) * scale) * SS
    w = STROKE * scale * SS
    ww = WAVE * scale * SS

    def dot(x, y, r, fill):
        d.ellipse([tx(x) - r, tx(y) - r, tx(x) + r, tx(y) + r], fill=fill)

    pts = [(tx(x), tx(y)) for x, y in RADICAL]
    d.line(pts, fill=radical, width=round(w), joint="curve")
    for x, y in RADICAL:
        dot(x, y, w / 2, radical)
    cx, cy = SRC
    dot(cx, cy, DOT * scale * SS, waves)
    for r in ARCS:
        R = r * scale * SS + ww / 2
        d.arc([tx(cx) - R, tx(cy) - R, tx(cx) + R, tx(cy) + R], -SPAN, SPAN, fill=waves, width=round(ww))
        for a in (-SPAN, SPAN):
            dot(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)), ww / 2, waves)
    return im.resize((N, N), Image.LANCZOS)


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    bg = background()
    full = bg.convert("RGBA")
    full.alpha_composite(glyph(1.0))
    full.convert("RGB").save(out / "icon.png")                       # iOS / default: no transparency
    full.convert("RGB").resize((512, 512), Image.LANCZOS).save(out / "play-store-icon-512.png")
    full.convert("RGB").resize((48, 48), Image.LANCZOS).save(out / "favicon.png")
    # Android adaptive: launchers crop to the middle ~66%, so the mark is smaller there
    glyph(0.62).save(out / "android-icon-foreground.png")
    bg.save(out / "android-icon-background.png")
    glyph(0.62, WHITE, WHITE).save(out / "android-icon-monochrome.png")
    # previews only: how launchers mask it
    for name, radius in (("preview-circle.png", 512), ("preview-squircle.png", 230)):
        adaptive = bg.convert("RGBA")
        adaptive.alpha_composite(glyph(0.62))
        crop = adaptive.crop((171, 171, 853, 853)).resize((512, 512), Image.LANCZOS)   # the visible 66%
        mask = Image.new("L", (512, 512), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, 511, 511], radius=radius // 2, fill=255)
        crop.putalpha(mask)
        crop.save(out / name)


if __name__ == "__main__":
    main(sys.argv[1])
