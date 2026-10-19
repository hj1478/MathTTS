#!/usr/bin/env python3
"""Run the pipeline on ONE image and collect every stage's output (the Modal worker's job).

Same stages, same order and same guards as run.py — this calls the stage code
(ocr_vl.run_image, normalize.normalize_math, sre-probe/speak.js --strict,
tts_probe.synth) and changes none of it. Where it differs from run.py, it is
for running as a service rather than as a CLI:

  - The OCR model stays loaded between jobs. run.py drops it before spawning
    node because on a laptop it starves speak.js of RAM; the worker container
    is sized for both.
  - Stage 4 synthesizes the SSML version only. tts_full.py writes plain AND
    SSML wavs for A/B listening; a service needs one, and one call per job
    halves what the Azure F0 quota pays for. It asks Azure for MP3 (24 kHz,
    48 kbit/s mono) instead of tts_probe's WAV: about 1/8 the size, so it can
    be served from the job store and downloads faster (FINDINGS.md, 2026-10-19).
  - Stage 3 runs the plain and SSML speak.js passes at the same time instead
    of one after the other. They write different files. When the plain pass
    fails --strict, the SSML pass's output is discarded, so the result is the
    same as run.py's, where the SSML pass would never have run.
  - A stage-4 failure does not fail the job. The text stages are the result;
    audio carries its own status, and an exhausted quota is reported as
    "quota_reached" rather than as an error.
  - Stage 1.5 (--dots) stays off, as in a default run.py — it needs an OpenAI
    key the service does not have.

run.py stops before stage 4 when speak.js --strict fails (a formula stitched
as salvage or a placeholder). That guard is kept: the text is returned, the
audio is "skipped", and Azure is never asked to read a placeholder aloud.

The CLI below loads the OCR model, so run it only on a machine sized for it
(not the dev laptop), e.g. inside the worker image:
  python backend/job.py "kr question 1.png" --skip-tts
"""
import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import normalize                 # noqa: E402  (needs ROOT on sys.path)
from backend import limits       # noqa: E402

SPEAK_JS = ROOT / "sre-probe" / "speak.js"
VOICE = "ko-KR-SunHiNeural"      # run.py's default
AUDIO_NAME = "audio.mp3"
AUDIO_MEDIA_TYPE = "audio/mpeg"
SPEAK_TIMEOUT_S = 120

# Korean messages travel with the machine-readable codes so every client
# shows the same wording; docs/API.md lists them all.
AUDIO_MESSAGES = {
    "ready": "음성이 준비되었습니다.",
    "quota_reached": "이번 달 음성 합성 한도에 도달했습니다. 텍스트 결과는 정상적으로 확인할 수 있습니다.",
    "skipped": "인식할 수 없는 수식이 있어 음성을 만들지 않았습니다. 텍스트 결과를 확인해 주세요.",
    "failed": "음성 합성에 실패했습니다. 텍스트 결과는 정상적으로 확인할 수 있습니다.",
    "not_requested": "음성 합성을 건너뛰었습니다.",
}
JOB_ERROR_MESSAGES = {
    "ocr_failed": "이미지에서 글자를 읽지 못했습니다. 다른 사진으로 다시 시도해 주세요.",
    "no_text_found": "이미지에서 문제를 찾지 못했습니다. 문제 하나가 잘 보이도록 다시 찍어 주세요.",
    "speech_stage_failed": "수식을 읽는 단계에서 오류가 발생했습니다.",
    "internal_error": "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    "timeout": "처리 시간이 너무 오래 걸려 중단했습니다. 다시 시도해 주세요.",
    "worker_lost": "처리가 중단되었습니다. 다시 시도해 주세요.",
}


class JobError(Exception):
    """A text stage failed — the job has no usable result."""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def _speak(norm_path, out_dir, ssml):
    """sre-probe/speak.js, exactly as run.py calls it (--strict, --voice, --write).

    Returns (exit_code, SUMMARY lines). Exit 2 is the --strict failure: the
    files were still written, but something stitched as salvage/placeholder.
    """
    cmd = ["node", str(SPEAK_JS), "--strict", "--voice", VOICE, "--write", str(out_dir)]
    if ssml:
        cmd.append("--ssml")
    cmd.append(str(norm_path))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=SPEAK_TIMEOUT_S)
    summary = [ln.strip() for ln in proc.stdout.splitlines() if ln.startswith("SUMMARY:")]
    if proc.returncode not in (0, 2):
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or [""]
        raise JobError("speech_stage_failed", tail[0])
    return proc.returncode, summary


def _synthesize(ssml_text, audio_path):
    """Stage 4 via tts_probe (the code tts_full.py uses), with tts_full's one retry.
    MP3 instead of tts_probe's WAV (see the module docstring)."""
    import azure.cognitiveservices.speech as speechsdk
    from tts_probe import make_config, synth
    try:
        cfg = make_config(VOICE)
    except SystemExit:  # make_config exits when credentials are missing
        return "failed", "Azure credentials not configured"
    cfg.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3)
    ok, detail = False, ""
    for attempt in (1, 2):  # tts_full.py: transient Azure errors — one retry fixes them
        try:
            ok, detail = synth(cfg, audio_path, ssml=ssml_text)
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        if ok:
            break
        if attempt == 1:
            time.sleep(2)
    if ok:
        return "ready", detail
    audio_path.unlink(missing_ok=True)  # never serve a half-written file
    return ("quota_reached" if limits.is_quota_error(detail) else "failed"), detail


