#!/usr/bin/env python3
"""Normalize OCR math markdown to canonical inline LaTeX.

PaddleOCR-VL emits math inconsistently: sometimes $...$ LaTeX, sometimes plain
text ("2x(3x+1)") or unicode ("x²", "≤"). This unifies all of it into consistent
inline $...$ LaTeX so a downstream verbalizer gets one format.

This is a HEURISTIC, not a LaTeX parser — there is no reliable way to tell a lone
variable from a stray letter, so it errs toward NOT wrapping when unsure.

DOES:
  - strip structural HTML (<div>/<img>...): OCR figure scaffolding, never
    speakable, and attribute soup would otherwise be wrapped as "math";
    <table> CELL TEXT is kept (one line per row) — dropping it loses problem
    data like a number list the question asks about
  - convert bare LaTeX left in PROSE (OCR omitting $..$: "26=2\\times13",
    "3^{2}") into the unicode the pipeline already handles; unwrap \\text{..},
    drop any remaining \\commands and stray backslashes (real prose never
    contains a backslash — it is always OCR residue)
  - eject list markers "(1)" / "[3]" (digit-only, space- or marker-followed)
    from bare runs and inline spans so "(3) (2)를" is not read "3 곱하기 2 를";
    a no-space "(2)(x+1)" still counts as a product
  - allow inline $..$ spans whose only Hangul is inside \\text{..} arguments
    (valid OCR math like $\\frac{(9\\text{와 }12\\text{의 공배수})}{..}$) by
    masking \\text bodies before span-matching and restoring them at the end
  - convert unicode math -> LaTeX: x²->x^2, ≤->\\leq, ×->\\times, √n->\\sqrt{n},
    sub/superscripts, greek (π->\\pi ...), geometry (∠->\\angle, △, ≡, ∽, ⊥, ∥, →;
    ° kept as-is — SRE-ko reads the raw char as "도" but misreads ^\\circ), repeating-
    decimal dots (2̇->\\dot{2}), digit-adjacent metric units (5cm->5\\mathrm{cm}),
    both inside existing $...$ and in bare text
  - wrap a bare math RUN in $...$ only when it has a clear signal: a super/subscript,
    a unicode math symbol, letter-digit adjacency (3x), an operator between operands
    (x-y, 2+3), a leading negative (-2.4), parentheses containing alphanumerics,
    an absolute-value pair (|x-2|), a ratio (3:4), or a repeating-decimal dot
  - canonicalize ^{2}->^2 (single char), keep ^{10} braced; same for _{...}
  - normalize \\(..\\) -> $..$ and \\[..\\] -> $$..$$; wrap bare \\begin{..}..\\end{..}
    environments in $$..$$ (and protect their insides from the bare-run wrapper)
  - clean OCR artifacts inside \\begin environments: empty first/last rows and empty
    leading cells (spoken as "빈 칸"), and unwrap an env left with one unaligned row
  - repair math spans that swallowed prose: a leading problem number ("$5. (3x+4)$")
    and everything from an unmatched '(' onward ("$p\\leq k<q(p, q$") are ejected
  - treat a $..$ containing Hangul as NOT math: a stray unpaired '$' in prose
    would otherwise pair with a later math '$' and swallow the prose between

DOESN'T (documented misses, chosen to avoid false positives):
  - wrap a lone variable with no signal: "x의" stays "x의" (would risk "A형"->"$A$형")
  - wrap bare numbers: "3.14", "7." (leading list numbers) stay as text
  - parse/validate LaTeX or resolve ambiguous digit ranges ("3-4" -> $3-4$ if it looks
    like subtraction; that's accepted as a known edge)
  - touch ℃/% or single-letter units (m, g, L): left as prose for the TTS voice,
    which reads them natively; a lone letter after a digit is usually a variable

CLI:
  python normalize.py "output/kr question 3.md"   # print normalized text
  python normalize.py --dir output                # normalize every *.md -> *.norm.md
  cat file.md | python normalize.py -             # stdin -> stdout
"""
import re
import sys
from pathlib import Path

# ------------------------------------------------------------------ tables

