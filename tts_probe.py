#!/usr/bin/env python3
"""Azure Neural TTS validation probe — is SRE's Korean math speech INTELLIGIBLE?

Speaks known-ambiguous SRE Korean outputs to .wav files for A/B listening.
NOT a pipeline: no SRE integration, no splicing. Just string -> Azure TTS -> wav.

For each test string, two files:
  (a) plain text, no SSML                      -> the baseline
  (b) SSML with <break time="300ms"/> pauses    -> does a pause fix the grouping?
For the control sentence, (b) is the SAME text wrapped in SSML with no break,
which isolates whether SSML wrapping itself changes prosody.

Verified against Azure Speech SDK 1.50.0 docs (2026-07):
  - auth: SpeechConfig(subscription=key, region=...) still supported; MS docs now
    prefer endpoint auth, so AZURE_SPEECH_ENDPOINT is honored when set
  - voices: ko-KR-SunHiNeural / ko-KR-InJoonNeural both current; HD variants
    exist (e.g. "ko-KR-SunHi:DragonHDLatestNeural") — pass via --voice
  - SSML: speak_ssml_async(); plain: speak_text_async(); success is
    ResultReason.SynthesizingAudioCompleted, failure details on .cancellation_details

Env (required, never hardcoded). Read from the process environment, else from a
.env file next to this script (KEY=VALUE lines; real env always wins):
  AZURE_SPEECH_KEY                       resource key
  AZURE_SPEECH_ENDPOINT                  e.g. https://<resource>.cognitiveservices.azure.com
  AZURE_SPEECH_REGION                    alternative to endpoint, e.g. koreacentral

Usage:
  python tts_probe.py                          # all cases -> ./audio/
  python tts_probe.py --voice ko-KR-InJoonNeural --break-ms 400 --out ./audio
"""
import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

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


def load_dotenv():
    """Tiny .env loader (no dependency): KEY=VALUE lines, # comments, real env wins."""
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("'\"")
        if k and v and k not in os.environ:
            os.environ[k] = v


def make_config(voice):
    import azure.cognitiveservices.speech as speechsdk
    load_dotenv()
    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION")
    endpoint = os.environ.get("AZURE_SPEECH_ENDPOINT")
    if not key or not (region or endpoint):
        sys.exit(
            "Missing Azure credentials. Either export them:\n"
            "  export AZURE_SPEECH_KEY=<your speech resource key>\n"
            "  export AZURE_SPEECH_ENDPOINT=<https://<resource>.cognitiveservices.azure.com>\n"
            "  (or AZURE_SPEECH_REGION instead of the endpoint)\n"
            "or fill in the .env file next to this script (AZURE_SPEECH_KEY= is\n"
            "currently blank there). Keys are never hardcoded in this script."
        )
    if endpoint:
        # normalize to scheme://host (tolerates trailing slash or a pasted path)
        p = urlparse(endpoint)
        cfg = speechsdk.SpeechConfig(subscription=key, endpoint=f"{p.scheme}://{p.netloc}")
    else:
        cfg = speechsdk.SpeechConfig(subscription=key, region=region)
    cfg.speech_synthesis_voice_name = voice
    cfg.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm)
    return cfg


def synth(cfg, path, text=None, ssml=None):
    """Synthesize one utterance to path. Returns (ok, detail)."""
    import azure.cognitiveservices.speech as speechsdk
    audio = speechsdk.audio.AudioOutputConfig(filename=str(path))
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=audio)
    result = (synthesizer.speak_ssml_async(ssml) if ssml
              else synthesizer.speak_text_async(text)).get()
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        size = path.stat().st_size if path.exists() else 0
        if size <= 44:  # nothing beyond a bare WAV header = silent failure
            return False, f"reported success but file is empty ({size} B)"
        return True, f"{size:,} B"
    if result.reason == speechsdk.ResultReason.Canceled:
        c = result.cancellation_details
        return False, f"canceled: {c.reason}; {c.error_details or '(no details)'}"
    return False, f"unexpected result: {result.reason}"


def main():
    ap = argparse.ArgumentParser(description="A/B validate Korean math speech on Azure Neural TTS.")
    ap.add_argument("--voice", default="ko-KR-SunHiNeural",
                    help="Korean neural voice (default ko-KR-SunHiNeural; alt ko-KR-InJoonNeural)")
    ap.add_argument("--break-ms", type=int, default=300, help="pause length for (b) versions")
    ap.add_argument("--out", default="./audio", help="output folder (default ./audio)")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = make_config(a.voice)
    br = f'<break time="{a.break_ms}ms"/>'

    print(f"voice: {a.voice}   break: {a.break_ms}ms   out: {out.resolve()}\n")
    rows, failures = [], 0
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
            rows.append((path.name, ok, detail))
            print(f"  [{'ok' if ok else 'FAIL':>4}] {path.name:<28} {detail}")

    print("\n" + "=" * 72)
    print("A/B LISTENING GUIDE  (play with: afplay audio/<file>)")
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
