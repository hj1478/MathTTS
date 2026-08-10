# MathTTS

Reads Korean math problems aloud: image → OCR (Korean + LaTeX) → spoken Korean math via SRE → TTS.

> [!IMPORTANT]
> **This README is a scaffold being filled in.** See issues #12 and #10.
>
> Every blockquote below marked **Guidance** is scaffolding, not content. Work
> top to bottom, write the section, then delete its guidance block — a leftover
> guidance block means that section is not done yet. Delete this notice and the
> self-check at the bottom last.
>
> The mechanical sections (Approach table, Running it, Limitations, Verified
> versions, Tools used) are filled in; the research narrative — the problem,
> the questions, the results, the worked example — can only come from the
> person who did the work.
>
> **Language.** This file is in English, matching the code comments and
> docstrings. Writing the research narrative in Korean instead is fine — switch
> deliberately and say so in one line. Being consistent is what matters, not
> which language you pick (issue #12, guideline 9).

## The problem

> [!TIP]
> **Guidance.** Three to five sentences. Answer:
> - Who has trouble, and in what situation?
> - What do they do today, and why is that not good enough?
> - What changes for them if this works?
>
> This is the one thing missing from the repository entirely. Without it, a
> reader cannot tell why any of the rest is needed.
>
> Common mistake: opening with the technology ("this connects OCR to TTS…").
> Open with the person and the situation instead.

TODO

## Research questions

> [!TIP]
> **Guidance.** Two to four questions, one or two sentences each. This section is
> what makes the document a piece of research rather than a description of a tool.
>
> Answer:
> - What exactly were you trying to find out when you started?
> - What result would count as success, and what would count as failure?
> - What did you not know at the outset — what might have turned out not to work
>   at all?
>
> Where to find them: two tools here were built to answer specific questions
> already. What question is `sre-probe/index.js` asking? What is each of the four
> test cases in `tts_probe.py` checking? Those are your candidates — this is a
> matter of writing down what you already know.
>
> Do not put the answers here. The answers go under **Results**.

TODO

## Approach

| Stage | Entry point | In → out | What it does |
|---|---|---|---|
| 0 (optional) | `pdf_to_images.py` | `*.pdf` → `pages/*.png` | Renders PDF pages to PNGs the OCR can read (200 DPI default) |
| 1. OCR | `ocr_vl.py` | `*.png` → `output/*.md` | PaddleOCR-VL, locally on CPU: Korean prose + inline `$...$` LaTeX |
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

> [!TIP]
> **Guidance.** The section most often left empty, and the most important one.
>
> Answer:
> - For each research question above, what was the answer?
> - How far did it get, and where did it stall?
> - What is that judgement based on — what did you see or hear?
> - What turned out differently from what you expected?
>
> One rule: distinguish what you actually verified from what you are assuming.
> The code comments already do this ("confirmed from real output, not assumed" /
> "verify by ear"). If something has not been checked, write that it has not
> been checked — a document that says so is more trustworthy, not less.
>
> Give the things that did not work the same weight as the things that did. In
> research a negative result is a result, not an appendix.

TODO

## Worked example

> [!TIP]
> **Guidance.** Take one problem and show every stage of it: source image, OCR
> output, normalized LaTeX, the Korean speech string, the audio file. Paste the
> real output of each stage in a code block and keep the commentary minimal.
>
> Why bother: it is faster to understand than any description, and it doubles as
> a reference point later — "this is what it used to produce".
>
> Which problem: `kr question 1.png` is the candidate. Its OCR output contains a
> real broken-parenthesis case, so the example itself shows what the normalize
> stage is for. That is more useful than an example where everything already works.

TODO

## Running it

Two dependency trees — Python **and** Node:

```sh
python3.11 -m venv venv && venv/bin/pip install -r requirements.txt
cd sre-probe && npm install && cd ..
```

**First run is expensive:** `ocr_vl.py` downloads model weights (hundreds of
MB) to `~/.paddlex/official_models/`, and CPU inference takes tens of seconds
per image. Both are printed at runtime; it is not hung.

**Credentials** — stages 0–3 are fully local; stage 4 (Azure TTS) and the LLM
eval scripts are the only network/paid parts. Copy `.env.example` to `.env`
next to the scripts, or export the same variables: `AZURE_SPEECH_KEY` plus
`AZURE_SPEECH_ENDPOINT` (or `AZURE_SPEECH_REGION`) for TTS; `OPENAI_API_KEY`
for `inbox_eval.py` / `dot_check.py`.

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
venv/bin/python -m pytest tests/       # normalize.py contract + span grammar
cd sre-probe && node --test            # JS span grammar (same fixtures) + SSML checker
python ocr_vl.py --eval .              # OCR each image, score against *.expect sidecars
```

- `<image>.expect` sidecars hold ground truth (`math` / `none`); images
  without one score as `unverified`.
- `speak.js` prints a per-file `SUMMARY:` line and, with `--strict`, exits
  non-zero when a formula stitched as salvage or a placeholder (`run.py` uses
  this to stop before paying Azure to read a placeholder aloud).
- Larger harnesses: `tts_eval.py` (golden cases + lint), `inbox_eval.py`
  (drop PDFs in `inbox/`, OCR → stitch → LLM judge), `dot_eval.py` (순환소수
  dot restoration).

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

Known failure: 순환소수 (repeating decimals) come out wrong on every path today,
for two independent reasons.

*The notation is lost.* PaddleOCR-VL drops the small dots printed above the
repeating digits, so `0.2̇4̇` arrives as a plain `0.24` and is spoken as if it
terminated. `dot_check.py` restores them from surrounding context, but nothing
in `run.py` calls it — today it runs inside `inbox_eval.py`, or by hand with
`python dot_check.py --write FILE.md`.

*The reading does not exist.* Even with the dots restored, nothing turns them
into the Korean 순환소수 reading. SRE names the decoration instead of
interpreting it, and this is not a matter of picking a different notation —
measured against SRE 5.0.0-rc.4 (clearspeak/default, 2026-08):

| Span | Spoken |
|---|---|
| `$0.2̇4̇$` (combining U+0307, what OCR and `dot_check.py` produce) | `0 마침표 2 위의 점 4 위의 점` |
| `$0.\dot{2}\dot{4}$` | identical to the row above |
| `$0.\overline{24}$` | `0 마침표 24 윗줄` |
| `$0.1\dot{6}$` | `0.1 6 위의 점` |

A listener needs something like `영 점 이사 순환`. Since every notation that
*means* "repeating" reads as a description of the mark, the missing piece is a
reading rule, not an encoding: re-emitting the dots as LaTeX from
`normalize.py` (which has no U+0307 rule today) would change nothing.

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

Environment used: macOS arm64 (Apple Silicon), Python 3.11 venv, CPU-only
(no CUDA).

## Tools used

- [PaddleOCR-VL](https://github.com/PaddlePaddle/PaddleOCR) — local Korean + math OCR (stage 1)
- [temml](https://temml.org/) — LaTeX → MathML (stage 3)
- [speech-rule-engine](https://github.com/Speech-Rule-Engine/speech-rule-engine) — MathML → Korean math speech (stage 3)
- [Azure Speech](https://learn.microsoft.com/azure/ai-services/speech-service/) — Korean neural TTS (stage 4)
- [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) — PDF page rendering (stage 0)

---

> [!IMPORTANT]
> **Self-check — go through this once everything is filled in, then delete this block.**
>
> It is done when someone who never opens the source can answer all of these from
> this README alone.
>
> - [ ] Whose problem does this solve, and what is it? (one sentence)
> - [ ] What was being investigated?
> - [ ] Did it work, and what is the evidence?
> - [ ] What was tried that did not work?
> - [x] Can I run one problem through to audio on my own machine, and do I know in
>       advance what the first run costs in time and disk?
> - [x] Which parts are known-broken, and which are simply unverified?
> - [x] Which claims were actually verified, against which versions, on what date?
>
> And one that applies to you specifically as the author:
>
> - [x] Six months from now, reading this README, will you still know why math is
>       normalized to `$...$` and why `engine="transformers"` must not be added?
>       (both are now recorded in `ocr_vl.py`'s module docstring — issue #3)
>
> If any of these has no answer, that section is not finished.
