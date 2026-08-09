#!/usr/bin/env python3
"""Stage 0 (optional): render a PDF's pages to PNGs that ocr_vl.py can read.

The pipeline proper starts at images; this closes the gap for PDF sources
like kma_sheet_13_8_prob.pdf (whose run folders output_kma/ etc. are already
reserved in .gitignore). Rendering uses pypdfium2 — pinned in requirements.txt.

DPI default is 200: PaddleOCR-VL works from photo-resolution input, and the
repo's own fixtures ("kr question N.png") are in that range. Raise it if thin
fraction bars or small subscripts come out broken.

Usage:
  python pdf_to_images.py kma_sheet_13_8_prob.pdf --out ./pages
  python ocr_vl.py --eval ./pages --out ./output_kma
"""
import argparse
import sys
from pathlib import Path


def render(pdf_path, out_dir, dpi):
    import pypdfium2 as pdfium

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(pdf_path))
    stem = Path(pdf_path).stem.replace(" ", "_")
    written = []
    for i, page in enumerate(pdf, start=1):
        bitmap = page.render(scale=dpi / 72)  # PDF user space is 72/inch
        dest = out / f"{stem}_p{i:02d}.png"
        bitmap.to_pil().save(dest)
        written.append(dest)
        print(f"  page {i} -> {dest}")
    return written


def main():
    ap = argparse.ArgumentParser(description="Render PDF pages to PNGs for ocr_vl.py.")
    ap.add_argument("pdf", help="path to a PDF")
    ap.add_argument("--out", default="./pages", help="output folder (default ./pages)")
    ap.add_argument("--dpi", type=int, default=200, help="render resolution (default 200)")
    a = ap.parse_args()

    if not Path(a.pdf).is_file():
        sys.exit(f"not a file: {a.pdf}")
    pages = render(a.pdf, a.out, a.dpi)
    print(f"{len(pages)} page(s) written to {a.out}")


if __name__ == "__main__":
    main()
