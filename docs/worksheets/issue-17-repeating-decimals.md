# Working notes: the 순환소수 reading problem

Issue: [#17](https://github.com/hj1478/MathTTS/issues/17) · related: [#15](https://github.com/hj1478/MathTTS/issues/15)

*A working document, not a reference. It is scaffolding for one open question — delete it when #17 closes.*

Do these in order. **Step 1 involves no code.** What you decide there governs everything after it, so don't reorder.

---

## What is happening right now

Put `0.2̇4̇` (순환소수 0.24, 순환마디 24) through the pipeline and here is what comes out:

| Input | What is spoken (clearspeak) |
|---|---|
| `$0.2̇4̇$` | `0 마침표 2 위의 점 4 위의 점` |
| `$0.24$` — OCR dropped the dots | `0.24` |
| `$x=0.242424\cdots$` | `x 는 0.242424 점 점 점` |

Both are wrong, and **wrong in different ways**:

- Without the dots → an ordinary terminating decimal. A listener has no way to know anything was lost.
- With the dots → a description of the printing. A listener cannot decode it at all.

There are two separate causes: ① OCR loses the dots, and ② **even when the dots are there, no rule in the pipeline reads them as Korean.** `dot_check.py` deals with ①. These notes are about ②.

---

## Step 0 — Reproduce it yourself

Don't start from someone else's table. Seeing it once makes every later judgement faster.

```sh
cd sre-probe && npm install && cd ..          # first time only
mkdir -p /tmp/dots

printf '순환소수 $0.2̇4̇$ 를 분수로 나타내시오.\n' > /tmp/dots/a.norm.md
printf '순환소수 $0.24$ 를 분수로 나타내시오.\n'   > /tmp/dots/b.norm.md

cd sre-probe && node speak.js /tmp/dots/a.norm.md /tmp/dots/b.norm.md
```

The `STITCHED` line is the sentence a TTS voice would actually read. Compare the two files.

> **Watch out** — the dots in `0.2̇4̇` must be the combining character U+0307, not some other mark that looks similar on screen. Copy the `printf` above and it will be right. Typing it by hand can silently give you a different character, and you can lose an hour to "why doesn't this work".

After this, the table in #17 will mean something concrete to you.

---

## Step 1 — Decide what should be heard (no code)

**Question: listening to `0.2̇4̇` with no screen in front of you, what should you hear?**

You are the only person on this project who can answer. Not the code, not the library, not me — this is a question for someone who knows the mathematics.

Things to settle:

- Does the reading name the 순환마디 out loud, or only signal that something repeats?
- Does the repetition marker come before the digits or after?
- Should a one-digit period (`0.16̇`) read differently from a two-digit one (`0.2̇4̇`)?
- What about a mixed case like `0.24̇5̇`, where the first decimal place does not repeat?
- **The important one** — is there a case that is unambiguous on paper but ambiguous by ear? Would any candidate reading make `0.2̇4̇` sound identical to some other number?

That last question is the whole point of the project. This pipeline is not built to match the page; it is built so that **the number survives being heard**.

Ground your answer in what textbooks use, how a teacher reads it aloud in class, and what sounds natural when you say it yourself. There may be more than one workable answer — in that case, **why you chose the one you chose** is the result.

**Write the decision into `FINDINGS.md` before writing any code.** Skip this step and whatever SRE happens to emit becomes your target by default. That is not a decision; that is an accident.

---

## Step 2 — One route is already closed

The obvious cheap fix would have been: `normalize.py` has no rule for the combining dot, so convert it to LaTeX and let SRE's Korean rules handle it. **That has been measured and it does not work.**

| Span | Spoken (clearspeak) |
|---|---|
| `$0.2̇4̇$` (combining U+0307) | `0 마침표 2 위의 점 4 위의 점` |
| `$0.\dot{2}\dot{4}$` | identical |
| `$0.\overline{24}$` | `0 마침표 24 윗줄` |
| `$0.1\dot{6}$` | `0.1 6 위의 점` |

SRE names the decoration whichever notation carries it. Verify it yourself if you want — same setup as step 0, just put those spans in the file — but the pattern across three notations is not a coincidence.

**What that tells you, and it is the useful part:** the gap is a **reading rule, not an encoding**. No amount of rewriting the notation will produce Korean words that do not exist in SRE's Korean rule set. Whatever you build has to *say something new*.

Two things worth thinking about before step 3:

- Does that change where the fix can live? A notation change would have belonged in `normalize.py` almost by definition. A reading rule is less obvious.
- SRE is a rule engine with its own locale files. Adding a Korean rule *inside* SRE is a third option nobody has weighed here. What would make that a good idea, and what would make it a bad one for a project this size? (Consider who maintains it, and what happens on the next SRE release.)

**If you do try other notations, record what you find in `FINDINGS.md` either way** — especially a negative result. It stops the next person retrying it, and a finding about a tool's limits is a real research result. Note the version and the date; a future SRE release could change the answer.

---

## Step 3 — Decide where the reading rule belongs

Two candidates in this repository, plus the SRE option raised in step 2. All three could work; they are not equivalent.

- **`normalize.py`** — its current job is turning the OCR's inconsistent math notation into canonical LaTeX.
- **`sre-probe/speak.js`** — it stitches Korean speech back into the surrounding prose.

**Question:** what is each file's job right now? Does "a Korean word" belong to that job? Is it natural for a language rule to live in the file that assembles Korean sentences, or should that file stay pure plumbing?

**Write one sentence of justification, then choose.** That sentence is most of what you learn here, and it is your answer when someone later asks "why did you put it there?"

One more thing to weigh: whichever file you pick, would someone using it for its original purpose be surprised by your change?

---

## Step 4 — Make sure it stays fixed

`eval/cases.json` exists for this: you give it an input snippet and the substrings the resulting speech must (or must not) contain.

**Question:** what should the assertion be? And — **would that assertion have caught today's behaviour?** If not, it is too loose.

Why this matters here: failures in this pipeline are not crashes. It runs to completion, exits 0, and produces the wrong sound. Without an automatic check, that only ever gets caught by a human listening to every run.

---

## Step 5 — Record it

One entry in `FINDINGS.md`. Three lines is fine.

- What you observed (the output you saw yourself in step 0)
- The reading you chose and **why** ← the most valuable part
- What you found out about SRE: what worked, what didn't, version, date
- Where you implemented it and why there
- What you still don't know

---

## Done when

- [ ] The chosen reading and the reasoning are written down
- [ ] `$0.2̇4̇$` produces it — **verified by running the chain, not by reading the code**
- [ ] A regression check exists, and you can explain why it would have failed before
- [ ] The entry for this can be deleted from *Limitations* in `README.md` (it is no longer a limitation)
- [ ] `FINDINGS.md` has the entry

---

## Side observation

From the same measurement: `\cdots` reads as `점 점 점` (clearspeak) or `줄임표` (mathspeak). In a 순환소수 problem the `…` in `0.242424…` is doing mathematical work, and `0.242424 점 점 점` is unpleasant to listen to.

Two facts to weigh it against: the number itself is still read correctly, and **the same question applies** (what should a listener hear?), so the answer may live in the same place as the one above.

---

## If you get stuck

- **Stuck on step 1** — that's normal. It is not a coding problem, it is a judgement call. Read it aloud, play it to someone, ask them what they heard.
- **Stuck on step 2** — if you want to test other notations, `node index.js` in `sre-probe/` run as-is shows you how that tool is fed; the expression list is at the top of the file.
- **Stuck on step 3** — read the docstrings of the two candidate files. Each one already states what job it thinks it has, which is most of the argument. For the third option, look at what `sre-probe/index.js` reports about which Korean rule sets exist.
