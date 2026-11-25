#!/usr/bin/env python3
"""Does PaddleOCR's page clean-up help on phone photos? An A/B on stage 1.

ocr_vl.py runs PaddleOCR-VL with orientation-classify and unwarping OFF, which
was decided for born-digital worksheet PDFs. A camera photo is neither flat nor
reliably upright, so this script reads the same photos with those two models
off and on, and scores each reading against the clean original.

  reference   the clean fixture (question_1.png, ...) read with both models
              off - what the pipeline produces today on a perfect input. Saved
              as OUT/ref/<fixture>.md; correct a file by hand and it is kept.
  photo       a picture of that fixture. It belongs to the fixture whose name
              its file name starts with: "question_1.jpg",
              "question_1 tilted.heic.jpg", ...
  configs     off | orient | unwarp | both   (which clean-up models run)

Scores, per photo and config (the reference is 0 / 100% by construction):
  CER   character edits to turn the reading into the reference, over the
        reference's length; whitespace is ignored. Lower is better.
  math  share of the reference's formulas that came out character-identical.

A photo is first put through what the app does before upload (EXIF rotation
applied, long side cut to 2400 px, JPEG quality 90 - the app's src/lib/image.ts), so
OCR sees what the backend would. --no-shrink skips that.

  python scripts/photo_eval.py --photos ./photos            # real photos
  python scripts/photo_eval.py --synth                      # made-up ones, see below

--synth makes three stand-in "photos" per fixture (shot at an angle with a
shadow; a curled page; turned 90 degrees) and evaluates those. It shows whether
the models react to the faults at all and that the harness works. It is NOT
evidence for real photos: the faults are drawn by this file, not by a lens.

Readings are cached in OUT by config and image content, so a second run only
reads what is new.
"""
import argparse, hashlib, io, json, re, sys
from pathlib import Path

from pipeline.normalize import SPAN

ROOT = Path(__file__).resolve().parent.parent  # the repo root

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
MAX_SIDE, JPEG_QUALITY = 2400, 90   # as the app's src/lib/image.ts (its own repository)
CONFIGS = {  # name -> (orientation-classify, unwarping)
    "off": (False, False), "orient": (True, False),
    "unwarp": (False, True), "both": (True, True),
}

_pipeline = None


def pipeline(device):
    """ocr_vl.pipeline() with the two clean-up models loaded as well; each call
    to predict() then switches them on or off, so every config shares one
    layout model and one recognizer."""
    global _pipeline
    if _pipeline is None:
        from paddleocr import PaddleOCRVL
        _pipeline = PaddleOCRVL(vl_rec_backend="native", device=device,
                                use_doc_orientation_classify=True,
                                use_doc_unwarping=True,
                                use_seal_recognition=False,
                                use_chart_recognition=False)
    return _pipeline


def read(image_bytes, suffix, config, device, cache_dir):
    """OCR markdown of an image under a config, cached on disk."""
    key = hashlib.sha256(image_bytes).hexdigest()[:16]
    cached = cache_dir / f"{key}.{config}.md"
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    from pipeline.ocr_vl import markdown_of
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache_dir / f"{key}{suffix}"
    tmp.write_bytes(image_bytes)
    orient, unwarp = CONFIGS[config]
    text = "\n\n".join(markdown_of(r) for r in pipeline(device).predict(
        str(tmp), use_doc_orientation_classify=orient, use_doc_unwarping=unwarp))
    cached.write_text(text, encoding="utf-8")
    return text


def as_uploaded(path):
    """The bytes the app would upload for this photo."""
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if max(im.size) > MAX_SIDE:
        k = MAX_SIDE / max(im.size)
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


# ---- scoring ---------------------------------------------------------------

def squash(s):
    return re.sub(r"\s+", "", s)


def edits(a, b):
    """Levenshtein distance."""
    if len(a) < len(b):
        a, b = b, a
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def spans(text):
    return [squash(m.group(0)) for m in SPAN.finditer(text)]


def score(reading, ref):
    """-> (CER, formulas matched, formulas in the reference)."""
    r = squash(ref)
    cer = edits(squash(reading), r) / max(len(r), 1)
    left, hit = spans(reading), 0
    want = spans(ref)
    for s in want:
        if s in left:
            left.remove(s)
            hit += 1
    return cer, hit, len(want)


# ---- stand-in photos -------------------------------------------------------

