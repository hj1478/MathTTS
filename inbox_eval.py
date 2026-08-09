#!/usr/bin/env python3
"""Drop-folder eval: PDFs/images in ./inbox -> full pipeline -> LLM-judged speech.

Put any worksheet PDF (or image) into ./inbox and run this script. Each input
goes through the real pipeline, then two reviewers go over the spoken output:

  1. PaddleOCR-VL (ocr_vl.py)   each page  -> runs/<name>/<name>_<p>.md
  2. dot_check.restore (text-only LLM)     -> <name>_<p>.dots.md when it
     restored 순환소수 dots OCR dropped     (skipped with --no-llm / --no-dots)
  3. normalize.normalize_math              -> <name>_<p>.norm.md
  4. sre-probe/speak.js --write            -> <name>_<p>.stitched.txt  (speech)
  5. review of the speech:
       - deterministic lint detectors from tts_eval.py (free, no API), and
       - an OpenAI judge that reads OCR markdown + stitched speech side by
         side and flags places a listening student would be misled.

Findings land in:
  runs/<name>/review.json    machine-readable (all pages, lint + judge)
  runs/<name>/review.md      human summary
  eval/suggested_cases.json  judge-proposed golden cases. Review them, move the
                             good ones into eval/cases.json (add "known": <why>
                             when documenting a struggle instead of fixing it).

.env keys (same loader as tts_probe.py; real env wins):
  OPENAI_API_KEY    required for the judge
  OPENAI_MODEL      default gpt-4o
  OPENAI_BASE_URL   default https://api.openai.com/v1

Usage:
  python inbox_eval.py                  # process inbox/, lint + judge
  python inbox_eval.py --no-llm         # pipeline + lint only, no API calls
  python inbox_eval.py --no-dots        # keep the judge, skip dot restoration
  python inbox_eval.py --force          # redo reviews (cached OCR is reused)
  python inbox_eval.py --force-ocr      # redo everything including OCR
  python inbox_eval.py --stitched DIR [--source DIR]
                                        # judge existing *.stitched.txt (no OCR);
                                        # --source pairs <name>.norm.md as ground truth
A finished input (runs/<name>/review.json exists) is skipped unless --force.
Exit code 1 if any error-level lint or judge finding was produced.
"""
import argparse
import json
import re
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import dot_check
import normalize
from llm import chat_json, openai_cfg
from tts_eval import lint_text

ROOT = Path(__file__).parent
INBOX = ROOT / "inbox"
RUNS = ROOT / "runs"
SUGGESTED = ROOT / "eval" / "suggested_cases.json"
CASES = ROOT / "eval" / "cases.json"
INPUT_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
MAX_CHARS = 15000  # per side sent to the judge; pages are normally way below this

# ------------------------------------------------------------ pipeline stages


def safe_stem(path):
    return re.sub(r"[^\w\-]+", "_", Path(path).stem).strip("_") or "input"


def ocr_pages(path, run_dir):
    """OCR one input (a PDF yields one result per page) -> ordered .md files."""
    import ocr_vl  # heavy import + lazy model load stay out of --stitched mode
    run_dir.mkdir(parents=True, exist_ok=True)
    device = ocr_vl.auto_device()
    print(f"  [ocr] {path.name} (device={device} — CPU is tens of sec/page)")
    pages = []
    for i, res in enumerate(ocr_vl.pipeline(device).predict(str(path))):
        md = run_dir / f"{safe_stem(path)}_{i}.md"
        md.write_text(ocr_vl.markdown_of(res), encoding="utf-8")
        pages.append(md)
        print(f"        page {i} -> {md.name}")
    (run_dir / "ocr.done").write_text("", encoding="utf-8")
    return pages


