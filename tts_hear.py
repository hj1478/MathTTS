"""Hear what the voice actually says: text -> pipeline -> Azure TTS -> Azure
speech recognition, printed next to what was sent.

The tests check the words the pipeline writes. They cannot see what Azure does
with them: skipping "①", reading "2번" as "두 번", or "4 마이너스" as "네
마이너스". Word-boundary events do not show it either (they echo the input).
Recognizing the audio does, roughly: the `Lexical` field of the detailed result
spells out each word as heard.

    python tts_hear.py                      # eval/hear_lines.txt
    python tts_hear.py my_lines.txt --formal

One problem line per input line. Read the output by eye: the recognizer mishears
too (letters, short words), so a difference is a lead, not a verdict. Numbers,
missing words and English unit names are the things to look for.
Needs the Azure key that tts_probe.make_config uses.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import azure.cognitiveservices.speech as sdk

import normalize
from tts_probe import make_config

ROOT = Path(__file__).resolve().parent
VOICE = "ko-KR-SunHiNeural"
ENVELOPE = ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="ko-KR">'
            f'<voice name="{VOICE}">%s</voice></speak>')


def hear(body):
    """SSML body -> the words Azure's recognizer hears in Azure's own audio."""
    cfg = make_config(VOICE)
    cfg.set_speech_synthesis_output_format(sdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm)
    r = sdk.SpeechSynthesizer(speech_config=cfg, audio_config=None).speak_ssml_async(ENVELOPE % body).get()
    if r.reason != sdk.ResultReason.SynthesizingAudioCompleted:
        return "TTS FAILED: " + r.cancellation_details.error_details[:200]
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(r.audio_data)
    try:
        rc = make_config(VOICE)
        rc.speech_recognition_language = "ko-KR"
        rc.output_format = sdk.OutputFormat.Detailed
        rec = sdk.SpeechRecognizer(speech_config=rc, audio_config=sdk.audio.AudioConfig(filename=f.name))
        out, done = [], []
        rec.recognized.connect(
            lambda e: out.append(json.loads(e.result.json)["NBest"][0]["Lexical"]) if e.result.text else None)
        rec.session_stopped.connect(lambda e: done.append(1))
        rec.canceled.connect(lambda e: done.append(1))
        rec.start_continuous_recognition()
        while not done:
            time.sleep(0.2)
        rec.stop_continuous_recognition()
    finally:
        os.unlink(f.name)
    return " | ".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("lines", nargs="?", default=str(ROOT / "eval" / "hear_lines.txt"))
    ap.add_argument("--formal", action="store_true", help="the accurate reading instead of the casual one")
    args = ap.parse_args()
    lines = [l.rstrip("\n") for l in open(args.lines, encoding="utf-8") if l.strip()]

    work = Path(tempfile.mkdtemp(prefix="tts-hear-"))
    try:
        (work / "in").mkdir()
        for i, line in enumerate(lines):
            (work / "in" / f"c{i:03d}.norm.md").write_text(normalize.normalize_math(line), encoding="utf-8")
        subprocess.run(["node", str(ROOT / "sre-probe" / "speak.js"), *([] if args.formal else ["--casual"]),
                        "--ssml", "--combos", "clearspeak/default", "--write", str(work / "out"),
                        "--dir", str(work / "in")], capture_output=True, text=True, check=False)

        def one(i):
            f = work / "out" / f"c{i:03d}.stitched.ssml"
            if not f.exists():
                return None, None
            body = re.sub(r"^<speak[^>]*><voice[^>]*>|</voice></speak>$", "", f.read_text(encoding="utf-8").strip())
            body = re.sub(r'</voice><voice name="[^"]*">', " ", body).replace("\n", " ")
            sent = re.sub(r'<sub alias="([^"]*)">[^<]*</sub>', r"\1", body)
            sent = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", sent)).strip()
            return sent, hear(body)

        with ThreadPoolExecutor(6) as pool:
            for i, (sent, heard) in enumerate(pool.map(one, range(len(lines)))):
                print(f"[{i}] {lines[i]}\n   sent : {sent}\n   heard: {heard}\n")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
