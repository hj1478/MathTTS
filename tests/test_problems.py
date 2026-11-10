"""backend/problems.py: splitting a page into numbered problems with their boxes.
backend/job.py: per-problem audio and the page audio built from it.
backend/progress.py: the tts stage on a page of problems.
"""
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import job, problems, progress  # noqa: E402

KMA = ROOT / "output_kma"


def block(label, bbox, text, order):
    return {"block_label": label, "block_bbox": bbox, "block_content": text, "block_order": order}


def page(*blocks, w=1000, h=2000):
    return {"width": w, "height": h, "parsing_res_list": list(blocks)}


@pytest.mark.parametrize("text, n", [
    ("1. 다음 수", 1), ("12) 계산", 12), ("[3] 다음", 3), ("문제 4 다음", 4), ("5번 다음", 5),
    ("1.23은 유한소수", None), ("1.5배", None), ("① 정수", None), ("(1) 소문항", None), ("다음", None),
])
def test_number_of(text, n):
    assert problems.number_of(text) == n


def test_split_basic_and_skips_page_furniture():
    res = page(
        block("doc_title", [0, 0, 1000, 100], "수학 평가", 1),
        block("text", [100, 200, 500, 300], "1. 첫 문제", 2),
        block("display_formula", [100, 300, 500, 400], "$$x+1$$", 3),
        block("text", [100, 500, 500, 600], "2. 둘째 문제", 4),
        block("text", [100, 600, 500, 700], "", 5),  # empty: no box
        block("footer", [0, 1900, 1000, 2000], "주최", None),
    )
    got = problems.split(res)
    assert [p["label"] for p in got] == ["1", "2"]
    assert got[0]["boxes"] == [[0.1, 0.1, 0.5, 0.2]]
    assert got[0]["text"] == "1. 첫 문제\n\n$$x+1$$"
    assert got[1]["boxes"] == [[0.1, 0.25, 0.5, 0.3]]


def test_one_problem_is_not_split():
    assert problems.split(page(block("text", [0, 0, 10, 10], "24. 문제", 1))) == []
    assert problems.split(page(block("text", [0, 0, 10, 10], "다음을 계산하시오", 1))) == []


def test_numbers_must_go_up():
    # "1." and "2." inside problem 28 are its sub-items, not new problems
    res = page(
        block("text", [0, 0, 400, 100], "27. 가", 1),
        block("text", [0, 100, 400, 200], "28. 나", 2),
        block("text", [0, 200, 400, 300], "1. 설비별 시간", 3),
        block("text", [0, 300, 400, 400], "2. 작업 간격", 4),
    )
    got = problems.split(res)
    assert [p["label"] for p in got] == ["27", "28"]
    assert "2. 작업 간격" in got[1]["text"]


def test_block_holding_two_problems_is_cut():
    res = page(
        block("text", [0, 0, 400, 100], "8. 가", 1),
        block("text", [0, 100, 400, 300], "끝 부분\n9. 나", 2),
    )
    got = problems.split(res)
    assert [p["label"] for p in got] == ["8", "9"]
    assert got[0]["boxes"] == [[0.0, 0.0, 0.4, 0.1]]  # merged with the first half
    assert got[1]["boxes"] == [[0.0, 0.1, 0.4, 0.15]]
    assert got[1]["text"] == "9. 나"


def test_figure_goes_to_the_problem_above_it_in_its_column():
    res = page(
        block("text", [0, 0, 400, 100], "1. 왼쪽", 1),
        block("text", [500, 0, 900, 100], "2. 오른쪽", 2),
        block("text", [500, 800, 900, 900], "3. 오른쪽 아래", 3),
        {"block_label": "image", "block_bbox": [100, 150, 300, 400], "block_content": ""},
    )
    got = problems.split(res)
    assert got[0]["boxes"] == [[0.0, 0.0, 0.4, 0.2]]
    assert len(got[1]["boxes"]) == 1 and len(got[2]["boxes"]) == 1


def test_problem_continuing_in_next_column_keeps_two_boxes():
    res = page(
        block("text", [0, 1500, 400, 1900], "1. 길다", 1),
        block("text", [500, 0, 900, 300], "이어지는 글", 2),
        block("text", [500, 400, 900, 500], "2. 다음", 3),
    )
    assert problems.split(res)[0]["boxes"] == [[0.0, 0.75, 0.4, 0.95], [0.5, 0.0, 0.9, 0.15]]


@pytest.mark.skipif(not KMA.exists(), reason="needs output_kma fixtures")
def test_kma_sheet_finds_every_problem():
    labels = []
    for i in range(6):
        res = json.loads((KMA / f"kma_sheet_13_8_prob_{i}_res.json").read_text(encoding="utf-8"))
        labels += [int(p["label"]) for p in problems.split(res)]
    assert labels == list(range(1, 31))


