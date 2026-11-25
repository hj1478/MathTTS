#!/usr/bin/env python3
"""Azure Neural TTS validation probe — is SRE's Korean math speech INTELLIGIBLE?

Speaks known-ambiguous SRE Korean outputs to .wav files for A/B listening.
NOT a pipeline: no SRE integration, no splicing. Just string -> Azure TTS -> wav.

For each test string, two files:
  (a) plain text, no SSML                      -> the baseline
  (b) SSML with <break time="300ms"/> pauses    -> does a pause fix the grouping?
For the control sentence, (b) is the SAME text wrapped in SSML with no break,
which isolates whether SSML wrapping itself changes prosody.

Credentials and synthesis: pipeline/azure_tts.py (AZURE_SPEECH_KEY and an
endpoint or region, from the environment or the repo's .env).

Usage:
  python scripts/tts_probe.py                          # all cases -> ./work/audio/
  python scripts/tts_probe.py --voice ko-KR-InJoonNeural --break-ms 400 --out ./work/audio
"""
import argparse
import sys
from pathlib import Path

from pipeline.azure_tts import make_config, synth

# {br} marks where the disambiguation pause goes in the SSML (b) version.
# (id, slug, plain_text, ssml_body_with_{br}, what_to_listen_for)
TESTS = [
    ("1", "fraction",
     "2 분의 x 더하기 1",
     "2 분의 {br}x 더하기 1",
     "Does 1a sound like (x+1)/2 or like x/2 + 1? Does the pause in 1b group it correctly?"),
    ("2", "nested",
     "분모가 c 더하기 1 이고 분자가 b 분의 a 인 분수",
     "분모가 c 더하기 1 이고 분자가 b 분의 {br}a 인 분수",
     "Is the inner fraction a/b clearly separate from denominator c+1?"),
    ("3", "chained",
     "p 작거나 같다 k 작다 q",
     "p 작거나 같다 {br}k 작다 {br}q",
     "SRE's weak spot: is the terse relation chain parseable at all by ear?"),
    ("4", "control",
     "다음 방정식을 구하시오",
     "다음 방정식을 구하시오",   # no break: isolates SSML-wrapper prosody effect
     "Clean prose baseline — both versions should sound identical and natural."),
]

SSML = ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xml:lang="ko-KR"><voice name="{voice}">{body}</voice></speak>')


def main():
    ap = argparse.ArgumentParser(description="A/B validate Korean math speech on Azure Neural TTS.")
    ap.add_argument("--voice", default="ko-KR-SunHiNeural",
                    help="Korean neural voice (default ko-KR-SunHiNeural; alt ko-KR-InJoonNeural)")
    ap.add_argument("--break-ms", type=int, default=300, help="pause length for (b) versions")
    ap.add_argument("--out", default="./work/audio", help="output folder (default ./work/audio)")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = make_config(a.voice)
    br = f'<break time="{a.break_ms}ms"/>'

    print(f"voice: {a.voice}   break: {a.break_ms}ms   out: {out.resolve()}\n")
    failures = 0
    for num, slug, plain, body, listen in TESTS:
        for tag, kwargs in (
            ("a", {"text": plain}),
            ("b", {"ssml": SSML.format(voice=a.voice, body=body.format(br=br))}),
        ):
            path = out / f"{num}{tag}-{slug}-{'plain' if tag == 'a' else 'ssml'}.wav"
            try:
                ok, detail = synth(cfg, path, **kwargs)
            except Exception as e:  # one failure must not kill the batch
                ok, detail = False, f"{type(e).__name__}: {e}"
            failures += not ok
            print(f"  [{'ok' if ok else 'FAIL':>4}] {path.name:<28} {detail}")

    print("\n" + "=" * 72)
    print("A/B LISTENING GUIDE  (play with: afplay <out>/<file>)")
    print("=" * 72)
    for num, slug, plain, body, listen in TESTS:
        print(f'\n  {num}a vs {num}b ({slug}):  "{plain}"')
        print(f"      {listen}")
    print("\n  Priority: 1a vs 1b — the fraction-grouping pause test.")
    if failures:
        print(f"\n{failures} synthesis call(s) FAILED — see rows above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
