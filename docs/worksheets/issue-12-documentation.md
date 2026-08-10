# Working notes: finishing the documentation

Issue: [#12](https://github.com/hj1478/MathTTS/issues/12)

*A working document, not a reference. It is scaffolding for one open question — delete it when #12 closes.*

Four sections of `README.md` are still `TODO`, and `FINDINGS.md` has no entries. These are the parts nobody else can write — not because they are hard, but because the answers are only in your head.

---

## Where things stand

```sh
grep -n 'TODO' README.md                 # what is still empty
grep -c 'Guidance' README.md             # leftover scaffolding blocks
sed -n '/^## Entries/,$p' FINDINGS.md    # the log, and its candidate list
```

| Written | Still `TODO` |
|---|---|
| Approach, Running it, Limitations, Verified versions, Tools used | The problem, Research questions, Results, Worked example |

`FINDINGS.md`: scaffold and a list of eight candidate entries; no entries written.

---

## Step 0 — Read what you already wrote

```sh
sed -n '/^## Limitations/,/^## Verified/p' README.md
```

Worth doing before writing more, because that section is the standard the rest has to meet. Notice what it does: it separates *deliberately not handled* from *not yet checked* from *known failure*, and it says out loud that the `<say-as>` change shipped without an ear check.

That last part is the hard skill in research writing, and it is already there. Whatever you write in *Results* should be that honest — which is the whole difficulty of that section.

---

## Step 1 — The problem

Currently the only thing entirely absent from the repository. A reader cannot tell why any of the rest exists.

Questions to answer, in three to five sentences:

- Who has trouble, and in what situation?
- What do they do today, and why is that not good enough?
- What changes for them if this works?

**The trap:** opening with the technology. "This project connects OCR to TTS…" describes the machinery, not the problem. Start with a person in a situation, and the machinery becomes obvious later.

A test for the draft: could someone who knows nothing about OCR, LaTeX, or SRE read your three sentences and say who this is for?

---

## Step 2 — Research questions

This section is what makes the repository a piece of research rather than a description of a tool.

Two to four questions, one or two sentences each:

- What exactly were you trying to find out when you started?
- What result would have counted as success, and what as failure?
- What did you *not* know at the outset — what might have turned out not to work at all?

**This is mostly transcription, not invention.** Two tools in the repo were built to answer specific questions:

```sh
sed -n '1,15p' sre-probe/index.js       # what is this probe asking?
sed -n '1,30p' tts_probe.py             # and what do its four test cases check?
```

Read those two docstrings and the questions are largely there in prose already. Your job is to state them as questions and say which ones mattered.

**Do not put the answers here.** Answers go in *Results*. Keeping them apart is what lets a reader see whether the project answered its own questions or drifted.

---

## Step 3 — Results

The section most often left empty, and the one a reader will judge the project by.

- For each question in step 2, what was the answer?
- How far did it get, and where did it stall?
- What is that judgement based on — what did you see or hear?
- What turned out differently from what you expected?

**The one rule:** keep verified and assumed visibly apart. If something has not been checked, write that it has not been checked. A document that says so is more trustworthy, not less — and `Limitations` already proves you can do this.

Where the raw material is:

```sh
sed -n '/^## Limitations/,/^## Verified/p' README.md   # what is known broken
sed -n '1,40p' eval/problems.md                        # what the eval found
```

Two honest facts you already have, as examples of the register: the 순환소수 reading does not exist and has been measured (#17); the `<say-as>` change went in on the strength of Azure's docs without listening (#9).

Give what did not work the same weight as what did. In research a negative result is a result, not an appendix.

---

## Step 4 — Worked example

One problem, shown at every stage. `kr question 1.png` is a good candidate: its OCR output contains the broken-parenthesis case that `normalize.py` repairs, so the example shows *why* stage 2 exists rather than just showing a success.

```sh
python run.py "kr question 1.png" --skip-tts
```

`run.py` prints the path of each artifact it writes; open them in order — the OCR markdown, the `.norm.md`, then the `.stitched.txt` under `stitched/`. Paste each one into the section as a code block. Add the wav if you run stage 4.

Keep the commentary minimal. The point is that a reader can see the transformation happen; if the stages need explaining at length, the Approach section is where that belongs.

This doubles as a reference point later: "this is what it used to produce."

---

## Step 5 — The first `FINDINGS.md` entry

The file has a template and eight candidates. Two things about them:

- Most of the content already exists in code comments — it needs a date and a sentence of conclusion, not new investigation.
- One is live right now: the 순환소수 work in #17 is producing exactly the kind of thing this log is for.

An entry can be three lines. A short entry written today beats a thorough one that never gets written.

The part people leave out, and the part worth most in six months: **what you expected before you ran it.** A finding is only surprising relative to a prediction.

---

## Step 6 — Remove the scaffolding

```sh
grep -n 'Guidance\|This README is a scaffold\|Self-check' README.md
```

Each guidance block goes when its section is written. The header notice and the trailing self-check block go last. A leftover block is the signal that something is unfinished, so leaving one behind after finishing makes the signal lie.

---

## Done when

The README already carries the test — the self-check block at the bottom of the file. Work through it as written; if any line has no answer, that section is not finished.

The one line it does not cover: `FINDINGS.md` should have at least one entry that someone else could learn from.

---

## If you get stuck

- **Stuck on step 1** — say it out loud to someone who does not know the project, then write down what you said. Spoken explanations skip the machinery automatically.
- **Stuck on step 2** — you are probably trying to invent questions. Read the two probe docstrings again; the questions were already asked in code.
- **Stuck on step 3** — write the failures first. They are easier to state precisely, and they set the honest tone for the rest.
- **Stuck on step 5** — pick the shortest candidate in the list, not the most important one. The habit matters more than the entry.
