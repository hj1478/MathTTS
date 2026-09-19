"""The --skip-ocr / --skip-normalize globs must not pick up derived files.

`dot_check.py` writes its patched copy of a page as `<stem>.dots.md` into the
same folder as the OCR output (inbox_eval.py does this on every judged run).
Before #15 that file matched the stage-1 glob, so a subsequent
`run.py --skip-ocr` normalized, stitched and synthesized the same page twice —
once with the 순환소수 dots and once without — silently, and paid Azure for
both.
"""
import run


def _touch(d, *names):
    for n in names:
        (d / n).write_text("", encoding="utf-8")


def test_source_pages_excludes_derived_files(tmp_path):
    _touch(tmp_path, "page.md", "page.dots.md", "page.norm.md",
           "page.dots.norm.md", "kr question 1.md")
    assert [p.name for p in run.source_pages(tmp_path)] == [
        "kr question 1.md", "page.md"]


def test_existing_norms_excludes_dots_duplicates(tmp_path):
    _touch(tmp_path, "page.md", "page.norm.md", "page.dots.norm.md")
    assert [p.name for p in run.existing_norms(tmp_path)] == ["page.norm.md"]


def test_source_pages_empty_folder(tmp_path):
    assert run.source_pages(tmp_path) == []
