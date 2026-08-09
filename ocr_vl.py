#!/usr/bin/env python3
"""Local PaddleOCR-VL harness for Korean math problems (stage 1). No paid API.

Verified against paddleocr 3.7.0 / paddlex 3.7.2 / paddlepaddle 3.3.1 on
macOS arm64 (CPU), 2026-07. Two findings below are cited by comments in this
file — they were established by running the model, not assumed.

THE $...$ CONVENTION (what LATEX/SPAN and everything downstream depend on)
  PaddleOCR-VL emits inline math wrapped in single dollars. Observed verbatim
  in real output on the repo fixtures (output/*.md), e.g. from
  "kr question 2.png":

      4.  $ -2^5 \\div \\{(-2)^4 \\times (-2)\\} $를 계산하시오.

  and from "kr question 1.png" (note the mis-placed closing $ — the case
  normalize.py's _emit_inline repairs):

      ... 범위는 $p\\leq k<q(p, q$는 상수)이다. 이때 $p^{2}+9q^{2}$의 값을 ...

  So $...$ is confirmed from real model output, not assumed. The model cannot
  be forced to emit any other delimiter; normalize.py canonicalizes whatever
  arrives into $...$ / $$...$$.

WHY engine="transformers" MUST NOT BE ADDED
  PaddleOCRVL accepts an `engine=` kwarg (paddle, paddle_static,
  paddle_dynamic, transformers, onnxruntime), but it is a GLOBAL switch: it
  applies to every sub-model in the pipeline, including the PP-DocLayoutV3
  layout model, which is paddle-only — so engine="transformers" crashes the
  pipeline. The knob that selects the VL recognizer backend is the separate
  `vl_rec_backend=` ("native" = in-process, no server; the *-server values
  need a running server + vl_rec_server_url). Leave `engine` unset and use
  vl_rec_backend="native".

INSTALL GOTCHA
  `pip install paddleocr` alone raises DependencyError at pipeline creation;
  `pip install "paddlex[ocr]==3.7.2"` is also required (see requirements.txt).
  Model weights (PP-DocLayoutV3 + PaddleOCR-VL) auto-download from HuggingFace
  to ~/.paddlex/official_models/ on first run — hundreds of MB.
"""
import argparse, re, sys, traceback
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
# Math-span grammar: single source of truth is normalize.SPAN (the $...$
# convention is confirmed from real PaddleOCR-VL output — see module docstring).
# sre-probe/speak.js keeps a JS copy of the inline rule; the shared fixtures in
# eval/fixtures/span_cases.json are checked by both test suites so the two
# languages cannot silently drift apart.
from normalize import SPAN as LATEX
HANGUL = re.compile(r"[가-힣ᄀ-ᇿ]")

_pipeline = None


def pipeline(device):
    """Load the PaddleOCR-VL pipeline once, lazily (not at import time)."""
    global _pipeline
    if _pipeline is None:
        print("\n[loading] First run downloads model weights (hundreds of MB) — "
              "slow the first time, cached after.\n", flush=True)
        from paddleocr import PaddleOCRVL
        # native = in-process VL, no server. Do NOT add engine="transformers": it is
        # a global switch that crashes the paddle-only layout model (see module docstring).
        _pipeline = PaddleOCRVL(vl_rec_backend="native", device=device)
    return _pipeline


def auto_device():
    try:
        import paddle
        if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count():
            return "gpu"
    except Exception:
        pass
    return "cpu"


def markdown_of(res):
    """Pull the markdown text straight from the result object (no disk round-trip)."""
    md = getattr(res, "markdown", None)
    if isinstance(md, dict):
        return md.get("markdown_texts", "") or ""
    return ""


