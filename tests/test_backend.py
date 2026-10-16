"""backend/limits.py: upload checks, quota detection, rate-limit slots.

No Modal or network needed; the web API in backend/modal_app.py is the caller.
"""
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import limits  # noqa: E402

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
