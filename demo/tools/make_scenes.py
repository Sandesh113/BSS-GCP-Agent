"""Render every walkthrough scene with the approved Charon voice (same settings as sample-charon.wav)."""
import json
import re
import sys
from pathlib import Path

from make_sample import MODEL, PROJECT, REGION, STYLE, GCLOUD  # noqa: F401  (same voice settings)
import base64
import subprocess
import wave

import requests

# Spoken forms for the audio only; captions keep the written names.
SPOKEN = [(r"TMFC(\d)(\d)(\d)", r"T-M-F-C \1-\2-\3"), (r"TMF(\d)(\d)(\d)", r"T-M-F \1-\2-\3"),
          (r"\bCFSs\b", "C-F-Ss"), (r"\bCFS\b", "C-F-S"), (r"\bCPQ\b", "C-P-Q"), (r"\bBSS\b", "B-S-S"),
          (r"\bHSS\b", "H-S-S"), (r"\bSMSC\b", "S-M-S-C"), (r"\bSMS\b", "S-M-S")]


def spoken(text):
    for pattern, replacement in SPOKEN:
        text = re.sub(pattern, replacement, text)
    return text


def main(scenes_path, out_dir, only=None):
    scenes = json.loads(Path(scenes_path).read_text(encoding="utf-8"))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    token = subprocess.run([str(GCLOUD), "auth", "print-access-token"], capture_output=True, text=True,
                           check=True).stdout.strip()
    url = (f"https://{REGION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT}/locations/{REGION}"
           f"/publishers/google/models/{MODEL}:generateContent")
    total = 0.0
    for number, text in enumerate(scenes, 1):
        if only and number not in only:
            continue
        body = {"contents": {"role": "user", "parts": {"text": f"{STYLE} {spoken(text)}"}},
                "generation_config": {"response_modalities": ["AUDIO"], "speech_config": {
                    "language_code": "en-GB", "voice_config": {"prebuilt_voice_config": {"voice_name": "Charon"}}}}}
        reply = requests.post(url, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=180)
        if not reply.ok:
            print(number, "HTTP", reply.status_code, reply.text[:400])
            continue
        pcm = base64.b64decode(reply.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
        path = out / f"scene-{number:02d}.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(pcm)
        seconds = len(pcm) / 48000
        total += seconds
        # Roughly 2.5 words per second; a much longer clip suggests the style instruction was read aloud.
        print(f"{number:2d} {seconds:5.1f}s  words={len(text.split()):3d}  {path.name}")
    print(f"total {total:.1f}s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], {int(n) for n in sys.argv[3:]} or None)