def test_split_dir(tmp_path):
    assert problems.split_dir(tmp_path) == []
    (tmp_path / "x_res.json").write_text("not json", encoding="utf-8")
    assert problems.split_dir(tmp_path) == []


def _items(*oks):
    return [{"speech": {"strict_ok": ok, "ssml": "<speak/>" if ok else None}} for ok in oks]


def test_problem_audio_and_page_audio(tmp_path, monkeypatch):
    def fake(ssml, path):
        path.write_bytes(b"MP3" + path.name.encode())
        return "ready", ""
    monkeypatch.setattr(job, "_synthesize", fake)
    pa = job._synthesize_problems(_items(True, True), tmp_path)
    assert pa == [("ready", ""), ("ready", "")]
    status, _ = job._whole_page(pa, tmp_path, tmp_path / "audio.mp3")
    assert status == "ready"
    assert (tmp_path / "audio.mp3").read_bytes() == b"MP3audio_1.mp3MP3audio_2.mp3"


def test_page_audio_status_when_a_problem_has_none(tmp_path, monkeypatch):
    monkeypatch.setattr(job, "_synthesize", lambda ssml, path: ("quota_reached", "429"))
    pa = job._synthesize_problems(_items(True, False), tmp_path)
    assert [s for s, _ in pa] == ["quota_reached", "skipped"]
    assert job._whole_page(pa, tmp_path, tmp_path / "audio.mp3")[0] == "quota_reached"
    assert not (tmp_path / "audio.mp3").exists()
    assert job._whole_page([("ready", ""), ("skipped", "")], tmp_path, tmp_path / "a.mp3")[0] == "skipped"


def test_tts_stage_on_a_page_of_problems():
    page_speech = {"text": "…", "ssml": None, "strict_ok": False}
    done = {"ocr": {}, "normalized": {}, "speech": page_speech}
    one_ok = {**done, "problems": _items(False, True)}
    none_ok = {**done, "problems": _items(False, False)}
    assert progress.stage_status("running", one_ok)["tts"] == "running"
    assert progress.stage_status("running", none_ok)["tts"] == "skipped"


@pytest.mark.skipif(not (KMA.exists() and (ROOT / "sre-probe" / "node_modules").exists())
                    or not shutil.which("node"), reason="needs output_kma and node")
def test_run_job_reads_each_problem(tmp_path):
    def fake_ocr(img, out_dir, device):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(KMA / "kma_sheet_13_8_prob_5_res.json", out_dir / "upload_res.json")
        shutil.copy(KMA / "kma_sheet_13_8_prob_5.md", out_dir / "upload.md")
        return (out_dir / "upload.md").read_text(encoding="utf-8"), str(out_dir / "upload.md")
    seen = []
    r = job.run_job(Path("upload.jpg"), tmp_path, "cpu", tts=False, ocr=fake_ocr,
                    on_output=lambda k, v: seen.append(k))
    parts = r["stages"]["problems"]
    assert [p["label"] for p in parts] == ["27", "28", "29", "30"]
    assert all(p["speech"]["text"] for p in parts)
    assert r["stages"]["speech"]["text"].startswith(parts[0]["speech"]["text"])
    assert seen.index("problems") < seen.index("speech")


# --- found in review, 2026-11-09 ---------------------------------------------

def test_intro_and_problem_1_in_one_block_are_cut():
    res = page(
        block("text", [0, 0, 400, 300], "[1~2] 다음을 읽고 물음에 답하시오.\n1. 첫 문제\n2. 둘째 문제", 1),
        block("text", [0, 400, 400, 500], "3. 셋째", 2),
    )
    got = problems.split(res)
    assert [p["label"] for p in got] == ["1", "2", "3"]
    assert got[0]["text"] == "[1~2] 다음을 읽고 물음에 답하시오.\n\n1. 첫 문제"


def test_sub_items_written_differently_are_not_problems():
    # the page numbers its problems "1." "2.": "3)" and "3번" are inside problem 1
    res = page(
        block("text", [0, 0, 400, 100], "1. 첫 문제", 1),
        block("text", [0, 100, 400, 200], "1) 가 2) 나", 2),
        block("text", [0, 200, 400, 300], "3) 다", 3),
        block("text", [0, 300, 400, 400], "3번 학생의 점수는?", 4),
        block("text", [0, 500, 400, 600], "2. 둘째 문제", 5),
    )
    got = problems.split(res)
    assert [p["label"] for p in got] == ["1", "2"]
    assert "3) 다" in got[0]["text"] and "3번 학생" in got[0]["text"]


