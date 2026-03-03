#!/usr/bin/env python3
"""
Generate VTT subtitle files from MP3 audio using Google Cloud Speech-to-Text.

For each persona, this script:
1. Reads MP3 files from videos/<persona>/
2. Uploads them to GCS (needed for files over 60s)
3. Runs Speech-to-Text with word-level timestamps
4. Generates .vtt files and saves them alongside the MP4 videos in
   video_web/persona/<persona_slug>/videos/

Usage:
    python3 generate_subtitles.py
"""

import os
import re
import subprocess
import sys
from google.cloud import speech

# Config
PROJECT_ID = "basic-garden-483315-e8"
GCS_BUCKET = "paidevo-data-storage"
GCS_TEMP_PREFIX = "subtitle-temp"

PERSONAS = {
    "The Autonomous Architect": "the_autonomous_architect",
    "The Disengaged Kinesthetic": "the_disengaged_kinesthetic",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEOS_SRC = os.path.join(BASE_DIR, "slides")
WEB_PERSONA = os.path.join(BASE_DIR, "video_web", "persona")

# Maximum characters per subtitle line
MAX_CHARS_PER_CUE = 80
# Maximum words per subtitle cue
MAX_WORDS_PER_CUE = 14


def extract_slide_num(mp3_name):
    """Extract slide number from MP3 filename like 'Slide_1_1_Lets_start.mp3' -> '1_1'"""
    m = re.match(r"Slide_(\d+(?:_\d+)?)", mp3_name)
    if m:
        return m.group(1)
    return None


def format_vtt_time(seconds):
    """Convert seconds to VTT timestamp format HH:MM:SS.mmm"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}.{ms:03d}"


def words_to_vtt_cues(words):
    """Group word-level timestamps into readable subtitle cues."""
    cues = []
    current_words = []
    current_chars = 0
    cue_start = None

    for word_info in words:
        word = word_info["word"]
        start = word_info["start"]
        end = word_info["end"]

        # Start a new cue if: too many chars, too many words, or long pause (>1.5s)
        if current_words:
            pause = start - current_words[-1]["end"]
            too_long = current_chars + len(word) + 1 > MAX_CHARS_PER_CUE
            too_many = len(current_words) >= MAX_WORDS_PER_CUE
            long_pause = pause > 1.5

            if too_long or too_many or long_pause:
                # Finish current cue
                cues.append({
                    "start": cue_start,
                    "end": current_words[-1]["end"],
                    "text": " ".join(w["word"] for w in current_words)
                })
                current_words = []
                current_chars = 0
                cue_start = None

        if cue_start is None:
            cue_start = start

        current_words.append(word_info)
        current_chars += len(word) + 1

    # Final cue
    if current_words:
        cues.append({
            "start": cue_start,
            "end": current_words[-1]["end"],
            "text": " ".join(w["word"] for w in current_words)
        })

    return cues


def generate_vtt(cues):
    """Generate VTT file content from cues."""
    lines = ["WEBVTT", ""]
    for i, cue in enumerate(cues, 1):
        lines.append(str(i))
        lines.append(f"{format_vtt_time(cue['start'])} --> {format_vtt_time(cue['end'])}")
        lines.append(cue["text"])
        lines.append("")
    return "\n".join(lines)


def upload_to_gcs(local_path, gcs_path):
    """Upload file to GCS."""
    full_gcs = f"gs://{GCS_BUCKET}/{gcs_path}"
    print(f"  Uploading to {full_gcs}...")
    subprocess.run(["gsutil", "cp", local_path, full_gcs], check=True, capture_output=True)
    return full_gcs


def delete_from_gcs(gcs_path):
    """Delete file from GCS."""
    full_gcs = f"gs://{GCS_BUCKET}/{gcs_path}"
    subprocess.run(["gsutil", "rm", full_gcs], capture_output=True)


def transcribe_mp3(mp3_path, gcs_temp_key):
    """Transcribe MP3 using Google Cloud Speech-to-Text with word timestamps."""
    # Upload to GCS (required for long audio recognition)
    gcs_uri = upload_to_gcs(mp3_path, gcs_temp_key)

    client = speech.SpeechClient()

    audio = speech.RecognitionAudio(uri=gcs_uri)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.MP3,
        sample_rate_hertz=24000,  # Google TTS default
        language_code="en-US",
        enable_word_time_offsets=True,
        enable_automatic_punctuation=True,
        model="latest_long",
    )

    print(f"  Transcribing (this may take a moment)...")
    operation = client.long_running_recognize(config=config, audio=audio)
    response = operation.result(timeout=300)

    # Extract words with timestamps
    words = []
    for result in response.results:
        alt = result.alternatives[0]
        for word_info in alt.words:
            start = word_info.start_time.total_seconds()
            end = word_info.end_time.total_seconds()
            words.append({
                "word": word_info.word,
                "start": start,
                "end": end,
            })

    # Clean up GCS
    delete_from_gcs(gcs_temp_key)

    return words


def process_persona(persona_name, persona_slug):
    """Process all MP3 files for a persona and generate VTT files."""
    src_dir = os.path.join(VIDEOS_SRC, persona_name)
    out_dir = os.path.join(WEB_PERSONA, persona_slug, "videos")

    if not os.path.isdir(src_dir):
        print(f"⚠️  Source directory not found: {src_dir}")
        return

    os.makedirs(out_dir, exist_ok=True)

    mp3_files = sorted([f for f in os.listdir(src_dir) if f.endswith(".mp3")])
    print(f"\n{'='*60}")
    print(f"Processing: {persona_name} ({len(mp3_files)} MP3 files)")
    print(f"{'='*60}\n")

    for mp3_file in mp3_files:
        slide_num = extract_slide_num(mp3_file)
        if slide_num is None:
            print(f"⚠️  Skipping {mp3_file} (can't extract slide number)")
            continue

        vtt_filename = f"Slide_{slide_num}.vtt"
        vtt_path = os.path.join(out_dir, vtt_filename)

        # Check if VTT already exists
        if os.path.exists(vtt_path):
            print(f"⏭️  {vtt_filename} already exists, skipping")
            continue

        mp3_path = os.path.join(src_dir, mp3_file)
        gcs_key = f"{GCS_TEMP_PREFIX}/{persona_slug}/{mp3_file}"

        print(f"🎙️  {mp3_file} → {vtt_filename}")

        try:
            words = transcribe_mp3(mp3_path, gcs_key)

            if not words:
                print(f"  ⚠️  No words detected, skipping")
                continue

            cues = words_to_vtt_cues(words)
            vtt_content = generate_vtt(cues)

            with open(vtt_path, "w") as f:
                f.write(vtt_content)

            print(f"  ✅ Generated {vtt_filename} ({len(cues)} subtitle cues)")

        except Exception as e:
            print(f"  ❌ Error: {e}")
            # Clean up GCS on error
            delete_from_gcs(gcs_key)


def main():
    print("🎬 Subtitle Generator — Google Cloud Speech-to-Text")
    print(f"   Project: {PROJECT_ID}\n")

    for persona_name, persona_slug in PERSONAS.items():
        process_persona(persona_name, persona_slug)

    print(f"\n{'='*60}")
    print("🎉 Done! VTT files are in video_web/persona/<persona>/videos/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
