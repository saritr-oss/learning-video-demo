#!/usr/bin/env python3
"""
Batch MuseTalk video generation script.

GCS structure expected:
  gs://video-generator-assets/
    inputs/
      {course_name}/
        audio/   ← upload MP3s here
        avatar/  ← upload english_woman.png here
    video-results/
      {course_name}/  ← results uploaded here

Usage:
  conda activate musetalk
  export CUDA_HOME=$CONDA_PREFIX
  cd /home/gilrubin/MuseTalk

  # Process all slides (one at a time, resumes automatically):
  python batch_generate.py the_disengaged_kinesthetic

  # Test with 1 slide only:
  python batch_generate.py the_disengaged_kinesthetic --test

  # To run as a background service that survives disconnection, use run_batch.sh.
"""

import os
import sys
import json
import subprocess
import yaml
from pathlib import Path
from PIL import Image

GCS_BUCKET       = "gs://video-generator-assets"
GCS_INPUT_BASE   = f"{GCS_BUCKET}/inputs"
GCS_OUTPUT_BASE  = f"{GCS_BUCKET}/video-results"
MUSETALK_DIR     = Path("/home/gilrubin/MuseTalk")
WORK_DIR         = MUSETALK_DIR / "work"


def run(cmd, check=True):
    print(f"$ {cmd}")
    return subprocess.run(cmd, shell=True, check=check)


def get_completed_from_gcs(gcs_output):
    """Return set of video stems already uploaded to GCS output folder."""
    result = subprocess.run(
        f"gsutil ls '{gcs_output}/*.mp4' 2>/dev/null",
        shell=True, capture_output=True, text=True
    )
    completed = set()
    for line in result.stdout.strip().split('\n'):
        line = line.strip()
        if line:
            completed.add(Path(line).stem)
    return completed


def get_audio_duration(audio_path):
    result = subprocess.run(
        f'ffprobe -v quiet -of csv=p=0 -show_entries format=duration "{audio_path}"',
        shell=True, capture_output=True, text=True
    )
    return float(result.stdout.strip())


AVATAR_BG_COLOR = (7, 13, 20)   # #070D14 — PAiDeVo dark-blue background


def flatten_avatar(avatar_path: Path, out_dir: Path) -> Path:
    """Flatten RGBA PNG onto the brand background colour and save as RGB PNG.
    Returns the flattened path (or the original if already RGB)."""
    img = Image.open(avatar_path)
    if img.mode != 'RGBA':
        return avatar_path
    bg = Image.new('RGB', img.size, AVATAR_BG_COLOR)
    bg.paste(img, mask=img.split()[3])  # use alpha channel as mask
    flat_path = out_dir / f"{avatar_path.stem}_flat.png"
    bg.save(flat_path)
    print(f"Flattened RGBA→RGB ({avatar_path.name} → {flat_path.name})")
    return flat_path


def pad_avatar_wide(avatar_path: Path, out_dir: Path, face_ratio: float = 0.35) -> tuple:
    """Scale face down so it occupies face_ratio of canvas height, then pad all sides.
    DWPose needs the face to be a small fraction of the total frame — same proportions
    as english_woman.png (face ~35% of height) which MuseTalk handles fine.
    Skips if already landscape (w > h × 1.5).
    Returns (path, crop_x, crop_y, crop_w, crop_h) — all zeros mean no rescale."""
    img = Image.open(avatar_path).convert('RGB')
    orig_w, orig_h = img.size
    if orig_w > orig_h * 1.5:
        print(f"Avatar already landscape ({orig_w}x{orig_h}), skipping rescale.")
        return avatar_path, 0, 0, orig_w, orig_h
    canvas_h = 1536
    face_h = int(canvas_h * face_ratio)   # e.g. 537 px
    face_w = int(orig_w * face_h / orig_h)
    canvas_w = max(2784, face_w * 4)      # ensure landscape
    scaled = img.resize((face_w, face_h), Image.LANCZOS)
    x = (canvas_w - face_w) // 2
    y = (canvas_h - face_h) // 2
    wide_path = out_dir / f"{avatar_path.stem}_wide.png"
    if not wide_path.exists():
        bg = Image.new('RGB', (canvas_w, canvas_h), AVATAR_BG_COLOR)
        bg.paste(scaled, (x, y))
        bg.save(wide_path)
        print(f"Rescaled avatar: {orig_w}x{orig_h} → {face_w}x{face_h} on {canvas_w}x{canvas_h} canvas")
        print(f"  crop back: x={x} y={y} w={face_w} h={face_h}")
    else:
        print(f"Reusing rescaled avatar: {wide_path.name}")
    return wide_path, x, y, face_w, face_h


def create_loop_video(avatar_path, audio_path, loop_video_path):
    duration = get_audio_duration(str(audio_path))
    run(
        f'ffmpeg -y -loop 1 -i "{avatar_path}" '
        f'-t {duration} -r 25 -pix_fmt yuv420p "{loop_video_path}"'
    )
    return loop_video_path


