#!/usr/bin/env python3
"""One wav per QUESTION: split cached OCR pages into individual questions and
synthesize each separately (audio/questions/<source>/<label>.wav).

A convenience driver over the normal stages, not a new stage: it re-normalizes
the cached raw OCR (output/*.md for the root images, runs/<name>/*_<p>.md for
every previously processed PDF), splits each page at question markers, runs
ONE speak.js --ssml pass over all chunks, then synthesizes every chunk with
Azure. Also emits a few synthetic 순환소수 questions (source "repeating_
decimals") so the chosen reading C is audible on full problems, not just
the dot_reading_probe.py candidate snippets.

Question boundaries (heuristic): a line starting with "N. " or "[N]" opens a
new question; page content before the first marker becomes a p<page>_intro
chunk when it is long enough to matter. Choice/answer markers like "(1)" or
"1)" deliberately do NOT split — they belong to their question.

Usage:
  python question_audio.py              # everything -> audio/questions/
  python question_audio.py --dry-run    # show the chunk table, no Azure calls

Writes audio/questions/manifest.tsv (file, chars, text preview) for browsing.
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import normalize

ROOT = Path(__file__).parent
QMARK = re.compile(r"^\s*(?:(\d{1,2})\.\s|\[(\d{1,2})\]\s?)")
TAGS = re.compile(r"<[^>]+>")
# OCR sometimes hallucinates emoji walls in headers (one produced 10+ minutes
# of TTS reading 📊 seventy times) — never meaningful in a worksheet, drop them
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")
_WORDCHAR = re.compile(r"[가-힣0-9A-Za-z]")


def _page_key(p):
    """Sort <name>_<n>.md by page NUMBER — the index is written unpadded, so
    plain sorted() puts _10 before _2 from ten pages on."""
    m = re.search(r"_(\d+)$", Path(p).stem)
    return (int(m.group(1)) if m else -1, str(p))

REPEATING_QUESTIONS = [
    ("q1_dots", "순환소수 0.2̇3̇을 분수로 나타내시오."),
    ("q2_critical_pair", "순환소수 0.12̇3̇과 0.1̇23̇의 순환마디를 각각 구하시오."),
    ("q3_overline", r"$1.\overline{23}$을 분수로 나타내시오."),
]


def split_questions(text, page):
    """Page text -> [(label, chunk_text)] split at question markers."""
    chunks, label, buf = [], f"p{page}_intro", []
    for line in text.splitlines():
        m = QMARK.match(line)
        if m:
            if "".join(buf).strip():
                chunks.append((label, "\n".join(buf)))
            label, buf = f"p{page}_q{m.group(1) or m.group(2)}", [line]
        else:
            buf.append(line)
    if "".join(buf).strip():
        chunks.append((label, "\n".join(buf)))
    # an intro that carries no real content (judged by Hangul/alnum characters,
    # not raw length — decoration can be long) isn't worth its own wav
    return [(l, t) for l, t in chunks
            if not (l.endswith("_intro") and len(_WORDCHAR.findall(t)) < 40)]


def collect():
    """-> [(source, label, raw_text)] for every cached question."""
    out = []
    for md in sorted((ROOT / "output").glob("*.md")):
        if md.name.endswith(".norm.md") or md.stem.startswith("page"):
            continue  # page.png is the English salvage fixture, not a question
        src = md.stem.replace(" ", "_")
        out.append((src, "q1", md.read_text(encoding="utf-8")))
    for run in sorted((ROOT / "runs").iterdir()):
        if not run.is_dir():
            continue
        for md in sorted(run.glob(f"{run.name}_*.md"), key=_page_key):
            if md.name.endswith((".norm.md", ".dots.md")):
                continue
            dots = md.parent / (md.stem + ".dots.md")   # prefer dot-restored text
            text = EMOJI.sub("", (dots if dots.exists() else md).read_text(encoding="utf-8"))
            page = md.stem.rsplit("_", 1)[1]
            for label, chunk in split_questions(text, page):
                out.append((run.name, label, chunk))
    for label, q in REPEATING_QUESTIONS:
        out.append(("repeating_decimals", label, q))
    # a question number can repeat on a page (answer-key columns) — suffix the
    # duplicates so files don't silently overwrite each other
    seen, deduped = {}, []
    for src, label, text in out:
        n = seen[(src, label)] = seen.get((src, label), 0) + 1
        deduped.append((src, label if n == 1 else f"{label}_{n}", text))
    return deduped


def main():
    ap = argparse.ArgumentParser(description="One wav per question from cached OCR.")
    ap.add_argument("--out", default="./audio/questions")
    ap.add_argument("--voice", default="ko-KR-SunHiNeural")
    ap.add_argument("--dry-run", action="store_true", help="chunk table only, no Azure")
    a = ap.parse_args()

    chunks = collect()
    print(f"{len(chunks)} question chunk(s) from "
          f"{len({s for s, _, _ in chunks})} source(s)")

    tmp = Path(tempfile.mkdtemp(prefix="qaudio-"))
    files = []
    for src, label, text in chunks:
        f = tmp / f"{src}__{label}.norm.md"
        f.write_text(normalize.normalize_math(text), encoding="utf-8")
        files.append((src, label, f))

    if a.dry_run:
        for src, label, f in files:
            preview = f.read_text(encoding="utf-8").strip().replace("\n", " ")[:70]
            print(f"  {src:<44} {label:<10} {preview}")
        return

    print("[stitch] one speak.js --ssml pass over all chunks...")
    proc = subprocess.run(
        ["node", str(ROOT / "sre-probe" / "speak.js"), "--ssml", "--voice", a.voice,
         "--write", str(tmp), *[str(f) for _, _, f in files]],
        capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"speak.js failed:\n{proc.stderr[-2000:]}")

    from tts_probe import make_config, synth
    cfg = make_config(a.voice)
    out_root = Path(a.out)
    out_root.mkdir(parents=True, exist_ok=True)   # manifest.tsv is written even
    manifest, failures = [], 0                    # if every chunk was skipped
    for i, (src, label, f) in enumerate(files, 1):
        ssml_file = tmp / f"{src}__{label}.stitched.ssml"
        if not ssml_file.exists():
            print(f"  [skip] {src}/{label}: no stitched output")
            continue
        ssml = ssml_file.read_text(encoding="utf-8").strip()
        dest = out_root / src / f"{label}.wav"
        dest.parent.mkdir(parents=True, exist_ok=True)
        preview = " ".join(TAGS.sub("", ssml).split())[:60]  # one line, tab-safe
        if dest.exists() and dest.stat().st_size > 44:  # rerun = fill gaps only
            manifest.append(f"{src}/{label}.wav\t{len(ssml)}\t{preview}")
            continue
        for attempt in (1, 2):  # transient Azure errors: one retry
            try:
                ok, detail = synth(cfg, dest, ssml=ssml)
            except Exception as e:
                ok, detail = False, f"{type(e).__name__}: {e}"
            if ok:
                break
        failures += not ok
        manifest.append(f"{src}/{label}.wav\t{len(ssml)}\t{preview}")
        print(f"  [{i:>3}/{len(files)}] [{'ok' if ok else 'FAIL':>4}] "
              f"{src}/{label}.wav  {detail}")

    (out_root / "manifest.tsv").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"\n{len(manifest)} wav(s) under {out_root}/  (manifest.tsv alongside)")
    if failures:
        sys.exit(f"{failures} synthesis call(s) FAILED — see rows above.")


if __name__ == "__main__":
    main()
