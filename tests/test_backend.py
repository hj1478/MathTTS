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


# --- rate-limit identity ------------------------------------------------------
@pytest.mark.parametrize("ip,key", [
    ("1.2.3.4", "1.2.3.4"),
    ("2001:db8:1:2:aaaa::1", "2001:db8:1:2::/64"),
    ("2001:db8:1:2:ffff:ffff:ffff:ffff", "2001:db8:1:2::/64"),  # same /64, same budget
    ("::ffff:1.2.3.4", "1.2.3.4"),                               # IPv4-mapped
    ("unknown", "unknown"),
])
def test_client_key_counts_ipv6_by_its_64(ip, key):
    assert limits.client_key(ip) == key


def test_ipv6_slot_keys_still_parse():
    key = limits.slot_keys(limits.client_key("2001:db8::1"), 7300, 2)[0]
    assert limits.slot_bucket("rl:" + key) == 2


# --- the web API (backend/modal_app.py web()), against an in-memory Dict --------
# Needs FastAPI, which only the web image installs; skipped without it.
class _Aio:
    """A modal method stand-in: callable, and awaitable as .aio(...)."""

    def __init__(self, f):
        self.f = f

    def __call__(self, *a, **k):
        return self.f(*a, **k)

    async def aio(self, *a, **k):
        return self.f(*a, **k)


class _FakeDict:
    def __init__(self):
        self.d = {}
        self.get = _Aio(lambda k, default=None: self.d.get(k, default))
        self.put = _Aio(self._put)
        self.contains = _Aio(lambda k: k in self.d)
        self.pop = _Aio(lambda k, default=None: self.d.pop(k, default))
        self.keys = lambda: list(self.d)

    def _put(self, k, v, skip_if_exists=False):
        if skip_if_exists and k in self.d:
            return False
        self.d[k] = v
        return True


class _FakeWorker:
    spawn_error = None

    def __init__(self):
        def spawn(*a):
            if _FakeWorker.spawn_error:
                raise _FakeWorker.spawn_error
            return type("Call", (), {"object_id": "fc-1"})()
        self.run = type("M", (), {"spawn": _Aio(spawn)})()
        self.warm = self.run


