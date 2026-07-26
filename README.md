<!--
=============================================================================
This README is a scaffold to fill in.                  (see issues #12, #10)
=============================================================================

How to use it
  1. Work top to bottom. Each section has a guidance comment listing the
     questions that section has to answer, then a TODO where the prose goes.
  2. Delete each guidance comment once you have written that section.
     A leftover guidance comment means the section is not done yet.
  3. When everything is filled in, check yourself against the list at the
     bottom of this file, then delete this block and that list.

The structure and the questions are provided. The content is yours to write:
the research question, the dead ends, and the results can only come from the
person who did the work.

On order
  The sections are ordered for a reader who will NOT run the code: problem,
  question, approach, results. You do not have to write them in that order —
  "Verified versions" and "Worked example" are mostly transcription, so they
  are the easiest places to start.

On language
  This file is in English, matching the code comments and docstrings. If you
  would rather write the research narrative in Korean, switch it deliberately
  and say so in one line — what matters is being consistent, not which
  language you pick (issue #12, guideline 9).

Length
  Aim for two screens total. If it outgrows that, move the per-stage detail
  into a file under docs/ and leave a link here.
=============================================================================
-->

# MathTTS

Reads Korean math problems aloud: image → OCR (Korean + LaTeX) → spoken Korean math via SRE → TTS.

<!-- Guidance — the one-liner above
     This is the line already in the repository description. Keep it, or
     sharpen it. Say only what the project does; motivation and background
     belong in the next section, not here.
-->

## The problem

<!-- Guidance — 3 to 5 sentences
     Questions to answer:
       - Who has trouble, and in what situation?
       - What do they do today, and why is that not good enough?
       - What changes for them if this works?

     This is the one thing missing from the repository entirely. Without it, a
     reader cannot tell why any of the rest is needed.

     Common mistake: opening with the technology ("this connects OCR to
     TTS..."). Open with the person and the situation instead.
-->

TODO

## Research questions

<!-- Guidance — 2 to 4 questions, one or two sentences each
     This section is what makes the document a piece of research rather than a
     description of a tool.

     Questions to answer:
       - What exactly were you trying to find out when you started?
       - What result would count as success, and what would count as failure?
       - What did you not know at the outset — what might have turned out not
         to work at all?

     Where to find them: two tools in this repository were built to answer
     specific questions already.
       - What question is sre-probe/index.js asking?
       - What is each of the four test cases in tts_probe.py checking?
     Those are your candidates. This is a matter of writing down what you
     already know, not inventing something new.

     Do not put the answers here. The answers go under "Results".
-->

TODO

## Approach

<!-- Guidance — a table, then one paragraph
     Fill in the stage table first. The first row below is filled in only to
     show the format; rewrite it in your own words along with the rest.

     Then one paragraph under the table. Questions to answer:
       - Why is this split into separate stages at all?
       - Why can the OCR output not go straight into TTS?
       - What breaks if you remove stage 2 (normalize)? What breaks without
         stage 3 (math to speech)?

     Why that paragraph matters: the list of stages can be recovered by
     reading the code. The reasoning behind the split cannot.
-->

| Stage | Entry point | In → out | What it does |
|---|---|---|---|
| 1. OCR | `ocr_vl.py` | `*.png` → `output/*.md` | TODO (example row — rewrite this) |
| 2. TODO | TODO | TODO | TODO |
| 3. TODO | TODO | TODO | TODO |
| 4. TODO | TODO | TODO | TODO |

TODO — one paragraph on why the pipeline is split this way

<!-- Guidance — list the investigation tools separately from the stages
     sre-probe/index.js and tts_probe.py are not pipeline stages; they are
     tools built to check something. Keep them out of the table and give them
     a line or two here. Right now that distinction lives only inside each
     file's docstring, so anyone opening the repository for the first time
     assumes all six files are part of the pipeline.
-->

TODO — the two investigation tools

## Results

<!-- Guidance — the section most often left empty, and the most important one
     Questions to answer:
       - For each research question above, what was the answer?
       - How far did it get, and where did it stall?
       - What is that judgement based on — what did you see or hear?
       - What turned out differently from what you expected?

     One rule: distinguish what you actually verified from what you are
     assuming. The code comments already do this ("confirmed from real output,
     not assumed" / "verify by ear before trusting the say-as tags"). If
     something has not been checked, write that it has not been checked. That
     is a perfectly good thing to write — a document that says so is more
     trustworthy, not less.

     Give the things that did not work the same weight as the things that did.
     In research a negative result is a result, not an appendix.
-->

TODO

## Worked example

<!-- Guidance — take one problem and show every stage of it
     Source image, then OCR output, then normalized LaTeX, then the Korean
     speech string, then the audio file. Paste the real output of each stage
     in a code block. Keep the commentary minimal.

     Why bother: it is faster to understand than any description, and it
     doubles as a reference point later — "this is what it used to produce".

     Which problem to pick: "kr question 1.png" is the candidate. Its OCR
     output contains a real broken-parenthesis case, so the example itself
     shows what the normalize stage is for. That is more useful than an
     example where everything already works.
-->

TODO

## Running it

<!-- Guidance — someone who just cloned this has to be able to follow it (#10)
     Easy things to leave out:
       - Installing the Python dependencies. requirements.txt currently does
         not install anywhere except macOS; either say so here or fix #7 first.
       - The separate npm install inside sre-probe/. It is its own dependency
         tree, which is why it is the most commonly missed step.
       - Credentials: which environment variables are needed and where .env
         goes. Point at .env.example, which already exists. Never write an
         actual key here.
       - The four commands in order, including that the folder names have to
         line up between stages and that stage 3 has to be run from inside
         sre-probe/.
       - First-run cost: stage 1 downloads hundreds of MB of model weights the
         first time and takes tens of seconds per image on CPU. Without a
         warning, that reads as the program having hung.
       - Which stages need the network or a paid service, and which are fully
         local.

     Run each command once and then write it down. Commands written from
     memory are wrong.
-->

TODO

## Limitations and what is unverified

<!-- Guidance — having this section makes the whole document more credible
     Separate three things:
       - What is deliberately not handled, and the reasoning behind that
       - What has not been checked yet
       - Known failures, and which inputs trigger them

     This is an easy section to write: most of it already exists in the code.
     See the "DOESN'T" list in normalize.py's docstring and the open say-as
     question in sre-probe/speak.js.

     What not to do: claim something the code cannot do. There is a PDF in
     this repository but no code that processes one; if the docs say PDF input
     works, a reader will believe it (#8).
-->

TODO

## Verified versions

<!-- Guidance — version, date, platform
     Why this is needed: "SRE supports Korean" is a claim with a shelf life.
     "SRE 5.0.0-rc.4, checked 2026-07" is a record. Six months from now, when
     something breaks, this table is the only reference for what changed.

     The code comments already work this way, so this is mostly transcription.
     Always include the date you checked.
-->

| Component | Version | Date checked |
|---|---|---|
| TODO | TODO | TODO |

Environment used: TODO (OS, CPU or GPU)

## Tools used

<!-- Guidance — name, one line on its role in the pipeline, one link each.
     This section is allowed to be short.
-->

TODO

<!--
=============================================================================
Self-check — go through this once everything is filled in
=============================================================================
It is done when someone who never opens the source can answer all of these
from this README alone.

  [ ] Whose problem does this solve, and what is it? (one sentence)
  [ ] What was being investigated?
  [ ] Did it work, and what is the evidence?
  [ ] What was tried that did not work?
  [ ] Can I run one problem through to audio on my own machine, and do I know
      in advance what the first run costs in time and disk?
  [ ] Which parts are known-broken, and which are simply unverified?
  [ ] Which claims were actually verified, against which versions, on what date?

And one that applies to you specifically as the author:

  [ ] Six months from now, reading this README, will you still know why math
      is normalized to $...$ and why engine="transformers" must not be added?
      (both of those are currently lost from the repository — issue #3)

If any of these has no answer, that section is not finished.
=============================================================================
-->