SUP = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6",
       "⁷": "7", "⁸": "8", "⁹": "9", "ⁿ": "n", "⁺": "+", "⁻": "-",
       # superscript letters (no superscript q exists in Unicode)
       "ᵃ": "a", "ᵇ": "b", "ᶜ": "c", "ᵈ": "d", "ᵉ": "e", "ᶠ": "f", "ᵍ": "g",
       "ʰ": "h", "ⁱ": "i", "ʲ": "j", "ᵏ": "k", "ˡ": "l", "ᵐ": "m", "ᵒ": "o",
       "ᵖ": "p", "ʳ": "r", "ˢ": "s", "ᵗ": "t", "ᵘ": "u", "ᵛ": "v", "ʷ": "w",
       "ˣ": "x", "ʸ": "y", "ᶻ": "z"}
SUB = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6",
       "₇": "7", "₈": "8", "₉": "9", "₊": "+", "₋": "-"}
SYM = {"×": r"\times ", "÷": r"\div ", "·": r"\cdot ", "⋅": r"\cdot ", "±": r"\pm ",
       "≤": r"\leq ", "≥": r"\geq ", "≠": r"\neq ", "≈": r"\approx ", "∞": r"\infty ",
       "−": "-", "∈": r"\in ", "∉": r"\notin ", "∑": r"\sum ", "∏": r"\prod ",
       "∫": r"\int ", "√": r"\sqrt ", "π": r"\pi ", "θ": r"\theta ", "α": r"\alpha ",
       "β": r"\beta ", "γ": r"\gamma ", "λ": r"\lambda ", "μ": r"\mu ", "σ": r"\sigma ",
       "φ": r"\phi ", "ω": r"\omega ", "ρ": r"\rho ", "Δ": r"\Delta ", "∆": r"\Delta ",
       # geometry/relations common in KO middle-school print. Spoken forms verified
       # against SRE-ko: ∠→"각", °→"도", ≡→"합동이다", ⊥→"수직이다", ∥→"평행하다";
       # ∽ and → read literally ("물결표", "오른쪽 화살표") but silence loses meaning.
       # ° stays as-is (identity): temml reads the raw char as "도", while ^\circ is
       # misread by SRE-ko as function composition — do NOT "canonicalize" it.
       "∠": r"\angle ", "△": r"\triangle ", "≡": r"\equiv ", "∽": r"\sim ",
       "⊥": r"\perp ", "∥": r"\parallel ", "≦": r"\leq ", "≧": r"\geq ",
       "→": r"\to ", "°": "°",
       # fill-in-the-blank box (□안에 알맞은 수): SRE-ko reads \Box as
       # "흰색 정사각형"; speak.js rewrites that to "네모" post-SRE
       "□": r"\Box "}
_SYM_TT = str.maketrans(SYM)  # every key is one char -> single-pass translate

_SUP_CLS = "".join(map(re.escape, SUP))
_SUB_CLS = "".join(map(re.escape, SUB))
_UNI_CLS = "".join(map(re.escape, list(SYM) + list(SUP) + list(SUB)))

# ------------------------------------------------------------------ regexes

# characters that may form a bare math run (excludes whitespace; handled separately)
# '|' (절댓값), ':' (비례식) and U+0307 combining dot (순환소수 2̇) are included so
# |x-2|, 3:4 and 0.2̇3̇ stay whole instead of splitting at the symbol.
_RUN_CLS = r"0-9A-Za-z+\-*/=^_<>()\[\]{}.,|:" + "̇" + _UNI_CLS
RUN = re.compile(rf"[{_RUN_CLS}](?:[{_RUN_CLS} ]*[{_RUN_CLS}])?")

# existing math spans to leave wrapped (contents still normalized).
# Inline $..$ may not contain Hangul, '$' or newlines: a stray unpaired '$' in
# prose would otherwise pair with a later math '$' and swallow the text between
# them (e.g. "가격은 $5 ... $3(x+1)$"). Real OCR math spans never contain Hangul.
# Bare \begin{..}..\end{..} environments are matched whole so their insides are
# protected from _wrap_bare (which would corrupt them piecemeal).
SPAN = re.compile(
    r"(\$\$.+?\$\$"
    r"|\\begin\{[^}]+\}.*?\\end\{[^}]+\}"
    r"|\$[^$\n가-힣]+?\$"
    r"|\\\(.+?\\\)|\\\[.+?\\\])",
    re.DOTALL,
)

