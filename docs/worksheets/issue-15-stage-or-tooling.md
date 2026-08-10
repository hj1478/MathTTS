# Working notes: is `dot_check.py` a pipeline stage or eval tooling?

Issue: [#15](https://github.com/hj1478/MathTTS/issues/15) · related: [#17](https://github.com/hj1478/MathTTS/issues/17)

*A working document, not a reference. It is scaffolding for one open question — delete it when #15 closes.*

The repository currently answers this question four different ways. Only one can be right, and until it is settled the README cannot honestly say which stages a plain run executes or what one run costs.

Steps 0–2 are reading and deciding. Nothing needs to be written until step 2, and no code until step 4.

---

## Step 0 — See the disagreement yourself

Six commands. Each one shows you a place that says something about where `dot_check.py` belongs.

```sh
sed -n '1,12p' dot_check.py              # how does it describe its own position?
sed -n '1,16p' run.py                    # which stages does the driver list?
grep -n 'dot' run.py                     # ...and how many times does it mention this one?
grep -n -A5 'Credentials' README.md      # which group is the OpenAI key filed under?
grep -n 'dot_check' README.md            # what does the README say about it elsewhere?
grep -n 'dot_check\|restore_dots' inbox_eval.py   # how does the eval harness use it?
```

Make a table: one row per source, one line for what it claims. Then mark which rows are consistent with each other.

They do not all agree, but don't take my word for the split — the README changed recently and part of it now describes the situation accurately while other parts don't. Working out *which* parts is the point of this step, and it tells you how much of the fix is editing text versus changing behaviour.

---

## Step 1 — Trace one page

Not "read the code" — follow one page of OCR text and watch where it goes.

**In `inbox_eval.py`:** find `restore_dots()`. What does it return? Then find where that return value is used — does anything downstream consume it, or is it only printed and saved? Follow it into `stitch()`.

**In `dot_eval.py`:** find where it calls into `dot_check`. What does it do with the result?

**The question:** one of these two scripts is using `dot_check.py` to *change the data that continues down the pipeline*. The other is using it to *find out how well it works*. Which is which — and what in the code told you?

A useful sharpener: what does `dot_check.py --write` do to a file? Is that the behaviour of something that transforms, or something that measures?

---

## Step 2 — Decide, and write one sentence

Stage, or tooling? Write the sentence before moving on — it is what you will point at later when the docs need to say something definite.

Two more questions that feed the sentence:

- **What breaks if it never runs?** You already know the answer from the *Limitations* section of the README. Is what breaks a *missing measurement*, or a *wrong output*?
- **Would you be comfortable if someone ran the whole pipeline and never knew this existed?** Your answer says something about which category it is in.

---

## Step 3 — If it is a stage: why is it off by default?

There is more than one reason, and running them together is how this gets decided badly. Separate them:

- **What does it cost?** Per page, and under what condition is a page sent at all? `needs_check()` is the gate — read it and work out how often it lets a page through.
- **What happens when the model is wrong?** `dot_eval.py`'s docstring argues that a miss and a false dot are not equally bad. Read that argument. Do you agree? Which one would you accept more of?
- **Does it actually improve the audio yet?** See #17. This one may be the deciding factor, and it is not about `dot_check.py` at all.

If any of these has no answer yet, that is itself the answer to "should it be on by default".

---

## Step 4 — If a plain run should reach it: predict, then run

`run.py` has no way to invoke `dot_check.py` today. Before you write the flag, answer these two on paper. Both have silent failure modes — nothing crashes, nothing prints an error.

**Prediction 1.** Stage 2 in `run.py` reads each page with `p.read_text()`. If your new stage writes the patched page to a *different* file, which file does stage 2 read? Which one *should* it read, if you want the raw OCR output to stay on disk for comparison? Write down the option you'll take and why.

**Prediction 2.** Look at how `--skip-ocr` collects its input:

```sh
grep -n -A3 'skip_ocr' run.py
```

Write down what that glob will match on a *second* run, once a patched page exists next to the original. Then create a dummy patched page and run it with `--skip-ocr --skip-speak --skip-tts` and see whether you were right. Count the files stage 2 reports.

Both predictions are the point of this step. Getting one wrong and finding out by running it is worth more than getting the flag working on the first try.

---

## Step 5 — Make the four sources agree

Whatever you decided, the four places from step 0 have to say the same thing. Depending on your answer, that may mean:

- `dot_check.py`'s docstring stops (or starts) calling itself a pipeline stage
- `run.py`'s docstring lists the stages it actually runs
- the README's Approach table gains a row, or does not
- the README's *Credentials* note says which stages need which key — and a reader can work out what a single run costs before starting

The test for this step: someone reading only the README should be able to say which stages a plain `python run.py image.png` executes. Right now they cannot.

---

## Step 6 — Record it

A `FINDINGS.md` entry. The decision, the sentence from step 2, and anything the predictions in step 4 got wrong — that last part is the most useful thing in the entry, and the easiest to leave out.

---

## Done when

- [ ] One answer, and the four sources from step 0 all agree with it
- [ ] If a plain run can reach it: a run with the flag off and a run with it on both behave sensibly, and you checked the second-run case from prediction 2
- [ ] If it stays tooling: `Limitations` explains that the repair exists but is not part of the pipeline, so a reader is not left thinking it runs
- [ ] The README lets a reader work out which stages cost money
- [ ] `FINDINGS.md` has the entry

---

## If you get stuck

- **Stuck on step 1** — follow the return value, not the function. Where does the string go after `restore_dots()` hands it back?
- **Stuck on step 2** — try writing the opposite sentence and see which one you can't defend.
- **Stuck on step 3** — the cost question is answerable by reading one function. Start there.
- **Stuck on step 4** — write the prediction down even if you're unsure. A wrong prediction you wrote down teaches more than a right one you kept in your head.