def _fake_page(monkeypatch, tmp_path, speech, synth=None):
    """run_job on a two-problem page with OCR and _speech faked."""
    def fake_ocr(img, out_dir, device):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        res = page(block("text", [0, 0, 400, 100], "1. 가 $x$", 1),
                   block("text", [0, 200, 400, 300], "2. 나 $y$", 2))
        (out_dir / "upload_res.json").write_text(json.dumps(res), encoding="utf-8")
        md = out_dir / "upload.md"
        md.write_text("1. 가 $x$\n\n2. 나 $y$", encoding="utf-8")
        return md.read_text(encoding="utf-8"), str(md)
    monkeypatch.setattr(job, "_speech", speech)
    monkeypatch.setattr(job, "_synthesize",
                        synth or (lambda ssml, path: (path.write_bytes(b"MP3"), ("ready", ""))[1]))
    stages = []
    r = job.run_job(Path("upload.jpg"), tmp_path, "cpu", tts=True, ocr=fake_ocr,
                    on_stage=stages.append)
    return r, stages


def test_every_problem_crashing_fails_the_job(tmp_path, monkeypatch):
    def crash(norm_path, stitch_dir):
        raise job.JobError("speech_stage_failed", "speak.js exited 1")
    with pytest.raises(job.JobError) as e:
        _fake_page(monkeypatch, tmp_path, crash)
    assert e.value.code == "speech_stage_failed"


def test_one_crashed_problem_says_failed_not_unreadable_formula(tmp_path, monkeypatch):
    def speech(norm_path, stitch_dir):
        if norm_path.name == "problem1.norm.md":
            raise job.JobError("speech_stage_failed", "speak.js exited 1")
        return "y", "<speak/>", True, []
    r, _ = _fake_page(monkeypatch, tmp_path, speech)
    assert [p["status"] for p in r["audio"]["problems"]] == ["failed", "ready"]
    assert r["audio"]["status"] == "failed"
    assert "_crashed" not in r["stages"]["problems"][0]


def test_no_readable_problem_does_not_start_tts(tmp_path, monkeypatch):
    r, stages = _fake_page(monkeypatch, tmp_path, lambda n, s: ("x", None, False, []))
    assert "tts" not in stages and "tts" not in r["timings_s"]
    assert [p["status"] for p in r["audio"]["problems"]] == ["skipped", "skipped"]
    assert r["audio"]["status"] == "skipped"


# --- the formal reading (speak.js without --casual), 2026-11-10 ----------------

def _two_readings(norm_path, stitch_dir, casual=True):
    name = "쉽게" if casual else "정확하게"
    return f"{name} {norm_path.name}", f"<speak>{name}</speak>", True, []


def test_each_problem_gets_a_formal_reading_but_no_formal_mp3(tmp_path, monkeypatch):
    asked = []

    def synth(ssml, path):
        asked.append(ssml)
        path.write_bytes(b"MP3")
        return "ready", ""
    r, _ = _fake_page(monkeypatch, tmp_path, _two_readings, synth)
    for i, (p, a) in enumerate(zip(r["stages"]["problems"], r["audio"]["problems"]), 1):
        assert p["speech"]["text"].startswith("쉽게")
        assert p["speech"]["formal"]["text"] == f"정확하게 problem{i}.norm.md"
        assert a["status"] == "ready" and "formal" not in a
    assert r["stages"]["speech"]["formal"]["text"].count("정확하게") == 2
    # Azure is asked for the casual reading only; the formal one waits for its button
    assert asked == ["<speak>쉽게</speak>"] * 2


def test_a_formal_reading_that_fails_is_left_out(tmp_path, monkeypatch):
    def speech(norm_path, stitch_dir, casual=True):
        if not casual:
            raise job.JobError("speech_stage_failed", "speak.js exited 1")
        return "y", "<speak/>", True, []
    r, _ = _fake_page(monkeypatch, tmp_path, speech)
    assert [p["status"] for p in r["audio"]["problems"]] == ["ready", "ready"]
    assert all("formal" not in p["speech"] for p in r["stages"]["problems"])
    assert "formal" not in r["stages"]["speech"]


def test_formal_audio_on_request(monkeypatch):
    def synth(ssml, path):
        path.write_bytes(b"MP3 " + ssml.encode())
        return "ready", ""
    monkeypatch.setattr(job, "_synthesize", synth)
    assert job.formal_audio("<speak/>") == ("ready", "", b"MP3 <speak/>")
    assert job.formal_audio(None)[0] == "skipped"
    monkeypatch.setattr(job, "_synthesize", lambda ssml, path: ("quota_reached", "429"))
    assert job.formal_audio("<speak/>") == ("quota_reached", "429", None)