# Structural HTML the OCR embeds around figures/tables. It is never speakable and
# the bare-run wrapper would otherwise turn attributes into "math" that a
# verbalizer spells out letter by letter ("t e x t 빼기 a l i g n ..."). Only
# known structural tags are matched so prose like "<m, n>=k" is untouched.
# Tables are handled FIRST by _table_text (cell content is real problem data);
# the <table> alternative below only catches malformed leftovers.
HTML_BLOCK = re.compile(
    r"<table\b.*?</table>"
    r"|<div\b[^>]*>|</div\s*>"
    r"|<img\b[^>]*/?>"
    r"|<br\s*/?>",
    re.DOTALL | re.IGNORECASE,
)
TABLE = re.compile(r"<table\b.*?</table>", re.DOTALL | re.IGNORECASE)
_TROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
_TCELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")

_SUP_RUN = re.compile(rf"[{_SUP_CLS}]+")
_SUB_RUN = re.compile(rf"[{_SUB_CLS}]+")
_SQRT_PAREN = re.compile(r"\\sqrt\s*\(([^)]*)\)")
_SQRT_ARG = re.compile(r"\\sqrt\s*([0-9]+|[A-Za-z])")
_SUP_UNBRACE = re.compile(r"\^\{([0-9A-Za-z])\}")
_SUB_UNBRACE = re.compile(r"_\{([0-9A-Za-z])\}")
_RDOT_DIGIT = re.compile("([0-9])̇")   # 2̇ (combining dot above) -> \dot{2}
# ^{\circ} / ^\circ -> raw ° INSIDE math: temml+SRE read the raw char as "도",
# while the superscript form is misread as function composition ("합성 함수")
_CIRC = re.compile(r"\^\s*\{?\s*\\circ\s*\}?")
# digit-adjacent metric unit -> \mathrm{..} so SRE says "센티미터", not "c m".
# Multi-letter units only: a lone m/g/L after a digit is more likely a variable.
_UNIT = re.compile(r"(?:(?<=[0-9])|(?<=\\Box ))(cm|mm|km|kg|mL|ml)(?![A-Za-z])")
# "\quad(a<0)" — a \quad-spaced parenthesized CONDITION after an expression;
# juxtaposition would be read as multiplication ("네모 곱하기 괄호 열고 a...")
_QUAD_COND = re.compile(r"\\q?quad\s*(?=\()")
_WS = re.compile(r"\s+")

_ENV_FIRST_ROW = re.compile(r"(\\begin\{[A-Za-z]+\*?\})\s*\\\\")
_ENV_LAST_ROW = re.compile(r"\\\\\s*&*\s*(?=\\end\{)")
_ENV_LEAD_CELL = re.compile(r"(\\begin\{[A-Za-z]+\*?\}\s*|\\\\\s*)&\s*")
# "&&" double-alignment (OCR piecewise: "2x+1 && (x>1)") -> one empty cell
# spoken as "빈 칸"; collapse to a single separator
_ENV_MULTI_AMP = re.compile(r"&\s*&+")
_ENV_TRIVIAL = re.compile(
    r"\\begin\{([A-Za-z]+)\*?\}((?:(?!\\begin\{|\\end\{|\\\\|&).)*)\\end\{\1\*?\}",
    re.DOTALL,
)
# array/tabular column spec ({r}, {c|c}) — layout, not content; unwrapping the
# env without dropping it would speak the spec ("r 빼기 4 콤마 ...")
_ENV_COLSPEC = re.compile(r"(\\begin\{(?:array|tabular)\*?\})\s*\{[^{}]*\}")
# a single-$ pair around a whole multi-line env ("$ \begin{array}...\end{array} $"):
# the inline SPAN can't match across newlines, so the env alternative would grab
# just the middle and leave two stray '$'s that later pair into EMPTY math spans
# lookarounds keep this off $$..$$ blocks: without them a second normalize pass
# would strip an already-canonical "$$\begin..\end$$" down to "$\begin..\end$"
_DOLLAR_ENV = re.compile(r"(?<!\$)\$(?!\$)\s*(\\begin\{[^}]+\}.*?\\end\{[^}]+\})\s*(?<!\$)\$(?!\$)",
                         re.DOTALL)

_PROBLEM_NO = re.compile(r"\s*(\d+)\.\s+(?=\S)")

