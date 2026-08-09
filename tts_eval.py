#!/usr/bin/env python3
"""Automated eval for the OCR -> normalize -> SRE-ko TTS-text pipeline.

Two layers, no listening required (the pipeline is deterministic text -> text):

1. GOLDEN CASES (eval/cases.json): each case is a raw OCR-style snippet fed
   through normalize.py + sre-probe/speak.js; the stitched Korean speech is
   checked against `must` / `mustnot` substrings.
     - a failing case is a regression;
     - a case marked "known": <reason> is an expected failure — it documents a
       struggle the pipeline has today. If it starts passing, the run says
       FIXED so the flag can be removed.

2. LINT (--lint DIR ...): signature detectors for failure classes that need no
   golden answer, run over any stitched output (including real worksheets):
   spelled-out HTML/LaTeX residue, silent math symbols, "빈 칸" cells,
   letter-by-letter spellouts, known SRE misreads, unbalanced spoken brackets.

Usage:
  python tts_eval.py                          # cases + lint stitched*/ dirs
  python tts_eval.py --cases eval/cases.json  # cases only
  python tts_eval.py --lint stitched_kma      # lint only
Exit code 1 on any unexpected case failure or error-level lint finding.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import normalize

ROOT = Path(__file__).parent

# ------------------------------------------------------------ lint detectors

DETECTORS = [
    # (name, severity, pattern) — pattern searched in the stitched speech text
    ("unsupported-math", "error", re.compile(r"지원되지 않는 수식")),
    ("latex-residue", "error", re.compile(r"\\[A-Za-z]{2,}|백슬래시|\$")),
    ("html-residue", "error", re.compile(r"<[a-z]+\b|style=|border=|width=", re.I)),
    # math symbols surviving into speech text = they were never verbalized
    ("silent-symbol", "error",
     re.compile("[∠△≡∽⊥∥≦≧≤≥×÷±√∈∉∑∏∫π°⁰¹²³⁴⁵⁶⁷⁸⁹ⁿ₀₁₂₃⋯−]")),
    ("empty-cell", "error", re.compile(r"빈 칸")),
    # runs of spaced single lowercase letters ("t e x t") — spelled-out garbage.
    # Uppercase is excluded: vertex lists like "삼각형 A B C" are legitimate.
    ("letter-spellout", "error", re.compile(r"(?:\b[a-z] ){3,}[a-z]\b")),
    ("sre-misread", "error",
     re.compile(r"합성 함수|논리곱|boldmath|흰색 정사각형|마침표 곱하기")),
]

BRACKET_PAIRS = [("괄호 열고", "괄호 닫고"),
                 ("중괄호 열고", "중괄호 닫고"),
                 ("대괄호 열고", "대괄호 닫고")]


def lint_text(text):
    """Return [(name, severity, evidence)] findings for one stitched text."""
    findings = []
    for name, severity, pat in DETECTORS:
        m = pat.search(text)
        if m:
            start = max(m.start() - 25, 0)
            snippet = text[start:m.end() + 25].replace("\n", " ")
            findings.append((name, severity, f"...{snippet}..."))
    for opener, closer in BRACKET_PAIRS:
        n_open, n_close = text.count(opener), text.count(closer)
        if n_open != n_close:
            findings.append(("unbalanced-brackets", "warn",
                             f"{opener} x{n_open} vs {closer} x{n_close}"))
    return findings


# ------------------------------------------------------------ golden cases


def stitch(named_inputs):
    """normalize each (name, text) and run speak.js once; return {name: speech}."""
    tmp = Path(tempfile.mkdtemp(prefix="ttseval-"))
    files = []
    for name, text in named_inputs:
        f = tmp / f"{name}.norm.md"
        f.write_text(normalize.normalize_math(text), encoding="utf-8")
        files.append(str(f))
    proc = subprocess.run(
        ["node", str(ROOT / "sre-probe" / "speak.js"), "--write", str(tmp), *files],
        capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"speak.js failed:\n{proc.stderr}")
    return {name: (tmp / f"{name}.stitched.txt").read_text(encoding="utf-8")
            for name, _ in named_inputs}


def run_cases(cases_path):
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    speech = stitch([(c["id"], c["input"]) for c in cases])
    n_pass = n_known = 0
    unexpected = []
    print(f"== golden cases ({cases_path}) ==")
    for c in cases:
        sp = speech[c["id"]]
        missing = [p for p in c.get("must", []) if p not in sp]
        present = [p for p in c.get("mustnot", []) if p in sp]
        ok = not missing and not present
        known = c.get("known")
        if ok and not known:
            n_pass += 1
            status = "PASS "
        elif ok and known:
            status = "FIXED"      # expected failure now passes -> drop the flag
        elif known:
            n_known += 1
            status = "KNOWN"
        else:
            unexpected.append(c["id"])
            status = "FAIL "
        print(f"  [{status}] {c['id']}")
        if status == "FAIL ":
            for p in missing:
                print(f"          missing : {p!r}")
            for p in present:
                print(f"          shouldn't contain : {p!r}")
            print(f"          speech  : {sp.strip()[:160]}")
        elif status == "KNOWN":
            print(f"          ({known})")
        elif status == "FIXED":
            print(f"          (was: {known} — remove the \"known\" flag)")
    print(f"  -> {n_pass} pass, {n_known} known struggles, {len(unexpected)} unexpected failures")
    return unexpected


def run_lint(dirs):
    n_err = 0
    for d in dirs:
        files = sorted(Path(d).glob("*.stitched.txt"))
        print(f"== lint {d} ({len(files)} files) ==")
        clean = True
        for f in files:
            findings = lint_text(f.read_text(encoding="utf-8"))
            for name, severity, evidence in findings:
                clean = False
                n_err += severity == "error"
                print(f"  [{severity:5}] {f.name}: {name}  {evidence}")
        if clean:
            print("  (clean)")
    return n_err


def main():
    args = sys.argv[1:]
    cases_path, lint_dirs = None, []
    if not args:
        cases_path = ROOT / "eval" / "cases.json"
        lint_dirs = [d for d in (ROOT / "stitched", ROOT / "stitched_kma") if d.is_dir()]
    i = 0
    while i < len(args):
        if args[i] == "--cases":
            i += 1
            cases_path = args[i]
        elif args[i] == "--lint":
            lint_dirs = args[i + 1:]
            break
        else:
            sys.exit("usage: tts_eval.py [--cases FILE] [--lint DIR ...]")
        i += 1

    failed_ids = run_cases(cases_path) if cases_path else []
    n_lint_err = run_lint(lint_dirs) if lint_dirs else 0
    if failed_ids or n_lint_err:
        sys.exit(f"\nFAILED: {len(failed_ids)} unexpected case failure(s), "
                 f"{n_lint_err} error-level lint finding(s)")


if __name__ == "__main__":
    main()