def main(course_name, test=False):
    gcs_input  = f"{GCS_INPUT_BASE}/{course_name}"
    gcs_output = f"{GCS_OUTPUT_BASE}/{course_name}"

    # Setup work directories
    course_dir  = WORK_DIR / course_name
    audio_dir   = course_dir / "audio"
    avatar_dir  = course_dir / "avatar"
    loops_dir   = course_dir / "loops"
    results_dir = course_dir / "results"

    for d in [audio_dir, avatar_dir, loops_dir, results_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Step 1 — Download from GCS
    print("\n=== Downloading assets from GCS ===")
    run(f"gsutil -m cp '{gcs_input}/audio/*' {audio_dir}/")
    run(f"gsutil -m cp '{gcs_input}/avatar/*' {avatar_dir}/")

    # Find avatar
    avatar_images = sorted(p for p in list(avatar_dir.glob("*.png")) + list(avatar_dir.glob("*.jpg")) if p.name != "avatar_map.json")
    if not avatar_images:
        print("ERROR: No avatar image found in avatar/")
        sys.exit(1)
    avatar_path = avatar_images[0]
    print(f"Default avatar: {avatar_path.name}")

    # Load per-slide avatar map if present
    avatar_map = None
    avatar_map_path = avatar_dir / "avatar_map.json"
    if avatar_map_path.exists():
        with open(avatar_map_path) as f:
            avatar_map = json.load(f)
        print(f"Per-slide avatar map loaded (default: {avatar_map.get('default')})")

    # Find audio files
    audio_files = sorted(
        list(audio_dir.glob("*.mp3")) + list(audio_dir.glob("*.wav")),
        key=lambda p: p.name
    )
    if not audio_files:
        print("ERROR: No audio files found in audio/")
        sys.exit(1)

    if test:
        audio_files = audio_files[:1]
        print(f"TEST MODE: processing 1 file → {audio_files[0].name}")
    else:
        print(f"Found {len(audio_files)} audio files")

    # Resume: skip slides already uploaded to GCS
    print("\n=== Checking GCS for completed videos (resume) ===")
    completed = get_completed_from_gcs(gcs_output)
    if completed:
        print(f"Already completed ({len(completed)}): {', '.join(sorted(completed))}")
        audio_files = [af for af in audio_files if af.stem not in completed]
        print(f"Remaining to process: {len(audio_files)}")
        if not audio_files:
            print("All slides already completed! Nothing to do.")
            sys.exit(0)
    else:
        print("No completed videos found in GCS, starting fresh.")

    # Process each slide one at a time: inference → upload → next
    os.chdir(MUSETALK_DIR)
    total = len(audio_files)
    config_path = course_dir / "inference_config.yaml"

    for i, audio_path in enumerate(audio_files):
        stem = audio_path.stem
        print(f"\n{'='*60}")
        print(f"  Slide {i+1}/{total}: {stem}")
        print(f"{'='*60}")

        # Resolve avatar for this slide
        if avatar_map:
            slide_avatar_name = avatar_map.get("slides", {}).get(stem, avatar_map.get("default"))
            slide_avatar = avatar_dir / slide_avatar_name
            if not slide_avatar.exists():
                print(f"WARNING: Avatar '{slide_avatar_name}' not found, falling back to {avatar_path.name}")
                slide_avatar = avatar_path
        else:
            slide_avatar = avatar_path
        print(f"Avatar for this slide: {slide_avatar.name}")

        # Flatten RGBA → RGB on brand background (fixes DWPose face detection)
        slide_avatar = flatten_avatar(slide_avatar, avatar_dir)

        # Pad horizontally so DWPose can detect a large close-up face;
        # crop_x > 0 means we'll crop the MuseTalk output back to portrait
        slide_avatar, crop_x, crop_y, crop_w, crop_h = pad_avatar_wide(slide_avatar, avatar_dir)

        # Create loop video (skip if already exists from a previous partial run)
        loop_video = loops_dir / f"{stem}_loop.mp4"
        if loop_video.exists():
            print(f"Loop video already exists, reusing: {loop_video.name}")
        else:
            create_loop_video(slide_avatar, audio_path, loop_video)

        # Generate single-task MuseTalk config
        with open(config_path, "w") as f:
            yaml.dump({
                "task_0": {
                    "video_path": str(loop_video),
                    "audio_path": str(audio_path)
                }
            }, f, default_flow_style=False)

        # Run MuseTalk inference for this slide
        slide_results_dir = results_dir / stem
        slide_results_dir.mkdir(exist_ok=True)
        run(
            f"PYTHONPATH=. python scripts/inference.py "
            f"--inference_config {config_path} "
            f"--result_dir {slide_results_dir} "
            f"--version v15 "
            f"--use_float16"
        )

        # Find and rename output
        output_dir = slide_results_dir / "v15"
        loop_stem  = f"{stem}_loop"
        expected   = output_dir / f"{loop_stem}_{stem}.mp4"
        renamed    = output_dir / f"{stem}.mp4"

        if expected.exists():
            expected.rename(renamed)
        else:
            matches = list(output_dir.glob(f"*{stem}*.mp4"))
            if matches:
                matches[0].rename(renamed)
            else:
                print(f"WARNING: No output found for {audio_path.name}, skipping upload.")
                continue

        # Crop back to face region if rescaling was applied
        if crop_x > 0 or crop_y > 0:
            cropped = output_dir / f"{stem}_final.mp4"
            run(
                f'ffmpeg -y -i "{renamed}" '
                f'-vf "crop={crop_w}:{crop_h}:{crop_x}:{crop_y}" '
                f'-c:a copy "{cropped}"'
            )
            renamed.unlink()
            cropped.rename(renamed)
            print(f"Cropped back to {crop_w}x{crop_h}")

        # Upload immediately — this is the checkpoint
        run(f"gsutil cp '{renamed}' '{gcs_output}/'")
        print(f"Uploaded {i+1}/{total}: {stem}.mp4")

    print(f"\nDone! All {total} videos at: {gcs_output}/")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python batch_generate.py <course_name> [--test]")
        print("Example: python batch_generate.py the_disengaged_kinesthetic")
        print("         python batch_generate.py the_disengaged_kinesthetic --test")
        sys.exit(1)
    test_mode = "--test" in sys.argv
    main(sys.argv[1], test=test_mode)
