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
    of one after the other, each with only the clearspeak combo the stitched
    output uses. They write different files. When the plain pass fails
    --strict, the SSML pass's output is discarded, so the result is the same
    as run.py's, where the SSML pass would never have run.
  - A stage-4 failure does not fail the job. The text stages are the result;
    audio carries its own status, and an exhausted quota is reported as
    "quota_reached" rather than as an error.
  - Stage 3 also makes a second, "formal" reading: speak.js without --casual,
    math spelled out the way SRE says it. A client lets the listener switch
    between the two. The casual reading is the job's result; the formal one
    is extra, and a failure in it only leaves the formal reading out. Stage 4
    does not send it to Azure: its MP3 is made only when a listener asks for
    it (formal_audio below, called by POST /jobs/{id}/formal-audio), so a job
    still costs one Azure call per problem.
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
from backend import limits, problems  # noqa: E402

SPEAK_JS = ROOT / "sre-probe" / "speak.js"
VOICE = "ko-KR-SunHiNeural"      # run.py's default
AUDIO_NAME = "audio.mp3"
AUDIO_MEDIA_TYPE = "audio/mpeg"
SPEAK_TIMEOUT_S = 120
# A page of numbered problems: how many problems run speak.js at once (two node
# processes each), and how many Azure calls run at once.
PARALLEL_PROBLEMS = 4
PARALLEL_TTS = 3

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


def _speak(norm_path, out_dir, ssml, casual=True):
    """sre-probe/speak.js as run.py calls it (--strict, --voice, --write), plus
    --casual: math is read as a person says it ("A 1", "x 마이너스 1 분의 x 플러스
    1", "3 이상"), not spelled out (sre-probe/casual.js). casual=False leaves
    --casual out, for the formal reading.

    Only the clearspeak combo: the stitched output uses the first combo, and
    the default second one (mathspeak) only fills speak.js's console table.

    Returns (exit_code, SUMMARY lines). Exit 2 is the --strict failure: the
    files were still written, but something stitched as salvage/placeholder.
    """
    cmd = ["node", str(SPEAK_JS), "--strict", "--combos", "clearspeak/default",
           "--voice", VOICE, "--write", str(out_dir)]
    if casual:
        cmd.insert(3, "--casual")
    if ssml:
        cmd.append("--ssml")
    cmd.append(str(norm_path))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              timeout=SPEAK_TIMEOUT_S)
    except subprocess.TimeoutExpired as e:
        raise JobError("speech_stage_failed", f"speak.js timed out after {SPEAK_TIMEOUT_S}s") from e
    if proc.returncode not in (0, 2):
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or [""]
        raise JobError("speech_stage_failed", tail[0])
    summary = [ln.strip() for ln in proc.stdout.splitlines() if ln.startswith("SUMMARY:")]
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


def _speech(norm_path, stitch_dir, casual=True):
    """Stage 3 on one .norm.md -> (spoken text, ssml or None, strict_ok, SUMMARY lines)."""
    base = norm_path.name.removesuffix(".norm.md")
    txt_path = stitch_dir / f"{base}.stitched.txt"
    ssml_path = stitch_dir / f"{base}.stitched.ssml"
    for p in (txt_path, ssml_path):
        p.unlink(missing_ok=True)
    with ThreadPoolExecutor(2) as pool:  # both at once; see the module docstring
        style = {} if casual else {"casual": False}
        plain = pool.submit(_speak, norm_path, stitch_dir, ssml=False, **style)
        with_ssml = pool.submit(_speak, norm_path, stitch_dir, ssml=True, **style)
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
    if not txt_path.exists():
        raise JobError("speech_stage_failed", "speak.js wrote no text output")
    spoken = txt_path.read_text(encoding="utf-8").strip()
    ssml = ssml_path.read_text(encoding="utf-8").strip() if ssml_path.exists() else None
    return spoken, ssml, strict_ok, summary


def _formal_speech(norm_path, formal_dir):
    """The formal reading of one .norm.md, as a "formal" entry for the speech
    dict, or None. It is an extra: whatever goes wrong here, the job goes on
    with the casual reading alone."""
    try:
        text, ssml, strict_ok, summary = _speech(norm_path, formal_dir, casual=False)
    except Exception as e:
        print(f"[speech] no formal reading for {norm_path.name}: {type(e).__name__}: {e}",
              file=sys.stderr)
        return None
    if not text:
        return None
    return {"text": text, "ssml": ssml, "strict_ok": strict_ok, "summary": summary}