def run_job(image, workdir, device, tts=True, on_stage=lambda stage: None, ocr=None,
            on_output=lambda key, value: None):
    """image -> dict of every stage's output. Raises JobError if a text stage fails.

    Writes into workdir: OCR markdown (+ the OCR's JSON), <stem>.norm.md,
    stitched/<stem>.stitched.{txt,ssml}, and audio.mp3 when stage 4 succeeds.

    `ocr` replaces the call to ocr_vl.run_image (same arguments and return);
    the Modal worker passes one that runs it in a killable child process
    (backend/ocr_proc.py). The original exception is the JobError's __cause__.

    `on_output(key, value)` is called as soon as each entry of the result's
    "stages" is ready ("ocr", "normalized", "math_spans", "speech"), so a
    caller can show the text before the audio is made.
    """
    import ocr_vl

    ocr = ocr or ocr_vl.run_image
    workdir = Path(workdir)
    ocr_dir, stitch_dir = workdir / "ocr", workdir / "stitched"
    timings = {}

    # --- stage 1: OCR ------------------------------------------------------
    on_stage("ocr")
    t = time.monotonic()
    try:
        text, md_path = ocr(image, ocr_dir, device)
    except Exception as e:
        raise JobError("ocr_failed", f"{type(e).__name__}: {e}") from e
    timings["ocr"] = round(time.monotonic() - t, 2)
    # run.py reads the markdown file the OCR saved; fall back to the result
    # object's text only if the save path was not reported
    md = Path(md_path) if md_path else None
    if md and md.exists():
        ocr_text = md.read_text(encoding="utf-8")
    else:
        md = ocr_dir / f"{Path(image).stem}.md"
        md.write_text(text, encoding="utf-8")
        ocr_text = text
    if not ocr_text.strip():
        raise JobError("no_text_found", "OCR returned no text")
    stages = {"ocr": {"text": ocr_text}}
    on_output("ocr", stages["ocr"])

    # --- stage 2: normalize ------------------------------------------------
    on_stage("normalize")
    norm_text = normalize.normalize_math(ocr_text)
    norm_path = md.with_suffix(".norm.md")
    norm_path.write_text(norm_text, encoding="utf-8")
    spans, korean = ocr_vl.analyze(norm_text)
    stages["normalized"] = {"text": norm_text}
    stages["math_spans"] = [
        {"source": s, "latex": s.strip("$").strip(), "display": s.startswith("$$")}
        for s in spans
    ]
    on_output("normalized", stages["normalized"])
    on_output("math_spans", stages["math_spans"])

    # --- stage 3: Korean math speech (plain, then SSML — run.py's order) ---
    on_stage("speech")
    t = time.monotonic()
    base = norm_path.name.removesuffix(".norm.md")
    txt_path = stitch_dir / f"{base}.stitched.txt"
    ssml_path = stitch_dir / f"{base}.stitched.ssml"
    for p in (txt_path, ssml_path):
        p.unlink(missing_ok=True)
    with ThreadPoolExecutor(2) as pool:  # both at once; see the module docstring
        plain = pool.submit(_speak, norm_path, stitch_dir, ssml=False)
        with_ssml = pool.submit(_speak, norm_path, stitch_dir, ssml=True)
        code, summary = plain.result()
        strict_ok = code == 0
        if strict_ok:
            ssml_code, ssml_summary = with_ssml.result()
            strict_ok = ssml_code == 0 and ssml_path.exists()
            summary += [f"(ssml) {s}" for s in ssml_summary]
        else:  # run.py stops here on a --strict failure: no SSML pass, no SSML output
            with_ssml.exception()  # wait for it; its result or error is discarded
    if not strict_ok and code != 0:
        ssml_path.unlink(missing_ok=True)
    timings["speech"] = round(time.monotonic() - t, 2)
    if not txt_path.exists():
        raise JobError("speech_stage_failed", "speak.js wrote no text output")
    spoken = txt_path.read_text(encoding="utf-8").strip()
    ssml = ssml_path.read_text(encoding="utf-8").strip() if ssml_path.exists() else None
    stages["speech"] = {
        "text": spoken,          # what the listener hears, as plain text
        "ssml": ssml,            # what was sent to Azure (None if not produced)
        "strict_ok": strict_ok,
        "summary": summary,
        "korean_present": korean,
    }
    on_output("speech", stages["speech"])

    # --- stage 4: Azure TTS ------------------------------------------------
    audio_path = workdir / AUDIO_NAME
    if not tts:
        audio_status, audio_detail = "not_requested", ""
    elif not strict_ok or not ssml:
        audio_status, audio_detail = "skipped", "speak.js --strict failed"
    else:
        on_stage("tts")
        t = time.monotonic()
        audio_status, audio_detail = _synthesize(ssml, audio_path)
        timings["tts"] = round(time.monotonic() - t, 2)

    return {
        "stages": stages,
        "audio": {
            "status": audio_status,
            "message": AUDIO_MESSAGES[audio_status],
            "_detail": audio_detail,     # server log only; stripped before returning
        },
        "timings_s": timings,
    }


def main():
    ap = argparse.ArgumentParser(description="Run the backend job on one image, locally.")
    ap.add_argument("image")
    ap.add_argument("--workdir", default="./runs/backend-job")
    ap.add_argument("--device", choices=["cpu", "gpu"])
    ap.add_argument("--skip-tts", action="store_true")
    a = ap.parse_args()
    import ocr_vl
    device = a.device or ocr_vl.auto_device()
    try:
        result = run_job(a.image, a.workdir, device, tts=not a.skip_tts,
                         on_stage=lambda s: print(f"[stage] {s}", file=sys.stderr))
    except JobError as e:
        sys.exit(f"job failed — {e}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
