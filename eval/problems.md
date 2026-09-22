# Problem inventory & status

Categorized record of every transcription problem found by the eval system
(inbox_eval judge + lint + probes), with fix status. Golden cases in
cases.json enforce every ✅; ⚠️ items carry a "known" flag and auto-flip to
FIXED when resolved. Updated 2026-09-22: 80/81 cases green, 1 known.

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

## D. Symbol verbalization (SRE-ko conventions) — 7/7 FIXED
- ✅ □ blank -> 네모 (box-blank-*, boxed-blank); □ABCD -> 사각형 (quadrilateral-not-blank)
- ✅ remainder 3⋯1 -> 몫/나머지 (division-remainder-dots)
- ✅ geometry/degree battery (angle, ⊥, ∥, ≡, 합동, ratio, 절댓값 …)
- ✅ 절댓값 OCR-typo family via _OCR_TYPOS map (ocr-typo-jeoldaetgab)
- ✅ ∽ -> 닮음이다 (similarity); △ -> 삼각형, 선분 overline, 사인/코사인, 제곱센티미터
- ✅ 순환소수 dot/overline -> reading C (#17, decided)
- ✅ f(3) -> "함수 f 의 3" (function-application) — f/g/h only
- Fix path used: fixMisreads() post-SRE rewrites + pre-SRE interception where
  the words must MOVE (선분, 순환소수, ⊥, 절댓값, x_{n+1}).

## E. Linearization ambiguity — POLICY DECIDED 2026-09-22, 4/5 resolved
Policy: nesting is spoken with SRE's own 시작/끝 forms, enabled PER SPAN and only
for the structure actually nested, so simple readings stay terse. Where no
toggle exists, say it as a teacher does. See FINDINGS.md 2026-09-22.
- ✅ 번분수 collision -> 분수시작/분수끝 (Fraction_GeneralEndFrac, per span)
- ✅ x_{n+1} vs x_n+1 -> "n 더하기 1 번째 x" (no Subscript_* toggle exists)
- ✅ nested radical grouping -> 루트끝 (Roots_RootEnd); works in the PLAIN path,
  so it replaces the SSML voice-change trick as the primary grouping cue
- ✅ exponent towers -> 지수시작/지수끝 (Exponent_AfterPower)
- ✅ root-of-fraction: was never ambiguous — √(9/16) and √9/16 already differ
- ⚠️ problem-defined notation <m,n>=k — unfixable in principle (custom-angle-notation)
- STILL to validate BY EAR: the text checks prove each pair is distinguishable,
  not that either reading is comfortable. 분수시작/분수끝 on a deep nest is long.

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