def restore_dots(cfg, md, text):
    """Text-only LLM pass over one OCR page: put back 순환소수 dots the OCR
    dropped (see dot_check.py). Returns the text to normalize; when it changed,
    the patched page is also saved as <stem>.dots.md so the judge and a human
    can see exactly what the pass did."""
    dots = md.parent / (md.stem + ".dots.md")
    dots.unlink(missing_ok=True)  # never let a stale patch from a past run linger
    if cfg is None or not dot_check.needs_check(text):
        return text
    patched, notes, err = dot_check.restore(cfg, text, md.stem)
    for n in notes:
        print(f"  [dots] {md.stem}: {n}")
    if err:
        print(f"  [dots] {md.stem}: {err}")
    if patched != text:
        dots.write_text(patched, encoding="utf-8")
    return patched


def stitch(md_files, out_dir, dots_cfg=None):
    """normalize each page .md and run speak.js once -> {page_stem: speech}."""
    norm_files = []
    for md in md_files:
        text = restore_dots(dots_cfg, md, md.read_text(encoding="utf-8"))
        norm = md.parent / (md.stem + ".norm.md")
        norm.write_text(normalize.normalize_math(text), encoding="utf-8")
        norm_files.append(norm)
    cmd = ["node", str(ROOT / "sre-probe" / "speak.js"), "--write", str(out_dir),
           *map(str, norm_files)]
    for attempt in (1, 2):  # empty-stderr nonzero exits = killed under memory
        proc = subprocess.run(cmd, capture_output=True, text=True)  # pressure;
        if proc.returncode == 0:                                    # retry once
            break
        detail = (f"exit {proc.returncode}; stderr: "
                  f"{proc.stderr.strip() or '(empty — likely killed by the OS)'}")
        if attempt == 1:
            print(f"  [retry] speak.js failed ({detail})")
    else:
        sys.exit(f"speak.js failed twice — {detail}")
    return {md.stem: (out_dir / f"{md.stem}.stitched.txt").read_text(encoding="utf-8")
            for md in md_files}


# ------------------------------------------------------------ OpenAI judge

JUDGE_SYSTEM = """\
You review a Korean math-worksheet text-to-speech pipeline for blind/low-vision \
students. You get SOURCE (OCR markdown of the page, math as LaTeX/plain notation; \
may be absent) and SPEECH (the exact Korean text that will be read aloud).

The verbalized-math style is intentional and CORRECT — e.g. "괄호 열고 x 더하기 1 \
괄호 닫고", "2 제곱", "3 분의 1", "루트 2". Do NOT flag style.

Korean math reading conventions — these are CORRECT, never flag them:
  - Fractions are read DENOMINATOR FIRST: "b 분의 a" means a/b. Worked example: \
\\frac{5}{3} -> "3 분의 5", \\frac{3}{5} -> "5 분의 3" — those readings are NOT \
swapped, they are correct. Likewise \\frac{13}{12} -> "12 분의 13", \\frac{A}{B} \
-> "B 분의 A". Misjudging this rule is the single most common false alarm.
  - "절댓값 a" is the COMPLETE and correct reading of |a| — nothing is missing.
  - "루트 2" for √2, "각 A" for ∠A, "n 제곱/세제곱" for powers, "는/은" for =.
  - Systems of equations are read as enumerated cases: "총 케이스 수 2 케이스 1: \
..." — intentional SRE phrasing, not garbage.
  - Problem/choice numbers ("5.", "(1)", "①") legitimately appear at the start of a \
sentence; flag them only when they FUSE INTO the math so a listener would take the \
number as part of the expression.

Flag only real problems a student listening WITHOUT seeing the page would hit:
  wrong-math        speech contradicts the source math
  garbled           word salad / broken reading (often from bad OCR LaTeX)
  residue           LaTeX, HTML, file names, layout junk read aloud
  missing-content   problem content in the source that never gets spoken
  ambiguous         reading a listener would parse as different math
  unnatural         phrasing so odd it obscures the math (high bar; usually warn)

Severity: "error" = student gets the math wrong or loses content; "warn" = \
confusing but recoverable.

MANDATORY self-check for every candidate finding, in this order:
  1. Write the source expression, then derive its correct Korean reading yourself
     (apply the conventions above, especially denominator-first fractions).
  2. Compare your derivation to the speech. If the speech already matches, the
     candidate is a false alarm — DISCARD it. Never emit a finding whose
     explanation concludes the speech is fine, and never emit two findings that
     contradict each other.
  3. speech_quote must be copied VERBATIM from SPEECH (character-exact substring,
     no paraphrase, no invented text). Findings with fabricated quotes are
     discarded by the harness.
Prefer missing a borderline nitpick over raising a false alarm; an empty findings \
list is a perfectly good answer.

For each finding, when you can, propose a MINIMAL golden case for a regression \
suite: a short raw OCR-style input snippet reproducing the issue, with "must" \
(substrings the correct speech must contain) and/or "mustnot" (substrings that \
must not appear). Keep must/mustnot phrases short and in the speech's own style.

Reply with ONLY this JSON object (no prose):
{"analysis": "<brief scratchpad: candidate issues and your self-check verdicts>",
 "findings": [{"category": "...", "severity": "error"|"warn",
  "speech_quote": "<exact substring of SPEECH>",
  "source_quote": "<relevant source excerpt or empty>",
  "correct_reading": "<what the speech should say, from your step-1 derivation>",
  "explanation": "<one sentence, English ok>",
  "suggested_case": {"id": "<kebab-case>", "input": "<raw snippet>",
                     "must": ["..."], "mustnot": ["..."]} or null}]}
An empty findings list means the page is fine."""


