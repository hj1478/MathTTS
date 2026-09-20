#!/usr/bin/env python3
"""Re-measure the notation coverage of issue #20 through the real chain.

Runs eval/fixtures/notation_coverage.md through normalize.py and then
sre-probe/speak.js — the same two stages a real page goes through — and prints
one row per span: the LaTeX that reached SRE and the Korean speech that came
back, post-processing included.

This is reference material, not a pass/fail check: it records what the pipeline
says today so a change can be compared against what it said before.

  python3 eval/notation_coverage.py                 # print the table
  python3 eval/notation_coverage.py --json OUT.json # and save it for diffing
  python3 eval/notation_coverage.py --diff OLD.json # compare against a save
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import normalize  # noqa: E402

FIXTURE = ROOT / "eval" / "fixtures" / "notation_coverage.md"


def _notations(text):
    """The fixture's notation lines: everything after the first '## ' heading
    that is not blank and not itself a heading."""
    lines, started = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            started = True
            continue
        if line.startswith("SUMMARY:"):  # speak.js's own trailer, not a reading
            break
        if started and line.strip() and not line.startswith("#"):
            lines.append(line.strip())
    return lines


def measure():
    """-> [(written, spoken)] in document order.

    Reads speak.js's STITCHED block, not its per-span table. The two differ:
    speak.js post-processes at stitch time — the repeating-decimal intercept in
    particular — so the per-span table shows SRE's raw reading and would
    under-report what a listener actually hears. Issue #20 measured stitched
    output for the same reason.
    """
    with tempfile.TemporaryDirectory() as tmp:
        norm = Path(tmp) / "notation_coverage.norm.md"
        norm.write_text(normalize.normalize_math(FIXTURE.read_text(encoding="utf-8")),
                        encoding="utf-8")
        proc = subprocess.run(["node", str(ROOT / "sre-probe" / "speak.js"), str(norm)],
                              capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"speak.js failed (exit {proc.returncode}):\n{proc.stderr}")

    out = proc.stdout.split("STITCHED", 1)
    if len(out) < 2:
        sys.exit("speak.js printed no STITCHED block")
    spoken = _notations(out[1])
    written = _notations(FIXTURE.read_text(encoding="utf-8"))
    if len(written) != len(spoken):
        sys.exit(f"fixture has {len(written)} notation(s) but the stitched output "
                 f"has {len(spoken)} line(s) — they must correspond one to one")
    return list(zip(written, spoken))


def main():
    ap = argparse.ArgumentParser(description="Re-measure #20's notation coverage.")
    ap.add_argument("--json", help="write the measurement here")
    ap.add_argument("--diff", help="compare against a previous --json save")
    a = ap.parse_args()

    rows = measure()
    if a.diff:
        before = {k: v for k, v in json.loads(Path(a.diff).read_text(encoding="utf-8"))}
        changed = [(w, before.get(w), s) for w, s in rows if before.get(w) != s]
        for written, was, now in changed:
            print(f"{written}\n  was: {was}\n  now: {now}")
        print(f"\n{len(changed)} of {len(rows)} span(s) changed")
    else:
        for written, spoken in rows:
            print(f"{written:<34} | {spoken}")
        print(f"\n{len(rows)} span(s)")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                encoding="utf-8")
        print(f"saved -> {a.json}")


if __name__ == "__main__":
    main()