# list markers: "(1)" / "[3]" (digit-only) followed by space, another marker, or
# end of run. "(2)(x+1)" — no space, followed by real math — is a product instead.
_LIST_MARKER = re.compile(r"([(\[]\d{1,2}[)\]]|\d{1,2}\))(?:\s+|(?=[(\[])|$)")
# space-delimited marker anywhere in prose (answer keys: "-5 (2) -5"): isolated
# with \x02 so it can never join a math run as implicit multiplication
_INNER_MARKER = re.compile(r"(^|\s)([(\[]\d{1,2}[)\]]|\d{1,2}\))(?=\s|$)", re.MULTILINE)
# fill-in-the-blank rendered as \boxed{..} -> box char + content ("네모 파이 m")
_BOXED = re.compile(r"\\boxed\s*\{([^{}]*)\}")
# □ + vertex letters is QUADRILATERAL notation (□ABCD = 사각형 ABCD), not a
# fill-in-the-blank box — disambiguate before the □→\Box (네모) mapping runs
# (?![A-Za-z]) not \b: Hangul counts as \w, so \b never fires before "가" etc.
_QUAD = re.compile(r"□\s*(?=[A-Z]{3,4}(?![A-Za-z]))")
# a run can never START with a matched ')': its opener sits outside the run
# (ejected or Hangul-split, e.g. "(수) 14:00"), so a leading closer is prose
_LEAD_CLOSE = re.compile(r"^[)\]}]+\s*")

# PaddleOCR-VL reliably corrupts 절댓값(+particle) — observed on every KMA and
# 단원평가 sheet so far. The corrupted forms are not valid Korean in a math
# worksheet, so whole-word replacement is safe. Longest first.
_OCR_TYPOS = [("절맞았이", "절댓값이"), ("절맞았어", "절댓값이"),
              ("절맛값", "절댓값"), ("절맞은", "절댓값은"), ("절망은", "절댓값은"),
              ("제물 사분면", "제몇 사분면")]

# --- bare-LaTeX-in-prose repair (OCR sometimes omits the $..$ delimiters) ---
_TEXT_CMD = re.compile(r"\\text\s*\{([^{}]*)\}")
# masking variant: skips bodies that already hold a \x00 sentinel, so the
# second masking pass (for env-Hangul wraps) can't re-mask a masked token
_TEXT_CMD_UNMASKED = re.compile("\\\\text\\s*\\{([^{}\x00]*)\\}")
_BARE_CMD = {"times": "×", "div": "÷", "cdot": "·", "leq": "≤", "geq": "≥",
             "neq": "≠", "pm": "±", "pi": "π", "sqrt": "√", "infty": "∞",
             # bare trig commands -> Korean words (in-span \tan is fine as-is)
             "sin": "싸인 ", "cos": "코싸인 ", "tan": "탄젠트 "}
