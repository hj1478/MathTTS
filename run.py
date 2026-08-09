#!/usr/bin/env python3
"""End-to-end driver: image/PDF -> wav in one command (issue #2).

Chains the four stages with the same default folders they use standalone,
so any stage can still be re-run in isolation with its own CLI:

  0. (PDF only)  pdf_to_images.py     *.pdf        -> pages/*.png
  1. OCR         ocr_vl.py            *.png        -> output/*.md
  2. Normalize   normalize.py         *.md         -> *.norm.md
  3. Speech      sre-probe/speak.js   *.norm.md    -> stitched/*.stitched.txt + .ssml
  4. TTS         tts_full.py          stitched/*   -> audio/*.wav  (needs Azure creds)

speak.js is resolved relative to THIS file, not the caller's cwd, and runs
with --strict: a span that would stitch as a placeholder stops the pipeline
before stage 4 pays Azure to read the placeholder aloud.

Usage:
  python run.py "kr question 1.png"
  python run.py kma_sheet_13_8_prob.pdf
  python run.py --dir somefolder
  python run.py "kr question 1.png" --skip-ocr --skip-tts   # redo middle stages

Skip flags reuse whatever artifacts the skipped stage left behind, so e.g.
--skip-ocr re-normalizes/re-stitches existing output/*.md without paying the
slow OCR step again.
"""
import argparse
import gc
import subprocess
import sys
from pathlib import Path

import normalize

ROOT = Path(__file__).resolve().parent
SPEAK_JS = ROOT / "sre-probe" / "speak.js"


def collect_images(a):
    """input/--dir -> list of image paths (rendering a PDF to pages first)."""
    import ocr_vl
    if a.dir:
        return sorted(p for p in Path(a.dir).iterdir()
                      if p.is_file() and p.suffix.lower() in ocr_vl.IMAGE_EXTS)
    src = Path(a.input)
    if src.suffix.lower() == ".pdf":
        import pdf_to_images
        print(f"[stage 0] {src.name} -> {a.pages}/")
        return pdf_to_images.render(src, a.pages, a.dpi)
    return [src]


def run_stage(tag, cmd, cwd=None):
    print(f"[{tag}] {' '.join(str(c) for c in cmd)}")
    proc = subprocess.run([str(c) for c in cmd], cwd=cwd)
    if proc.returncode != 0:
        sys.exit(f"[{tag}] failed (exit {proc.returncode}) — stopping before the next stage.")


def main():
    ap = argparse.ArgumentParser(description="image/PDF -> wav through all four stages.")
    ap.add_argument("input", nargs="?", help="an image or a PDF")
    ap.add_argument("--dir", help="run every image in this folder instead")
    ap.add_argument("--output", default="./output", help="stage 1/2 folder (default ./output)")
    ap.add_argument("--stitched", default="./stitched", help="stage 3 folder (default ./stitched)")
    ap.add_argument("--audio", default="./audio", help="stage 4 folder (default ./audio)")
    ap.add_argument("--pages", default="./pages", help="stage 0 folder for PDF pages")
    ap.add_argument("--dpi", type=int, default=200, help="PDF render DPI (default 200)")
    ap.add_argument("--voice", default="ko-KR-SunHiNeural", help="Azure voice")
    ap.add_argument("--device", choices=["cpu", "gpu"], help="OCR device (default: auto)")
    ap.add_argument("--lenient", action="store_true",
                    help="don't stop when a formula stitches as salvage/placeholder "
                         "(drops speak.js --strict)")
    ap.add_argument("--skip-ocr", action="store_true", help="reuse existing output/*.md")
    ap.add_argument("--skip-normalize", action="store_true", help="reuse existing *.norm.md")
    ap.add_argument("--skip-speak", action="store_true", help="reuse existing stitched/*")
    ap.add_argument("--skip-tts", action="store_true", help="stop before Azure synthesis")
    a = ap.parse_args()
    if bool(a.input) == bool(a.dir):
        ap.error("provide an image/PDF path, or --dir FOLDER (not both)")

    out = Path(a.output)

    # --- stage 1: OCR ------------------------------------------------------
    if a.skip_ocr:
        mds = sorted(p for p in out.glob("*.md") if not p.name.endswith(".norm.md"))
        print(f"[stage 1] skipped — reusing {len(mds)} .md file(s) in {out}")
    else:
        import ocr_vl
        images = collect_images(a)
        if not images:
            sys.exit("no images to OCR")
        device = a.device or ocr_vl.auto_device()
        print(f"[stage 1] OCR ({device}) — {len(images)} image(s)")
        mds = []
        for img in images:
            _, md_path = ocr_vl.run_image(img, out, device)
            print(f"  {Path(img).name} -> {md_path}")
            mds.append(Path(md_path))
        # drop the multi-GB VL model before spawning node — it starves speak.js
        # (same lesson as inbox_eval.py)
        ocr_vl._pipeline = None
        gc.collect()
    if not mds:
        sys.exit(f"no OCR markdown in {out} — nothing to do")

    # --- stage 2: normalize ------------------------------------------------
    if a.skip_normalize:
        norms = sorted(out.glob("*.norm.md"))
        print(f"[stage 2] skipped — reusing {len(norms)} .norm.md file(s)")
    else:
        norms = []
        for p in mds:
            dst = p.with_suffix(".norm.md")
            dst.write_text(normalize.normalize_math(p.read_text(encoding="utf-8")),
                           encoding="utf-8")
            norms.append(dst)
        print(f"[stage 2] normalized {len(norms)} file(s)")
    if not norms:
        sys.exit(f"no .norm.md files in {out} — nothing to stitch")

    # --- stage 3: Korean math speech (plain + SSML, for the A/B wavs) ------
    if a.skip_speak:
        print("[stage 3] skipped — reusing stitched/*")
    else:
        base = ["node", SPEAK_JS, "--voice", a.voice,
                "--write", Path(a.stitched).resolve()]
        if not a.lenient:
            base.insert(2, "--strict")
        norm_abs = [p.resolve() for p in norms]
        run_stage("stage 3", base + norm_abs)
        run_stage("stage 3", base + ["--ssml"] + norm_abs)

    # --- stage 4: Azure TTS ------------------------------------------------
    if a.skip_tts:
        print("[stage 4] skipped — no Azure synthesis")
        return
    run_stage("stage 4", [sys.executable, ROOT / "tts_full.py",
                          "--stitched", a.stitched, "--out", a.audio,
                          "--voice", a.voice])


if __name__ == "__main__":
    main()
