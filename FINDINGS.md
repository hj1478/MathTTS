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
> - [ ] **Does SRE support Korean math speech at all, and in which domains and
>   styles?** This is what `sre-probe/index.js` was built to answer. Include the
>   part that was surprising: clearspeak "styles" turned out to be combinatorial
>   preference toggles rather than distinct named styles.
> - [ ] **What does PaddleOCR-VL's raw output actually look like?** The whole
>   downstream chain depends on the `$...$` convention. Record what you saw that
>   confirmed it — `ocr_vl.py` says it was confirmed from real output, but the
>   evidence itself is now lost (issue #3).
> - [ ] **`engine="transformers"` crashes the paddle-only layout model.** A trap
>   worth writing down before someone tries swapping the VL backend again — which
>   will be you (issue #3).
> - [ ] **Why a heuristic instead of a LaTeX parser?** `normalize.py` states the
>   decision; the log is where the reasoning and the alternatives you rejected go.
> - [ ] **SRE's SSML envelope is rejected by Azure.** SRE emits
>   `<speak version="1.1" xml:lang="ko">` with no `<voice>`; Azure wants
>   `version="1.0"`, `xml:lang="ko-KR"` and a `<voice>` tag, so `speak.js` strips
>   and re-wraps it. Worth an entry because it is a non-obvious incompatibility
>   between two tools that both claim to speak SSML.
> - [ ] **Is the Korean math speech actually intelligible by ear?** `tts_probe.py`
>   was built to answer this — four test cases, `1a` vs `1b` being the fraction
>   grouping test. The answer is not recorded anywhere. This is the single most
>   valuable missing entry: it is the question the whole project rests on.
> - [ ] **Azure's transient "Codec decoding is not started within 2s".** Handled
>   with one retry in `tts_full.py:47`. Short entry — what you saw, how often, what
>   fixed it.
> - [ ] **`interpret-as="character"` vs `"characters"`.** Still unresolved
>   (issue #9). Log it as an open question now, and add the answer when you check
>   it — a dated "unresolved" entry is a legitimate entry.
>
> Two of these — the OCR output convention and the `engine="transformers"` crash —
> are the findings issue #3 is about recovering. Writing them here is the same work.