# (?![A-Za-z]) not \b: a digit may follow directly ("2\times13") and \b would
# fail between two word chars, dropping the command instead of converting it
_BARE_CMD_RE = re.compile(r"\\(" + "|".join(_BARE_CMD) + r")(?![A-Za-z]) ?")
_INV_SUP = {v: k for k, v in SUP.items()}
_INV_SUB = {v: k for k, v in SUB.items()}
_BARE_SUP_RE = re.compile(r"\^\{([0-9A-Za-z+\-]{1,4})\}")
_BARE_SUB_RE = re.compile(r"_\{([0-9A-Za-z+\-]{1,4})\}")
_RESIDUE_CMD = re.compile(r"\\[A-Za-z]+\*?")
_TEXT_MASK = re.compile("\x00(\\d+)\x00")
# a VALID \frac{a}{b} left bare in prose (choice lists: "③ +\frac{5}{4}") must
# become a $..$ span, not be scrubbed to "{5}{4}"; one nesting level per arg.
# A directly-adjacent leading integer is a MIXED NUMBER (2\frac{3}{4} = 대분수)
# and must stay inside the span so SRE reads "2 와 4 분의 3".
_FRAC_ARG = r"\{((?:[^{}]|\{[^{}]*\})*)\}"
_BARE_FRAC = re.compile(r"(\d*)\\frac\s*" + _FRAC_ARG + r"\s*" + _FRAC_ARG)
_FRAC_MASK = re.compile("\x01(\\d+)\x01")
# mixed number with the integer OUTSIDE the span ("2$\frac{1}{3}$") -> move it in
_MIXED_SPAN = re.compile(r"(\d+)\$\s*(?=\\frac)")
# Hangul as a math operand (\sqrt{분산}, \frac{공배수}{n}) -> wrap in \text{} so
# the span survives the no-Hangul rule (the \text masking handles the rest).
# Second \frac arg first: after arg 1 gains \text{}, its braces would break \1.
_HANGUL_ARG2 = re.compile(r"(\\frac\s*\{[^{}]*\}\s*)\{(\s*[가-힣][^{}]*)\}")
_HANGUL_ARG1 = re.compile(r"(\\(?:sqrt|frac))\s*\{(\s*[가-힣][^{}]*)\}")
# division-with-remainder "13÷4=3⋯1" -> spoken Korean; digit⋯digit only, so
# sequence ellipses ("1, 4, 7, ⋯" — comma-separated) never match
_REMAINDER = re.compile(r"(\d+)\s*⋯\s*(\d+)")
# bare Hangul inside a \begin..\end body (piecewise conditions "(x는 짝수)")
# gets \text{}-wrapped so the span survives the no-Hangul rule via masking
_ENV_BLOCK = re.compile(r"\\begin\{[^}]+\}.*?\\end\{[^}]+\}", re.DOTALL)
_HANGUL_RUN = re.compile(r"[가-힣](?:[가-힣 \t]*[가-힣])?")
# bare trig words in prose ("sin 30°"): OCR often emits them without \ or $
_TRIG = re.compile(r"\b(sin|cos|tan)(?![A-Za-z])\s*")
_TRIG_KO = {"sin": "싸인 ", "cos": "코싸인 ", "tan": "탄젠트 "}
# a run of ONLY connector dots (가운뎃점 · in headers, ··· ellipsis) is Korean
# punctuation, not math — wrapping it makes SRE say "닷"
_CONNECTOR_ONLY = re.compile(r"^[·⋅… ]+$")

# math signals for _is_math (paren clause is plain string logic, not a regex)
_SIG_UNI = re.compile(rf"[{_UNI_CLS}]")                            # x², ≤, π, √, ×
_SIG_ADJ = re.compile(r"[A-Za-z][0-9]|[0-9][A-Za-z]")              # 3x, x2
_SIG_OP = re.compile(r"[0-9A-Za-z]\s*[-+*/=^<>]\s*[0-9A-Za-z]")    # x-y, 2+3, a=b
_SIG_NEG = re.compile(r"^-\s*[0-9]")                               # -2.4
_SIG_ABS = re.compile(r"\|[^|]+\|")                                # |a|, |x-2|
_SIG_RATIO = re.compile(r"[0-9A-Za-z]:[0-9A-Za-z]")                # 3:4 (비례식)
_SIG_RDOT = re.compile("[0-9]̇")                              # 2̇ (순환소수)
# a 4+-letter lowercase word means English PROSE, not math (variables are 1–2
# letters; sin/cos/tan are converted earlier) — wrapping it makes SRE spell it
# out letter by letter ("f 의 i g 의 u r e 빼기 d e p e n d e n t")
_ENGLISH_WORD = re.compile(r"[a-z]{4,}")
# symbols inside an English-prose run stay unwrapped — voice them as words so
# they aren't silently dropped by the TTS voice
_SILENT_KO = str.maketrans({"√": "루트 ", "±": "플러스 마이너스 ", "×": "곱하기 ",
                            "÷": "나누기 ", "≤": " 작거나 같다 ", "≥": " 크거나 같다 ",
                            "π": "파이 ", "∠": "각 ", "°": "도 ",
                            "²": " 제곱 ", "³": " 세제곱 "})
# digit-range directly after a Hangul char ("초1-2", "중1-1 단원평가") is a
# grade/section LABEL — reading the hyphen as 빼기 turns it into subtraction
_GRADE_RANGE = re.compile(r"\d{1,2}-\d{1,2}")

# ------------------------------------------------------------------ helpers


