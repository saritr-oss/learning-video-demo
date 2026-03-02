import re
import json
import base64
import urllib.request
import subprocess
import os

import sys

def synthesize_slides():
    # Usage: python synthesize_slides.py <directory> <request_json> [--test]
    # Example: python synthesize_slides.py "videos/The Disengaged Kinesthetic" request_male_en-GB-Studio-B.json
    # Example: python synthesize_slides.py "videos/The Disengaged Kinesthetic" request_male_en-GB-Studio-B.json --test
    if len(sys.argv) < 3:
        print("Usage: python synthesize_slides.py <directory> <request_json> [--test]")
        print("Example: python synthesize_slides.py \"videos/The Disengaged Kinesthetic\" request_male_en-GB-Studio-B.json")
        sys.exit(1)

    base_dir = sys.argv[1]
    request_json = sys.argv[2]
    test_mode = "--test" in sys.argv

    # Find the .txt file inside the directory
    txt_files = [f for f in os.listdir(base_dir) if f.endswith(".txt")]
    if not txt_files:
        print(f"No .txt file found in {base_dir}")
        sys.exit(1)
    filepath = os.path.join(base_dir, txt_files[0])
    print(f"Found text file: {filepath}")

    print("Getting auth token...")
    try:
        token = subprocess.check_output(
            ["gcloud", "auth", "application-default", "print-access-token"]
        ).decode().strip()
    except Exception as e:
        print("Failed to get gcloud token. Run `gcloud auth application-default login` first.")
        return

    try:
        project_id = subprocess.check_output(
            ["gcloud", "config", "get-value", "project"]
        ).decode().strip()
    except Exception as e:
        print("Failed to get gcloud project. Is it configured?")
        return

    # Load request template
    try:
        with open(request_json, "r") as f:
            template = json.load(f)
        print(f"Voice: {template['voice']['name']}")
    except FileNotFoundError:
        print(f"{request_json} not found.")
        return
        
    print(f"Reading {filepath} and saving inside {base_dir}")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Find all slides (supports decimal sub-slides like [Slide 1.1])
    pattern = r'(\[Slide [\d.]+\])(.*?)(?=\[Slide [\d.]+\]|$)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    url = "https://texttospeech.googleapis.com/v1/text:synthesize"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "x-goog-user-project": project_id
    }

    if test_mode:
        matches = matches[:1]
        print(f"TEST MODE: processing 1 slide only.")
    else:
        print(f"Found {len(matches)} slides. Processing starting from slide 1.")

    for slide_marker, slide_text in matches:
        slide_text = slide_text.strip()
        # Clean non-verbal symbols and control chars invalid in XML before synthesis
        clean_text = slide_text.replace('*', '').replace('●', '').replace('—', '-')
        # Strip C0 control chars except tab, newline, carriage return (invalid in XML/SSML)
        clean_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', clean_text)
        
        if not clean_text:
            continue
            
        # Create a meaningful name
        slide_num = re.search(r'[\d.]+', slide_marker).group().replace('.', '_')
        words = re.sub(r'[^\w\s]', '', slide_text).split()
        short_title = "_".join(words[:5])
        filename = f"Slide_{slide_num}_{short_title}.mp3"
        filename = os.path.join(base_dir, filename)

        if os.path.exists(filename):
            print(f"Skipping {filename} (already exists)")
            continue

        print(f"Synthesizing {filename}...")
        
        req_data = template.copy()
        # Use SSML mode when text contains tags (e.g. <break time="15s"/>)
        if '<' in clean_text:
            # Split on SSML tags, escape text segments, keep tags verbatim
            import xml.sax.saxutils as _sx
            parts = re.split(r'(<[^>]+>)', clean_text)
            ssml_body = ''.join(
                p if p.startswith('<') and p.endswith('>') else _sx.escape(p)
                for p in parts
            )
            req_data["input"] = {"ssml": f"<speak>{ssml_body}</speak>"}
        else:
            req_data["input"] = {"text": clean_text}
        data = json.dumps(req_data).encode("utf-8")
        
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as response:
                res_body = response.read()
                res_json = json.loads(res_body)
                
                audio_content = res_json.get("audioContent")
                if audio_content:
                    with open(filename, "wb") as out:
                        out.write(base64.b64decode(audio_content))
                    print(f"Success! Audio saved to {filename}")
                else:
                    print("No audioContent in response:", res_json)
        except urllib.error.HTTPError as e:
            print(f"HTTP Error: {e.code} - {e.read().decode('utf-8')}")
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    synthesize_slides()
