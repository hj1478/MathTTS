#!/usr/bin/env python3
"""Normalize OCR math markdown to canonical inline LaTeX.

PaddleOCR-VL emits math inconsistently: sometimes $...$ LaTeX, sometimes plain
text ("2x(3x+1)") or unicode ("x²", "≤"). This unifies all of it into consistent
inline $...$ LaTeX so a downstream verbalizer gets one format.

This is a HEURISTIC, not a LaTeX parser — there is no reliable way to tell a lone
variable from a stray letter, so it errs toward NOT wrapping when unsure.

DOES:
  - convert unicode math -> LaTeX: x²->x^2, ≤->\\leq, ×->\\times, √n->\\sqrt{n},
    sub/superscripts, greek (π->\\pi ...), both inside existing $...$ and in bare text
  - wrap a bare math RUN in $...$ only when it has a clear signal: a super/subscript,
    a unicode math symbol, letter-digit adjacency (3x), an operator between operands
    (x-y, 2+3), or parentheses containing alphanumerics
  - canonicalize ^{2}->^2 (single char), keep ^{10} braced; same for _{...}
  - normalize \\(..\\) -> $..$ and \\[..\\] -> $$..$$; wrap bare \\begin{..}..\\end{..}
    environments in $$..$$ (and protect their insides from the bare-run wrapper)
  - treat a $..$ containing Hangul as NOT math: a stray unpaired '$' in prose
    would otherwise pair with a later math '$' and swallow the prose between

DOESN'T (documented misses, chosen to avoid false positives):
  - wrap a lone variable with no signal: "x의" stays "x의" (would risk "A형"->"$A$형")
  - wrap bare numbers: "3.14", "7." (leading list numbers) stay as text
  - parse/validate LaTeX or resolve ambiguous digit ranges ("3-4" -> $3-4$ if it looks
    like subtraction; that's accepted as a known edge)

CLI:
  python normalize.py "output/kr question 3.md"   # print normalized text
  python normalize.py --dir output                # normalize every *.md -> *.norm.md
  cat file.md | python normalize.py -             # stdin -> stdout
"""
import re
import sys
from pathlib import Path

SUP = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6",
       "⁷": "7", "⁸": "8", "⁹": "9", "ⁿ": "n", "⁺": "+", "⁻": "-"}
SUB = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6",
       "₇": "7", "₈": "8", "₉": "9", "₊": "+", "₋": "-"}
SYM = {"×": r"\times ", "÷": r"\div ", "·": r"\cdot ", "⋅": r"\cdot ", "±": r"\pm ",
       "≤": r"\leq ", "≥": r"\geq ", "≠": r"\neq ", "≈": r"\approx ", "∞": r"\infty ",
       "−": "-", "∈": r"\in ", "∉": r"\notin ", "∑": r"\sum ", "∏": r"\prod ",
       "∫": r"\int ", "√": r"\sqrt ", "π": r"\pi ", "θ": r"\theta ", "α": r"\alpha ",
       "β": r"\beta ", "γ": r"\gamma ", "λ": r"\lambda ", "μ": r"\mu ", "σ": r"\sigma ",
       "φ": r"\phi ", "ω": r"\omega ", "ρ": r"\rho ", "Δ": r"\Delta ", "∆": r"\Delta "}

_SUP_CLS = "".join(map(re.escape, SUP))
_SUB_CLS = "".join(map(re.escape, SUB))
_UNI_CLS = "".join(map(re.escape, list(SYM) + list(SUP) + list(SUB)))
# characters that may form a bare math run (excludes whitespace; handled separately)
_RUN_CLS = r"0-9A-Za-z+\-*/=^_<>()\[\]{}.," + _UNI_CLS
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


def _latexify(s):
    """Convert unicode math + canonicalize LaTeX in an expression (no wrapping)."""
    s = re.sub(rf"[{_SUP_CLS}]+", lambda m: "^{" + "".join(SUP[c] for c in m.group()) + "}", s)
    s = re.sub(rf"[{_SUB_CLS}]+", lambda m: "_{" + "".join(SUB[c] for c in m.group()) + "}", s)
    for k, v in SYM.items():
        s = s.replace(k, v)
    s = re.sub(r"\\sqrt\s*\(([^)]*)\)", r"\\sqrt{\1}", s)
    # digits group greedily: √10 means sqrt(10), so \sqrt 10 -> \sqrt{10};
    # letters stay single (√ab is ambiguous, don't guess)
    s = re.sub(r"\\sqrt\s*([0-9]+|[A-Za-z])", r"\\sqrt{\1}", s)
    s = re.sub(r"\^\{([0-9A-Za-z])\}", r"^\1", s)   # x^{2} -> x^2 (single char only)
    s = re.sub(r"_\{([0-9A-Za-z])\}", r"_\1", s)
    return re.sub(r"\s+", " ", s).strip()


def _is_math(core):
    """True if a run (already stripped of edge punctuation) has a clear math signal."""
    return bool(
        re.search(rf"[{_UNI_CLS}]", core)                             # any unicode math: x², ≤, π, √, ×
        or re.search(r"[A-Za-z][0-9]|[0-9][A-Za-z]", core)           # 3x, x2
        or re.search(r"[0-9A-Za-z]\s*[-+*/=^<>]\s*[0-9A-Za-z]", core)  # x-y, 2+3, a=b
        or ("(" in core and re.search(r"[0-9A-Za-z]", core))         # (x+1)
    )


def _wrap_bare(text):
    def repl(m):
        run = m.group()
        core = run.strip(" .,")                       # keep .,/space adjacent to Korean outside
        if not core or not _is_math(core):
            return run
        i = run.find(core)
        return f"{run[:i]}${_latexify(core)}${run[i + len(core):]}"
    return RUN.sub(repl, text)


def _emit_inline(inner):
    """Wrap an inline math span, repairing a mis-placed closing delimiter that
    swallowed a trailing '(' + prose. An unmatched '(' inside a math span is always
    wrong (e.g. the q1 OCR '$p\\leq k<q(p, q$'), so eject from that paren onward to
    prose. Anything else is left intact — never drop content."""
    depth, cut = 0, None
    for i, ch in enumerate(inner):
        if ch == "(":
            if depth == 0:
                cut = i               # start of a group not yet closed
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
            if depth == 0:
                cut = None            # that group closed -> balanced so far
    if depth > 0 and cut is not None:  # leftover unmatched '(' -> split there
        math, after = inner[:cut], inner[cut:]
    else:
        math, after = inner, ""
    core = f"${_latexify(math)}$" if math.strip() else math
    return f"{core}{after}"


def normalize_math(text):
    """Normalize all math in OCR markdown to canonical inline $...$ LaTeX."""
    out = []
    for part in SPAN.split(text):
        if not part:
            continue
        if part.startswith("$$") and part.endswith("$$"):
            out.append(f"$${_latexify(part[2:-2])}$$")
        elif part.startswith(r"\begin"):
            out.append(f"$${_latexify(part)}$$")          # bare env -> $$..$$
        elif part.startswith("$") and part.endswith("$") and len(part) > 1:
            out.append(_emit_inline(part[1:-1]))
        elif part.startswith(r"\(") and part.endswith(r"\)"):
            out.append(_emit_inline(part[2:-2]))          # \(..\) -> $..$
        elif part.startswith(r"\[") and part.endswith(r"\]"):
            out.append(f"$${_latexify(part[2:-2])}$$")    # \[..\] -> $$..$$
        else:
            out.append(_wrap_bare(part))
    return "".join(out)


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