def _clean_envs(s):
    """Drop OCR artifacts inside \\begin..\\end environments: empty first/last
    rows, empty leading cells (both verbalized as "빈 칸"), and unwrap an
    environment reduced to a single unaligned row — OCR wrapping noise around
    what is really just an expression or list."""
    s = _ENV_COLSPEC.sub(r"\1", s)
    s = _ENV_MULTI_AMP.sub("&", s)
    prev = None
    while prev != s:
        prev = s
        s = _ENV_FIRST_ROW.sub(r"\1", s)
        s = _ENV_LAST_ROW.sub("", s)
        s = _ENV_LEAD_CELL.sub(r"\1", s)
        s = _ENV_TRIVIAL.sub(r"\2", s)
    return s


def _latexify(s, literal_braces=False):
    """Convert unicode math + canonicalize LaTeX in an expression (no wrapping).

    literal_braces: for bare plain-text runs, where '{'/'}' are printed braces
    (÷{(-2)⁴×(-2)}) and must become \\{..\\} — in a LaTeX span they are grouping
    and must be left alone. Safe because bare runs can never contain LaTeX
    commands ('\\' is not a run character)."""
    if literal_braces:
        s = s.replace("{", r"\{").replace("}", r"\}")
    s = _clean_envs(s)
    s = _CIRC.sub("°", s)
    s = _RDOT_DIGIT.sub(r"\\dot{\1}", s)
    s = _SUP_RUN.sub(lambda m: "^{" + "".join(SUP[c] for c in m.group()) + "}", s)
    s = _SUB_RUN.sub(lambda m: "_{" + "".join(SUB[c] for c in m.group()) + "}", s)
    s = s.translate(_SYM_TT)
    s = _SQRT_PAREN.sub(r"\\sqrt{\1}", s)
    # digits group greedily: √10 means sqrt(10), so \sqrt 10 -> \sqrt{10};
    # letters stay single (√ab is ambiguous, don't guess)
    s = _SQRT_ARG.sub(r"\\sqrt{\1}", s)
    s = _SUP_UNBRACE.sub(r"^\1", s)   # x^{2} -> x^2 (single char only)
    s = _SUB_UNBRACE.sub(r"_\1", s)
    s = _QUAD_COND.sub(", ", s)
    s = _UNIT.sub(r"\\mathrm{\1}", s)  # after unbracing so "b^2cm" sees the digit
    return _WS.sub(" ", s).strip()


def _is_math(core):
    """True if a run (already stripped of edge punctuation) has a clear math signal."""
    if _ENGLISH_WORD.search(core):
        return False
    return bool(
        _SIG_UNI.search(core)
        or _SIG_ADJ.search(core)
        or _SIG_OP.search(core)
        or _SIG_NEG.search(core)
        or _SIG_ABS.search(core)
        or _SIG_RATIO.search(core)
        or _SIG_RDOT.search(core)
        or ("(" in core and re.search(r"[0-9A-Za-z]", core))
    )


def _table_text(m):
    """<table> -> its cell text, one line per row. The markup is scaffolding but
    the cells are real problem data (e.g. the number list a question asks about)."""
    rows = _TROW.findall(m.group()) or [m.group()]
    lines = []
    for row in rows:
        cells = [_TAG.sub(" ", c).strip() for c in _TCELL.findall(row)]
        cells = [c for c in cells if c]
        if cells:
            lines.append(" ".join(cells))
    return ("\n\n" + "\n\n".join(lines) + "\n\n") if lines else " "


def _delatex_prose(s):
    """Repair bare LaTeX left in PROSE (outside any $..$): convert known commands
    to the unicode the pipeline already handles, unbrace ^{..}/_{..} into unicode
    scripts, unwrap \\text{..}, then drop leftover \\commands and stray
    backslashes — real Korean prose never contains a backslash, so any survivor
    is OCR residue that would otherwise become spelled-out "math" runs."""
    if "\\" not in s and "^{" not in s and "_{" not in s:
        return s
    s = _CIRC.sub("°", s)          # ^{\circ} in bare prose, e.g. \tan 60^{\circ}
    s = _TEXT_CMD.sub(r"\1", s)
    s = re.sub(r"\\text\s*\{", " ", s)   # unclosed \text{ (OCR) — orphan brace
                                         # would join a math run as 중괄호
    kept = []  # valid bare \frac -> $..$ span, masked past the residue scrub

    def _keep_frac(m):
        kept.append(f"${m.group(1)}\\frac{{{m.group(2)}}}{{{m.group(3)}}}$")
        return f"\x01{len(kept) - 1}\x01"

    s = _BARE_FRAC.sub(_keep_frac, s)
    s = _BARE_CMD_RE.sub(lambda m: _BARE_CMD[m.group(1)], s)

    def scripts(table):
        def repl(m):
            try:
                return "".join(table[c] for c in m.group(1))
            except KeyError:
                return m.group()      # no unicode form (e.g. 'q') — leave as-is
        return repl

    s = _BARE_SUP_RE.sub(scripts(_INV_SUP), s)
    s = _BARE_SUB_RE.sub(scripts(_INV_SUB), s)
    s = _RESIDUE_CMD.sub(" ", s)
    s = s.replace("\\", " ")
    return _FRAC_MASK.sub(lambda m: kept[int(m.group(1))], s)