def clip(text, label):
    if len(text) > MAX_CHARS:
        return text[:MAX_CHARS] + f"\n...[{label} truncated at {MAX_CHARS} chars]"
    return text


def judge_page(cfg, source, speech, tag):
    """Ask the judge about one page. Returns (findings, error_string)."""
    user = (f"SOURCE (OCR markdown):\n{clip(source, 'source') if source else '(not available)'}\n\n"
            f"SPEECH (will be read aloud):\n{clip(speech, 'speech')}")
    data, err = chat_json(cfg, JUDGE_SYSTEM, user, tag)
    if err:
        return [], err
    return valid_findings(data.get("findings", []), speech), ""


def valid_findings(items, speech):
    """Keep only well-formed findings; drop fabricated quotes (they track
    hallucinated findings almost perfectly); fix severity."""
    out = []
    for f in items if isinstance(items, list) else []:
        if not isinstance(f, dict) or not f.get("explanation"):
            continue
        quote = str(f.get("speech_quote", ""))
        if quote and quote not in speech:
            continue  # judge "quoted" text the speech doesn't contain
        f = {"category": str(f.get("category", "other")),
             "severity": f.get("severity") if f.get("severity") in ("error", "warn") else "warn",
             "speech_quote": quote,
             "source_quote": str(f.get("source_quote", "")),
             "correct_reading": str(f.get("correct_reading", "")),
             "explanation": str(f["explanation"]),
             "suggested_case": f.get("suggested_case") or None}
        sc = f["suggested_case"]
        if not (isinstance(sc, dict) and sc.get("id") and sc.get("input")
                and (sc.get("must") or sc.get("mustnot"))):
            f["suggested_case"] = None
        out.append(f)
    return out


# ------------------------------------------------------------ reports

def known_inputs():
    inputs = set()
    for path in (CASES, SUGGESTED):
        if path.exists():
            try:
                inputs |= {c.get("input", "") for c in
                           json.loads(path.read_text(encoding="utf-8"))}
            except ValueError:
                pass
    return inputs


