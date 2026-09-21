# Findings

A dated log of what was tried, what happened, and what it changed. This is the
research record for the project; `README.md` carries the summary and the
conclusions, this file carries the trail that led to them.

> [!IMPORTANT]
> **This file is a scaffold being filled in.** See issue #12.
>
> Every blockquote marked **Guidance** is scaffolding, not content — delete each
> one as you use it, and delete this notice once the log is under way.
>
> **Order.** Oldest first; append new entries at the bottom. Read top to bottom
> and the file tells the story of the project, which is what a reader who is not
> you will want. You do not need a summary at the top — that is what the README's
> *Results* section is for.
>
> **Entries can be three lines.** The one thing that kills a log like this is
> feeling like homework. A short entry written the same day beats a thorough one
> that never gets written. If an experiment took two minutes, its entry can too.
>
> **Write it as you go, not at the end.** The details that matter — the exact
> error, the version, what you expected — are gone within a week.

## Entry template

> [!TIP]
> **Guidance.** Copy the block below for each new entry. Keep the headings; drop
> any line that has nothing to say. `Result` is the one to be careful with: state
> plainly whether you checked something or are assuming it, in the same way the
> code comments already do ("confirmed from real output, not assumed").

```markdown
## YYYY-MM-DD — one-line title

**Question.** What were you trying to find out?

**What I did.** Enough that you could repeat it — tool, version, input, command.

**What happened.** The actual observation. Paste real output when it is short.

**Result.** What you now believe, and whether it is verified or assumed.

**Changed as a result.** Code, design, or plan — or "nothing".

**Still open.** What this did not answer. (Delete if nothing.)
```

## Entries

