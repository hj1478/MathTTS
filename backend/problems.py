"""Split one OCR'd page into its numbered problems, with where each one is.

PaddleOCR-VL's layout model (PP-DocLayoutV3) returns the page as blocks, each
with a label, a bounding box and its text, in reading order. They are in the
`<stem>_res.json` that ocr_vl.run_image saves next to the markdown:

    {"width": 1458, "height": 2064, "parsing_res_list": [
        {"block_label": "text", "block_bbox": [116, 278, 529, 312],
         "block_order": 3, "block_content": "1. 다음 수에 대한 설명으로 옳지 않은 것은?"},
        {"block_label": "display_formula", ...}, ...]}

A block whose text starts with a problem number ("1.", "2)", "문제 3") opens a
new problem, and the blocks after it belong to it until the next number. The
number must go up, so a choice like "1)" inside problem 4 does not split it,
and "1.23은" (a decimal) is not a number label.

Pure, with no OCR or Modal import, so tests/test_problems.py can check it locally.
"""
import json
import re
from pathlib import Path

# Page furniture, never part of a problem.
SKIP_LABELS = {"header", "footer", "number", "footnote", "header_image", "footer_image",
               "aside_text", "seal", "doc_title"}
# Blocks with no text that still show part of a problem (a figure), so they
# belong in its highlight.
PICTURE_LABELS = {"image", "chart", "figure"}
# "1." "12)" "[3]" "3번" "문제 4", but not "1.23" or "1.5배"
NUMBER = re.compile(r"^\s*(?:\[\s*(\d{1,3})\s*\]|(\d{1,3})\s*(?:[.)．]|번)(?!\d)|문제\s*(\d{1,3}))")
# A problem number jumps by at most this much: a larger jump is more likely a
# number inside the text (a year, a page number) than the next problem.
MAX_JUMP = 10


def number_of(text):
    """The problem number a block starts with, or None."""
    m = NUMBER.match(text or "")
    if not m:
        return None
    return int(next(g for g in m.groups() if g))


def _merge(boxes):
    """Union the boxes that share any horizontal range: one rectangle per column."""
    out = []
    for b in boxes:
        b = list(b)
        merged = True
        while merged:
            merged = False
            for o in out:
                if b[0] < o[2] and o[0] < b[2]:  # x ranges overlap
                    out.remove(o)
                    b = [min(b[0], o[0]), min(b[1], o[1]), max(b[2], o[2]), max(b[3], o[3])]
                    merged = True
                    break
        out.append(b)
    return out


def _pieces(b, after):
    """One block -> [(bbox, text)]: split where a line starts the next problem
    number. OCR sometimes runs the end of one problem and the start of the next
    into one block; the box is cut at the same line, in proportion."""
    text = (b.get("block_content") or "").strip()
    bbox = b["block_bbox"]
    lines = text.split("\n")
    cuts, last = [0], after
    for i, line in enumerate(lines):
        n = number_of(line)
        if i and n is not None and last is not None and last < n <= last + MAX_JUMP:
            cuts.append(i)
        if n is not None and (last is None or last < n <= last + MAX_JUMP):
            last = n
    if len(cuts) == 1:
        return [(bbox, text)]
    x0, y0, x1, y1 = bbox
    out = []
    for k, c in enumerate(cuts):
        e = cuts[k + 1] if k + 1 < len(cuts) else len(lines)
        top = y0 + (y1 - y0) * c / len(lines)
        bottom = y0 + (y1 - y0) * e / len(lines)
        out.append(([x0, round(top), x1, round(bottom)], "\n".join(lines[c:e]).strip()))
    return out


def _owner(problems, bbox):
    """For a block outside the reading order (a figure, a table): the problem
    that starts above it in the same column, or else the nearest start."""
    # a problem's text can continue into the next column, so any of its boxes counts
    above = [(o[1], i) for i, p in enumerate(problems) for o in p["boxes"]
             if bbox[0] < o[2] and o[0] < bbox[2] and o[1] <= bbox[1]]
    if above:
        return problems[max(above)[1]]
    start = [p["boxes"][0] for p in problems]
    return problems[min(range(len(problems)),
                        key=lambda i: abs(start[i][1] - bbox[1]) + abs(start[i][0] - bbox[0]))]


def split(res):
    """OCR result dict -> [{"label": "1", "boxes": [[x0, y0, x1, y1], ...], "text": md}].

    Boxes are fractions of the page width and height (0..1), so they still fit
    when the client shows a resized copy of the photo. Returns [] when the page
    has fewer than two numbered problems: then it is read as one piece.
    """
    w, h = res.get("width") or 0, res.get("height") or 0
    blocks = [b for b in res.get("parsing_res_list") or []
              if (b.get("block_label") or "") not in SKIP_LABELS
              and len(b.get("block_bbox") or ()) == 4
              # an empty text block is OCR noise, and its box would stretch the highlight
              and ((b.get("block_content") or "").strip()
                   or b.get("block_label") in PICTURE_LABELS)]
    if not w or not h or not blocks:
        return []
    ordered = sorted((b for b in blocks if b.get("block_order") is not None),
                     key=lambda b: b["block_order"])
    # figures and tables come without a reading order: placed by position below
    loose = [b for b in blocks if b.get("block_order") is None]
    problems, lead = [], []  # lead: text before the first number
    last = None
    for b in ordered:
        for bbox, text in _pieces(b, last):
            n = number_of(text)
            if n is not None and (last is None or last < n <= last + MAX_JUMP):
                problems.append({"label": str(n), "boxes": [bbox], "parts": [text]})
                last = n
            elif b.get("block_label") == "paragraph_title":
                continue  # a section heading ("서술형"), not problem text
            elif problems:
                problems[-1]["boxes"].append(bbox)
                if text:
                    problems[-1]["parts"].append(text)
            else:
                lead.append((bbox, text))
    if len(problems) < 2:
        return []
    for b in loose:
        p = _owner(problems, b["block_bbox"])
        p["boxes"].append(b["block_bbox"])
        text = (b.get("block_content") or "").strip()
        if text and not text.startswith("<"):  # an HTML table is not read aloud
            p["parts"].append(text)
    # Text before the first number ("[1~3] 다음을 읽고 …") is read with problem 1.
    if lead:
        problems[0]["boxes"][:0] = [b for b, _ in lead]
        problems[0]["parts"][:0] = [t for _, t in lead if t]
    return [{
        "label": p["label"],
        "boxes": [[round(x0 / w, 4), round(y0 / h, 4), round(x1 / w, 4), round(y1 / h, 4)]
                  for x0, y0, x1, y1 in _merge(p["boxes"])],
        "text": "\n\n".join(p["parts"]),
    } for p in problems]


def split_dir(ocr_dir):
    """split() on the OCR result JSON in ocr_dir; [] if there is none or it is unreadable."""
    found = sorted(Path(ocr_dir).glob("*_res.json"))
    if len(found) != 1:
        return []  # none, or more than one page: read as one piece
    try:
        return split(json.loads(found[0].read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, KeyError):
        return []
