# MathTTS

Reads Korean math problems aloud: image → OCR (Korean + LaTeX) → spoken Korean math via SRE → TTS.

## The problem

A Korean 초·중 math worksheet is mostly notation, and the notation only works
if you can see it: the dots above the digits of a 순환소수, the overline on
선분 AB, △, ⊥, stacked fractions, exponents. A student who cannot read the
page gets nothing usable out of it. A screen reader reads the Korean prose
around the maths and then spells the formula out symbol by symbol or skips it;
hand the same file to a TTS voice and it reads "backslash frac" aloud.

So the reading is done by a person — a teacher, a parent, a volunteer. That
works, and it does not scale. It has to happen again for every worksheet, and
it means the student cannot practise alone.

This project asks whether the chain can be closed without that person in the
room: a page of Korean problems in, Korean math speech out, in the words a
Korean teacher would use. Stages 1 and 4 are off-the-shelf. The stage that
decides whether any of it works is the middle one — LaTeX to *Korean* speech —
and exactly one tool attempts it.

## Research questions

**Q1. Can speech-rule-engine produce Korean math speech at all, and in which
configurations?** SRE is the only engine found that claims a Korean locale, so
if its `ko` support is a stub the project has no middle stage and stops here.
Success: usable Korean for ordinary school expressions. Failure: a locale that
falls back to English or to symbol names. (`sre-probe/index.js`)

