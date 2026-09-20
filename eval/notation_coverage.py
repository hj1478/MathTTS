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
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import normalize  # noqa: E402

FIXTURE = ROOT / "eval" / "fixtures" / "notation_coverage.md"
SPAN = re.compile(r"^  \$(.+)\$$")
READING = re.compile(r"^    \S+ (.*)$")


def measure():
    """-> [(latex, speech)] in document order."""
    with tempfile.TemporaryDirectory() as tmp:
        norm = Path(tmp) / "notation_coverage.norm.md"
        norm.write_text(normalize.normalize_math(FIXTURE.read_text(encoding="utf-8")),
                        encoding="utf-8")
        proc = subprocess.run(["node", str(ROOT / "sre-probe" / "speak.js"), str(norm)],
                              capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"speak.js failed (exit {proc.returncode}):\n{proc.stderr}")

    rows, latex = [], None
    for line in proc.stdout.splitlines():
        if line.startswith("STITCHED"):
            break
        m = SPAN.match(line)
        if m:
            latex = m.group(1)
            continue
        m = READING.match(line)
        if m and latex is not None:
            rows.append((latex, m.group(1).strip()))
            latex = None
    return rows


def main():
    ap = argparse.ArgumentParser(description="Re-measure #20's notation coverage.")
    ap.add_argument("--json", help="write the measurement here")
    ap.add_argument("--diff", help="compare against a previous --json save")
    a = ap.parse_args()

    rows = measure()
    if a.diff:
        before = {k: v for k, v in json.loads(Path(a.diff).read_text(encoding="utf-8"))}
        changed = [(l, before.get(l), s) for l, s in rows if before.get(l) != s]
        for latex, was, now in changed:
            print(f"{latex}\n  was: {was}\n  now: {now}")
        print(f"\n{len(changed)} of {len(rows)} span(s) changed")
    else:
        for latex, speech in rows:
            print(f"{latex:<36} | {speech}")
        print(f"\n{len(rows)} span(s)")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                encoding="utf-8")
        print(f"saved -> {a.json}")


if __name__ == "__main__":
    main()
