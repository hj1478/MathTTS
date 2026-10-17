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

> **Correction (2026-10-16).** The first line is not verbatim model output.
> The model wrote it without the braces; see the 2026-10-16 entry "OCR drops the
> braces in `kr question 2.png`". The `$...$` convention itself stands: the
> unedited output uses it too.

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

`Paren_CoordPoint` and `Paren_Interval` appeared to do nothing. That reading
was WRONG, and the correction is the more useful half of this entry: they do
work, in both `ko` and `en`, and they produce good Korean —

```
Paren_CoordPoint   (3, 4)   ->  좌표 3 콤마 4
Paren_Interval     (3, 4)   ->  열린 구간 3 에서 4 까지
```

— but only when the comma survives into the MathML. temml lexes `(3,4)` with
no space as a SINGLE token, `<mn>3,4</mn>`, reading the comma as a thousands
separator; `(3, 4)` with a space becomes `<mn>3</mn><mo separator>,</mo>
<mn>4</mn>`. No paren preference can fire on the first form because there is no
list there to recognize.

The consequence is bigger than the preferences. With the comma tokenized,
`Paren_Auto` — the DEFAULT — already speaks the fence:
`(-3, 4)` -> "괄호 열고 마이너스 3 콤마 4 괄호 닫고". The corpus writes 48 of
its 50 coordinate pairs with the space. So the real defect was never the
missing fence: it was `_INNER_MARKER` swallowing the pair before it reached
SRE at all, and once that was fixed the default reading was already correct.

**Result.** Verified by running them, in both locales. `AbsoluteValue_AbsEnd`
is a real alternative to `splitAbs`, though not a straight swap: it applies to
every absolute value including `|-4|`, where the prefix reading is already
complete, and "절댓값시작 / 절댓값끝" are compounds where the postfix form is
ordinary Korean.

`splitFences`' tuple half is a different story: it is mostly redundant. It
duplicates what `Paren_Auto` already does for the 48 spaced pairs, and the 2
unspaced ones would be better served by normalizing the spacing at the source
— which would also make `Paren_CoordPoint` and `Paren_Interval` available,
since they need the same tokenization.

**Changed as a result.** Nothing yet — recorded, not acted on. Swapping
`splitFences`' tuple half for `Paren_Speak` is the strongest candidate and
would delete code.

**Still open.** Two lessons, and the second only surfaced because the first
was written down wrong. I reached for interception without checking whether the
engine had a supported knob — and then, on finding two toggles that seemed
inert, concluded "listed but not implemented" from a single unspaced test case
instead of asking why. Testing `en` alongside `ko` would have shown the same
behaviour in both and pointed at temml rather than at SRE.

The other ~28 toggles remain untried. `ImpliedTimes_None`, `Fraction_Over` and
`Ellipses_AndSoOn` all look relevant to open items (the 번분수 collision,
`\cdots`), and the tokenization caveat above applies to all of them: a toggle
that looks inert may just be missing the structure it matches on.

## 2026-10-16 — PaddleOCR-VL hangs on a T4 container's first OCR call; neither more CPUs nor turning off queue mode fixes it

**Question.** The first deployed job on Modal (T4) never finished: it sat in
the OCR stage until the 600 s function timeout. Why, and what fixes it?

**What I did.** Diagnostic Modal functions on the worker image (in
`backend/modal_app.py`) that print the device, dtype and weight locations, time
OCR calls on `kr question 1.png`, and dump every thread's stack
(`faulthandler`) if a call is still running after 60 s. paddle 3.3.1 (CUDA
12.6 build), paddleocr 3.7.0, paddlex 3.7.2, Tesla T4.

Ruled out first: the model is on the GPU (`DocVLMLocalPredictor:
device=gpu`), the weights are baked into the image (no runtime download), and
the dtype is float32. paddlex only picks bfloat16 when
`paddle.amp.is_bfloat16_supported()`, which is False on a T4.

Then two hypotheses, each tested and each wrong:

1. **My prediction: the CPU allocation.** The default container has `nproc` = 1
   (so `OMP_NUM_THREADS` = 1); `cpu=4` would fix it. 10 calls in one container
   per configuration.
2. **The concurrency explanation.** paddlex's queue mode (`use_queues=True`, its
   default) runs layout (CV) and VLM in separate threads, which would touch the
   GPU for the first time concurrently. Test: `use_queues=False` (paddlex runs
   the stages one after the other in the calling thread), 20 fresh containers,
   one OCR call each.

**What happened.** Both were wrong.