**Q2. Across the 초·중 curriculum, what does the chain read correctly, and
where does it fail?** The test applied to each reading is whether *a listener
could reconstruct the original expression from the words alone* — not whether
the translation is defensible symbol by symbol. Failures scattered at random
would mean there is nothing systematic to fix; the more useful outcome is
failures that cluster, because a cluster has a mechanism.
(`eval/notation_coverage.py`, issue #20)

**Q3. 순환소수 — the one notation known to be lost before the pipeline even
starts. Can it be recovered, and once recovered, is it read?** The expected
answer at the outset was that restoring the dots would be enough, since the
rest of the chain was already handling the notation it was given. Success:
`0.2̇4̇` is spoken as a number that repeats. (`dot_check.py`, issue #17)

**Q4. Is the resulting Korean math speech intelligible by ear?** Everything
above is a judgement made by reading strings. This is the question the project
actually rests on, and the only one whose answer cannot be obtained by running
anything. Success: a listener writes down the expression that was intended.
Failure: they write down a different one — not an awkward reading, a wrong
answer. (`tts_probe.py`, `dot_reading_probe.py`)

## Approach

| Stage | Entry point | In → out | What it does |
|---|---|---|---|
| 0 (optional) | `pdf_to_images.py` | `*.pdf` → `pages/*.png` | Renders PDF pages to PNGs the OCR can read (200 DPI default) |
| 1. OCR | `ocr_vl.py` | `*.png` → `output/*.md` | PaddleOCR-VL, locally on CPU: Korean prose + inline `$...$` LaTeX |
| 1.5 (optional) | `dot_check.py` | `*.md` → `*.dots.md` | Restores the 순환소수 dots the OCR drops, from page context via an LLM. A transform, not a measurement — but **`run.py` has no flag for it yet** (#15) |
| 2. Normalize | `normalize.py` | `*.md` → `*.norm.md` | Canonicalizes the OCR's inconsistent math (unicode, bare runs, stray `$`) into `$...$` LaTeX |
| 3. Math → speech | `sre-probe/speak.js` | `*.norm.md` → `stitched/*.stitched.txt` / `.ssml` | temml → MathML → SRE (locale ko); stitches Korean speech back into the prose |
| 4. TTS | `tts_full.py` | `stitched/*` → `audio/*.wav` | Azure Neural TTS; plain and SSML versions per problem for A/B listening |

The split exists because no single tool crosses the whole gap: the OCR emits
math notation, not words, so its output cannot go straight to a TTS voice
(which would spell out or skip the LaTeX). Stage 2 exists because the OCR
emits math in three inconsistent shapes (`$...$`, unicode `x²≤`, plain
`2x(3x+1)`) — without it, stage 3 would only find the spans that happened to
arrive already delimited. Stage 3 is the actual subject of the project:
turning LaTeX into *Korean* math speech, which only SRE attempts.

Two files are investigation tools, not stages: `sre-probe/index.js` (does SRE
support Korean math speech at all, and in which domains/styles?) and
`tts_probe.py` (is the resulting Korean speech intelligible by ear? A/B wavs).
Their docstrings record what each one established.

## Results

**Q1 — Yes, and "style" does not mean what it appears to.** SRE 5.0.0-rc.4
ships Korean for both ClearSpeak and MathSpeak. The surprise was in the
options table: ClearSpeak's 93 Korean "styles" are combinatorial preference
toggles (`Fraction_Over`, `Roots_RootEnd`, `AbsoluteValue_AbsEnd`, …), not 93
distinct named styles, so a sweep over them is not the experiment it looks
like. MathSpeak has three real styles (`brief`, `default`, `sbrief`). The
probe also prints a locale key SRE itself spells `clearspaek`. Everything
below uses `clearspeak/default`.

**Q2 — 40 of 51 notations read correctly, and the failures cluster.** Measured
through `normalize.py` + `speak.js`, SRE 5.0.0-rc.4, `clearspeak/default`,
2026-09-20; reproduce with `python3 eval/notation_coverage.py`.

| 51 notations, 초등 → 중3 | Reads correctly | Awkward or incomplete | Not conveyed |
|---|---|---|---|
| | 40 | 7 | 4 |

Arithmetic, equations, powers, fractions, roots and the quadratic formula all
survive: `y=ax²+bx+c` reads `y 는 a x 제곱 더하기 b x 더하기 c`, and
parenthesised expressions keep their grouping audibly (`괄호 열고 … 괄호
닫고`), so order of operations is preserved. What fails is almost entirely
geometry notation and ratios — and the failures share one mechanism:

| Written | Spoken | What is missing |
|---|---|---|
| `\overline{AB}` (선분) | `A B 윗줄` | the word 선분 never appears |
| `∽` (닮음) | `물결표` | the relation is named as a glyph |
| `≅` (합동) | `거의 같다` | that is the reading of ≈, not of 합동 |
| `3:4` (비) | `3 콜론 4` | not 삼 대 사 |

SRE-ko describes the mark rather than interpreting it. That is the same
mechanism as Q3's, which is why four further rows were fixable by one change
(`fixMisreads()` in `speak.js`, issue #20): △ was `흰색 상향 삼각형`, cm² was
`센티미터 제곱`, sin/cos were spelled `싸인`/`코싸인`, and ⊥ was `l 수직이다 m`.
Two of the four rows above are deliberately *not* fixed there — see
*Limitations*.

The seven awkward readings are ambiguity rather than error: `|-4|`, `(3,4)`
versus `[3,4]`, `p ≤ k < q`, `√(x+1)` versus `√x+1`, and inline `2/3`, which
reads as division (`2 나누기 3`) rather than as a fraction.

**Q3 — the expected fix does not work, and that is the most useful result
here.** 순환소수 fail twice, independently. First, PaddleOCR-VL drops the dots
printed above the repeating digits, so `0.2̇4̇` arrives as a plain `0.24` — a
different number, with nothing downstream able to detect it. `dot_check.py`
restores them from page context.

Second, and this is what was not expected: restoring the dots does not make
them audible. SRE-ko names the decoration whichever notation carries it.

| Span | clearspeak/default | mathspeak/default |
|---|---|---|
| `$0.2̇4̇$` (combining U+0307) | `0 마침표 2 위의 점 4 위의 점` | `0 마침표 2 위에 있는 점 4 위에 있는 점` |
| `$0.\dot{2}\dot{4}$` | identical | identical |
| `$0.\overline{24}$` | `0 마침표 24 윗줄` | `0 마침표 24 윗줄` |

So the missing piece is a **reading rule, not an encoding** — Korean words that
exist nowhere in the chain. `speak.js` now intercepts these decimals before SRE
and speaks reading C from the #17 experiment (`0.1̇2̇3̇` → `영 점 일 이삼 이삼
반복`). That is one candidate adopted as an interim default because any
faithful reading beats `위의 점`; which reading is unambiguous by ear is Q4.

**Q4 — not answered.** No one has listened. Every judgement above was made by
reading strings, which is exactly the method that cannot settle whether
`2 분의 x 더하기 1` is heard as (x+1)/2 or as x/2 + 1, or whether reading C can
be told apart from a reading of a different repetend. The harnesses exist
(`tts_probe.py`'s four cases, `dot_reading_probe.py`'s A/B wavs, with
predictions to be written down first at
`docs/findings/17_repeating_decimals.md`), and both need an Azure key and a
listener. Until that is done, the honest summary of this project is that it
produces Korean math speech which has not been shown to be intelligible.

## Worked example

One page, every stage. `eval/fixtures/sample_page.md` is committed OCR output
from a 중2 순환소수 worksheet, so the example shows the project's signature
failure rather than a case where everything works.

**Stage 1 — OCR (`ocr_vl.py`).** What PaddleOCR-VL produced:

```markdown
**5.** 순환소수 $0.24$ 를 분수로 나타내는 과정이다. $x=0.242424\cdots$ 라 하면
$100x=24.242424\cdots$ 이므로 $99x=24$, 즉 $x=\frac{24}{99}=\frac{8}{33}$ 이다.
```

The dots above `24` are already gone. The printed page says `0.2̇4̇`.

**Stage 2 — normalize (`normalize.py`).** Unchanged for this line: the OCR
already delimited every span. Stage 2 exists for the pages where it does not.

**Stage 3 — Korean speech (`sre-probe/speak.js`).** What a voice would read:

```
**5.** 순환소수 0.24 를 분수로 나타내는 과정이다. x 는 0.242424 점 점 점 라 하면
100 x 는 24.242424 점 점 점 이므로 99 x 는 24 , 즉 x 같다 99 분의 24 같다 33 분의 8 이다.
```

`SUMMARY: 11 span(s), ok: 11` — the run reports complete success. The sentence
says the word 순환소수 and then reads a number that terminates: the student
hears a confident contradiction. Two smaller things are visible in the same
line: `\cdots` reads `점 점 점`, and the chained equality switches from `는` to
`같다` partway through.

**With the dots restored** (`dot_check.py`, not part of a plain run — see
#15), stage 2 emits `$0.\dot{2}\dot{4}$` and stage 3 reads:

```
**5.** 순환소수 영 점 이사 이사 반복 를 분수로 나타내는 과정이다.
```

Faithful, and provisional: whether a listener can tell that apart from a
different repetend is Q4.

**Stage 4 — TTS (`tts_full.py`).** Azure synthesises both the plain and the
SSML version into `audio/`, for the A/B listening that has not yet been done.

## Running it

Two dependency trees — Python **and** Node:

```sh
python3.11 -m venv venv && venv/bin/pip install -r requirements.txt
cd sre-probe && npm install && cd ..
```

**First run is expensive:** `ocr_vl.py` downloads model weights (hundreds of
MB) to `~/.paddlex/official_models/`, and CPU inference takes tens of seconds
per image. Both are printed at runtime; it is not hung.

**Credentials and cost** — three groups, not two. Copy `.env.example` to
`.env` next to the scripts, or export the same variables.

| Group | Covers | Credential | Cost |
|---|---|---|---|
| Local | stages 0–3: `pdf_to_images.py`, `ocr_vl.py`, `normalize.py`, `speak.js` | none | free — CPU time and one model download |
| Azure | stage 4 `tts_full.py`, plus `tts_probe.py` / `dot_reading_probe.py` | `AZURE_SPEECH_KEY` + `AZURE_SPEECH_ENDPOINT` (or `AZURE_SPEECH_REGION`) | per character synthesized |
| OpenAI | `dot_check.py` (a transform), and the harnesses that drive it or an LLM judge: `inbox_eval.py`, `dot_eval.py` | `OPENAI_API_KEY` | one temperature-0 call per page that passes `needs_check()` |

`run.py --skip-tts` touches nothing paid. A full `run.py` uses the Azure row
only: it never reaches the OpenAI row, because it cannot invoke stage 1.5 (#15).

`run.py` chains everything:

```sh
python run.py "kr question 1.png"          # image → wav
python run.py kma_sheet_13_8_prob.pdf      # PDF → pages → wav
python run.py --dir pages --skip-tts       # stop before Azure synthesis
```

Per-stage skip flags (`--skip-ocr`, `--skip-normalize`, `--skip-speak`,
`--skip-tts`) reuse the previous stage's artifacts, and every stage is still
runnable alone:

```sh
python ocr_vl.py "kr question 1.png" --out ./output
python normalize.py --dir output
node sre-probe/speak.js --ssml --write ./stitched --dir ./output
python tts_full.py --stitched ./stitched --out ./audio
```

Checks:

```sh
venv/bin/python -m pytest tests/       # normalize.py contract, span grammar, run.py globs
cd sre-probe && node --test            # JS span grammar (same fixtures) + SSML checker
python ocr_vl.py --eval .              # OCR each image, score against *.expect sidecars
```

- `<image>.expect` sidecars hold ground truth (`math` / `none`); images
  without one score as `unverified`.
- `speak.js` prints a per-file `SUMMARY:` line and, with `--strict`, exits
  non-zero when a formula stitched as salvage or a placeholder (`run.py` uses
  this to stop before paying Azure to read a placeholder aloud).
- `eval/notation_coverage.py` re-measures what the pipeline reads correctly
  across the 초·중 curriculum (issue #20) through the real chain, and
  `--diff OLD.json` shows what a change moved. Reference material, not
  pass/fail.
- Larger harnesses: `tts_eval.py` (golden cases + lint), `inbox_eval.py`
  (drop PDFs in `inbox/`, OCR → stitch → LLM judge), `dot_eval.py` (순환소수
  dot restoration).

Everything above except `inbox_eval.py` and `dot_eval.py` runs without
credentials, and `.github/workflows/checks.yml` runs exactly that set on every
push.

## Limitations and what is unverified

Deliberately not handled (see `normalize.py`'s docstring for the reasoning):
a lone variable with no math signal stays unwrapped (`x의` stays `x의` — the
alternative risks `A형` → `$A$형`); bare numbers and list numbering stay
text; ambiguous digit ranges are accepted as a known edge.

Not yet checked: whether SRE's `<say-as>` tags audibly improve the speech.
The attribute is now rewritten to Azure's documented `"characters"` (see
`speak.js`), but the A/B ear check with `tts_probe.py` has not been done.
Whether SRE's Korean fraction/relation grouping is intelligible by ear is
likewise an open listening question — `tts_probe.py`'s four cases exist for
it.

SRE-ko names several glyphs by their Unicode description instead of reading
them as mathematics. `speak.js`'s `fixMisreads()` now corrects the four where
the right Korean is unambiguous (△, cm², 사인/코사인, ⊥). Two are left alone
on purpose: ≅ reads "거의 같다", which is *also* the correct reading of ≈, and
∽ reads "물결표" — rewriting either in the speech would corrupt spans that were
already right, so they have to be fixed while the notation still exists. 선분
`AB` and the 비 `3:4` are likewise still open (`eval/problems.md`, section D2).

Known failure, half-addressed: 순환소수 (repeating decimals) had two
independent problems; one remains, one has a provisional fix.

*The notation is lost (still open).* **A plain `python run.py` mis-reads every
순환소수 on the page.** PaddleOCR-VL drops the small dots printed above the
repeating digits, so `0.2̇4̇` arrives as a plain `0.24`, and the pipeline exits 0
having spoken it as a number that terminates — a confident wrong answer, with
nothing in the output flagging it. `dot_check.py` restores the dots from page
context, and with them the reading below applies; but `run.py` has no way to
invoke it. Today it runs inside `inbox_eval.py`, or by hand with
`python dot_check.py --write FILE.md` (open question #15).

Why it is not simply switched on by default: **its precision has never been
measured.** `dot_eval.py` exists for exactly that — precision and recall per
number, with false dots as the failures to watch, since a miss only reproduces
the status quo while a false dot corrupts a number that was already right — but
its numbers are recorded nowhere in this repository. That measurement is what
the default should be decided on, and it has not been made.

*The reading (provisional).* SRE itself cannot read the notation — it names
the decoration instead of interpreting it, whatever the encoding; measured
against SRE 5.0.0-rc.4 (clearspeak/default, 2026-08):

| Span | Spoken by SRE |
|---|---|
| `$0.2̇4̇$` (combining U+0307, what OCR and `dot_check.py` produce) | `0 마침표 2 위의 점 4 위의 점` |
| `$0.\dot{2}\dot{4}$` (what `normalize.py` emits for the row above) | identical to the row above |
| `$0.\overline{24}$` | `0 마침표 24 윗줄` |
| `$0.1\dot{6}$` | `0.1 6 위의 점` |

So `speak.js` now intercepts `\dot{}`/`\overline{}` decimals before SRE and
speaks them directly as **reading C** from the #17 experiment — pattern twice,
then 반복: `0.2̇4̇` → "영 점 이사 이사 반복". This is ONE candidate adopted as
an interim default because any faithful reading beats "위의 점" — *which*
reading is unambiguous by ear is still open (#17): the competing candidates
and A/B wavs are generated by `dot_reading_probe.py`, with predictions to
fill in at `docs/findings/17_repeating_decimals.md` before listening.

Known failure: `page.png`'s pseudo-LaTeX integral does not parse; it stitches
via the best-effort salvage path (visible in the `SUMMARY:` line).

## Verified versions

| Component | Version | Date checked |
|---|---|---|
| paddleocr / paddlex / paddlepaddle | 3.7.0 / 3.7.2 / 3.3.1 | 2026-07 |
| speech-rule-engine | 5.0.0-rc.4 | 2026-07 |
| temml | ^0.13.3 | 2026-07 |
| azure-cognitiveservices-speech | 1.50.0 | 2026-07 |
| Azure SSML say-as docs (`characters`) | page dated 2026-02 | 2026-08 |
| pypdfium2 | 5.11.0 | 2026-08 |
| SRE-ko notation coverage (`eval/notation_coverage.py`) | 40/51 correct | 2026-09 |

Environment used: macOS arm64 (Apple Silicon), Python 3.11 venv, CPU-only
(no CUDA).

## Tools used

- [PaddleOCR-VL](https://github.com/PaddlePaddle/PaddleOCR) — local Korean + math OCR (stage 1)
- [temml](https://temml.org/) — LaTeX → MathML (stage 3)
- [speech-rule-engine](https://github.com/Speech-Rule-Engine/speech-rule-engine) — MathML → Korean math speech (stage 3)
- [Azure Speech](https://learn.microsoft.com/azure/ai-services/speech-service/) — Korean neural TTS (stage 4)
- [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) — PDF page rendering (stage 0)
