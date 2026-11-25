# Problem inventory & status

Categorized record of every transcription problem found by the eval system
(inbox_eval judge + lint + probes), with fix status. Golden cases in
cases.json enforce every ✅; ⚠️ items carry a "known" flag and auto-flip to
FIXED when resolved. Updated 2026-07-28: 47/55 cases green, 8 known.

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

## H. Heard in the audio (2026-11-25, 30 survey problems) — see docs/FINDINGS.md
Found by listening and by measuring the audio (hear-back, word level, formula
pairs), not by the text checks above. Rules are in pipeline/speech/speak.js.
- ✅ exponent ran into the next term -> power word 25% slower, no pause after it
- ✅ 제곱 heard "제고" (a pause after it) -> same rule; 14 -> 28 of 31 recognized
- ✅ "분의 이" heard as "…a" -> a 2 after 의/는/은 said slower
- ✅ last word before "괄호 닫고" 6–9 dB down -> no pause before a closing bracket
- ✅ several-term denominator / numerator paced; (2x-1)/3 vs 2x/3-1 no longer the same audio
- ✅ (2/3)² read as 2²/3 (SRE drops the brackets) -> brackets said (text too)
- ✅ one-digit 순환마디 "사 사" too fast -> the pair 40% slower
- ✅ one-letter denominator, and a letter ending a phrase before a comma, unclear
- ✅ xy²: slight pause before the letter that carries the power
- ✅ capitals 30% higher in pitch -> dropped; second voice for roots off (VOICE_CHANGE)
- ✅ △ABC∽△DEF phrased "A 닮음이다 B" -> "A 와 B 는 닮음" (also ≡ ⊥ ∥ between figures)
- ✅ △FGH read "F 의 G H"; \square EFGH in math read 네모 -> vertices, 사각형
- ✅ pause between an angle and 도 (sin²60°) removed
- ⚠️ root end unmarked while the second voice is off: √(2+1) vs √2+1, √(4a²) vs √4·a²
- ⚠️ `A < 90°` -> "A 는 90 보다 작다 도" (unit after the comparison)
- ⚠️ "y 는 이" heard "느니"; "사 괄호 닫고" heard "사과로 닫고"
- ⚠️ every pause left in still costs the word before it 6–9 dB
- ⚠️ nested fractions (section E) unchanged