> [!TIP]
> **Guidance.** Write entries below this line, oldest first.
>
> Nothing here yet — but the project has already produced findings that live only
> in code comments, where a reader will not find them. Those are your first
> entries, and most of the content already exists; it needs a date and a sentence
> of conclusion. Work through them in whatever order you remember them.
>
> - [x] **Does SRE support Korean math speech at all, and in which domains and
>   styles?** This is what `sre-probe/index.js` was built to answer. Include the
>   part that was surprising: clearspeak "styles" turned out to be combinatorial
>   preference toggles rather than distinct named styles.
> - [x] **What does PaddleOCR-VL's raw output actually look like?** The whole
>   downstream chain depends on the `$...$` convention. Record what you saw that
>   confirmed it — `ocr_vl.py` says it was confirmed from real output, but the
>   evidence itself is now lost (issue #3).
> - [x] **`engine="transformers"` crashes the paddle-only layout model.** A trap
>   worth writing down before someone tries swapping the VL backend again — which
>   will be you (issue #3).
> - [x] **Why a heuristic instead of a LaTeX parser?** `normalize.py` states the
>   decision; the log is where the reasoning and the alternatives you rejected go.
> - [x] **SRE's SSML envelope is rejected by Azure.** SRE emits
>   `<speak version="1.1" xml:lang="ko">` with no `<voice>`; Azure wants
>   `version="1.0"`, `xml:lang="ko-KR"` and a `<voice>` tag, so `speak.js` strips
>   and re-wraps it. Worth an entry because it is a non-obvious incompatibility
>   between two tools that both claim to speak SSML.
> - [x] **Is the Korean math speech actually intelligible by ear?** `tts_probe.py`
>   was built to answer this — four test cases, `1a` vs `1b` being the fraction
>   grouping test. The answer is not recorded anywhere. This is the single most
>   valuable missing entry: it is the question the whole project rests on.
> - [x] **Azure's transient "Codec decoding is not started within 2s".** Handled
>   with one retry in `tts_full.py:47`. Short entry — what you saw, how often, what
>   fixed it.
> - [x] **`interpret-as="character"` vs `"characters"`.** Still unresolved
>   (issue #9). Log it as an open question now, and add the answer when you check
>   it — a dated "unresolved" entry is a legitimate entry.
>
> Two of these — the OCR output convention and the `engine="transformers"` crash —
> are the findings issue #3 is about recovering. Writing them here is the same work.

---

> Entries below marked *(backfilled 2026-09-21)* were recovered from code
> comments and issue history rather than written at the time. Where the original
> evidence was lost, the entry says so instead of reconstructing it.

## 2026-07 — PaddleOCR-VL emits inline math as `$...$` *(backfilled 2026-09-21)*

**Question.** What does the OCR's raw output actually look like? Every stage
downstream assumes a `$...$` convention.

**What I did.** Ran `ocr_vl.py` over the repo fixtures on macOS arm64 CPU —
paddleocr 3.7.0 / paddlex 3.7.2 / paddlepaddle 3.3.1 — and read the markdown it
wrote to `output/`.

**What happened.** Inline math arrives wrapped in single dollars, verbatim:

```
4.  $ -2^5 \div \{(-2)^4 \times (-2)\} $를 계산하시오.
... 범위는 $p\leq k<q(p, q$는 상수)이다. 이때 $p^{2}+9q^{2}$의 값을 ...
```

The second line also shows the model closing a span too late, swallowing
"(p, q" and the Korean after it.

**Result.** Verified from real output, not assumed. The model cannot be made to
emit any other delimiter, so `normalize.py` canonicalizes whatever arrives.

**Changed as a result.** The `$...$` grammar became the single contract between
stages — `normalize.SPAN`, imported by `ocr_vl.py` and mirrored in `speak.js`,
with `eval/fixtures/span_cases.json` checked by both test suites (#4).

**Still open.** The original run's console output is gone; only the fixture
markdown in `output/` survives as evidence. That loss is what issue #3 was
about, and it is the reason this log exists.

## 2026-07 — `engine="transformers"` crashes the pipeline *(backfilled 2026-09-21)*

**Question.** Can the VL recognizer be swapped to a transformers backend?

**What I did.** Passed `engine="transformers"` to `PaddleOCRVL(...)`.

**What happened.** The pipeline crashed. `engine=` is a GLOBAL switch applied to
every sub-model, including the PP-DocLayoutV3 layout model, which is paddle-only.

**Result.** Verified. The knob that actually selects the VL recognizer backend
is the separate `vl_rec_backend=` ("native" = in-process, no server; the
`*-server` values need a running server and `vl_rec_server_url`).

**Changed as a result.** `ocr_vl.py` leaves `engine` unset and passes
`vl_rec_backend="native"`, with the trap written into its module docstring.

**Still open.** Nothing — but this is the entry to reread before trying it again.

## 2026-08 — SRE speaks Korean math; its "styles" are preference toggles *(backfilled 2026-09-21)*

**Question.** Does speech-rule-engine support Korean math speech at all, and in
which domains and styles?

**What I did.** `sre-probe/index.js`, against SRE 5.0.0-rc.4. Capabilities come
from `sre -c ko --opt`, which lists only LOADED locales — hence the `-c ko`.
Re-measured 2026-09-21 while writing this entry.

**What happened.** Korean is supported in both `clearspeak` and `mathspeak`.
The surprise was the shape of "style": `mathspeak` has three real named styles
(brief, default, sbrief), while `clearspeak` exposes ~30 COMBINATORIAL
preference toggles instead — `Fraction_Over`, `Paren_Speak`,
`AbsoluteValue_AbsEnd`, `ImpliedTimes_None` and so on. They are not alternative
voices; they are individual switches.

**Result.** Verified. Also, two API facts worth keeping: `setupEngine()` returns
a Promise and must be awaited, while `toSpeech()` is then synchronous.

**Changed as a result.** `clearspeak/default` became the register used for the
stitched view, `mathspeak/default` the unambiguous cross-check.

**Still open.** The toggles were never systematically tried, and that turned out
to matter — see the 2026-09-21 entry on `Paren_Speak`.

## 2026-08 — SRE's SSML envelope is rejected by Azure *(backfilled 2026-09-21)*

**Question.** Can SRE's SSML output be handed straight to Azure Neural TTS?

**What happened.** No. Two tools that both claim to speak SSML disagree on the
envelope. SRE emits `<speak version="1.1" xml:lang="ko">` with no `<voice>`;
Azure requires `version="1.0"`, `xml:lang="ko-KR"` and a `<voice>` element.
Azure rejects SRE's document outright.

**Result.** Verified. `speak.js` strips each span to its inner markup and
re-wraps the whole document in the Azure envelope.

**Changed as a result.** `ssmlInner()` plus `AZURE_SSML()` in `speak.js`. Since
that envelope is assembled by string-joining regex-extracted markup and nothing
parses it until Azure does, `checkWellFormed()` was added to catch a stray `<`,
an unclosed tag or bad nesting locally rather than as a stage-4 synthesis error
(#11).

## 2026-08 — `interpret-as="character"` is not a documented Azure value *(backfilled 2026-09-21)*

**Question.** SRE writes `interpret-as="character"`. Does Azure accept it?

**What I did.** Checked Azure's SSML pronunciation page on learn.microsoft.com
(page dated 2026-02, checked 2026-08) against SRE's output.

**What happened.** Azure's `say-as` table lists `characters` and `spell-out`.
The singular `character` is not a documented value, so Azure would silently
ignore the tag — and the disambiguation the whole SSML path exists for would be
lost, with no error to notice.

**Result.** Verified against documentation, NOT by ear. `ssmlInner()` rewrites
the attribute during the re-wrap (issue #9).

**Still open.** Whether the `say-as` tags audibly change anything at all is
unmeasured. Shipping a fix for a silent failure on documentation alone is
exactly the kind of thing this log should flag.

## 2026-08 — Azure's transient "Codec decoding is not started within 2s" *(backfilled 2026-09-21)*

**What happened.** Synthesis calls intermittently failed with
`Codec decoding is not started within 2s`. Not reproducible on demand and not
tied to any particular input.

**Result.** Treated as transient, on the evidence that a retry succeeds. One
retry has been enough every time observed; no frequency was recorded, which is
the one thing this entry should have and does not.

**Changed as a result.** One retry in `tts_full.py`, and the same pattern in
`question_audio.py` and `dot_reading_probe.py`. A failure is printed rather than
raised so one bad call cannot kill a batch.

## 2026-08 — Why a heuristic, not a LaTeX parser *(backfilled 2026-09-21)*

**Question.** `normalize.py` has to find math in OCR text that arrives in three
inconsistent shapes (`$...$`, unicode `x²≤`, plain `2x(3x+1)`). Parse it, or
pattern-match it?

**Result.** A heuristic, deliberately. A parser needs to know where math STARTS,
and that is the part the OCR does not tell you: there is no reliable way to
distinguish a lone variable from a stray letter, so "x의 값" must stay prose
while "3x" becomes math. The rule adopted is to err toward NOT wrapping — a
missed span is read as prose, while a false one is spelled out letter by letter,
which is far worse to listen to.

**Changed as a result.** `normalize.py` wraps a bare run only on a clear signal
(super/subscript, unicode math symbol, letter-digit adjacency, an operator
between operands, a leading negative, parenthesised alphanumerics, an
absolute-value pair, a ratio, a repeating-decimal dot). Its docstring lists the
DOESN'T cases as deliberate misses, and `tests/test_normalize.py` keeps the
should-not cases alongside the should ones.

**Still open.** The heuristic keeps being wrong in ways only real pages reveal —
seven separate wrapping bugs were found in one 2026-09-21 session by running the
whole corpus, none by the unit tests.

## 2026-08 — Is the Korean math speech intelligible by ear? UNRESOLVED

**Question.** The question the whole project rests on. `tts_probe.py` was built
to answer it: four cases, `1a` vs `1b` being the fraction-grouping test — does a
300 ms pause make "2 분의 x 더하기 1" group as (x+1)/2 rather than x/2 + 1?

**What happened.** The wavs can be generated. **No verdict has been recorded**,
here or anywhere else.

**Result.** Unknown, and logged as unknown deliberately. Everything the project
claims about quality is currently about the LaTeX → Korean stage; whether the
result is *understandable* is unmeasured. The same gap covers the `<say-as>`
markup (above) and the 순환소수 reading (below), which was chosen on paper.

**Still open.** All of it. Cost: `python tts_probe.py`, then listen to eight
files. This is the cheapest high-value experiment left in the repository.

## 2026-09-21 — 순환소수 need a reading of their own; SRE cannot supply one

**Question.** What should a listener hear for `0.2̇4̇`, and which candidate
Korean reading stays unambiguous by ear?

**What I did.** Measured what SRE-ko emits for every encoding of a repeating
decimal (SRE 5.0.0-rc.4, `clearspeak/default`, via `sre-probe/speak.js`), then
wrote three candidate readings as functions in `dot_reading_probe.py` and
generated its five-case table with `python dot_reading_probe.py --dry-run`.

**What happened.** SRE names the decoration instead of reading the number, and
does so identically whatever the encoding:

```
$0.2̇4̇$             ->  0 마침표 2 위의 점 4 위의 점
$0.\dot{2}\dot{4}$  ->  (identical to the row above)
$0.\overline{24}$   ->  0 마침표 24 윗줄
```

**Result.** Verified, by running the chain and not by reading the code: no SRE
domain or style produces a reading, so the reading has to be produced *before*
SRE sees the span. Reading C — "영 점 이사 이사 반복", the repetend twice then
반복 — was adopted as the project default on 2026-09-21. Recorded plainly: that
was a choice among the three candidates as written, **not** the outcome of the
listening test `dot_reading_probe.py` exists for. Its Prediction and Result
lines in `docs/findings/17_repeating_decimals.md` are still blank.

**Changed as a result.** `speak.js` intercepts `\dot{}`/`\overline{}` decimals
before temml/SRE and emits reading C directly, in both the plain and SSML
paths. Two regression cases in `eval/cases.json` — `repeating-decimal-dots` and
`repeating-decimal-overline` — assert "이삼 이삼 반복" and forbid "위의 점" and
"윗줄". They would have failed before the change: "위의 점" and "윗줄" are
exactly what the measurement above produced.

**Still open.** Whether reading C survives the case3-vs-case5 pair by ear. On a
partial repetend it separates 0.12̇3̇ ("일 이삼 이삼") from 0.1̇23̇ ("일이삼 일이삼")
by phrasing alone, and a TTS voice may flatten phrasing — that pair is the whole
point of the probe. Reading B marks the boundary with a word ("영 점 일 **다음**
이삼이 반복") and is the ready fallback; swapping `readRepeating()` is the change.
Separately, the dots are still *lost* before any of this can help: OCR drops
them and nothing in `run.py` calls `dot_check.py` (#15).

## 2026-09-21 — SRE has preference toggles for two things I fixed by interception

**Question.** Written while backfilling the entry above, which noted that
clearspeak's ~30 preference toggles were never systematically tried. Were any
of them relevant to the readings just fixed by hand?

**What I did.** Ran each candidate toggle against the `ko` locale directly:

```
Paren_Auto             (3,4)      ->  3 콤마 4
Paren_Speak            (3,4)      ->  괄호 열고 3 콤마 4 괄호 닫고
Paren_CoordPoint       (3,4)      ->  3 콤마 4
Paren_Interval         [3,4]      ->  3 콤마 4
AbsoluteValue_Auto     |x-2|+3    ->  절댓값 x 빼기 2 더하기 3
AbsoluteValue_AbsEnd   |x-2|+3    ->  절댓값시작 x 빼기 2 절댓값끝 더하기 3
```

**What happened.** `Paren_Speak` produces exactly the output `splitFences` was
written to produce, from a supported engine setting instead of a regex.
`AbsoluteValue_AbsEnd` solves the same scope problem `splitAbs` solves, by
bracketing the operand rather than moving the marker after it.

`Paren_CoordPoint` and `Paren_Interval` are LISTED for `ko` but do nothing —
the preference exists in the option table without a Korean rule behind it. So
"listed" and "implemented" are not the same thing, which is the part that would
have been worth knowing before trusting the table.

**Result.** Verified by running them. Two working alternatives to code already
merged. Neither is a straight swap:
  - `Paren_Speak` is GLOBAL — it would also affect parens SRE currently elides
    sensibly, which is unmeasured;
  - `AbsoluteValue_AbsEnd` applies to every absolute value including `|-4|`,
    where the plain prefix reading is already complete, and "절댓값시작 /
    절댓값끝" are compounds where the postfix form is ordinary Korean.

**Changed as a result.** Nothing yet — recorded, not acted on. Swapping
`splitFences`' tuple half for `Paren_Speak` is the strongest candidate and
would delete code.

**Still open.** The honest lesson: I reached for interception without checking
whether the engine had a supported knob, and the entry two above had already
flagged that the toggles were never tried. The other ~28 remain untried, and
`ImpliedTimes_None`, `Fraction_Over` and `Ellipses_AndSoOn` all look relevant
to open items (the 번분수 collision, `\cdots`).
