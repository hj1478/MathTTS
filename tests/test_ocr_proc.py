"""backend/ocr_proc.py: the hard kill, against a fake child (tests/fake_ocr_child.py).

No paddle, no GPU, no Modal. The point is the guarantee the worker relies on:
a call that hangs is cut off at its timeout and leaves NO process behind,
even when the child ignores SIGTERM and has a grandchild of its own.
"""
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.ocr_proc import OcrFailed, OcrProcess, OcrTimeout  # noqa: E402

FAKE = "tests.fake_ocr_child"


def _group_gone(pgid, within=5.0):
    """True once no process is left in the child's process group."""
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def _start(mode, timeout=10):
    ocr = OcrProcess(device=mode, child_module=FAKE)
    ocr.start(timeout=timeout)
    return ocr


def test_ok_call_returns_and_close_leaves_nothing():
    ocr = _start("ok")
    pid = ocr.pid
    assert ocr.run("/tmp/a.png", "/tmp/out", timeout=5) == ("text of a.png", "/tmp/out/x.md")
    ocr.close()
    assert not ocr.alive()
    assert _group_gone(pid)


def test_hung_call_is_killed_at_the_cutoff():
    ocr = _start("hang")
    pid = ocr.pid
    t = time.monotonic()
    with pytest.raises(OcrTimeout):
        ocr.run("/tmp/a.png", "/tmp/out", timeout=2)
    elapsed = time.monotonic() - t
    assert 2 <= elapsed < 4, elapsed           # the cutoff, plus the kill
    assert not ocr.alive()                     # SIGKILL, though it ignores SIGTERM
    assert _group_gone(pid)                    # and its grandchild went with it


def test_hung_model_load_is_killed():
    ocr = OcrProcess(device="hang_load", child_module=FAKE)
    t = time.monotonic()
    with pytest.raises(OcrTimeout):
        ocr.start(timeout=2)
    assert time.monotonic() - t < 4
    assert not ocr.alive()
    assert _group_gone(ocr.pid)


def test_ocr_error_is_reported_and_child_survives():
    ocr = _start("error")
    with pytest.raises(OcrFailed, match="fake OCR failure"):
        ocr.run("/tmp/a.png", "/tmp/out", timeout=5)
    assert ocr.alive()                         # a normal error is not a reason to kill
    ocr.close()
    assert not ocr.alive()


def test_crashed_child_is_reported():
    ocr = _start("crash")
    with pytest.raises(OcrFailed, match="died"):
        ocr.run("/tmp/a.png", "/tmp/out", timeout=5)
    assert not ocr.alive()
    with pytest.raises(OcrFailed, match="not running"):
        ocr.run("/tmp/a.png", "/tmp/out", timeout=5)