@pytest.fixture
def api(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend import modal_app
    store = _FakeDict()
    monkeypatch.setattr(modal_app, "store", store)
    monkeypatch.setattr(modal_app, "Worker", _FakeWorker)
    monkeypatch.setattr(_FakeWorker, "spawn_error", None)
    client = TestClient(modal_app.web.local(), raise_server_exceptions=False)
    return client, store, modal_app


def _post_image(client):
    return client.post("/jobs", files={"image": ("q.png", _png(), "image/png")})


def test_spawn_failure_is_503_and_frees_the_slot(api):
    client, store, _ = api
    _FakeWorker.spawn_error = RuntimeError("modal down")
    r = _post_image(client)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "service_unavailable"
    assert not [k for k in store.d if k.startswith("rl:")]          # slot given back
    (rec,) = [v for k, v in store.d.items() if k.startswith("job:")]
    assert rec["status"] == "failed" and rec["error"]["code"] == "internal_error"


def test_submit_claims_a_slot_and_records_the_call(api):
    client, store, _ = api
    r = _post_image(client)
    assert r.status_code == 202
    job_id = r.json()["id"]
    assert store.d[f"call:{job_id}"]["id"] == "fc-1"
    assert len([k for k in store.d if k.startswith("rl:")]) == 1


def test_unknown_path_and_wrong_method_use_the_error_body(api):
    client, _, _ = api
    r = client.get("/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.get("/jobs")
    assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"


def test_unhandled_error_is_500_with_body_and_cors(api, monkeypatch):
    client, store, _ = api

    def broken(*a, **k):
        raise RuntimeError("dict unavailable")
    monkeypatch.setattr(store, "get", _Aio(broken))
    r = client.get("/jobs/abc123", headers={"Origin": "http://localhost:8081"})
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert r.headers["access-control-allow-origin"] == "http://localhost:8081"


def _job(store, job_id, status, quiet_s, call=True):
    import time
    now = time.time()
    store.d[f"job:{job_id}"] = {"status": status, "stage": None,
                                "created": now - quiet_s, "updated": now - quiet_s}
    if call:
        store.d[f"call:{job_id}"] = {"id": "fc-1", "created": now - quiet_s}


def _call_outcome(monkeypatch, modal_app, exc):
    """FunctionCall.from_id(...).get.aio(timeout=0) raises exc (None: returns)."""
    def get(timeout=None):
        if exc:
            raise exc
    fc = type("FC", (), {"get": _Aio(get)})()
    monkeypatch.setattr(modal_app.modal.FunctionCall, "from_id", staticmethod(lambda _id: fc))


def test_transient_modal_error_does_not_fail_a_live_job(api, monkeypatch):
    from grpclib import GRPCError, Status
    client, store, modal_app = api
    _job(store, "a1", "running", 30)
    _call_outcome(monkeypatch, modal_app, GRPCError(Status.UNAVAILABLE, "blip"))
    assert client.get("/jobs/a1").json()["status"] == "running"
    _call_outcome(monkeypatch, modal_app, TimeoutError())          # no output yet
    assert client.get("/jobs/a1").json()["status"] == "running"


def test_crashed_call_is_worker_lost(api, monkeypatch):
    from modal.exception import InternalFailure
    client, store, modal_app = api
    _job(store, "a2", "running", 30)
    _call_outcome(monkeypatch, modal_app, InternalFailure("container crashed"))
    body = client.get("/jobs/a2").json()
    assert body["status"] == "failed" and body["error"]["code"] == "worker_lost"


def test_queued_job_without_a_call_is_lost_after_a_minute(api, monkeypatch):
    client, store, modal_app = api
    _job(store, "a3", "queued", 30, call=False)                    # spawn may be in flight
    assert client.get("/jobs/a3").json()["status"] == "queued"
    _job(store, "a4", "queued", modal_app.SPAWN_LOST_AFTER_S + 5, call=False)
    assert client.get("/jobs/a4").json()["error"]["code"] == "worker_lost"


def test_running_past_the_job_timeout_is_lost_without_asking_modal(api, monkeypatch):
    from grpclib import GRPCError, Status
    client, store, modal_app = api
    _job(store, "a5", "running", modal_app.RUNNING_LOST_AFTER_S + 5)
    _call_outcome(monkeypatch, modal_app, GRPCError(Status.UNAVAILABLE, "unreachable"))
    assert client.get("/jobs/a5").json()["error"]["code"] == "worker_lost"


def test_ipv6_clients_share_a_budget_per_64(api, monkeypatch):
    client, store, modal_app = api
    monkeypatch.setattr(modal_app, "RATE_LIMIT_PER_HOUR", 1)
    from fastapi.testclient import TestClient
    app = modal_app.web.local()  # the limit is read when the app is built
    first = TestClient(app, client=("2001:db8:1:2::1", 1000))
    second = TestClient(app, client=("2001:db8:1:2::99", 1000))
    other = TestClient(app, client=("2001:db8:1:3::1", 1000))
    assert _post_image(first).status_code == 202
    assert _post_image(second).status_code == 429
    assert _post_image(other).status_code == 202                   # another /64


def test_cleanup_dates_audio_by_its_job_without_downloading_it(monkeypatch, tmp_path):
    import time

    from backend import modal_app
    store = _FakeDict()
    monkeypatch.setattr(modal_app, "store", store)
    monkeypatch.setattr(modal_app, "JOBS_DIR", tmp_path / "none")
    old = time.time() - modal_app.RETENTION_S - 60
    new = time.time()
    store.d.update({"job:old": {"created": old}, "audio:old": {"data": b"x", "created": old},
                    "job:new": {"created": new}, "audio:new": {"data": b"x", "created": new},
                    "audio:orphan": {"data": b"x", "created": new},
                    "call:old": {"created": old}})
    read = []
    get = store.get

    def tracking_get(k, default=None):
        read.append(k)
        return get(k, default)
    monkeypatch.setattr(store, "get", tracking_get)
    modal_app.cleanup.local()
    assert set(store.d) == {"job:new", "audio:new"}
    assert not [k for k in read if k.startswith("audio:")]
