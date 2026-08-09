"""Regression tests for normalize.py, from its documented contract (issue #6).

The SHOULD-NOT cases matter as much as the SHOULD cases: they are what stops
the heuristic from wrapping ordinary Korean text as if it were math.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from normalize import normalize_math

TRANSFORMS = [
    # unicode -> LaTeX
    ("넓이가 x²이다", "넓이가 $x^2$이다"),
    ("x ≤ 3", r"$x \leq 3$"),
    ("3 × 4", r"$3 \times 4$"),
    ("√n", r"$\sqrt{n}$"),
    ("원주율 π", "원주율 $\\pi$"),
    ("$x²$", "$x^2$"),
    # bare runs with a clear math signal get wrapped
    ("3x", "$3x$"),
    ("x-y", "$x-y$"),
    ("2+3", "$2+3$"),
    ("(x+1)", "$(x+1)$"),
    # single-char super/subscripts lose braces; multi-char keep them
    ("$x^{2}$", "$x^2$"),
    ("$x^{10}$", "$x^{10}$"),
    ("$a_{1}$", "$a_1$"),
    ("$a_{10}$", "$a_{10}$"),
    # delimiter canonicalization
    (r"\(x+1\)", "$x+1$"),
    (r"\[x+1\]", "$$x+1$$"),
    (r"\begin{aligned}x&=1\\y&=2\end{aligned}",
     r"$$\begin{aligned}x&=1\\y&=2\end{aligned}$$"),
    ("$$x^2+1$$", "$$x^2+1$$"),
    # \sqrt argument grouping: digits group greedily, letters stay single
    (r"$\sqrt 10$", r"$\sqrt{10}$"),
    (r"$\sqrt a$", r"$\sqrt{a}$"),
    (r"$\sqrt(25)$", r"$\sqrt{25}$"),
]

# Deliberate non-transforms: erring toward NOT wrapping when unsure.
UNCHANGED = [
    "x의 값",                    # wrapping would risk A형 -> $A$형
    "A형과 B형",
    "3.14",                      # bare number
    "7. 다음 물음에 답하시오.",   # list numbering
    "가격은 $5달러$이다",         # $..$ containing Hangul is not math
]


@pytest.mark.parametrize("src,expected", TRANSFORMS)
def test_transforms(src, expected):
    assert normalize_math(src) == expected


@pytest.mark.parametrize("src", UNCHANGED)
def test_left_alone(src):
    assert normalize_math(src) == src


def test_stray_dollar_does_not_swallow_prose():
    # "$5 이고 값은 $" contains Hangul, so the stray '$' cannot pair up and
    # swallow the prose; the real span at the end is already canonical.
    src = "가격은 $5 이고 값은 $3(x+1)$"
    assert normalize_math(src) == src


def test_unmatched_paren_repair():
    # _emit_inline: real q1 OCR put the closing '$' too late, swallowing
    # '(p, q' + prose. The span is split at the unmatched '(' so trailing
    # prose is ejected from the math span. The only place normalize.py
    # deliberately cuts up content it was handed.
    src = r"$p\leq k<q(p, q$는 소수)"
    assert normalize_math(src) == r"$p\leq k<q$(p, q는 소수)"


def test_balanced_parens_not_ejected():
    src = "$f(x)=2(x+1)$"
    assert normalize_math(src) == src


@pytest.mark.parametrize("src,_", TRANSFORMS)
def test_idempotent(src, _):
    once = normalize_math(src)
    assert normalize_math(once) == once


def test_text_masks_never_leak():
    # regression: the second \text-masking pass must skip already-masked
    # bodies, or the single unmask pass restores a bare \x00N\x00 sentinel
    # instead of the Hangul body (found on the hangul-text-in-math case)
    src = (r"즉, $ \frac{(9\text{와 }12\text{의 공배수})}"
           r"{(26\text{과 }13\text{의 공약수})} $의 꼴이어야 한다.")
    out = normalize_math(src)
    assert "\x00" not in out
    assert "공배수" in out and "공약수" in out


def test_dollar_env_leaves_block_math_alone():
    # regression: the "$ \begin..\end $" -> bare-env rule must not fire on the
    # inner dollars of an already-canonical $$..$$ block (broke idempotency)
    src = r"$$\begin{aligned}x&=1\\y&=2\end{aligned}$$"
    assert normalize_math(src) == src
