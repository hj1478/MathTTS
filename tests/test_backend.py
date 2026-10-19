"""backend/limits.py: upload checks, quota detection, rate-limit slots.
backend/progress.py: per-stage status for GET /jobs/{id}.

No Modal or network needed; the web API in backend/modal_app.py is the caller.
"""
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import limits, progress  # noqa: E402

PIL = pytest.importorskip("PIL.Image")


def _png(size=(8, 8)):
    buf = io.BytesIO()
    PIL.new("RGB", size, "white").save(buf, "PNG")
    return buf.getvalue()


def test_sniff_by_bytes():
    assert limits.sniff_image(_png()) == ".png"
    assert limits.sniff_image(b"\xff\xd8\xff\xe0" + b"\0" * 20) == ".jpg"
    assert limits.sniff_image(b"RIFF\0\0\0\0WEBPVP8 ") == ".webp"
    assert limits.sniff_image(b"%PDF-1.7") is None
    assert limits.sniff_image(b"<svg xmlns=") is None


def test_heic_is_named_not_generic():
    heic = b"\0\0\0\x18ftypheic" + b"\0" * 16
    assert limits.sniff_image(heic) is None
    assert limits.is_heic(heic)
    assert not limits.is_heic(_png())


def test_check_decodes():
    assert limits.check_decodes(_png()) is None
    assert limits.check_decodes(_png()[:30]) is not None          # truncated
    assert "too many pixels" in limits.check_decodes(_png((8000, 6000)))


@pytest.mark.parametrize("detail,quota", [
    ("canceled: CancellationReason.Error; WebSocket upgrade failed: Too many requests (429)", True),
    ("canceled: ...; Quota exceeded", True),
    ("canceled: CancellationReason.Error; Connection failed (no connection to the remote host)", False),
    ("", False),
    (None, False),
])
def test_quota_detection(detail, quota):
    assert limits.is_quota_error(detail) is quota


def test_slots_cap_per_window():
    taken = set()

    def put_if_absent(key):
        if key in taken:
            return False
        taken.add(key)
        return True

    now = 7200.5
    results = [limits.take_slot(put_if_absent, "1.2.3.4", now, limit=3) for _ in range(4)]
    assert [ok for ok, _ in results] == [True, True, True, False]
    assert 0 < results[-1][1] <= 3600
    # another IP and the next window are independent
    assert limits.take_slot(put_if_absent, "5.6.7.8", now, limit=3)[0]
    assert limits.take_slot(put_if_absent, "1.2.3.4", now + 3600, limit=3)[0]


def test_slot_bucket_roundtrip():
    key = limits.slot_keys("2001:db8::1", 7300, 2)[1]
    assert limits.slot_bucket(key) == 2
    assert limits.slot_bucket("rl:" + key) == 2
    assert limits.slot_bucket("job:abc") is None


def test_warmup_slots_are_separate_from_job_slots():
    # POST /warmup claims slots for "warm:<ip>", so it never uses up a job slot
    key = limits.slot_keys("warm:2001:db8::1", 7300, 2)[0]
    assert limits.slot_bucket("rl:" + key) == 2
    assert key not in limits.slot_keys("2001:db8::1", 7300, 2)


OCR = {"ocr": {"text": "x"}}
TEXT = {**OCR, "normalized": {"text": "x"}, "math_spans": []}
SPOKEN = {**TEXT, "speech": {"text": "엑스", "ssml": "<speak/>", "strict_ok": True}}


@pytest.mark.parametrize("status,stages,audio,expected", [
    ("queued", {}, None, "pending pending pending pending"),
    ("running", {}, None, "running pending pending pending"),
    ("running", OCR, None, "done running pending pending"),
    ("running", TEXT, None, "done done running pending"),
    ("running", SPOKEN, None, "done done done running"),
    # strict failure: Azure is not called, so tts is skipped as soon as speech is known
    ("running", {**TEXT, "speech": {"text": "?", "ssml": None, "strict_ok": False}}, None,
     "done done done skipped"),
    ("done", SPOKEN, "ready", "done done done done"),
    ("done", SPOKEN, "skipped", "done done done skipped"),
    ("done", SPOKEN, "quota_reached", "done done done failed"),
    ("failed", {}, None, "failed skipped skipped skipped"),
    ("failed", TEXT, None, "done done failed skipped"),
    ("failed", SPOKEN, None, "done done done failed"),     # worker lost during tts
])
def test_stage_status(status, stages, audio, expected):
    got = progress.stage_status(status, stages, audio)
    assert list(got) == list(progress.STAGES)
    assert " ".join(got.values()) == expected


# --- job.run_job stage 3: plain and SSML speak.js passes run at the same time ---
def _fake_speak(plain_code, ssml_raises=False):
    """Stands in for job._speak: writes the file speak.js would, returns its exit code."""
    from backend import job

    def speak(norm_path, out_dir, ssml):
        out_dir.mkdir(parents=True, exist_ok=True)
        base = norm_path.name.removesuffix(".norm.md")
        if ssml:
            if ssml_raises:
                raise job.JobError("speech_stage_failed", "boom")
            (out_dir / f"{base}.stitched.ssml").write_text("<speak/>", encoding="utf-8")
            return 0, ["SUMMARY: ssml"]
        (out_dir / f"{base}.stitched.txt").write_text("엑스 더하기 일", encoding="utf-8")
        return plain_code, ["SUMMARY: plain"]
    return speak


def _run(tmp_path, monkeypatch, speak):
    from backend import job
    monkeypatch.setattr(job, "_speak", speak)
    image = tmp_path / "q.png"
    image.write_bytes(b"")

    def ocr(img, out_dir, device):
        out_dir.mkdir(parents=True, exist_ok=True)
        return "문제 $x+1$", None
    return job.run_job(image, tmp_path / "work", "gpu", tts=False, ocr=ocr)


def test_speech_both_passes_ok(tmp_path, monkeypatch):
    sp = _run(tmp_path, monkeypatch, _fake_speak(0))["stages"]["speech"]
    assert sp["strict_ok"] and sp["ssml"] == "<speak/>"
    assert sp["summary"] == ["SUMMARY: plain", "(ssml) SUMMARY: ssml"]


@pytest.mark.parametrize("ssml_raises", [False, True])
def test_speech_strict_failure_discards_ssml_pass(tmp_path, monkeypatch, ssml_raises):
    # as in run.py, where the SSML pass never runs after a --strict failure
    r = _run(tmp_path, monkeypatch, _fake_speak(2, ssml_raises))
    sp = r["stages"]["speech"]
    assert not sp["strict_ok"] and sp["ssml"] is None
    assert sp["summary"] == ["SUMMARY: plain"]
    assert not list((tmp_path / "work" / "stitched").glob("*.ssml"))
