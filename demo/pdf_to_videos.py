#!/usr/bin/env python3
"""Generate slide-by-slide HeyGen videos from a PDF.

Setup:
  pip install pypdf python-dotenv requests

Usage:
  python pdf_to_videos.py \
      --pdf path/to/source.pdf \
      --persona disengaged \
      --start 1 --end 14 \
      --output-dir demo/video/output/disengaged
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from pypdf import PdfReader

API_BASE = "https://api.heygen.com"

PERSONAS = {
    "architect": {
        "talking_photo_id": "81f4cfdd12f44d2d86d7d3162c87d0b0",
        "voice_id": "TQlmmB9mmQTUqSzdqwZD",
        "speed": 0.95,
        "scale": 2.5,
        "use_avatar_iv_model": True,
        "cheerful": True,
    },
    "disengaged": {
        "talking_photo_id": "9bfd7389737c433e82c9c549701b906c",
        "voice_id": "3682592b135445539f3c190a6fb7de60",
        "speed": 1.0,
        "scale": 1.0,
        "use_avatar_iv_model": True,
        "cheerful": True,
    },
}

SLIDE_RE = re.compile(r"\[\s*Slide\s+([\d.]+)[^\]]*\]", re.IGNORECASE)


def extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join(p.extract_text() or "" for p in reader.pages)


def normalize(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = re.sub(r"<[^>]*>", "", text)
    text = text.replace("[", "").replace("]", "")
    text = text.replace("*", "").replace("●", "").replace("—", "-")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[:\s]+", "", text)
    return text


def split_slides(raw: str) -> list[tuple[str, str]]:
    matches = list(SLIDE_RE.finditer(raw))
    out: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        sid = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        out.append((sid, normalize(raw[start:end])))
    return out


def filename_for(slide_id: str) -> str:
    return f"slide{slide_id.replace('.', '_')}.mp4"


def in_range(slide_id: str, start: int, end: int) -> bool:
    n = int(slide_id.split(".")[0])
    return start <= n <= end


def edit_in_editor(text: str) -> str:
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write(text)
        path = f.name
    try:
        subprocess.call([editor, path])
        with open(path) as f:
            return f.read().strip()
    finally:
        os.unlink(path)


def confirm_or_edit(slide_id: str, body: str) -> str | None:
    while True:
        print(f"\n----- Slide {slide_id} ({len(body)} chars) -----")
        print(body)
        print("-" * 60)
        choice = input("[a]pprove / [e]dit / [s]kip / [q]uit > ").strip().lower()
        if choice in ("a", ""):
            return body
        if choice == "e":
            body = edit_in_editor(body)
            continue
        if choice == "s":
            return None
        if choice == "q":
            sys.exit("Aborted by user")
        print("Invalid choice")


def submit(api_key: str, cfg: dict, text: str, dimension: dict) -> str:
    character = {
        "type": "talking_photo",
        "talking_photo_id": cfg["talking_photo_id"],
        "scale": cfg.get("scale", 1.0),
    }
    if cfg.get("use_avatar_iv_model"):
        character["use_avatar_iv_model"] = True
    if cfg.get("cheerful"):
        text = f'<speak><prosody pitch="+12%" rate="105%">{text}</prosody></speak>'
    payload = {
        "video_inputs": [
            {
                "character": character,
                "voice": {
                    "type": "text",
                    "voice_id": cfg["voice_id"],
                    "input_text": text,
                    "speed": cfg["speed"],
                },
                "background": {"type": "color", "value": "#1a2332"},
            }
        ],
        "dimension": dimension,
    }
    r = requests.post(
        f"{API_BASE}/v2/video/generate",
        headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"submit error: {data['error']}")
    return data["data"]["video_id"]


def wait_and_download(
    api_key: str, video_id: str, out_path: Path, poll: int = 10, timeout_min: int = 20
) -> None:
    deadline = time.time() + timeout_min * 60
    while time.time() < deadline:
        try:
            r = requests.get(
                f"{API_BASE}/v1/video_status.get",
                headers={"X-Api-Key": api_key},
                params={"video_id": video_id},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()["data"]
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as e:
            print(f"  transient error: {e}; retrying", flush=True)
            time.sleep(poll)
            continue
        status = data.get("status")
        print(f"  {status}", flush=True)
        if status == "completed":
            with requests.get(data["video_url"], stream=True, timeout=300) as v:
                v.raise_for_status()
                with open(out_path, "wb") as f:
                    for chunk in v.iter_content(8192):
                        f.write(chunk)
            return
        if status == "failed":
            raise RuntimeError(f"render failed: {data.get('error')}")
        time.sleep(poll)
    raise TimeoutError("render did not complete in time")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--persona", required=True, choices=sorted(PERSONAS.keys()))
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, default=None, help="last slide (inclusive); defaults to last slide in PDF")
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=1280)
    ap.add_argument("--auto", action="store_true", help="skip the interactive approve/edit prompt")
    args = ap.parse_args()

    load_dotenv()
    api_key = os.environ.get("HEYGEN_API")
    if not api_key:
        sys.exit("HEYGEN_API not set (check .env)")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    cfg = PERSONAS[args.persona]
    dimension = {"width": args.width, "height": args.height}

    print(f"Reading PDF: {args.pdf}")
    slides = split_slides(extract_text(args.pdf))
    if not slides:
        sys.exit("No [Slide N] markers found in PDF")
    print(f"Slides found: {[s for s, _ in slides]}")

    end = args.end if args.end is not None else max(int(sid.split('.')[0]) for sid, _ in slides)
    targets = [(sid, body) for sid, body in slides if in_range(sid, args.start, end)]
    print(f"Reviewing {len(targets)} slide(s) in [{args.start},{end}]")

    approved: list[tuple[str, str, Path]] = []
    for sid, body in targets:
        out = args.output_dir / filename_for(sid)
        if out.exists():
            print(f"[skip] {out.name} already exists")
            continue
        if not body:
            print(f"[skip] Slide {sid}: empty body")
            continue
        if args.auto:
            approved.append((sid, body, out))
            continue
        new_body = confirm_or_edit(sid, body)
        if new_body is None:
            print(f"[skip] Slide {sid}: user skipped")
            continue
        approved.append((sid, new_body, out))

    if not approved:
        print("\nNothing to render.")
        return

    print(f"\n===== Review complete: {len(approved)} slide(s) approved =====")
    for sid, _, out in approved:
        print(f"  Slide {sid} → {out.name}")
    if not args.auto:
        if input("\nProceed with rendering? [y]/n > ").strip().lower() == "n":
            sys.exit("Aborted before rendering.")

    print("\n===== Rendering =====")
    for sid, body, out in approved:
        print(f"\nSlide {sid} ({len(body)} chars) → {out.name}")
        vid = submit(api_key, cfg, body, dimension)
        print(f"  video_id={vid}")
        wait_and_download(api_key, vid, out)
        print(f"  saved: {out}")


if __name__ == "__main__":
    main()