def _eject_list_markers(s):
    """Split leading list markers off a run: "(1) 45" -> ("(1) ", "45"),
    "(3)(2)" -> ("(3) (2) ", ""). A no-space marker followed by non-marker math
    ("(2)(x+1)") is a product and is left intact. Returns ("", s) when absent."""
    lead, rest = "", s
    while (m := _LIST_MARKER.match(rest)):
        gap = m.end() > len(m.group(1))           # whitespace followed the marker
        nxt = rest[m.end():]
        if not gap and nxt[:1] == "(" and not _LIST_MARKER.match(nxt) and _is_math(nxt):
            break
        lead += m.group(1) + " "
        rest = nxt
    return lead, rest


def _eject_problem_number(s):
    """Split a leading problem number off a math span: "5. (3x+4)..." ->
    ("5. ", "(3x+4)..."). OCR sometimes swallows it into the math, where it
    would be verbalized as "5 마침표 곱하기". Returns ("", s) when absent."""
    m = _PROBLEM_NO.match(s)
    if m:
        return f"{m.group(1)}. ", s[m.end():]
    return "", s


def _split_unmatched_paren(s):
    """Split (math, rest) at the first '(' that never closes — an unmatched '('
    inside a math run is always mis-captured prose (e.g. 'q(p, q는 상수)')."""
    depth, cut = 0, None
    for i, ch in enumerate(s):
        if ch == "(":
            if depth == 0:
                cut = i               # start of a group not yet closed
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
            if depth == 0:
                cut = None            # that group closed -> balanced so far
    if depth > 0 and cut is not None:
        return s[:cut], s[cut:]
    return s, ""


# ------------------------------------------------------------------ wrapping


def _wrap_bare(text):
    def repl(m):
        run = m.group()
        core = run.strip(" .,:")                      # keep .,:/space adjacent to Korean outside
                                                      # (a ratio ':' is interior, a label ':' is edge)
        if not core or _CONNECTOR_ONLY.match(core) or not _is_math(core):
            if _ENGLISH_WORD.search(core) and _SIG_UNI.search(core):
                return run.translate(_SILENT_KO)
            return run
        if (_GRADE_RANGE.fullmatch(core) and m.start() > 0
                and "가" <= m.string[m.start() - 1] <= "힣"):
            return run
        i = run.find(core)
        j = i + len(core)
        lead, rest = _eject_problem_number(core)
        if lead and _is_math(rest):                   # still math without the number
            core = rest
        else:
            lead = ""
        mlead, mrest = _eject_list_markers(core)
        if mlead:
            if not mrest.strip() or not _is_math(mrest):
                return run                            # marker(s) + non-math: prose
            lead += mlead
            core = mrest
        mclose = _LEAD_CLOSE.match(core)
        if mclose:
            if not _is_math(core[mclose.end():]):
                return run
            lead += mclose.group()
            core = core[mclose.end():]
        math, after = _split_unmatched_paren(core)
        if not math.strip():
            return run
        return f"{run[:i]}{lead}${_latexify(math, literal_braces=True)}${after}{run[j:]}"
    return RUN.sub(repl, text)


def _emit_inline(inner):
    """Wrap an inline math span, repairing delimiters that swallowed prose: a
    leading problem number and everything from an unmatched '(' onward are
    ejected back to prose. Anything else is left intact — never drop content."""
    lead, inner = _eject_problem_number(inner)
    mlead, mrest = _eject_list_markers(inner)
    if mlead:
        lead += mlead
        inner = mrest
    math, after = _split_unmatched_paren(inner)
    core = f"${_latexify(math)}$" if math.strip() else math
    return f"{lead}{core}{after}"