def synth(fixture, out_dir):
    """Three made-up photos of a fixture -> their paths."""
    import cv2
    import numpy as np
    rng = np.random.default_rng(int(hashlib.sha256(fixture.name.encode()).hexdigest()[:8], 16))
    page = cv2.imread(str(fixture))
    # a phone puts far more pixels on a problem than these screenshots have
    k = max(1.0, 1600 / max(page.shape[:2]))
    page = cv2.resize(page, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    page = cv2.copyMakeBorder(page, 60, 60, 60, 60, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    h, w = page.shape[:2]
    m = int(0.18 * max(h, w))                       # desk around the page
    H, W = h + 2 * m, w + 2 * m
    desk = np.full((H, W, 3), (70, 95, 120), np.uint8)  # brown, BGR

    def on_desk(img, quad):
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        M = cv2.getPerspectiveTransform(src, np.float32(quad))
        out = desk.copy()
        return cv2.warpPerspective(img, M, (W, H), dst=out, borderMode=cv2.BORDER_TRANSPARENT,
                                   flags=cv2.INTER_CUBIC)

    def lens(img, shadow):
        f = img.astype(np.float32)
        if shadow:  # darker toward one corner, as under a phone held over a desk
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            f *= (1 - 0.45 * np.clip((xx / W + yy / H) / 2, 0, 1) ** 1.5)[..., None]
        f = cv2.GaussianBlur(f, (0, 0), 1.1)
        f += rng.normal(0, 4, f.shape)
        return np.clip(f, 0, 255).astype(np.uint8)

    flat = [[m, m], [m + w, m], [m + w, m + h], [m, m + h]]
    tilt = [[m + 0.13 * w, m + 0.10 * h], [m + 0.90 * w, m - 0.02 * h],
            [m + 1.04 * w, m + 1.00 * h], [m - 0.06 * w, m + 0.92 * h]]
    # a page lifting at the spine: each column slides vertically along a sine
    xs = np.arange(w, dtype=np.float32)
    lift = 0.07 * h * np.sin(np.pi * xs / w)
    mapx = np.tile(xs, (h, 1))
    mapy = np.arange(h, dtype=np.float32)[:, None] + lift[None, :] - lift.max() / 2
    curled = cv2.remap(page, mapx, mapy, cv2.INTER_CUBIC, borderValue=(255, 255, 255))

    made = {
        "tilt": lens(on_desk(page, tilt), shadow=True),
        "curl": lens(on_desk(curled, flat), shadow=True),
        "rot90": cv2.rotate(lens(on_desk(page, flat), shadow=False), cv2.ROTATE_90_CLOCKWISE),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, img in made.items():
        p = out_dir / f"{fixture.stem} {name}.jpg"
        cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        paths.append(p)
    return paths


# ---- run -------------------------------------------------------------------

def images_in(folder):
    return sorted(p for p in Path(folder).iterdir()
                  if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--photos", help="folder of phone photos, named after their fixture")
    ap.add_argument("--synth", action="store_true", help="make stand-in photos from the fixtures instead")
    ap.add_argument("--fixtures", default=str(ROOT / "fixtures"), help="folder of clean originals (default: fixtures/)")
    ap.add_argument("--only", help="comma-separated fixture names to keep (without extension)")
    ap.add_argument("--configs", default="off,both", help="comma-separated, of: " + ", ".join(CONFIGS))
    ap.add_argument("--out", default=str(ROOT / "work" / "runs" / "photo_eval"))
    ap.add_argument("--device", choices=["cpu", "gpu"])
    ap.add_argument("--no-shrink", action="store_true", help="do not apply the app's resize/JPEG step")
    a = ap.parse_args()
    if bool(a.photos) == a.synth:
        ap.error("give --photos FOLDER or --synth")
    configs = a.configs.split(",")
    if bad := [c for c in configs if c not in CONFIGS]:
        ap.error(f"unknown config {bad}")

    from pipeline.ocr_vl import auto_device
    device = a.device or auto_device()
    out, cache = Path(a.out), Path(a.out) / "cache"
    fixtures = {p.stem: p for p in images_in(a.fixtures)}
    if a.only:
        fixtures = {k: v for k, v in fixtures.items() if k in a.only.split(",")}
    if not fixtures:
        sys.exit(f"no fixture images in {a.fixtures}")

    if a.synth:
        photos = [p for f in fixtures.values() for p in synth(f, out / "synth")]
    else:
        photos = images_in(a.photos)

    def fixture_of(photo):  # longest fixture name the photo's name starts with
        names = [n for n in fixtures if photo.stem.lower().startswith(n.lower())]
        return max(names, key=len) if names else None

    refs = {}

    def ref(name):
        if name not in refs:
            f = out / "ref" / f"{name}.md"
            if not f.exists():
                print(f"[ref] {name}", flush=True)
                f.parent.mkdir(parents=True, exist_ok=True)
                fx = fixtures[name]
                f.write_text(read(fx.read_bytes(), fx.suffix, "off", device, cache), encoding="utf-8")
            refs[name] = f.read_text(encoding="utf-8")
        return refs[name]

    rows, skipped = [], []
    for photo in photos:
        name = fixture_of(photo)
        if name is None:
            skipped.append(photo.name)
            continue
        data, suffix = (photo.read_bytes(), photo.suffix) if a.no_shrink else (as_uploaded(photo), ".jpg")
        for c in configs:
            print(f"[{c}] {photo.name}", flush=True)
            cer, hit, n = score(read(data, suffix, c, device, cache), ref(name))
            rows.append({"photo": photo.name, "fixture": name, "config": c,
                         "cer": cer, "math_hit": hit, "math_total": n})

    width = max([len(r["photo"]) for r in rows] + [5])
    print("\n" + f"{'photo':<{width}}  " + "  ".join(f"{c + ' CER':>10} {'math':>6}" for c in configs))
    for photo in dict.fromkeys(r["photo"] for r in rows):
        cells = []
        for c in configs:
            r = next(r for r in rows if r["photo"] == photo and r["config"] == c)
            cells.append(f"{r['cer']:>10.1%} {str(r['math_hit']) + '/' + str(r['math_total']):>6}")
        print(f"{photo:<{width}}  " + "  ".join(cells))
    print("-" * (width + 2 + 19 * len(configs)))
    cells = []
    for c in configs:
        rs = [r for r in rows if r["config"] == c]
        hit, n = sum(r["math_hit"] for r in rs), sum(r["math_total"] for r in rs)
        mean = sum(r["cer"] for r in rs) / max(len(rs), 1)
        cells.append(f"{mean:>10.1%} {str(hit) + '/' + str(n):>6}")
    print(f"{'mean CER, formulas matched':<{width}}  " + "  ".join(cells))
    if skipped:
        print(f"\nskipped (name starts with no fixture's name): {', '.join(skipped)}")
    (out / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nreadings: {cache}/<hash>.<config>.md   rows: {out / 'results.json'}")


if __name__ == "__main__":
    main()
