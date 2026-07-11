#!/usr/bin/env python3
"""Speak WHOLE Korean math problems (prose + math) through Azure Neural TTS.

Input: stitched files produced by  sre-probe/speak.js --write ../stitched
  *.stitched.txt   plain stitched text (SRE markup:none)   -> speak_text_async
  *.stitched.ssml  Azure-enveloped SSML (SRE markup:ssml,  -> speak_ssml_async
                   structural <break>s, <say-as> character, prosody rate)

Output: ./audio/<name>-full-plain.wav and <name>-full-ssml.wav for A/B listening.
Reuses tts_probe.py for .env loading, SpeechConfig, and verified synthesis.

Note: the voice INSIDE a .ssml file's <voice> tag was fixed when speak.js wrote
it (its --voice flag); --voice here only affects the plain versions.

Usage:  python tts_full.py [--stitched ./stitched] [--out ./audio]
"""
import argparse
import sys
from pathlib import Path

from tts_probe import make_config, synth


def main():
    ap = argparse.ArgumentParser(description="Speak whole stitched problems (plain vs SSML A/B).")
    ap.add_argument("--stitched", default="./stitched", help="folder with *.stitched.txt/.ssml")
    ap.add_argument("--out", default="./audio", help="output folder (default ./audio)")
    ap.add_argument("--voice", default="ko-KR-SunHiNeural", help="voice for the PLAIN versions")
    a = ap.parse_args()

    files = sorted(Path(a.stitched).glob("*.stitched.*"))
    if not files:
        sys.exit(f"No *.stitched.txt / *.stitched.ssml in {a.stitched} — "
                 "generate them with: node sre-probe/speak.js --write ./stitched ...")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = make_config(a.voice)

    failures = 0
    for f in files:
        kind = "ssml" if f.suffix == ".ssml" else "plain"
        base = f.name.split(".stitched.")[0].replace(" ", "_")
        path = out / f"{base}-full-{kind}.wav"
        content = f.read_text(encoding="utf-8").strip()
        kwargs = {"ssml": content} if kind == "ssml" else {"text": content}
        for attempt in (1, 2):  # transient Azure errors happen ("Codec decoding
            try:                # is not started within 2s") — one retry fixes them
                ok, detail = synth(cfg, path, **kwargs)
            except Exception as e:  # one failure must not kill the batch
                ok, detail = False, f"{type(e).__name__}: {e}"
            if ok:
                break
            if attempt == 1:
                print(f"  [retry] {path.name}: {detail}")
        failures += not ok
        print(f"  [{'ok' if ok else 'FAIL':>4}] {path.name:<40} {detail}")

    print("\nA/B per question: <name>-full-plain.wav  vs  <name>-full-ssml.wav")
    print("(ssml = SRE's own structural breaks + say-as + prosody; plain = bare text)")
    if failures:
        print(f"\n{failures} synthesis call(s) FAILED — see rows above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