def save_suggestions(pages, provenance):
    """Append judge-proposed cases to eval/suggested_cases.json (dedup by input)."""
    seen = known_inputs()
    fresh = []
    for page in pages:
        for f in page["judge"]:
            sc = f["suggested_case"]
            if sc and sc["input"] not in seen:
                seen.add(sc["input"])
                fresh.append({**sc, "why": f["explanation"],
                              "from": f"{provenance}/{page['page']}"})
    if fresh:
        existing = (json.loads(SUGGESTED.read_text(encoding="utf-8"))
                    if SUGGESTED.exists() else [])
        SUGGESTED.write_text(
            json.dumps(existing + fresh, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    return len(fresh)


def write_reports(run_dir, name, model, pages):
    (run_dir / "review.json").write_text(
        json.dumps({"input": name, "model": model, "pages": pages},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [f"# Review: {name}", f"judge model: {model}", ""]
    for p in pages:
        lines.append(f"## {p['page']}")
        if p.get("judge_error"):
            lines.append(f"- JUDGE ERROR: {p['judge_error']}")
        for n, sev, ev in p["lint"]:
            lines.append(f"- lint [{sev}] {n}: {ev}")
        for f in p["judge"]:
            lines.append(f"- judge [{f['severity']}] {f['category']}: "
                         f"{f['explanation']}")
            if f["speech_quote"]:
                lines.append(f"    - speech: {f['speech_quote']!r}")
            if f["source_quote"]:
                lines.append(f"    - source: {f['source_quote']!r}")
            if f.get("correct_reading"):
                lines.append(f"    - should say: {f['correct_reading']!r}")
        if not p["lint"] and not p["judge"] and not p.get("judge_error"):
            lines.append("- clean")
        lines.append("")
    (run_dir / "review.md").write_text("\n".join(lines), encoding="utf-8")


def count(pages, kind, sev):
    if kind == "lint":
        return sum(1 for p in pages for _, s, _ in p["lint"] if s == sev)
    return sum(1 for p in pages for f in p["judge"] if f["severity"] == sev)


# ------------------------------------------------------------ drivers

def review_pages(cfg, page_texts, sources, run_dir, name):
    """Lint + (optionally) judge each page; write reports; return pages list.
    Judge calls are network-bound, so pages go out 4 at a time."""
    pages = []
    judged = {}
    if cfg:
        to_judge = {s: t for s, t in page_texts.items() if t.strip()}
        if to_judge:
            print(f"  [judge] {len(to_judge)} page(s) x {cfg['model']}, 4 in parallel")
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {s: pool.submit(judge_page, cfg, sources.get(s, ""), t, s)
                       for s, t in to_judge.items()}
            judged = {s: f.result() for s, f in futures.items()}
    for stem in sorted(page_texts):
        speech = page_texts[stem]
        entry = {"page": stem, "lint": lint_text(speech), "judge": []}
        if not speech.strip():
            entry["judge_error"] = "empty speech — page skipped"
        elif cfg:
            entry["judge"], err = judged[stem]
            if err:
                entry["judge_error"] = err
        pages.append(entry)
    write_reports(run_dir, name, cfg["model"] if cfg else "(lint only)", pages)
    n_sugg = save_suggestions(pages, name)
    n_err = count(pages, "lint", "error") + count(pages, "judge", "error")
    n_warn = count(pages, "lint", "warn") + count(pages, "judge", "warn")
    n_judge_err = sum(1 for p in pages if p.get("judge_error"))
    print(f"  -> {len(pages)} page(s): {n_err} error, {n_warn} warn, "
          f"{n_sugg} new suggested case(s)"
          + (f", {n_judge_err} judge failure(s)" if n_judge_err else "")
          + f"  ({run_dir / 'review.md'})")
    return n_err


def release_ocr():
    """Drop the multi-GB VL model before spawning node — it starved speak.js."""
    import gc
    mod = sys.modules.get("ocr_vl")
    if mod is not None:
        mod._pipeline = None
    gc.collect()


def process_inbox(cfg, force, force_ocr=False, no_dots=False):
    inputs = sorted(p for p in INBOX.iterdir()
                    if p.is_file() and p.suffix.lower() in INPUT_EXTS) if INBOX.is_dir() else []
    if not inputs:
        INBOX.mkdir(exist_ok=True)
        print(f"inbox/ is empty — drop PDFs or images into {INBOX} and rerun.")
        return 0

    # Phase 1: OCR every input (model stays loaded across files, loaded at most once).
    todo = []
    for path in inputs:
        name = safe_stem(path)
        run_dir = RUNS / name
        print(f"== {path.name} ==")
        if (run_dir / "review.json").exists() and not force:
            print(f"  already reviewed ({run_dir/'review.json'}) — use --force to redo")
            continue
        cached = [p for p in sorted(run_dir.glob(f"{name}_*.md"))
                  if not p.name.endswith((".norm.md", ".dots.md"))]
        if cached and (run_dir / "ocr.done").exists() and not force_ocr:
            print(f"  [ocr] reusing {len(cached)} cached page(s) in {run_dir}")
            mds = cached
        else:
            mds = ocr_pages(path, run_dir)
        if mds:
            todo.append((name, run_dir, mds))
        else:
            print("  no pages produced — skipping")
    release_ocr()

    # Phase 2: normalize + stitch + lint + judge, with the model gone.
    total_err = 0
    for name, run_dir, mds in todo:
        print(f"== review {name} ==")
        page_texts = stitch(mds, run_dir, dots_cfg=None if no_dots else cfg)
        # the judge should see the page as the pipeline consumed it — dots
        # restored — or it would flag the restored speech as wrong-math
        sources = {}
        for md in mds:
            dots = md.parent / (md.stem + ".dots.md")
            sources[md.stem] = (dots if dots.exists() else md).read_text(encoding="utf-8")
        total_err += review_pages(cfg, page_texts, sources, run_dir, name)
    return total_err


def process_stitched(cfg, dirs, source_dir):
    total_err = 0
    for d in map(Path, dirs):
        files = sorted(d.glob("*.stitched.txt"))
        print(f"== {d} ({len(files)} stitched file(s)) ==")
        if not files:
            continue
        page_texts = {f.name.split(".stitched.")[0]: f.read_text(encoding="utf-8")
                      for f in files}
        sources = {}
        if source_dir:
            for stem in page_texts:
                src = Path(source_dir) / f"{stem}.norm.md"
                if src.exists():
                    sources[stem] = src.read_text(encoding="utf-8")
        total_err += review_pages(cfg, page_texts, sources, d, d.name)
    return total_err


def main():
    ap = argparse.ArgumentParser(
        description="Run inbox/ PDFs through the pipeline and LLM-judge the speech.")
    ap.add_argument("--no-llm", action="store_true", help="pipeline + lint only")
    ap.add_argument("--no-dots", action="store_true",
                    help="skip the 순환소수 dot-restore LLM pass (judge still runs)")
    ap.add_argument("--force", action="store_true",
                    help="redo reviews (OCR stays cached)")
    ap.add_argument("--force-ocr", action="store_true",
                    help="redo everything including OCR")
    ap.add_argument("--gentle", action="store_true",
                    help="halve OCR CPU threads + lower process priority — "
                         "slower, but the laptop stays cool and usable")
    ap.add_argument("--model", help="override OPENAI_MODEL for the judge")
    ap.add_argument("--stitched", nargs="+", metavar="DIR",
                    help="judge existing *.stitched.txt dirs instead of inbox/")
    ap.add_argument("--source", metavar="DIR",
                    help="with --stitched: dir holding matching <name>.norm.md")
    a = ap.parse_args()

    if a.gentle:  # must happen before paddle is imported (ocr_pages does that)
        os.environ.setdefault("OMP_NUM_THREADS", str(max(1, (os.cpu_count() or 4) // 2)))
        os.nice(10)

    cfg = None if a.no_llm else openai_cfg(a.model)
    if a.stitched:
        n_err = process_stitched(cfg, a.stitched, a.source)
    else:
        n_err = process_inbox(cfg, a.force or a.force_ocr, a.force_ocr, a.no_dots)
    if n_err:
        sys.exit(f"\nFAILED: {n_err} error-level finding(s) — see review.md files")


if __name__ == "__main__":
    main()
