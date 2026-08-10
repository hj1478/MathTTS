#!/usr/bin/env python3
"""Text-only LLM pass: restore repeating-decimal dots (순환소수) that OCR lost.

PaddleOCR-VL routinely drops the small dots printed above 순환소수 digits, so
0.2̇4̇ on paper arrives as the plain "0.24" — and once the dot is gone no later
stage can invent it back, so the number is spoken as if it terminated. This pass
runs BETWEEN OCR and normalize: it shows the page TEXT
(no image) to an LLM and asks which decimals the surrounding context PROVES are
repeating, then re-inserts U+0307 combining dots — the exact representation OCR
would have produced — so the rest of the pipeline is untouched.

Text-only means the model never sees the glyphs, so it must not guess.
Guardrails, in order:
  - needs_check(): a page is sent at all only if it has a decimal AND a
    repetition signal (순환 keyword, decimal followed by an ellipsis, or a
    dot that survived OCR) — no signal, no API call;
  - the model must name the 순환마디 and quote verbatim on-page evidence;
  - code accepts a correction only if the period matches the printed trailing
    digits and the evidence quote really is on the page;
  - already-dotted numbers can't match the patch pattern, so they're left alone.

Dot placement follows the Korean convention: first and last digit of the
순환마디 (one dot when it's a single digit): 0.24 period 24 -> 0.2̇4̇,
0.245 period 45 -> 0.24̇5̇, 0.16 period 6 -> 0.16̇.

Restoring the dots alone was NOT sufficient: SRE reads the notation as
typography, not as a number — $0.2̇4̇$ / $\dot{2}$ / $\overline{24}$ all speak
as descriptions of the mark ("위의 점", "윗줄"; measured, SRE 5.0.0-rc.4,
2026-08). The missing reading rule now exists PROVISIONALLY: speak.js
intercepts \dot{}/\overline{} decimals before SRE and speaks reading C from
the #17 experiment ("영 점 이사 이사 반복") — which reading is actually
unambiguous by ear is still open (#17, dot_reading_probe.py). See the
README's "Limitations".

Used by inbox_eval.py when the judge is enabled; also runs standalone:
  python dot_check.py FILE.md ...          # report what would change
  python dot_check.py --write FILE.md ...  # and patch the files in place
"""
import argparse
import re
import sys
from pathlib import Path

from llm import chat_json, openai_cfg

_DOT = "̇"                                    # combining dot above
_DECIMAL = re.compile(r"[0-9]\.[0-9]")
# repetition signals: 순환소수/순환마디 keyword, a dot OCR did keep, or an
# expanded decimal with a trailing ellipsis ("0.2424..." / "0.24⋯" / "$0.24\cdots$")
_SIGNAL = re.compile(r"순환|[0-9]̇|[0-9]+\.[0-9]+ ?(?:\.\.\.|…|⋯|\\cdots)")
_NUMBER = re.compile(r"[0-9]+\.[0-9]+")
# evidence is compared verbatim-modulo-cosmetics: the model quotes LaTeX spans
# inconsistently ("$x=0.242424\\cdots$" vs "x = 0.242424\cdots", or \(..\) for
# the page's $..$), so drop LaTeX delimiter pairs, then strip whitespace, '$'
# and '\' from both sides before the substring check
_LATEX_DELIM = re.compile(r"\\[()\[\]]")
_COSMETIC = re.compile(r"[\s$\\]+")


def _canon(s):
    return _COSMETIC.sub("", _LATEX_DELIM.sub("", s))
MAX_CHARS = 15000  # sent to the model; worksheet pages are normally way below

