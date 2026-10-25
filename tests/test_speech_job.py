"""backend/job.py's speak.js call: a hang is a speech-stage failure, not internal_error."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import job  # noqa: E402


def test_speak_timeout_is_speech_stage_failed(tmp_path, monkeypatch):
    def hang(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
    monkeypatch.setattr(job.subprocess, "run", hang)
    with pytest.raises(job.JobError) as e:
        job._speak(tmp_path / "q.norm.md", tmp_path, ssml=False)
    assert e.value.code == "speech_stage_failed"
    assert "timed out" in e.value.detail


def test_speak_uses_only_the_stitched_combo_and_utf8(tmp_path, monkeypatch):
    seen = {}

    def run(cmd, **kw):
        seen.update(cmd=cmd, **kw)
        return subprocess.CompletedProcess(cmd, 0, stdout="SUMMARY: 1 span(s), ok: 1\n", stderr="")
    monkeypatch.setattr(job.subprocess, "run", run)
    assert job._speak(tmp_path / "q.norm.md", tmp_path, ssml=True) == (
        0, ["SUMMARY: 1 span(s), ok: 1"])
    assert seen["cmd"][seen["cmd"].index("--combos") + 1] == "clearspeak/default"
    assert "--ssml" in seen["cmd"] and seen["encoding"] == "utf-8"


def test_speak_real_node_run(tmp_path):
    """The real speak.js with job.py's arguments (needs node + sre-probe/node_modules)."""
    norm = tmp_path / "q.norm.md"
    norm.write_text("문제 $-2<x<3$ 일 때", encoding="utf-8")
    code, summary = job._speak(norm, tmp_path / "out", ssml=False)
    assert code == 0 and summary == ["SUMMARY: 1 span(s), ok: 1"]
    text = (tmp_path / "out" / "q.stitched.txt").read_text(encoding="utf-8")
    assert "마이너스 2 는 x 보다 작다" in text