def normalize_math(text):
    """Normalize all math in OCR markdown to canonical inline $...$ LaTeX."""
    for bad, good in _OCR_TYPOS:
        text = text.replace(bad, good)
    text = text.replace("☐", "□").replace("▢", "□")   # box-char variants
    text = TABLE.sub(_table_text, text)
    text = HTML_BLOCK.sub(" ", text)
    text = _DOLLAR_ENV.sub(r"\1", text)   # "$ \begin..\end $" -> bare env
    text = _BOXED.sub(r"□\1", text)       # \boxed{..} -> fill-in-blank box
    text = _QUAD.sub("사각형 ", text)      # □ABCD -> 사각형 ABCD (not a blank)
    text = _REMAINDER.sub(r"몫 \1 나머지 \2", text)   # 13÷4=3⋯1
    text = text.replace("⋯", "…")         # leftover sequence ellipses -> prose
    text = _MIXED_SPAN.sub(r"$\1", text)  # 2$\frac{1}{3}$ -> $2\frac{1}{3}$
    text = _HANGUL_ARG2.sub(r"\1{\\text{\2}}", text)
    text = _HANGUL_ARG1.sub(r"\1{\\text{\2}}", text)

    # Mask \text{..} bodies so a GENUINE math span whose only Hangul lives in
    # \text arguments isn't rejected by SPAN's no-Hangul rule and shredded.
    masked = []

    def _mask(m):
        masked.append(m.group(1))
        return "\\text{\x00" + str(len(masked) - 1) + "\x00}"

    text = _TEXT_CMD.sub(_mask, text)
    # existing \text bodies are masked now, so any Hangul still inside an env
    # body is bare (piecewise conditions) — wrap it in \text and mask again
    text = _ENV_BLOCK.sub(
        lambda m: _HANGUL_RUN.sub(lambda h: "\\text{" + h.group(0) + "}", m.group(0)),
        text)
    text = _TEXT_CMD_UNMASKED.sub(_mask, text)  # skip already-masked bodies:
    # re-masking them nests sentinels and the single unmask pass would leak them

    out = []
    for part in SPAN.split(text):
        if not part:
            continue
        if part.startswith("$$") and part.endswith("$$"):
            out.append(f"$${_latexify(part[2:-2])}$$")
        elif part.startswith(r"\begin"):
            out.append(f"$${_latexify(part)}$$")          # bare env -> $$..$$
        elif part.startswith("$") and part.endswith("$") and len(part) > 1:
            prev = out[-1][-1:] if out and out[-1] else ""
            if (_GRADE_RANGE.fullmatch(part[1:-1].strip())
                    and "가" <= prev <= "힣"):
                out.append(part[1:-1].strip())    # "조$1-2$" label, not math
            else:
                out.append(_emit_inline(part[1:-1]))
        elif part.startswith(r"\(") and part.endswith(r"\)"):
            out.append(_emit_inline(part[2:-2]))          # \(..\) -> $..$
        elif part.startswith(r"\[") and part.endswith(r"\]"):
            out.append(f"$${_latexify(part[2:-2])}$$")    # \[..\] -> $$..$$
        else:
            part = _TRIG.sub(lambda m: _TRIG_KO[m.group(1)], part)
            part = _INNER_MARKER.sub("\\1\x02\\2\x02", _delatex_prose(part))
            out.append(_wrap_bare(part).replace("\x02", ""))
    return _TEXT_MASK.sub(lambda m: masked[int(m.group(1))], "".join(out))


# ------------------------------------------------------------------ CLI


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit("usage: normalize.py <file.md> | --dir FOLDER | -")
    if args[0] == "--dir":
        folder = Path(args[1]) if len(args) > 1 else Path(".")
        mds = sorted(p for p in folder.glob("*.md") if not p.name.endswith(".norm.md"))
        for p in mds:
            dst = p.with_suffix(".norm.md")
            dst.write_text(normalize_math(p.read_text(encoding="utf-8")), encoding="utf-8")
            print(f"{p.name} -> {dst.name}")
        if not mds:
            print(f"No .md files in {folder}")
    elif args[0] == "-":
        sys.stdout.write(normalize_math(sys.stdin.read()))
    else:
        sys.stdout.write(normalize_math(Path(args[0]).read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
