#!/usr/bin/env python3
"""Render slide PDFs into per-page JPGs for the video_web site.

Source: demo/The_Leadership_Blueprint/{the_autonomous_architect,the_disengaged_kinesthetic}/slides-adapted-images.pdf
Target: video_web/the_leadership_blueprint/{architect,disengaged}/slides/{N}.jpg

By default each page is auto-trimmed to the bounding box of non-white
content, removing any white margins (top/bottom/left/right) introduced
by the source PDF layout.

Setup:
    pip install pymupdf pillow

Usage:
    python extract_slides_to_zoominfo.py            # render + trim (default)
    python extract_slides_to_zoominfo.py --no-trim  # keep white margins
    python extract_slides_to_zoominfo.py --zoom 3   # higher resolution
    python extract_slides_to_zoominfo.py --force    # overwrite existing JPGs
    python extract_slides_to_zoominfo.py --dry-run
"""

import argparse
import io
from pathlib import Path

import pymupdf
from PIL import Image

REPO = Path(__file__).resolve().parent

PERSONAS = {
    "the_autonomous_architect": "architect",
    "the_disengaged_kinesthetic": "disengaged",
}


def trim_white(img: Image.Image, threshold: int = 240) -> Image.Image:
    """Crop the image to the bounding box of pixels darker than `threshold`."""
    rgb = img.convert("RGB") if img.mode != "RGB" else img
    gray = rgb.convert("L")
    mask = gray.point(lambda p: 0 if p > threshold else 255)
    bbox = mask.getbbox()
    return rgb.crop(bbox) if bbox else rgb


def render_pdf(pdf_path: Path, out_dir: Path, zoom: float, dry_run: bool, trim: bool, force: bool) -> tuple[int, int]:
    doc = pymupdf.open(pdf_path)
    matrix = pymupdf.Matrix(zoom, zoom)
    written = skipped = 0
    for i, page in enumerate(doc, start=1):
        target = out_dir / f"{i}.jpg"
        if target.exists() and not force:
            print(f"[skip] {target.relative_to(REPO)} already exists (use --force to overwrite)")
            skipped += 1
            continue
        print(f"[render] {pdf_path.name} page {i} -> {target.relative_to(REPO)}")
        if not dry_run:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            if trim:
                img = trim_white(img)
            img.save(str(target), format="JPEG", quality=88)
        written += 1
    doc.close()
    return written, skipped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zoom", type=float, default=2.0, help="render zoom factor (default 2.0)")
    ap.add_argument("--no-trim", action="store_true", help="keep white margins (default: trim)")
    ap.add_argument("--force", action="store_true", help="overwrite existing JPGs")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src_base = REPO / "demo" / "The_Leadership_Blueprint"
    dst_base = REPO / "video_web" / "the_leadership_blueprint"

    total_written = total_skipped = 0
    for src_name, dst_name in PERSONAS.items():
        pdf = src_base / src_name / "slides-adapted-images.pdf"
        if not pdf.is_file():
            print(f"[skip pdf] {pdf} not found")
            continue
        out_dir = dst_base / dst_name / "slides"
        out_dir.mkdir(parents=True, exist_ok=True)
        w, s = render_pdf(pdf, out_dir, args.zoom, args.dry_run, not args.no_trim, args.force)
        total_written += w
        total_skipped += s

    print(f"\nDone: {total_written} rendered, {total_skipped} skipped")


if __name__ == "__main__":
    main()