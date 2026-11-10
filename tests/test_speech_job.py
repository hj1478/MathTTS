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
    assert "--casual" in seen["cmd"]


def test_speak_real_node_run(tmp_path):
    """The real speak.js with job.py's arguments (needs node + sre-probe/node_modules)."""
    norm = tmp_path / "q.norm.md"
    norm.write_text("문제 $-2<x<3$ 일 때", encoding="utf-8")
    code, summary = job._speak(norm, tmp_path / "out", ssml=False)
    assert code == 0 and summary == ["SUMMARY: 1 span(s), ok: 1"]
    text = (tmp_path / "out" / "q.stitched.txt").read_text(encoding="utf-8")
    assert "마이너스 2 는 x 보다 작다" in text


def test_formal_reading_leaves_casual_out(tmp_path, monkeypatch):
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    monkeypatch.setattr(job.subprocess, "run", run)
    job._speak(tmp_path / "q.norm.md", tmp_path, ssml=False, casual=False)
    assert "--casual" not in seen[0] and "--strict" in seen[0]


def test_single_problem_has_both_readings(tmp_path):
    """Real speak.js: the two readings differ, and each has its SSML."""
    norm = tmp_path / "q.norm.md"
    norm.write_text("$x \\ge 3$ 일 때 $\\frac{x+1}{x-1}$ 의 값", encoding="utf-8")
    spoken, formal = job._both_readings(norm, tmp_path / "stitched", tmp_path / "stitched_formal")
    entry = job._speech_entry(spoken, formal)
    assert entry["strict_ok"] and entry["formal"]["strict_ok"]
    assert entry["text"] != entry["formal"]["text"]
    assert "3 이상" in entry["text"]
    assert entry["ssml"] and entry["formal"]["ssml"]