SYSTEM = """\
You repair OCR text from Korean math worksheets. The OCR model drops the small \
dots printed above repeating-decimal digits (순환소수 표기): 0.2̇4̇ on paper \
(= 0.2424..., 순환마디 24) arrives as the plain "0.24". You get TEXT ONLY — no \
page image — so act as a proofreader, not a guesser: report a number ONLY when \
the surrounding text uniquely determines both that it repeats AND its exact \
순환마디 (repeating block). Legitimate evidence:
  - its expanded form appears nearby: "0.242424..." for 0.24 (period "24")
  - an equation ties it to its fraction: 0.24 = 24/99 (period "24"),
    0.16 = 1/6 (period "6")
  - the text states the block: "0.245의 순환마디는 45"
  - the number still carries SOME dots and the text pins down the rest
NOT evidence: the word 순환소수 merely appearing somewhere (problems mix \
repeating and finite decimals); a decimal "looking" repeating; a period you \
could only get by solving the problem yourself. In particular, a number merely \
LABELED 순환소수 ("순환소수 0.24 를 분수로 나타내시오"), or a problem that \
ASKS for its 순환마디 ("0.63 의 순환마디를 구하시오"), proves the number \
repeats but NEVER determines WHICH digits repeat — for 0.24 both 0.2̇4̇ and \
0.24̇ fit, and the 마디 may even be the answer the student must find. Omit \
such numbers UNLESS other on-page evidence (an expanded form, a fraction \
equation, a stated 마디) independently pins the period. Worksheets often \
restate a number before asking about it — a page showing "$0.477777\\cdots$" \
alongside the compact 0.47 proves period "7" no matter what the problem \
then asks; the question wording never cancels printed evidence.

Report the compact printed number (e.g. 0.24) whose dots were lost — never the \
expanded "0.242424..." writing itself; with its ellipsis it already shows the \
repetition. The period must be the TRAILING digits of the printed number: for \
"0.245" a period of "45" works (0.2454545...), "24" is impossible. If the \
printed digits and the period disagree, or you are at all unsure, omit the \
number. An empty list is a perfectly good answer.

Reply with ONLY this JSON (no prose):
{"analysis": "<brief scratchpad: candidates and why kept/dropped>",
 "numbers": [{"number": "<verbatim as printed, e.g. 0.24>",
              "period": "<repeating block, e.g. 24>",
              "evidence": "<verbatim quote from TEXT that proves it>"}]}

The evidence must be ONE contiguous verbatim span of TEXT — never join \
sentences from different places into one quote. If the proof lives in a \
different sentence than the number itself, quote only the decisive span \
(e.g. just the expanded form or the fraction equation)."""


def needs_check(text):
    """Cheap gate: decimal present AND a repetition signal — else no API call."""
    return bool(_DECIMAL.search(text)) and bool(_SIGNAL.search(text))


def _dotify(number, period):
    """0.245, 45 -> 0.24̇5̇ (dots on first+last digit of the trailing period)."""
    whole, frac = number.split(".")
    marks = {len(frac) - len(period), len(frac) - 1}
    return whole + "." + "".join(d + _DOT if i in marks else d
                                 for i, d in enumerate(frac))


def restore(cfg, text, tag):
    """One page of OCR text -> (patched_text, notes, error). Corrections the
    validators reject are reported in notes but never applied."""
    # temperature 0: this is extraction, not judgment — run-to-run sampling
    # variance directly costs recall (a number caught one run, missed the next)
    data, err = chat_json(cfg, SYSTEM,
                          "PAGE TEXT (OCR markdown):\n" + text[:MAX_CHARS], tag,
                          temperature=0)
    if err:
        return text, [], err
    notes, patched = [], text
    items = data.get("numbers")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        number = str(item.get("number", ""))
        period = str(item.get("period", ""))
        evidence = str(item.get("evidence", ""))
        if not _NUMBER.fullmatch(number) or not period.isdigit():
            continue
        if not number.split(".")[1].endswith(period):
            notes.append(f"rejected {number}: period {period!r} doesn't match "
                         "the printed trailing digits")
            continue
        if not evidence or _canon(evidence) not in _canon(text):
            notes.append(f"rejected {number}: evidence {evidence!r} not found "
                         "on the page")
            continue
        dotted = _dotify(number, period)
        # standalone token only: no digit/'.' before (avoid the tail of a longer
        # number), no digit/dot after (avoid a prefix of "0.242424" / "0.24̇")
        patched, n = re.subn(rf"(?<![0-9.]){re.escape(number)}(?![0-9{_DOT}])",
                             dotted, patched)
        if n:
            notes.append(f"{number} -> {dotted} ({n}x; evidence: {evidence!r})")
    return patched, notes, ""


def main():
    ap = argparse.ArgumentParser(
        description="Restore 순환소수 dots OCR lost, via a text-only LLM pass.")
    ap.add_argument("files", nargs="+", metavar="FILE")
    ap.add_argument("--write", action="store_true", help="patch files in place")
    ap.add_argument("--model", help="override OPENAI_MODEL")
    a = ap.parse_args()
    cfg = openai_cfg(a.model)
    failed = False
    for f in map(Path, a.files):
        text = f.read_text(encoding="utf-8")
        if not needs_check(text):
            print(f"{f}: no repetition signal — skipped (no API call)")
            continue
        patched, notes, err = restore(cfg, text, f.name)
        for n in notes:
            print(f"{f}: {n}")
        if err:
            print(f"{f}: {err}")
            failed = True
        elif patched == text:
            print(f"{f}: nothing to restore")
        elif a.write:
            f.write_text(patched, encoding="utf-8")
            print(f"{f}: patched in place")
        else:
            print(f"{f}: would change (rerun with --write to apply)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