def _both_readings(norm_path, stitch_dir, formal_dir):
    """Stage 3 twice at the same time -> (_speech's casual result, formal entry
    or None). Raises what the casual _speech raises."""
    with ThreadPoolExecutor(1) as pool:
        formal = pool.submit(_formal_speech, norm_path, formal_dir)
        return _speech(norm_path, stitch_dir), formal.result()


def _speech_entry(spoken, formal):
    text, ssml, strict_ok, summary = spoken
    entry = {"text": text, "ssml": ssml, "strict_ok": strict_ok, "summary": summary}
    if formal:
        entry["formal"] = formal
    return entry


def problem_audio_name(i):
    """The MP3 of problem i (1-based) in the job folder."""
    return f"audio_{i}.mp3"


def formal_audio(ssml):
    """The formal reading's MP3, on request -> (status, detail, MP3 bytes or None).
    One Azure call (two if the first fails), as stage 4 makes for the casual one."""
    import tempfile
    if not ssml:
        return "skipped", "no formal SSML", None
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / AUDIO_NAME
        status, detail = _synthesize(ssml, path)
        return status, detail, path.read_bytes() if status == "ready" else None


def _no_audio(crashed):
    """Audio status of a problem that is not sent to Azure: speak.js crashed on
    it ("failed"), or --strict found a formula it could not read ("skipped")."""
    if crashed:
        return "failed", "speech_stage_failed"
    return "skipped", "speak.js --strict failed"


def _synthesize_problems(items, workdir, crashed=None):
    """Stage 4 per problem -> [(audio status, detail)], in order. A problem whose
    speech failed --strict is skipped, as a whole page would be."""
    crashed = crashed or [False] * len(items)
    def one(i, p):
        sp = p["speech"]
        if not sp["strict_ok"] or not sp["ssml"]:
            return _no_audio(crashed[i - 1])
        return _synthesize(sp["ssml"], Path(workdir) / problem_audio_name(i))
    with ThreadPoolExecutor(PARALLEL_TTS) as pool:
        return list(pool.map(one, range(1, len(items) + 1), items))


# When not every problem has audio, the page's status is the most telling one.
_PAGE_STATUS_ORDER = ("quota_reached", "failed", "skipped")


def _whole_page(problem_audio, workdir, audio_path):
    """The whole page's audio from its problems': their MP3s back to back when
    every problem has one (MP3 frames concatenate), else the most telling status."""
    statuses = [st for st, _ in problem_audio]
    if all(st == "ready" for st in statuses):
        with open(audio_path, "wb") as out:
            for i in range(1, len(statuses) + 1):
                out.write((Path(workdir) / problem_audio_name(i)).read_bytes())
        return "ready", f"{len(statuses)} problems"
    status = next(st for st in _PAGE_STATUS_ORDER if st in statuses)
    return status, "; ".join(f"{i}: {st} {d}" for i, (st, d) in enumerate(problem_audio, 1)
                             if st != "ready")


