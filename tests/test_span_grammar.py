"""The math-span grammar must behave identically in Python and JS (issue #4).

eval/fixtures/span_cases.json holds the tricky inputs; this test checks the
Python side (normalize.SPAN), sre-probe/span.test.js checks the JS copy in
speak.js against the same file. Editing one grammar and forgetting the other
fails one of the two suites instead of going unnoticed.

Only the $-delimited forms are compared: speak.js consumes normalize.py
output, which emits nothing else, so its grammar is deliberately narrower
than normalize.SPAN (which also accepts raw \\(..\\), \\[..\\] and
\\begin{..}..\\end{..} from the OCR).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import normalize
import ocr_vl

CASES = json.loads((ROOT / "eval" / "fixtures" / "span_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_python_span_grammar(case):
    found = [m.group(0) for m in normalize.SPAN.finditer(case["text"])
             if m.group(0).startswith("$")]
    assert found == case["spans"]


def test_ocr_vl_shares_the_python_definition():
    # ocr_vl.LATEX must stay an import of normalize.SPAN, not drift back
    # into a third hand-written copy.
    assert ocr_vl.LATEX is normalize.SPAN
