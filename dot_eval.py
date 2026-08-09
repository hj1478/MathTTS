#!/usr/bin/env python3
"""Accuracy eval for the 순환소수 dot-restore pass (dot_check.py).

Measures, per NUMBER (not per page): recall — truly repeating decimals that end
up dotted — and precision — added dots that are right (right number AND right
순환마디; 0.24̇ for 0.2̇4̇ is a placement error). The two are not symmetric: a
miss just reproduces the pre-dot_check status quo, while a false dot actively
corrupts a correct number, so false positives are the failures to watch.

1. CASES (default; eval/dot_cases.json): labeled OCR-style snippets are run
   through dot_check.restore; the corrections it actually APPLIED (dotted
   numbers in output minus input) are compared with the case's "expect" list
   [{number, period}]. The negatives ("expect": []) are the point of the
   suite — pages engineered to tempt the model into guessing. A case with
   "known": <why> is an expected failure documenting a current limitation
   (prints FIXED when it starts passing, like tts_eval.py).
   Costs one temperature-0 API call per non-gated case — run on demand after a
   prompt/model change, not in per-commit CI.

2. SCORE (--score PATH ...): end-to-end detection rate against ground truth.
   PATH is a page image (OCR'd first — tens of sec/page on CPU) or an
   already-OCR'd .md; the sidecar '<PATH>.expect_dots' holds the truth as read
   off the PRINTED page: one "number:period" line per dotted decimal
   (e.g. "0.24:24"), or the single word "none". Both stages are scored — dots
   present in the raw OCR text (OCR alone) and after dot_check (OCR+LLM) —
   and the recall delta between them is the pass's real detection-rate gain.

Exit 1 on any unexpected case failure, or any FP/FN in --score.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import dot_check
from llm import openai_cfg

ROOT = Path(__file__).parent
DOT = dot_check._DOT
_LATEX_DOT = re.compile(r"\\dot\{([0-9])\}")
_DOTTED_TOKEN = re.compile(rf"[0-9]+\.(?:[0-9]{DOT}?)+")


def dotted_numbers(text):
    """All dotted decimals in text -> {(plain_number, period)}. Reads both the
    combining-dot form (0.2̇4̇ — raw OCR / dot_check output) and \\dot{2}
    (normalized LaTeX). Period = digits from the first dotted digit through the
    last one, per the printed first+last-of-마디 convention."""
    text = _LATEX_DOT.sub(rf"\g<1>{DOT}", text)
    out = set()
    for tok in _DOTTED_TOKEN.finditer(text):
        whole, frac_marked = tok.group().split(".", 1)
        digits, marks = [], []
        for ch in frac_marked:
            if ch == DOT:
                marks.append(len(digits) - 1)
            else:
                digits.append(ch)
        if marks:
            frac = "".join(digits)
            out.add((f"{whole}.{frac}", frac[marks[0]:marks[-1] + 1]))
    return out


def fmt(pairs):
    return ", ".join(f"{n}:{p}" for n, p in sorted(pairs)) or "(none)"


# ------------------------------------------------------------ cases mode

def run_cases(cfg, path):
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    n_pass = n_known = n_fail = tp = fp = fn = 0
    for c in cases:
        text = c["input"]
        expect = {(e["number"], e["period"]) for e in c.get("expect", [])}
        if dot_check.needs_check(text):
            patched, _, err = dot_check.restore(cfg, text, c["id"])
            if err:
                sys.exit(f"[{c['id']}] {err}")
            applied, gated = dotted_numbers(patched) - dotted_numbers(text), False
        else:
            applied, gated = set(), True
        ok, known = applied == expect, c.get("known")
        tag = ("FIXED" if known else "PASS ") if ok else ("KNOWN" if known else "FAIL ")
        extra = "  (gated — no API call)" if gated else ""
        print(f"  [{tag}] {c['id']}{extra}")
        if not ok:
            print(f"          expected {fmt(expect)}  |  applied {fmt(applied)}")
            if known:
                print(f"          known: {known}")
        if not known:  # documented limitations stay out of the headline numbers
            n_pass += ok
            n_fail += not ok
            tp += len(expect & applied)
            fp += len(applied - expect)
            fn += len(expect - applied)
        else:
            n_known += 1
    prec = f"{tp}/{tp + fp}" if tp + fp else "n/a (nothing applied)"
    rec = f"{tp}/{tp + fn}" if tp + fn else "n/a"
    print(f"  -> {n_pass} pass, {n_known} known struggle(s), {n_fail} unexpected "
          f"failure(s); numbers: precision {prec}, recall {rec}")
    return n_fail


# ------------------------------------------------------------ score mode

def load_truth(path):
    side = Path(str(path) + ".expect_dots")
    if not side.exists():
        return None
    truth = set()
    for line in side.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line != "none":
            num, _, per = line.partition(":")
            truth.add((num.strip(), per.strip()))
    return truth


def run_score(cfg, paths):
    rows, failed = [], False
    for p in map(Path, paths):
        truth = load_truth(p)
        if truth is None:
            print(f"{p}: no .expect_dots sidecar — skipped")
            continue
        if p.suffix.lower() == ".md":
            text = p.read_text(encoding="utf-8")
        else:
            import ocr_vl  # heavy — imported only when an image needs OCR
            text, _ = ocr_vl.run_image(p, ROOT / "output", ocr_vl.auto_device())
        stage2 = stage1 = dotted_numbers(text)
        if dot_check.needs_check(text):
            patched, _, err = dot_check.restore(cfg, text, p.name)
            if err:
                print(f"{p}: {err}")
                failed = True
            else:
                stage2 = dotted_numbers(patched)
        rows.append((p.name, truth, stage1, stage2))

    print(f"\n{'page':<34} {'truth':<16} {'ocr alone':<22} ocr+dot_check")
    print("-" * 96)
    t1 = [0, 0, 0]
    t2 = [0, 0, 0]

    def cell(truth, got, tot):
        s = (len(truth & got), len(got - truth), len(truth - got))
        for i, v in enumerate(s):
            tot[i] += v
        return f"TP {s[0]} FP {s[1]} FN {s[2]}"

    for name, truth, s1, s2 in rows:
        print(f"{name:<34} {fmt(truth):<16} {cell(truth, s1, t1):<22} "
              f"{cell(truth, s2, t2)}")
        failed |= bool((truth - s2) | (s2 - truth))
    n_true = t1[0] + t1[2]
    print("-" * 96)
    print(f"recall  {t1[0]}/{n_true} -> {t2[0]}/{n_true}   "
          f"precision after pass: {t2[0]}/{t2[0] + t2[1] if t2[0] + t2[1] else 1}"
          f"   (over {len(rows)} page(s))")
    return failed


def main():
    ap = argparse.ArgumentParser(
        description="Accuracy eval for dot_check.py (precision/recall per number).")
    ap.add_argument("--cases", default=str(ROOT / "eval" / "dot_cases.json"),
                    help="labeled snippet suite (default eval/dot_cases.json)")
    ap.add_argument("--score", nargs="+", metavar="PATH",
                    help="score images/.md pages against <PATH>.expect_dots sidecars")
    ap.add_argument("--model", help="override OPENAI_MODEL")
    a = ap.parse_args()
    cfg = openai_cfg(a.model)
    bad = run_score(cfg, a.score) if a.score else run_cases(cfg, a.cases)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
