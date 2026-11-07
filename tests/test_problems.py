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
