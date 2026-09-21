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


# --- orphan brackets: their partner was split off by Hangul, so they are prose

@pytest.mark.parametrize("src", [
    "## 막대/꺾은선그래프(초3-4)",   # grade label, not "3 빼기 4 괄호 닫고"
    "## 소수의 곱셈 (초5-6)",
    "## 그래프 (초 3-4)",            # the guard must see past the space
    "(초1-2)",
    "중1-1 단원평가",
])
def test_grade_label_survives_a_wrapping_paren(src):
    assert normalize_math(src) == src


def test_orphan_closer_is_ejected_from_the_span():
    # the "(" sits outside the run (Hangul split it off), so a ")" left inside
    # the span would be spoken as a "괄호 닫고" that never opened
    assert normalize_math("(가로 3+4)") == "(가로 $3+4$)"
    # a genuinely balanced pair still belongs to the math
    assert normalize_math("점 P(a+1)") == "점 $P(a+1)$"


# --- units inside a math span (SRE spells a bare unit out letter by letter)

@pytest.mark.parametrize("src,expected", [
    ("$r = 3 cm$", r"$r = 3\mathrm{cm}$"),      # space-separated, was "3 c m"
    ("$145cm$", r"$145\mathrm{cm}$"),
    (r"$\Box cm$", r"$\Box \mathrm{cm}$"),
    ("□ cm", r"$\Box \mathrm{cm}$"),            # □ -> "\Box " leaves 2 spaces
])
def test_units_become_mathrm(src, expected):
    assert normalize_math(src) == expected


# --- a leading "N." is only a problem number when the rest is still math

def test_decimal_span_is_not_split_as_a_problem_number():
    assert normalize_math("$3. 14$") == "$3. 14$"
    assert normalize_math("접수 2026. 07. 21(화)") == "접수 2026. 07. 21(화)"


def test_problem_number_ejection_still_works():
    assert normalize_math("$5. (3x+4)$") == "5. $(3x+4)$"


# --- table cells are problem data: never drop a row the OCR malformed

def test_table_row_without_cell_tags_keeps_its_text():
    src = "<table><tr><td>2, 4, 6</td></tr><tr>8, 10, 12</tr></table>"
    out = normalize_math(src)
    assert "2, 4, 6" in out and "8, 10, 12" in out


def test_truncated_table_does_not_leak_markup():
    out = normalize_math("<table><td>12</td>")
    assert "<" not in out and "12" in out


# --- a clock time is not a 비례식 (the ratio signal made it "14 콜론 00")

@pytest.mark.parametrize("src", [
    "1) 2026.06.24(수) 14:00 문제 공개",
    "회의는 09:30 시작",
    "2:00 에 만나자",
])
def test_clock_time_is_not_wrapped_as_a_ratio(src):
    assert normalize_math(src) == src


@pytest.mark.parametrize("src,expected", [
    ("두 수의 비는 3:4 이다", "두 수의 비는 $3:4$ 이다"),
    ("변의 비가 5:12 인 삼각형", "변의 비가 $5:12$ 인 삼각형"),
])
def test_real_ratios_still_wrap(src, expected):
    assert normalize_math(src) == expected


# --- coordinate pairs: "(3, 4)" was split by the answer-key marker rule

@pytest.mark.parametrize("src,expected", [
    ("점 (3, 4)", "점 $(3, 4)$"),          # " 4)" is the pair's 2nd element…
    ("점 (-3, 4)", "점 $(-3, 4)$"),
    ("순서쌍 (2, -3)", "순서쌍 $(2, -3)$"),
    ("구간 [3, 4]", "구간 $[3, 4]$"),       # '[' is a math signal now
])
def test_coordinate_pairs_are_math(src, expected):
    assert normalize_math(src) == expected


@pytest.mark.parametrize("src,expected", [
    ("-5 (2) -5", "$-5$ (2) $-5$"),        # …but a real marker still ejects
    ("1) 다음을 구하시오", "1) 다음을 구하시오"),
    ("[3] 답", "[3] 답"),
    ("[1단계] 다음을", "[1단계] 다음을"),     # orphan '[' — its ']' Hangul split off
])
def test_list_markers_and_orphan_brackets_still_prose(src, expected):
    assert normalize_math(src) == expected
