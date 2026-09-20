# Problem inventory & status

Categorized record of every transcription problem found by the eval system
(inbox_eval judge + lint + probes), with fix status. Golden cases in
cases.json enforce every ✅; ⚠️ items carry a "known" flag and auto-flip to
FIXED when resolved. Updated 2026-09-20: 60/66 cases green, 6 known.

## A. OCR markup leaking into speech — 6/6 FIXED
- ✅ HTML div/img scaffolding spelled out (html-figure)
- ✅ tables deleted with their problem data (html-table, html-table-content)
- ✅ $-wrapped multiline arrays -> stray $ / empty spans (dollar-wrapped-array)
- ✅ array column spec {r} read as math
- ✅ temml ParseError read aloud -> salvage() Korean fallback (garbled-ocr-latex, salvage-symbol-list)
- ✅ orphan unclosed \text{ brace -> 중괄호 (trig-bare-latex-circ)

## B. Math notation outside $..$ — 6/6 FIXED
- ✅ bare \times / ^{2} ("t i m e s", "집합") (bare-latex-prose, -exponent-times)
- ✅ bare \frac in choice lists ("{5}{4}") (bare-frac-choice-list)
- ✅ bare trig words + \tan 60^{\circ} (trig-bare-words, trig-bare-latex-circ)
- ✅ ^\circ -> 합성 함수 (degree-circ-in-span; retired known degree-circ-latex)
- ✅ Hangul operands \sqrt{분산}, \text{와} fractions (sqrt-hangul-arg, hangul-text-in-math)
- ✅ 대분수 all 3 OCR forms (mixed-number-in-span / -digit-outside-span / -bare)

## C. Prose wrongly wrapped as math — 6/6 FIXED
- ✅ problem numbers "5." (problem-number-ejected)
- ✅ list markers (1) [3] 1) adjacent/interior (5 cases incl. answer-key-inline-markers)
- ✅ label colons (label-colon-stays-prose)
- ✅ 가운뎃점 · headers -> "닷" (middot-header-not-math)
- ✅ schedule dates + orphan close-parens (paren-only-marker-schedule)
- ✅ unmatched-paren prose capture (unmatched-paren-ejected)

## D. Symbol verbalization (SRE-ko conventions) — 5 fixed, 4 OPEN
- ✅ □ blank -> 네모 (box-blank-*, boxed-blank); □ABCD -> 사각형 (quadrilateral-not-blank)
- ✅ remainder 3⋯1 -> 몫/나머지 (division-remainder-dots)
- ✅ geometry/degree battery (angle, ⊥, ∥, ≡, 합동, ratio, 절댓값 …)
- ✅ 절댓값 OCR-typo family via _OCR_TYPOS map (ocr-typo-jeoldaetgab)
- ⚠️ ∽ -> "물결표" not 닮음 (similarity)
- ⚠️ 순환소수 dot/overline phrasing (repeating-decimal-dots, -overline)
- ⚠️ f(3) -> "f 의 3" ambiguity (function-application)
- Fix path for all ⚠️: fixMisreads() post-SRE rewrite layer in speak.js.

## D2. Glyphs named instead of read (#20 coverage run) — 4 fixed, 2 OPEN
Measured through the real chain; re-measure with `python3 eval/notation_coverage.py`.
- ✅ △ -> "흰색 상향 삼각형" -> 삼각형 (same mechanism as □ -> 네모)
- ✅ cm² -> "센티미터 제곱" -> 제곱센티미터 (Korean puts the power first)
- ✅ sin/cos spelled 싸인/코싸인 -> 사인/코사인. Was hardcoded in FOUR places
  (SRE output, normalize.py's two bare-trig maps, speak.js's salvage map), so
  the spelling depended on which path a span took.
- ✅ ⊥ -> "l 수직이다 m" -> "l 은 m 과 수직이다", by rendering \perp as
  \parallel and swapping the verb, so SRE's own 은/는·과/와 agreement applies
- ⚠️ ≅ (\cong) -> "거의 같다" not 합동. NOT fixable in fixMisreads: "거의 같다"
  is the correct reading of ≈, so rewriting the Korean would corrupt a span
  that was already right. Has to be fixed while the notation still exists —
  \cong -> \equiv in normalize.py, since \equiv already reads 합동이다.
- ⚠️ ∽ (\sim) -> "물결표" not 닮음 (same argument; \sim is also "은 ~와 같이
  분포한다" elsewhere). See also D's `similarity`.
- ⚠️ line segment `\overline{AB}` -> "A B 윗줄", never 선분. The digit case is
  already intercepted (REPDEC); the letter case is not.
- ⚠️ 3:4 (비) -> "삼 콜론 사" not 삼 대 사 — but `cases.json`'s `ratio` case
  ASSERTS 콜론 for `x:y`. Both are probably right in context, so this needs a
  context rule and a split golden case, not a rename.

## E. Inherent linearization ambiguity — OPEN by nature (policy, not bugs)
- ⚠️ 번분수 collision: (1/2)/3 and 1/(2/3) speak identically (nested-fraction-collision)
- ⚠️ x_{n+1} vs x_n+1 indistinguishable (subscript-expression-ambiguity)
- ⚠️ nested radical grouping √(3+2√2) (nested-radical-grouping)
- ⚠️ problem-defined notation <m,n>=k — unfixable in principle (custom-angle-notation)
- (unfiled, fragile): exponent towers 2^(3²) vs (2³)²; root-of-fraction √(9/16)
- Needs a phrasing-policy decision (explicit 괄호 / verbose forms vs listenability);
  validate with listening tests, not text checks.

## F. Upstream OCR quality — partially addressable
- ✅ recurring typo map pattern (절댓값 family) — extend _OCR_TYPOS as new ones appear
- ⚠️ repeating-decimal dots silently lost by OCR (0.3̇6̇ -> 0.36, wrong number,
  undetectable downstream)
- ⚠️ figures / dialogue bubbles / number lines absent or garbled — needs a
  vision-description layer (next frontier)
- ⚠️ one-off typos: 잦을(값을), ∂ as choice markers

## G. Eval system
- ✅ judge FP suppression: Korean conventions + mandatory self-check + verbatim-quote filter
- ✅ outage resilience: 3x retry w/ backoff, 4-way parallel judging
- residual: judge still occasionally flips denominator-first fractions — treat
  lone fraction-order findings as suspect
