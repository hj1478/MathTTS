"""Per-stage status for GET /jobs/{id}, derived from which outputs a job record holds.

Pure, with no Modal or FastAPI import, so tests/test_backend.py can check it
locally. backend/modal_app.py is the only caller.

The worker writes each entry of "stages" as soon as job.run_job produces it, so
which outputs are present says how far the job got. The stages run in order,
one at a time.
"""

STAGES = ("ocr", "normalize", "speech", "tts")
# the "stages" entry each text stage fills; tts fills "audio", which only the
# finished result has
_OUTPUT = {"ocr": "ocr", "normalize": "normalized", "speech": "speech"}
_AUDIO = {"ready": "done", "skipped": "skipped", "not_requested": "skipped",
          "quota_reached": "failed", "failed": "failed"}


def _tts_skipped(stages):
    # job.run_job does not call Azure when speak.js --strict failed
    speech = stages.get("speech")
    return speech is not None and not (speech.get("strict_ok") and speech.get("ssml"))


def stage_status(status, stages, audio_status=None):
    """Job status + the stage outputs so far -> {stage: state}, in pipeline order.

    state is one of pending, running, done, skipped, failed:
      queued   every stage pending
      running  stages with output done; the first one without is running
      done     text stages done; tts from audio.status (ready -> done,
               skipped -> skipped, quota_reached / failed -> failed)
      failed   stages with output done; the first one without failed (the job
               failed there); the rest skipped
    """
    stages = stages or {}
    if status == "done":
        out = {name: "done" for name in _OUTPUT}
        out["tts"] = _AUDIO.get(audio_status, "failed")
        return out
    out, reached = {}, False
    for name in STAGES:
        if name == "tts" and _tts_skipped(stages):
            out[name] = "skipped"
        elif name in _OUTPUT and _OUTPUT[name] in stages:
            out[name] = "done"
        elif status == "queued" or reached:
            out[name] = "pending" if status in ("queued", "running") else "skipped"
        else:
            out[name] = "running" if status == "running" else "failed"
            reached = True
    return out