```
cpu=default                     10 ok, 0 hangs   9.8 s first call, then 4.5–4.7 s
cpu=4                            0 ok, 1 hang    hung on call 1 (GPU 0 %, after 60 s)
use_queues=False, 20 fresh      13 hangs         run stopped early: success count never printed
```

With `use_queues=False` the hang is single-threaded. Each of the 13 stack dumps
has exactly three threads: the OCR call, Modal's event loop and the main
thread, with no paddlex worker threads. Every one is stuck at the same place,
with the GPU idle:

```
ocr-call (the only thread doing OCR; use_queues=False)
  ocr_vl.py:102  run_image -> pipeline(device).predict(...)
  paddleocr/_pipelines/paddleocr_vl.py:186  predict
  paddlex/inference/pipelines/_parallel.py:161  predict
  .../paddleocr_vl/pipeline.py:1189  predict -> _process_vlm        (non-queue path)
  .../paddleocr_vl/pipeline.py:959   _process_vlm
  .../paddleocr_vl/pipeline.py:743   get_layout_parsing_results
  .../paddleocr_vl/pipeline.py:517   _paddleocr_vl_run_vl_recognition_batches
  .../models/doc_vlm/predictor.py:248  process -> self.infer.generate(
  .../doc_vlm/modeling/paddleocr_vl/_paddleocr_vl.py:817  generate
  .../common/transformers/generation/utils.py:1116  generate -> greedy_search
  .../common/transformers/generation/utils.py:1284  greedy_search -> self(**model_inputs)
  .../doc_vlm/modeling/paddleocr_vl/_paddleocr_vl.py:668  forward -> self.model.embed_tokens(input_ids)
  paddle/nn/functional/input.py:335  embedding -> _C_ops.embedding(...)   <- never returns
```

With queue mode on (the cpu=4 hang), the stack below `_process_vlm` is
identical; it just runs in paddlex's `_worker_vlm` thread while the caller
polls `queue_vlm.get(timeout=0.5)` at `pipeline.py:1170`.

Totals on T4, all the same image: **3 of 5 first calls in a fresh container
hung** before the queue test, and **at least 13 of the (at most) 20** in it;
**0 of 9 later calls** in a container whose first call succeeded.

**Result.** A first-call hang in the native `_C_ops.embedding` op on the first
decoding step, GPU idle, on a T4 with this Paddle build. Verified: it is not
the CPU allocation, not paddlex's threading, not a CPU fallback, not a runtime
weight download, and not the dtype. The underlying cause inside Paddle is NOT
known; I am not debugging Paddle internals.

Hosting lessons, all verified on Modal:
- Modal's function timeout raises `InputCancellation` in the main thread only.
  A hung paddlex thread keeps running, and keeps the GPU, after the job is
  cancelled.
- A container that crashes has its input rescheduled by Modal: until a
  failure rate is exceeded for an ephemeral app, and indefinitely for a
  deployed one, regardless of `retries=0`.
- Retiring the container (`stop_fetching_inputs`) does not reliably free the
  GPU either. Several hung containers in the 20-container test ran until
  Modal's 900 s runner heartbeat timeout, and two were still listed after
  `modal app stop` and `modal container stop`.

**Changed as a result.** The OCR call moves into a child process that the
worker kills outright at the cutoff, so a hang cannot hold a GPU past it.
Next test: the same 10-fresh-container check on an L4. If the L4 also hangs,
the plan is to switch OCR to the PaddleOCR-VL hosted API.

**Still open.** Whether the hang is specific to the T4 (L4 test pending), and
why `_C_ops.embedding` never returns. *Answered in the next entry: not
T4-specific, and the cause is Paddle's `auto_growth` allocator.*

> **Note (2026-10-17).** The diagnostic commands in this and the next two
> entries were run as `modal run backend/modal_app.py::<name>`. They have since
> moved to their own app: `modal run backend/diagnostics.py::<name>`
> ("mathtts-diag"), so the production app holds only Worker, web and cleanup.
> `cpu_check` now runs in a CPU-only container with the CPU paddlepaddle build
> of the same version, not on a T4 with the GPU unused as described below.

## 2026-10-16 — The first-call hang is Paddle's `auto_growth` allocator; `FLAGS_allocator_strategy=naive_best_fit` fixes it (10/10)

**Question.** Is the first-call hang in the previous entry specific to the T4,
and is there a fix short of switching to the hosted API?

**What I did.** First, the same check on an L4: 10 fresh containers, one OCR call
each, `kr question 1.png`, 60 s cutoff, default allocator. Then I searched the
PaddleOCR issue tracker before debugging further, and found two matching reports:

- [PaddleOCR #17693](https://github.com/PaddlePaddle/PaddleOCR/issues/17693):
  PaddleOCR-VL hangs on the first inference in an endless `ioctl` loop inside
  Paddle's default `auto_growth` GPU allocator. The workaround is
  `FLAGS_allocator_strategy=naive_best_fit`. A py-spy native stack in that
  thread matches ours (`embed_tokens` → `_C_ops.embedding`). The same comment
  reports v1.6 hanging 6/8 on Paddle 3.2.1 while `pipeline_version="v1"` was
  stable, so pinning an older Paddle is unlikely to help.
- [PaddleOCR #17640](https://github.com/PaddlePaddle/PaddleOCR/issues/17640):
  the same symptom. Its reporter got 10/10 with `naive_best_fit`.

Then the flag test: the 10-fresh-container check on a T4 with
`FLAGS_allocator_strategy=naive_best_fit` set in the OCR child process's
environment before paddle is imported (`OcrProcess(env=...)`). Each child
reported the strategy paddle actually uses, from `paddle.get_flags`. Run with
`modal run backend/modal_app.py::fresh_test --gpu T4 --allocator naive_best_fit`.

**What happened.**

```
L4,  default allocator (auto_growth)    1 ok, 9 hangs     the 1 ok: first call 8.6 s
T4,  naive_best_fit                    10 ok, 0 hangs     first call 6.0–7.2 s (median 6.8)
                                                          model load 9.1–17.1 s
```

Every T4 child reported `allocator_strategy: naive_best_fit`, paddle 3.3.1, and
was gone at the end (hard kill not needed). GPU memory with the flag, after the
first call: nvidia-smi 7,941–8,026 MiB used; paddle peak 8,121 MiB allocated,
8,431–8,509 MiB reserved. Earlier default-allocator runs on the T4 showed about
10,095 MiB used, so the flag uses less memory, not more.

The same day, the default allocator hung again on a T4. In the golden-output
check below, its first process was killed at 60 s, and a fresh process then
succeeded.

**Result.** Verified on T4: with `naive_best_fit`, 10 of 10 fresh first calls
succeed, against 3/5 and at least 13/20 hangs with the default allocator in
the previous entry. The hang is not specific to the T4 (the L4 hung 9/10). The
mechanism (the `ioctl` loop inside `auto_growth`) is taken from #17693, and only
partly observed here.

The native-stack check (`modal run backend/modal_app.py::stack_check`): a fresh
default-allocator process, with the threads inspected once the first call is
still running at 25 s. The call hung in both of the two runs (GPU 0 %, the same
Python stack ending in `_C_ops.embedding`, killed at 60 s). But no native stack
can be had on Modal: ptrace is not permitted in the container (gdb:
`ptrace: Operation not permitted`; py-spy: `Permission denied (os error 13)`),
and gVisor's `/proc` has no `wchan` or `syscall` files. What `/proc/<pid>/task/*/stat`
does show: of the hung child's 25 threads, exactly one is running (state `R`)
in all three samples 2 s apart, and the rest are sleeping. So the hung call is
a busy loop on the CPU with the GPU idle, which is consistent with #17693's
endless `ioctl` loop. That it is `ioctl` is not shown.

The allocator does not change OCR output. The six golden images (kr question
1–5, page) gave byte-identical markdown with `naive_best_fit` and with the
default allocator on the same T4
(`modal run backend/modal_app.py::output_check`).

Predictions that were wrong, for the record:
- "The CPU allocation": `cpu=4` hung on its first call (previous entry).
- "Concurrency between paddlex's threads": it still hung with `use_queues=False`
  (previous entry).
- "It is a T4 problem, so an L4 will fix it": the L4 hung 9/10.
- "The 3.3.1 build is at fault, so pin Paddle 3.2.1": not run. #17693 reports
  the hang on 3.2.1.

**Changed as a result.** The production worker sets
`FLAGS_allocator_strategy=naive_best_fit` in the OCR child's environment. The
child-process hard kill stays as a backstop. No switch to the hosted API.

**Still open.** Whether the busy loop is the `ioctl` loop of #17693. Checking
would need a host where ptrace is allowed. `pipeline_version="v1"` was not tried.

## 2026-10-16 — OCR drops the braces in `kr question 2.png`; the saved `output/` markdown was hand-edited

**Question.** In the golden-output check, `kr question 2.png` differed from the
saved `output/kr question 2.md`. Which one is right, and where does the
difference come from?

**What I did.** Looked at the image, then ran the same pipeline and settings
(`ocr_vl.pipeline`, paddle 3.3.1, paddleocr 3.7.0, paddlex 3.7.2) with
`device="cpu"`: `modal run backend/modal_app.py::cpu_check`. It runs on a T4
container with the GPU unused, because paddlepaddle-gpu cannot even import in
a CPU-only container (`ImportError: libcuda.so.1: file too short`). I also
compared the file dates in `output/`.

**What happened.** The image reads −2⁵ ÷ {(−2)⁴ × (−2)}, with braces. Every
run of the model drops them:

```
image (by eye)        -2^5 ÷ {(-2)^4 × (-2)}
GPU, T4, both allocators  4.  $ -2^5 \div (-2)^4 \times (-2) $를 계산하시오.
CPU (x86, Modal)          4.  $ -2^5 \div (-2)^4 \times (-2) $를 계산하시오.     26.6 s
output/kr question 2_res.json   (Jul 1, the original run)   the same, no braces
output/kr question 2.md         (Jul 18)  4.  $ -2^5 \div \{(-2)^4 \times (-2)\} $를 계산하시오.
```

The `.md` is the only file with the braces. It is dated Jul 18, while the
`_res.json` written by the same `run_image` call is dated Jul 1, and its
`block_content` has no braces. No commit records the edit (`output/` is not in
git).

**Result.** A known OCR error, verified on GPU and CPU: PaddleOCR-VL drops the
braces in this image. That changes the meaning: −2⁵ ÷ {16 × (−2)} = 1, but the
OCR text reads (−2⁵ ÷ 16) × (−2) = 4, and the problem is read aloud wrong. GPU
and CPU agree here, so this is not a GPU-vs-CPU difference.

`output/kr question 2.md` was edited by hand on Jul 18. That is inferred from
the file dates and the `_res.json`, not recorded anywhere. It should not be
used as a golden reference for OCR output until that is confirmed. The other
five golden images match their saved markdown exactly. The `$...$` entry above
quoted the edited line as verbatim output; it now carries a correction.

**Changed as a result.** Nothing in the pipeline. The correction note on the
2026-07 entry.

**Still open.** Who edited the file and why (perhaps to check the downstream
stages on the correct formula). How often the OCR drops grouping braces across
the 58-page corpus.

## 2026-10-17 — `POST /warmup` 20 s ahead cuts a cold job from 50 s to 35 s; early text shows OCR at 24–40 s

**Question.** How much of the user's wait do the two new latency features
remove: `POST /warmup` (start a worker while the user picks a photo) and
`GET /jobs/{id}` returning each stage's text as soon as it is ready?

**What I did.** Deployed `mathtts`, confirmed with `modal container list` that
no worker container was up before each run, and ran one cold job per case on
`kr question 1.png` with `scripts/smoke_test.py` (T4, polling every 1.5 s;
times are from the upload, as the client sees them):

    A  python scripts/smoke_test.py <url>                     # no warmup
    B  python scripts/smoke_test.py <url> --warmup-lead 20    # /warmup, 20 s, upload

**What happened.**

| | queued (cold start) until | OCR text visible | spoken text visible | done (wav ready) |
|---|---|---|---|---|
| A, no warmup | 29.4 s | 39.8 s | 42.4 s | **49.9 s** |
| B, `/warmup` 20 s before | 11.8 s | 23.5 s | 28.0 s | **34.9 s** |

Server stage timings were the same in both (OCR 9.8 / 9.4 s, speech 1.4 /
2.3 s, TTS 3.3 / 3.5 s), so the whole 15 s difference is the cold start. Both
jobs produced the same 7-span result and the same 1,557,646 B wav.

**Result.** Measured, one run each, so expect a few seconds of variance. A cold
start costs about 30 s (container start plus model load in the OCR child). A
20 s lead removes 20 of it, leaving ~9 s, so a lead of about 30 s or more
should hide it fully. Early text means the user can read the OCR text about
10 s, and the spoken text about 7 s, before the audio is ready. Poll timing
adds up to 1.5 s to every "visible" figure.

**Changed as a result.** docs/API.md tells the frontend to call `/warmup` when
the app opens and to show `stages` text as it arrives.

**Still open.** Scheduled keep-warm (`min_containers` via
`Function.autoscaler.update()` from a `modal.Cron`), GPU memory snapshots (alpha
in Modal's docs; whether a model held by a child process can be captured is not
documented) and fallback GPU types (`gpu=["T4", "L4"]`) were checked against
the Modal docs but not tried.