def run_image(image, out_dir, device):
    """OCR one image -> (markdown_text, saved_md_path). Raises on failure.

    Text comes from the result object; artifacts are written to out_dir and the
    ACTUAL written path is read back from res.save_path (no filename assumption).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    text, md_path = "", ""
    for res in pipeline(device).predict(str(image)):  # iterable — may yield >1
        res.save_to_markdown(save_path=str(out))
        md_path = str(getattr(res, "save_path", "") or "")  # real path, set by the call
        res.save_to_json(save_path=str(out))                # (also sets save_path -> ignore)
        text += ("\n\n" if text else "") + markdown_of(res)
    return text, md_path


def analyze(text):
    """From extracted markdown -> (math_spans_in_reading_order, korean_present)."""
    spans = list(dict.fromkeys(m.group(0).strip() for m in LATEX.finditer(text)))
    return spans, bool(HANGUL.search(text))


def expected_math(image):
    """Read '<image>.expect' sidecar -> True (math) / False (none) / None (no ground truth)."""
    side = Path(str(image) + ".expect")
    if not side.exists():
        return None
    tok = side.read_text(encoding="utf-8").strip().lower()
    if tok.startswith(("math", "yes", "y", "true", "1")):
        return True
    if tok.startswith(("none", "no", "n", "false", "0")):
        return False
    return None


def verdict(found, expected):
    """expected True(math)/False(none)/None(unknown) + found -> one-word verdict."""
    if expected is None:
        return "unverified"
    if expected and not found:
        return "MISS"          # expected math, found none — the real failure
    if not expected and found:
        return "spurious?"
    return "ok"


def show_single(image, out_dir, device):
    text, md_path = run_image(image, out_dir, device)
    math, korean = analyze(text)
    bar = "=" * 72

    # PRIMARY: the model's own markdown, math inline in reading-order position.
    print(f"\n{bar}\nREADING ORDER  (authoritative — math sits inline where the model placed it)\n{bar}")
    print(text.strip() or "(empty)")

    # SECONDARY: presence check only. Does NOT preserve position — trust the view above.
    print(f"\n{bar}\nQUICK CHECK  (presence only, not position)\n{bar}")
    print(f"  math: {len(math)} span(s) -> {', '.join(math)}" if math
          else "  math: NONE found — if this image contains math, it was missed")
    print(f"  korean: {'present' if korean else 'ABSENT'}")
    print(f"  saved:  {md_path or '(unknown)'}  (+ _res.json alongside)")
    print(bar)


def run_eval(folder, out_dir, device):
    images = sorted(p for p in Path(folder).iterdir()
                    if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    if not images:
        print(f"No images found in {folder} (looked for {sorted(IMAGE_EXTS)}).")
        return
    print(f"Found {len(images)} image(s) in {folder}. Running batch...\n")
    print(f"{'image':<26} {'expect':<7} {'found':<6} {'verdict':<10} output")
    print("-" * 84)
    verdicts = []
    for p in images:
        try:
            text, md_path = run_image(p, out_dir, device)
            found, exp = bool(LATEX.search(text)), expected_math(p)
            v = verdict(found, exp)
            exp_s = "math" if exp else "none" if exp is False else "—"
            print(f"{p.name:<26} {exp_s:<7} {('yes' if found else 'no'):<6} {v:<10} {md_path}")
        except Exception as e:
            v = "ERROR"
            print(f"{p.name:<26} {'—':<7} {'—':<6} {'ERROR':<10} {type(e).__name__}: {e}")
        verdicts.append(v)
    print("-" * 84)
    print(f"MISS (expected math, found none): {verdicts.count('MISS')}   "
          f"ERROR (crashed, not judged): {verdicts.count('ERROR')}   "
          f"unverified (no <image>.expect sidecar): {verdicts.count('unverified')}")
    if "unverified" in verdicts:
        print("Add '<image>.expect' files (math|none) to turn 'unverified' rows into real pass/fail.")


def main():
    ap = argparse.ArgumentParser(description="Local PaddleOCR-VL harness (Korean + math). No paid API.")
    ap.add_argument("input", nargs="?", help="path to a single image")
    ap.add_argument("--eval", metavar="FOLDER", help="run every image in FOLDER, print a summary table")
    ap.add_argument("--out", default="./output", help="output folder (default ./output)")
    ap.add_argument("--device", choices=["cpu", "gpu"], help="force device (default: auto)")
    a = ap.parse_args()

    device = a.device or auto_device()
    print(f"[device] {device}" + ("  — CPU-only: VLM inference will be SLOW (tens of sec/image)."
                                  if device == "cpu" else ""))
    if a.eval:
        run_eval(a.eval, a.out, device)
    elif a.input:
        try:
            show_single(a.input, a.out, device)
        except Exception:
            traceback.print_exc()
            sys.exit(1)
    else:
        ap.error("provide an image path, or use --eval FOLDER")


if __name__ == "__main__":
    main()