def run_job(image, workdir, device, tts=True, on_stage=lambda stage: None, ocr=None,
            on_output=lambda key, value: None):
    """image -> dict of every stage's output. Raises JobError if a text stage fails.

    Writes into workdir: OCR markdown (+ the OCR's JSON), <stem>.norm.md,
    stitched/<stem>.stitched.{txt,ssml}, and audio.mp3 when stage 4 succeeds
    (stitched_formal/ for the formal reading).

    `ocr` replaces the call to ocr_vl.run_image (same arguments and return);
    the Modal worker passes one that runs it in a killable child process
    (backend/ocr_proc.py). The original exception is the JobError's __cause__.

    `on_output(key, value)` is called as soon as each entry of the result's
    "stages" is ready ("ocr", "normalized", "math_spans", "problems",
    "speech"), so a caller can show the text before the audio is made.

    A page with two or more numbered problems also gets stages["problems"]
    (each with its boxes, text and speech) and audio["problems"] (one status
    per problem; problem i's MP3 is problem_audio_name(i)). The page's own
    audio.mp3 is then their MP3s back to back.

    The formal reading, where it could be made, is speech["formal"] (text,
    ssml, strict_ok, summary), on the page and on each problem. It has no
    audio here: see formal_audio.
    """
    import ocr_vl

    ocr = ocr or ocr_vl.run_image
    workdir = Path(workdir)
    ocr_dir, stitch_dir = workdir / "ocr", workdir / "stitched"
    formal_dir = workdir / "stitched_formal"
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
    # A page with several numbered problems is read one problem at a time
    # (backend/problems.py), each with its own speech, guard and audio, so the
    # client can play and highlight them one by one.
    parts = problems.split_dir(ocr_dir)
    on_stage("speech")
    t = time.monotonic()
    if parts:
        for i, part in enumerate(parts, 1):
            part["normalized"] = normalize.normalize_math(part["text"])
            part["norm_path"] = ocr_dir / f"problem{i}.norm.md"
            part["norm_path"].write_text(part["normalized"], encoding="utf-8")
        def speak_part(part):
            # one problem speak.js can't read loses its audio, not the whole page
            try:
                return _both_readings(part["norm_path"], stitch_dir, formal_dir), None
            except JobError as e:
                return (("", None, False, [f"speech_stage_failed: {e.detail}"]), None), e
        with ThreadPoolExecutor(PARALLEL_PROBLEMS) as pool:
            results = list(pool.map(speak_part, parts))
        errors = [e for _, e in results if e is not None]
        if len(errors) == len(parts):
            raise errors[0]  # nothing was read: the job failed, as for a single page
        spoken_parts = [r for r, _ in results]
        crashed = [e is not None for _, e in results]
        stages["problems"] = [{
            "label": part["label"],
            "boxes": part["boxes"],
            "normalized": {"text": part["normalized"]},
            "speech": _speech_entry(spoken, formal),
        } for part, (spoken, formal) in zip(parts, spoken_parts)]
        stages["speech"] = {
            "text": "\n\n".join(p["speech"]["text"] for p in stages["problems"]),
            "ssml": None,  # one per problem, in stages.problems
            "strict_ok": all(p["speech"]["strict_ok"] for p in stages["problems"]),
            "summary": [f"[{p['label']}] {line}" for p in stages["problems"]
                        for line in p["speech"]["summary"]],
            "korean_present": korean,
        }
        formals = [p["speech"].get("formal") for p in stages["problems"]]
        if all(formals):
            stages["speech"]["formal"] = {
                "text": "\n\n".join(f["text"] for f in formals),
                "ssml": None,
                "strict_ok": all(f["strict_ok"] for f in formals),
                "summary": [],
            }
        on_output("problems", stages["problems"])
    else:
        # text: what the listener hears, as plain text; ssml: what is sent to
        # Azure (None if not produced)
        stages["speech"] = _speech_entry(*_both_readings(norm_path, stitch_dir, formal_dir))
        stages["speech"]["korean_present"] = korean
    timings["speech"] = round(time.monotonic() - t, 2)
    on_output("speech", stages["speech"])

    # --- stage 4: Azure TTS ------------------------------------------------
    audio_path = workdir / AUDIO_NAME
    problem_audio = None
    if not tts:
        audio_status, audio_detail = "not_requested", ""
    elif parts and not any(p["speech"]["strict_ok"] and p["speech"]["ssml"]
                           for p in stages["problems"]):
        # no problem can be read aloud: stage 4 does not run (progress shows it skipped)
        problem_audio = [_no_audio(c) for c in crashed]
        audio_status, audio_detail = _whole_page(problem_audio, workdir, audio_path)
    elif parts:
        on_stage("tts")
        t = time.monotonic()
        problem_audio = _synthesize_problems(stages["problems"], workdir, crashed)
        audio_status, audio_detail = _whole_page(problem_audio, workdir, audio_path)
        timings["tts"] = round(time.monotonic() - t, 2)
    elif not stages["speech"]["strict_ok"] or not stages["speech"]["ssml"]:
        audio_status, audio_detail = "skipped", "speak.js --strict failed"
    else:
        on_stage("tts")
        t = time.monotonic()
        audio_status, audio_detail = _synthesize(stages["speech"]["ssml"], audio_path)
        timings["tts"] = round(time.monotonic() - t, 2)

    audio = {
        "status": audio_status,
        "message": AUDIO_MESSAGES[audio_status],
        "_detail": audio_detail,     # server log only; stripped before returning
    }
    if problem_audio is not None:
        audio["problems"] = [{"status": st, "message": AUDIO_MESSAGES[st], "_detail": d}
                             for st, d in problem_audio]

    return {"stages": stages, "audio": audio, "timings_s": timings}


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
