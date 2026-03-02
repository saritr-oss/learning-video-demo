import json
import base64
import urllib.request
import subprocess

def synthesize():
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

    url = "https://texttospeech.googleapis.com/v1/text:synthesize"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "x-goog-user-project": project_id
    }

    try:
        with open("request.json", "rb") as f:
            data = f.read()
    except FileNotFoundError:
        print("request.json not found.")
        return

    print("Sending request to Text-to-Speech API...")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read()
            res_json = json.loads(res_body)
            
            audio_content = res_json.get("audioContent")
            if audio_content:
                with open("sample.mp3", "wb") as out:
                    out.write(base64.b64decode(audio_content))
                print("Success! Audio saved to sample.mp3")
            else:
                print("No audioContent in response:", res_json)
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.read().decode('utf-8')}")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    synthesize()
