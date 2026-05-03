#!/usr/bin/env python3
"""Copy avatar videos from demo/video/output/ into the video_web site.

Source: demo/video/output/{architect,disengaged}/slide{N}.mp4
Target: video_web/the_leadership_blueprint/{architect,disengaged}/videos/Slide_{N}.mp4

Idempotent: skips files that already exist at the target.

Usage:
    python move_demo_to_zoominfo.py            # copy (default)
    python move_demo_to_zoominfo.py --move     # move instead of copy
    python move_demo_to_zoominfo.py --dry-run  # preview only
"""

import argparse
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent
SRC_BASE = REPO / "demo" / "video" / "output"
DST_BASE = REPO / "video_web" / "the_leadership_blueprint"

COURSES = {
    "architect": "architect",
    "disengaged": "disengaged",
}

NAME_RE = re.compile(r"^slide([\d_]+)\.mp4$", re.IGNORECASE)


def target_name(src_name: str) -> str | None:
    m = NAME_RE.match(src_name)
    return f"Slide_{m.group(1)}.mp4" if m else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--move", action="store_true", help="move instead of copy")
    args = ap.parse_args()

    op = shutil.move if args.move else shutil.copy2
    label = "move" if args.move else "copy"

    handled = skipped = unknown = 0
    for src_dir, dst_dir in COURSES.items():
        src = SRC_BASE / src_dir
        dst = DST_BASE / dst_dir / "videos"
        if not src.is_dir():
            print(f"[skip dir] {src} does not exist")
            continue
        dst.mkdir(parents=True, exist_ok=True)

        for f in sorted(src.iterdir()):
            if not f.is_file() or f.suffix != ".mp4":
                continue
            new_name = target_name(f.name)
            if not new_name:
                print(f"[skip] {f.name} (unrecognized name)")
                unknown += 1
                continue
            target = dst / new_name
            if target.exists():
                print(f"[skip] {target.relative_to(REPO)} already exists")
                skipped += 1
                continue
            print(f"[{label}] {f.relative_to(REPO)} -> {target.relative_to(REPO)}")
            if not args.dry_run:
                op(str(f), str(target))
            handled += 1

    print(f"\nDone: {handled} {label}d, {skipped} skipped, {unknown} unrecognized")


if __name__ == "__main__":
    main()