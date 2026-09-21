#!/usr/bin/env python3
"""End-to-end driver: image/PDF -> wav in one command (issue #2).

Chains the stages with the same default folders they use standalone, so any
stage can still be re-run in isolation with its own CLI:

  0. (PDF only)  pdf_to_images.py     *.pdf        -> pages/*.png
  1. OCR         ocr_vl.py            *.png        -> output/*.md
  1.5 Dots       dot_check.py         *.md         -> *.dots.md   (--dots only)
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
  python run.py sheet.pdf --dots                            # + 순환소수 repair

Stage 1.5 is OFF by default and is the only stage besides 4 that costs money
(one OpenAI call per page that has BOTH a decimal and a repetition signal —
`dot_check.needs_check` gates the rest away). It is opt-in for two reasons
that outlive each other: a plain run is otherwise key-free, and a wrong dot
CORRUPTS a correct number where a missing one merely reproduces the status
quo. It writes `<stem>.dots.md` beside the raw OCR rather than over it, so the
unpatched page stays inspectable; stage 2 then prefers the patched file and
says so.

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
    ap.add_argument("--dots", action="store_true",
                    help="stage 1.5: restore 순환소수 dots the OCR dropped "
                         "(needs OPENAI_API_KEY; one call per signalling page)")
    ap.add_argument("--model", help="override OPENAI_MODEL for --dots")
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
        # ".dots.md" (dot_check.py --write) is a PATCHED COPY of a page, not
        # another page: globbing it in normalizes and stitches it alongside its
        # own original, silently doubling the output and the Azure bill. Whether
        # a plain run should PREFER the patched copy is the open question in #15;
        # processing both is wrong under either answer. inbox_eval.py already
        # excludes it the same way.
        mds = sorted(p for p in out.glob("*.md")
                     if not p.name.endswith((".norm.md", ".dots.md")))
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

    # --- stage 1.5: 순환소수 dot restoration (opt-in; costs an LLM call) ----
    if a.dots:
        import dot_check
        cfg = dot_check.openai_cfg(a.model)
        print(f"[stage 1.5] dot restore ({cfg['model']}) — {len(mds)} page(s)")
        patched_n = failed = 0
        for p in mds:
            dots = p.with_suffix(".dots.md")
            dots.unlink(missing_ok=True)   # never reuse a stale patch
            text = p.read_text(encoding="utf-8")
            if not dot_check.needs_check(text):
                continue                   # no repetition signal -> no API call
            patched, notes, err = dot_check.restore(cfg, text, p.name)
            for n in notes:
                print(f"  [dots] {p.name}: {n}")
            if err:                        # a page left unpatched is a
                failed += 1                # degradation, not a corruption:
                print(f"  [dots] FAILED {p.name}: {err}")   # warn, keep going
            elif patched != text:
                dots.write_text(patched, encoding="utf-8")
                patched_n += 1
        print(f"[stage 1.5] {patched_n} page(s) patched"
              + (f", {failed} FAILED (those pages keep the OCR's own text)" if failed else ""))

    # --- stage 2: normalize ------------------------------------------------
    if a.skip_normalize:
        norms = sorted(out.glob("*.norm.md"))
        print(f"[stage 2] skipped — reusing {len(norms)} .norm.md file(s)")
    else:
        norms = []
        for p in mds:
            # prefer the dot-restored page when one exists — raw OCR stays on
            # disk and inspectable, which is why the patch is a separate file
            dots = p.with_suffix(".dots.md")
            src = dots if dots.exists() else p
            if src is dots:
                print(f"  [dots] normalizing the restored {dots.name}")
            dst = p.with_suffix(".norm.md")
            dst.write_text(normalize.normalize_math(src.read_text(encoding="utf-8")),
                           encoding="utf-8")
            norms.append(dst)
        print(f"[stage 2] normalized {len(norms)} file(s)")
    if not norms:
        sys.exit(f"no .norm.md files in {out} — nothing to stitch")

    # --- stage 3: Korean math speech (plain + SSML, for the A/B wavs) ------
    if a.skip_speak:
        print("[stage 3] skipped — reusing stitched/*")
    else:
        stitch_dir = Path(a.stitched).resolve()
        base = ["node", SPEAK_JS, "--voice", a.voice, "--write", stitch_dir]
        if not a.lenient:
            base.insert(2, "--strict")
        norm_abs = [p.resolve() for p in norms]
        # speak.js deliberately does NOT write a file whose SSML came out
        # malformed. Clear this run's targets first and check them after, or
        # --lenient walks past the failure and stage 4 pays Azure to read the
        # PREVIOUS run's file back as if it were this one.
        targets = [stitch_dir / f"{p.name.removesuffix('.norm.md')}.stitched.{ext}"
                   for p in norms for ext in ("txt", "ssml")]
        for t in targets:
            t.unlink(missing_ok=True)
        run_stage("stage 3", base + norm_abs)
        run_stage("stage 3", base + ["--ssml"] + norm_abs)
        missing = [t.name for t in targets if not t.exists()]
        if missing:
            sys.exit(f"[stage 3] speak.js wrote no output for {', '.join(missing)} "
                     "— malformed SSML; stopping before stage 4.")

    # --- stage 4: Azure TTS ------------------------------------------------
    if a.skip_tts:
        print("[stage 4] skipped — no Azure synthesis")
        return
    run_stage("stage 4", [sys.executable, ROOT / "tts_full.py",
                          "--stitched", a.stitched, "--out", a.audio,
                          "--voice", a.voice])


if __name__ == "__main__":
    main()
